import ctypes
import ipaddress
import json
import os
import re
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from ..config import Settings
from .base import VpnError, refresh_region_plan, refresh_region_requires_regions, validate_refresh_region

REGION_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
CONNECTED = "Connected"
CONNECTING = "Connecting"
DISCONNECTED = "Disconnected"
OPENVPN_CONNECTED_MARKER = "Initialization Sequence Completed"


class ProtonOpenVpnClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._process: subprocess.Popen[str] | None = None
        self._selected_region: str | None = None
        self._active_region: str | None = None
        self._active_config_path: str | None = None
        self._connected_marker_seen = False
        self._log_lines: list[str] = []
        self._log_lock = threading.Lock()

    def launch_gui(self) -> dict[str, Any]:
        return {"message": "Proton OpenVPN provider does not use the Proton VPN desktop GUI"}

    def enable_background(self) -> dict[str, Any]:
        return {"message": "Proton OpenVPN runs as a managed OpenVPN process when connect is called"}

    def connect(self, wait: bool = False) -> dict[str, Any]:
        active_process = self._active_process()
        if not active_process:
            cleaned_pid = self._cleanup_pid_file_process()
            if cleaned_pid is None:
                self._cleanup_orphan_processes()
            active_process = self._active_process()
        if active_process:
            data: dict[str, Any] = {
                "message": "Managed Proton OpenVPN process is already running",
                "connectionstate": self.get_connection_state(),
                "pid": active_process.pid,
                "region": self._active_region,
                "config_path": self._active_config_path,
            }
            if wait:
                data["connectionstate"] = self.wait_for_state(CONNECTED, self.settings.proton_connect_timeout_seconds)
            return data

        region, config_path = self._selected_config()
        self._ensure_windows_admin()
        self._ensure_file(self.settings.proton_openvpn_path, "Proton OpenVPN executable was not found")
        command = [self.settings.proton_openvpn_path, "--config", str(config_path)]
        if self.settings.proton_openvpn_auth_file:
            self._ensure_auth_file(self.settings.proton_openvpn_auth_file)
            command.extend(["--auth-user-pass", self.settings.proton_openvpn_auth_file])

        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                shell=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError as exc:
            raise VpnError("Proton OpenVPN process could not be started", status_code=503, command=command, stderr=str(exc)) from exc

        self._process = process
        self._active_region = region
        self._active_config_path = str(config_path)
        self._connected_marker_seen = False
        self._write_pid_file(process.pid, region, str(config_path))
        self._clear_log_lines()
        self._start_log_reader(process)

        data = {
            "message": "Proton OpenVPN connect command sent",
            "region": region,
            "config_path": str(config_path),
            "pid": process.pid,
            "connectionstate": self.get_connection_state(),
        }
        if wait:
            data["connectionstate"] = self.wait_for_state(CONNECTED, self.settings.proton_connect_timeout_seconds)
        return data

    def disconnect(self, wait: bool = False) -> dict[str, Any]:
        process = self._active_process()
        cleaned_pid = None
        if process:
            self._terminate_process(process)
            cleaned_pid = process.pid
        else:
            cleaned_pid = self._cleanup_pid_file_process()
            if cleaned_pid is None:
                self._clear_active_process()
                self._remove_pid_file()
                return {"message": "No managed Proton OpenVPN process is running", "connectionstate": DISCONNECTED}

        self._clear_active_process()
        self._remove_pid_file()
        data: dict[str, Any] = {"message": "Proton OpenVPN disconnect command sent", "connectionstate": DISCONNECTED, "pid": cleaned_pid}
        if wait:
            data["connectionstate"] = self.wait_for_state(DISCONNECTED, self.settings.proton_connect_timeout_seconds)
        return data

    def set_region(self, region: str) -> dict[str, Any]:
        region = self._validate_region(region)
        regions = self._regions_by_id()
        if region not in regions:
            raise VpnError("Proton OpenVPN region was not found", status_code=404, stderr=region)
        self._selected_region = region
        return {"region": region, "config_path": str(regions[region]), "message": "Proton OpenVPN region selected for the next connect"}

    def get_region(self) -> str | None:
        return self._active_region or self._selected_region or self._default_region()

    def get_regions(self) -> list[str]:
        return sorted(self._regions_by_id())

    def get_connection_state(self) -> str:
        process = self._active_process()
        if not process:
            return DISCONNECTED
        if self._connected_marker_seen:
            return CONNECTED
        return CONNECTING

    def get_pubip(self) -> str | None:
        return self._read_public_ip()

    def get_vpnip(self) -> str | None:
        if self.get_connection_state() != CONNECTED:
            return None
        return self._read_public_ip()

    def ip_info(self) -> tuple[dict[str, Any], list[str]]:
        warnings: list[str] = []
        pubip = self._safe_public_ip(warnings)
        vpnip = pubip if self.get_connection_state() == CONNECTED else None
        return {
            "pubip": pubip,
            "vpnip": vpnip,
            "vpnip_source": "PROTON_IP_CHECK_URL when the managed OpenVPN process is connected",
        }, warnings

    def status(self) -> tuple[dict[str, Any], list[str]]:
        warnings: list[str] = ["Proton OpenVPN status only tracks the OpenVPN process launched by this API process."]
        connection_state = self.get_connection_state()
        pubip = self._safe_public_ip(warnings)
        process = self._active_process()
        pid_file_data = self._read_pid_file()
        pid_file_pid = pid_file_data.get("pid") if pid_file_data else None
        pid_file_alive = isinstance(pid_file_pid, int) and self._is_openvpn_pid(pid_file_pid)
        return {
            "connectionstate": connection_state,
            "region": self.get_region(),
            "selected_region": self._selected_region,
            "active_region": self._active_region,
            "pubip": pubip,
            "vpnip": pubip if connection_state == CONNECTED else None,
            "vpnip_source": "PROTON_IP_CHECK_URL when the managed OpenVPN process is connected",
            "pid": process.pid if process else None,
            "pid_file_pid": pid_file_pid,
            "pid_file_alive": pid_file_alive,
            "config_path": self._active_config_path or (pid_file_data or {}).get("config_path"),
            "state_source": "managed_openvpn_process",
        }, self._dedupe(warnings)

    def wait_for_state(self, expected_state: str, timeout_seconds: float) -> str:
        deadline = time.monotonic() + timeout_seconds
        last_state = self.get_connection_state()
        while time.monotonic() < deadline:
            last_state = self.get_connection_state()
            if last_state == expected_state:
                return last_state
            if expected_state == CONNECTED and last_state == DISCONNECTED:
                raise VpnError(
                    "Proton OpenVPN process exited before it connected",
                    status_code=502,
                    stderr=self._log_tail(),
                )
            time.sleep(1)
        raise VpnError(
            f"Timed out waiting for Proton OpenVPN state {expected_state}",
            status_code=504,
            stderr=f"last_state={last_state}; log={self._log_tail()}",
        )

    def refresh_ip(self, region: str | None = None) -> tuple[dict[str, Any], list[str], bool]:
        requested_region = validate_refresh_region(region) if region else None
        current_region = self.get_region()
        before, before_warnings = self.ip_info()
        before_vpnip = before.get("vpnip")
        if not before_vpnip:
            raise VpnError(
                "Proton OpenVPN refresh-ip requires an active managed OpenVPN connection. Use /vpn/proton-openvpn/connect first.",
                status_code=409,
                stderr=str(before),
            )

        regions = self.get_regions() if refresh_region_requires_regions(requested_region) else []
        region_plan = refresh_region_plan(requested_region, current_region, regions)
        candidates = region_plan.candidates
        max_attempts = max(0, self.settings.proton_refresh_max_attempts)
        deadline = time.monotonic() + max(1, self.settings.proton_refresh_timeout_seconds)
        warnings = [*before_warnings, "Proton OpenVPN reconnect does not guarantee a different IP."]
        tried_regions: list[str] = []
        after: dict[str, Any] = {"pubip": None, "vpnip": None}
        selected_region = candidates[0] if candidates else current_region
        changed = False
        connectionstate = ""
        attempt = 0

        while self._time_remaining(deadline) > 0 and (max_attempts == 0 or attempt < max_attempts):
            attempt += 1
            self._ensure_time_remaining(deadline)
            if candidates:
                selected_region = candidates[(attempt - 1) % len(candidates)]
                tried_regions.append(selected_region)
                self.set_region(selected_region)
            connectionstate = self._reconnect(deadline)
            after, new_warnings, connectionstate = self._wait_for_valid_after_vpnip(deadline)
            warnings.extend(new_warnings)
            if after["vpnip"] != before_vpnip:
                changed = True
                break
            warnings.append(f"Attempt {attempt} returned the same Proton OpenVPN IP: {after['vpnip']}")

        data = {
            "mode": region_plan.mode,
            "country_key": region_plan.country_key,
            "requested_region": requested_region,
            "initial_region": current_region,
            "selected_region": selected_region,
            "missing_regions": region_plan.missing_regions,
            "tried_regions": tried_regions,
            "before": before,
            "after": after,
            "changed": changed,
            "attempts": attempt,
            "max_attempts": max_attempts,
            "refresh_timeout_seconds": self.settings.proton_refresh_timeout_seconds,
            "compare_field": "vpnip",
            "connectionstate": connectionstate,
        }
        if not changed:
            message = "Proton OpenVPN did not provide a different valid IP before refresh timeout"
            if max_attempts:
                message = "Proton OpenVPN did not provide a different valid IP after the configured attempts"
            raise VpnError(message, status_code=504, stderr=str({"data": data, "warnings": self._dedupe(warnings)}))
        return data, self._dedupe(warnings), changed

    def _reconnect(self, deadline: float) -> str:
        self._ensure_time_remaining(deadline)
        self.disconnect(wait=True)
        delay = min(max(0, self.settings.proton_reconnect_delay_seconds), self._time_remaining(deadline))
        if delay:
            time.sleep(delay)
        self._ensure_time_remaining(deadline)
        self.connect(wait=False)
        return self.wait_for_state(CONNECTED, min(self.settings.proton_connect_timeout_seconds, self._time_remaining(deadline)))

    def _wait_for_valid_after_vpnip(self, deadline: float) -> tuple[dict[str, Any], list[str], str]:
        warnings: list[str] = []
        last_after: dict[str, Any] = {"pubip": None, "vpnip": None}
        last_state = ""
        while time.monotonic() < deadline:
            last_state = self.get_connection_state()
            if last_state == DISCONNECTED:
                raise VpnError("Proton OpenVPN connection failed while waiting for IP after refresh", status_code=502, stderr=self._log_tail())
            if last_state == CONNECTED:
                last_after, new_warnings = self.ip_info()
                warnings.extend(new_warnings)
                if last_after.get("vpnip"):
                    return last_after, self._dedupe(warnings), last_state
            time.sleep(min(2, self._time_remaining(deadline)))
        raise VpnError("Timed out waiting for a valid Proton OpenVPN IP after refresh", status_code=504, stderr=f"connectionstate={last_state}; after={last_after}")

    def _selected_config(self) -> tuple[str, Path]:
        regions = self._regions_by_id()
        if self._selected_region:
            config_path = regions.get(self._selected_region)
            if config_path is None:
                raise VpnError("Selected Proton OpenVPN region was not found", status_code=404, stderr=self._selected_region)
            return self._selected_region, config_path
        default_region = self._default_region_from_map(regions)
        return default_region, regions[default_region]

    def _default_region(self) -> str | None:
        try:
            regions = self._regions_by_id()
        except VpnError:
            return self._selected_region
        return self._selected_region or self._default_region_from_map(regions)

    def _default_region_from_map(self, regions: dict[str, Path]) -> str:
        if self.settings.proton_ovpn_config_path:
            config_region = Path(self.settings.proton_ovpn_config_path).stem
            if config_region in regions:
                return config_region
        return sorted(regions)[0]

    def _regions_by_id(self) -> dict[str, Path]:
        regions: dict[str, Path] = {}
        config_path_value = self.settings.proton_ovpn_config_path.strip()
        if config_path_value:
            config_path = Path(config_path_value)
            self._ensure_file(str(config_path), "Proton OpenVPN .ovpn config file was not found")
            if config_path.suffix.lower() != ".ovpn":
                raise VpnError("Proton OpenVPN config file must have .ovpn extension", status_code=400, stderr=str(config_path))
            regions[config_path.stem] = config_path

        config_dir_value = self.settings.proton_ovpn_config_dir.strip()
        if config_dir_value:
            config_dir = Path(config_dir_value)
            if not config_dir.is_dir():
                raise VpnError("Proton OpenVPN config directory was not found", status_code=503, stderr=str(config_dir))
            for config_path in sorted(config_dir.glob("*.ovpn")):
                if config_path.is_file():
                    regions[config_path.stem] = config_path

        if not regions:
            raise VpnError("No Proton OpenVPN .ovpn config files were configured", status_code=503)
        return regions

    def _validate_region(self, region: str) -> str:
        region = region.strip()
        if not region or not REGION_PATTERN.fullmatch(region):
            raise VpnError("Region format is invalid", status_code=400)
        return region

    def _read_public_ip(self) -> str | None:
        url = self.settings.proton_ip_check_url.strip()
        if not url:
            return None
        try:
            with urllib.request.urlopen(url, timeout=max(1, self.settings.proton_command_timeout_seconds)) as response:
                value = response.read(128).decode("utf-8", "replace").strip()
        except (OSError, urllib.error.URLError, TimeoutError) as exc:
            raise VpnError("Could not read public IP for Proton OpenVPN", status_code=502, stderr=str(exc)) from exc
        return self._normalize_ip(value)

    def _safe_public_ip(self, warnings: list[str]) -> str | None:
        try:
            value = self._read_public_ip()
        except VpnError as exc:
            warnings.append(exc.message)
            return None
        if value is None and self.settings.proton_ip_check_url.strip():
            warnings.append("Ignored invalid public IP from PROTON_IP_CHECK_URL")
        return value

    def _normalize_ip(self, value: str | None) -> str | None:
        if not value:
            return None
        try:
            return str(ipaddress.ip_address(value.strip()))
        except ValueError:
            return None

    def _active_process(self) -> subprocess.Popen[str] | None:
        if self._process is None:
            return None
        if self._process.poll() is None:
            return self._process
        self._clear_active_process()
        self._remove_pid_file()
        return None

    def _clear_active_process(self) -> None:
        self._process = None
        self._active_region = None
        self._active_config_path = None
        self._connected_marker_seen = False

    def _terminate_process(self, process: subprocess.Popen[str]) -> None:
        process.terminate()
        try:
            process.wait(timeout=max(1, self.settings.proton_command_timeout_seconds))
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    def _pid_file_path(self) -> Path:
        return Path(self.settings.proton_openvpn_pid_file)

    def _write_pid_file(self, pid: int, region: str, config_path: str) -> None:
        pid_file = self._pid_file_path()
        data = {"pid": pid, "region": region, "config_path": config_path, "executable": self.settings.proton_openvpn_path}
        pid_file.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")

    def _read_pid_file(self) -> dict[str, Any] | None:
        pid_file = self._pid_file_path()
        if not pid_file.is_file():
            return None
        try:
            data = json.loads(pid_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self._remove_pid_file()
            return None
        if not isinstance(data, dict):
            self._remove_pid_file()
            return None
        return data

    def _remove_pid_file(self) -> None:
        try:
            self._pid_file_path().unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass

    def _cleanup_pid_file_process(self) -> int | None:
        data = self._read_pid_file()
        if not data:
            return None
        pid = data.get("pid")
        if not isinstance(pid, int) or pid <= 0:
            self._remove_pid_file()
            return None
        if not self._is_openvpn_pid(pid):
            self._remove_pid_file()
            return None
        self._terminate_pid(pid)
        if self._is_openvpn_pid(pid):
            raise VpnError("Managed Proton OpenVPN process could not be terminated", status_code=503, stderr=f"pid={pid}")
        self._remove_pid_file()
        return pid

    def _cleanup_orphan_processes(self) -> int | None:
        if not self.settings.proton_openvpn_cleanup_orphan_processes:
            return None
        pids = self._openvpn_pids()
        if not pids:
            return None
        if len(pids) != 1:
            raise VpnError(
                "Multiple orphan OpenVPN processes are running; refusing to guess which one to terminate",
                status_code=409,
                stderr=",".join(str(pid) for pid in pids),
            )
        pid = pids[0]
        self._terminate_pid(pid)
        if self._is_openvpn_pid(pid):
            raise VpnError("Orphan OpenVPN process could not be terminated", status_code=503, stderr=f"pid={pid}")
        return pid

    def _openvpn_pids(self) -> list[int]:
        if os.name != "nt":
            return []
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq openvpn.exe", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            shell=False,
            check=False,
            timeout=max(1, self.settings.proton_command_timeout_seconds),
        )
        pids: list[int] = []
        for line in (result.stdout or "").splitlines():
            parts = [part.strip().strip('"') for part in line.split(",")]
            if len(parts) < 2 or parts[0].lower() != "openvpn.exe":
                continue
            try:
                pids.append(int(parts[1]))
            except ValueError:
                pass
        return pids

    def _is_openvpn_pid(self, pid: int) -> bool:
        if os.name != "nt":
            return False
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            shell=False,
            check=False,
            timeout=max(1, self.settings.proton_command_timeout_seconds),
        )
        output = (result.stdout or "").lower()
        return "openvpn.exe" in output

    def _terminate_pid(self, pid: int) -> None:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/F"],
                capture_output=True,
                text=True,
                shell=False,
                check=False,
                timeout=max(1, self.settings.proton_command_timeout_seconds),
            )
            return
        try:
            os.kill(pid, 15)
        except OSError:
            pass

    def _ensure_file(self, path: str, message: str) -> None:
        if not os.path.isfile(path):
            raise VpnError(message, status_code=503, stderr=path)

    def _ensure_windows_admin(self) -> None:
        if os.name != "nt":
            return
        try:
            is_admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
        except OSError:
            is_admin = False
        if not is_admin:
            raise VpnError(
                "Proton OpenVPN connect must run from an elevated Administrator process on Windows",
                status_code=503,
                stderr="OpenVPN needs Administrator rights to configure the VPN adapter with netsh.",
            )

    def _ensure_auth_file(self, path: str) -> None:
        self._ensure_file(path, "Proton OpenVPN auth file was not found")
        try:
            data = Path(path).read_bytes()
        except OSError as exc:
            raise VpnError("Proton OpenVPN auth file could not be read", status_code=503, stderr=path) from exc
        if data.startswith(b"\xef\xbb\xbf"):
            raise VpnError("Proton OpenVPN auth file must be saved without UTF-8 BOM", status_code=400, stderr=path)
        non_empty_lines = [line for line in data.splitlines() if line.strip()]
        if len(non_empty_lines) < 2:
            raise VpnError("Proton OpenVPN auth file must contain username on line 1 and password on line 2", status_code=400, stderr=path)

    def _ensure_time_remaining(self, deadline: float) -> None:
        if self._time_remaining(deadline) <= 0:
            raise VpnError("Timed out refreshing Proton OpenVPN IP", status_code=504)

    def _time_remaining(self, deadline: float) -> float:
        return max(0, deadline - time.monotonic())

    def _start_log_reader(self, process: subprocess.Popen[str]) -> None:
        thread = threading.Thread(target=self._read_process_output, args=(process,), daemon=True)
        thread.start()

    def _read_process_output(self, process: subprocess.Popen[str]) -> None:
        if process.stdout is None:
            return
        for line in process.stdout:
            line = line.strip()
            if not line:
                continue
            if OPENVPN_CONNECTED_MARKER in line:
                self._connected_marker_seen = True
            with self._log_lock:
                self._log_lines.append(line)
                if len(self._log_lines) > 100:
                    self._log_lines = self._log_lines[-100:]

    def _clear_log_lines(self) -> None:
        with self._log_lock:
            self._log_lines = []

    def _log_tail(self) -> str:
        with self._log_lock:
            return "\n".join(self._log_lines[-20:])

    def _dedupe(self, warnings: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for warning in warnings:
            if warning and warning not in seen:
                result.append(warning)
                seen.add(warning)
        return result
