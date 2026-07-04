import ipaddress
import os
import re
import subprocess
import time
from typing import Any

from ..config import Settings
from .base import VpnError, refresh_region_plan, refresh_region_requires_regions, validate_refresh_region

REGION_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
CONNECTED = "Connected"
DISCONNECTED = "Disconnected"
INTERRUPTED = "Interrupted"


class ExpressVpnClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def launch_gui(self) -> dict[str, Any]:
        self._ensure_file(self.settings.expressvpn_gui_path, "ExpressVPN GUI executable was not found")
        subprocess.Popen([self.settings.expressvpn_gui_path])
        return {"message": "ExpressVPN GUI launched"}

    def enable_background(self) -> dict[str, Any]:
        output = self._run_expressvpnctl("background", "enable")
        return {"message": output or "ExpressVPN background mode enabled"}

    def connect(self, wait: bool = False) -> dict[str, Any]:
        output = self._run_expressvpnctl("connect")
        data: dict[str, Any] = {"message": output or "ExpressVPN connect command sent"}
        if wait:
            data["connectionstate"] = self.wait_for_state(CONNECTED, self.settings.expressvpn_connect_timeout_seconds)
        return data

    def disconnect(self, wait: bool = False) -> dict[str, Any]:
        output = self._run_expressvpnctl("disconnect")
        data: dict[str, Any] = {"message": output or "ExpressVPN disconnect command sent"}
        if wait:
            data["connectionstate"] = self.wait_for_state(DISCONNECTED, self.settings.expressvpn_connect_timeout_seconds)
        return data

    def set_region(self, region: str) -> dict[str, Any]:
        region = self._validate_region(region)
        output = self._run_expressvpnctl("set", "region", region)
        return {"region": region, "message": output or "ExpressVPN region updated"}

    def get_region(self) -> str | None:
        region = self._run_expressvpnctl("get", "region")
        return region or None

    def get_regions(self) -> list[str]:
        output = self._run_expressvpnctl("get", "regions")
        return [line.strip() for line in output.splitlines() if line.strip()]

    def get_connection_state(self) -> str:
        return self._run_expressvpnctl("get", "connectionstate")

    def get_pubip(self) -> str | None:
        return self._normalize_ip(self._run_expressvpnctl("get", "pubip"))

    def get_vpnip(self) -> str | None:
        return self._normalize_ip(self._run_expressvpnctl("get", "vpnip"))

    def ip_info(self) -> tuple[dict[str, Any], list[str]]:
        warnings: list[str] = []
        return {
            "pubip": self._safe_get_ip("pubip", warnings),
            "vpnip": self._safe_get_ip("vpnip", warnings),
        }, warnings

    def status(self) -> tuple[dict[str, Any], list[str]]:
        warnings: list[str] = []
        return {
            "connectionstate": self._safe_get("connectionstate", warnings),
            "region": self._safe_get("region", warnings),
            "pubip": self._safe_get_ip("pubip", warnings),
            "vpnip": self._safe_get_ip("vpnip", warnings),
        }, warnings

    def wait_for_state(self, expected_state: str, timeout_seconds: float) -> str:
        deadline = time.monotonic() + timeout_seconds
        last_state = ""
        while time.monotonic() < deadline:
            last_state = self.get_connection_state()
            if last_state == expected_state:
                return last_state
            time.sleep(1)
        raise VpnError(
            f"Timed out waiting for ExpressVPN state {expected_state}",
            status_code=504,
            stderr=f"last_state={last_state}",
        )

    def refresh_ip(self, region: str | None = None) -> tuple[dict[str, Any], list[str], bool]:
        requested_region = validate_refresh_region(region) if region else None
        current_region = self.get_region()
        before, before_warnings = self.ip_info()
        before_vpnip = before.get("vpnip")
        if not before_vpnip:
            raise VpnError(
                "Could not read a valid ExpressVPN vpnip before refresh",
                status_code=409,
                stderr=str(before),
            )

        regions = self.get_regions() if refresh_region_requires_regions(requested_region) else []
        region_plan = refresh_region_plan(requested_region, current_region, regions)
        candidates = region_plan.candidates

        max_attempts = max(0, self.settings.expressvpn_refresh_max_attempts)
        deadline = time.monotonic() + max(1, self.settings.expressvpn_refresh_timeout_seconds)
        warnings = [*before_warnings, "ExpressVPN reconnect does not guarantee a different IP."]
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
            warnings.append(f"Attempt {attempt} returned the same ExpressVPN vpnip: {after['vpnip']}")

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
            "refresh_timeout_seconds": self.settings.expressvpn_refresh_timeout_seconds,
            "compare_field": "vpnip",
            "connectionstate": connectionstate,
        }

        if not changed:
            message = "ExpressVPN did not provide a different valid vpnip before refresh timeout"
            if max_attempts:
                message = "ExpressVPN did not provide a different valid vpnip after the configured attempts"
            raise VpnError(
                message,
                status_code=504,
                stderr=str({"data": data, "warnings": self._dedupe(warnings)}),
            )
        return data, self._dedupe(warnings), changed

    def _wait_for_valid_after_vpnip(self, deadline: float) -> tuple[dict[str, Any], list[str], str]:
        warnings: list[str] = []
        last_after: dict[str, Any] = {"pubip": None, "vpnip": None}
        last_state = ""
        while time.monotonic() < deadline:
            last_state = self.get_connection_state()
            if last_state in {DISCONNECTED, INTERRUPTED}:
                raise VpnError(
                    "ExpressVPN connection failed while waiting for vpnip after refresh",
                    status_code=502,
                    stderr=f"connectionstate={last_state}",
                )
            last_after, new_warnings = self.ip_info()
            warnings.extend(new_warnings)
            if last_after.get("vpnip"):
                return last_after, self._dedupe(warnings), last_state
            time.sleep(min(2, self._time_remaining(deadline)))
        raise VpnError(
            "Timed out waiting for a valid ExpressVPN vpnip after refresh",
            status_code=504,
            stderr=f"connectionstate={last_state}; after={last_after}",
        )

    def _reconnect(self, deadline: float) -> str:
        self._ensure_time_remaining(deadline)
        self._run_expressvpnctl("disconnect")
        delay = min(max(0, self.settings.expressvpn_reconnect_delay_seconds), self._time_remaining(deadline))
        if delay:
            time.sleep(delay)
        self._ensure_time_remaining(deadline)
        self._run_expressvpnctl("connect")
        return self.wait_for_state(
            CONNECTED,
            min(self.settings.expressvpn_connect_timeout_seconds, self._time_remaining(deadline)),
        )

    def _run_expressvpnctl(self, *args: str, timeout: int | None = None) -> str:
        self._ensure_file(self.settings.expressvpn_ctl_path, "ExpressVPN CLI executable was not found")
        command = [self.settings.expressvpn_ctl_path, *args]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout or self.settings.expressvpn_command_timeout_seconds,
                shell=False,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise VpnError(
                "ExpressVPN command timed out",
                status_code=504,
                command=command,
                stderr=str(exc),
            ) from exc
        except OSError as exc:
            raise VpnError(
                "ExpressVPN command could not be started",
                status_code=503,
                command=command,
                stderr=str(exc),
            ) from exc

        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        if result.returncode != 0:
            raise VpnError(
                "ExpressVPN command failed",
                status_code=502,
                command=command,
                stderr=stderr or stdout,
                returncode=result.returncode,
            )
        return stdout

    def _safe_get(self, key: str, warnings: list[str]) -> str | None:
        try:
            return self._run_expressvpnctl("get", key) or None
        except VpnError as exc:
            warnings.append(f"Could not read ExpressVPN {key}: {exc.message}")
            return None

    def _safe_get_ip(self, key: str, warnings: list[str]) -> str | None:
        raw_value = self._safe_get(key, warnings)
        ip_value = self._normalize_ip(raw_value)
        if raw_value and ip_value is None:
            warnings.append(f"Ignored invalid ExpressVPN {key}: {raw_value}")
        return ip_value

    def _normalize_ip(self, value: str | None) -> str | None:
        if not value:
            return None
        try:
            return str(ipaddress.ip_address(value.strip()))
        except ValueError:
            return None

    def _validate_region(self, region: str) -> str:
        region = region.strip()
        if not region or not REGION_PATTERN.fullmatch(region):
            raise VpnError("Region format is invalid", status_code=400)
        return region

    def _ensure_file(self, path: str, message: str) -> None:
        if not os.path.isfile(path):
            raise VpnError(message, status_code=503, stderr=path)

    def _ensure_time_remaining(self, deadline: float) -> None:
        if self._time_remaining(deadline) <= 0:
            raise VpnError("Timed out refreshing ExpressVPN vpnip", status_code=504)

    def _time_remaining(self, deadline: float) -> float:
        return max(0, deadline - time.monotonic())

    def _dedupe(self, warnings: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for warning in warnings:
            if warning and warning not in seen:
                result.append(warning)
                seen.add(warning)
        return result
