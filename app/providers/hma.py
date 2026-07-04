import ipaddress
import json
import os
import struct
import subprocess
import time
from typing import Any

from ..config import Settings
from .base import VpnError, refresh_region_plan, refresh_region_requires_regions, validate_refresh_region

HMA_CONNECTED = "connected"
HMA_DISCONNECTED = "disconnected"
HMA_CONNECTING = "connecting"
HMA_DISCONNECTING = "disconnecting"
REGION_ALLOWED_CHARS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-")


class HmaClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._selected_region: str | None = None

    def launch_gui(self) -> dict[str, Any]:
        self._ensure_file(self.settings.hma_gui_path, "HMA GUI executable was not found")
        subprocess.Popen([self.settings.hma_gui_path])
        return {"message": "HMA GUI launched"}

    def enable_background(self) -> dict[str, Any]:
        return {
            "message": "HMA background service is managed by Windows service",
            "service": self.settings.hma_service_name,
        }

    def connect(self, wait: bool = False) -> dict[str, Any]:
        if self._selected_region:
            response = self._send_message({"action": "Vpn_Connect_NmSvc", "gatewayId": self._selected_region})
            message = f"HMA connect command sent for {self._selected_region}"
        else:
            response = self._send_message({"action": "Vpn_ConnectToOptimal_NmSvc"})
            message = "HMA connect command sent"

        data: dict[str, Any] = {"message": message, "response": response}
        if wait:
            data["connectionstate"] = self.wait_for_state(HMA_CONNECTED, self.settings.hma_connect_timeout_seconds)
        return data

    def disconnect(self, wait: bool = False) -> dict[str, Any]:
        response = self._send_message({"action": "Vpn_Disconnect_NmSvc"})
        data: dict[str, Any] = {"message": "HMA disconnect command sent", "response": response}
        if wait:
            data["connectionstate"] = self.wait_for_state(HMA_DISCONNECTED, self.settings.hma_connect_timeout_seconds)
        return data

    def set_region(self, region: str) -> dict[str, Any]:
        region = self._validate_region(region)
        gateways = self._get_gateways()
        if not any(self._gateway_id(gateway) == region for gateway in gateways):
            raise VpnError("HMA region was not found", status_code=404, stderr=region)
        self._selected_region = region
        return {"region": region, "message": "HMA region selected for the next connect"}

    def get_region(self) -> str | None:
        state = self._get_state_data()
        return self._current_region_from_state(state) or self._selected_region

    def get_regions(self) -> list[str]:
        regions = [region for region in (self._gateway_id(gateway) for gateway in self._get_gateways()) if region]
        return sorted(set(regions))

    def get_connection_state(self) -> str:
        state = self._get_state_data()
        return self._normalize_state(state.get("vpnStatus"))

    def get_pubip(self) -> str | None:
        state = self._get_state_data()
        return self._ip_from_public_info(state, connected_only=False)

    def get_vpnip(self) -> str | None:
        state = self._get_state_data()
        if self._normalize_state(state.get("vpnStatus")) != HMA_CONNECTED:
            return None
        return self._ip_from_public_info(state, connected_only=True)

    def ip_info(self) -> tuple[dict[str, Any], list[str]]:
        state = self._get_state_data()
        public_ip_info = state.get("publicIpInfo") if isinstance(state.get("publicIpInfo"), dict) else {}
        current_ip = self._ip_from_public_info(state, connected_only=False)
        vpn_ip = self._ip_from_public_info(state, connected_only=True) if self._normalize_state(state.get("vpnStatus")) == HMA_CONNECTED else None
        warnings: list[str] = []
        if current_ip is None:
            warnings.append("Could not read HMA current public IP")
        return {
            "pubip": current_ip,
            "vpnip": vpn_ip,
            "publicIpInfo": public_ip_info,
            "vpnip_source": "publicIpInfo.current.ip when connected",
        }, warnings

    def status(self) -> tuple[dict[str, Any], list[str]]:
        state = self._get_state_data()
        connection_state = self._normalize_state(state.get("vpnStatus"))
        current_ip = self._ip_from_public_info(state, connected_only=False)
        vpn_ip = self._ip_from_public_info(state, connected_only=True) if connection_state == HMA_CONNECTED else None
        active_gateway = state.get("activeGateway") if isinstance(state.get("activeGateway"), dict) else None
        active_region = self._current_region_from_state(state)
        region = active_region or self._selected_region
        data = {
            "connectionstate": connection_state,
            "raw_connectionstate": state.get("vpnStatus"),
            "region": region,
            "region_available": region is not None,
            "region_source": "active_connection" if active_region else "selected_for_next_connect" if self._selected_region else None,
            "region_message": None if region else "HMA exposes the active region only after connect, or a selected region after calling POST /vpn/hma/region with a body.",
            "selected_region": self._selected_region,
            "pubip": current_ip,
            "vpnip": vpn_ip,
            "vpnip_source": "publicIpInfo.current.ip when connected",
            "active_gateway": active_gateway,
            "connected_location_key": state.get("connectedLocationKey"),
            "connectionInfo": state.get("connectionInfo") if isinstance(state.get("connectionInfo"), dict) else {},
        }
        warnings: list[str] = []
        if current_ip is None:
            warnings.append("Could not read HMA current public IP")
        return data, warnings

    def wait_for_state(self, expected_state: str, timeout_seconds: float) -> str:
        expected_state = self._normalize_state(expected_state)
        deadline = time.monotonic() + timeout_seconds
        last_state = ""
        while time.monotonic() < deadline:
            last_state = self.get_connection_state()
            if last_state == expected_state:
                return last_state
            time.sleep(1)
        raise VpnError(
            f"Timed out waiting for HMA state {expected_state}",
            status_code=504,
            stderr=f"last_state={last_state}",
        )

    def refresh_ip(self, region: str | None = None) -> tuple[dict[str, Any], list[str], bool]:
        requested_region = validate_refresh_region(region) if region else None
        initial_state = self.get_connection_state()
        if initial_state != HMA_CONNECTED:
            raise VpnError(
                "HMA refresh-ip requires an active VPN connection. Use /vpn/hma/connect first.",
                status_code=409,
                stderr=f"connectionstate={initial_state}",
            )

        before, before_warnings = self.ip_info()
        before_ip = before.get("vpnip")
        if not before_ip:
            raise VpnError("Could not read a valid HMA VPN IP before refresh", status_code=409, stderr=str(before))

        current_region = self.get_region()
        regions = self.get_regions() if refresh_region_requires_regions(requested_region) else []
        region_plan = refresh_region_plan(requested_region, current_region, regions)
        candidates = region_plan.candidates

        max_attempts = max(1, self.settings.hma_refresh_max_attempts)
        deadline = time.monotonic() + max(1, self.settings.hma_refresh_timeout_seconds)
        attempt = 0
        warnings = [*before_warnings, "HMA reconnect does not guarantee a different IP."]
        tried_regions: list[str] = []
        after: dict[str, Any] = {"pubip": None, "vpnip": None}
        changed = False
        connectionstate = initial_state

        while self._time_remaining(deadline) > 0 and attempt < max_attempts:
            attempt += 1
            if candidates:
                selected_region = candidates[(attempt - 1) % len(candidates)]
                self.set_region(selected_region)
                tried_regions.append(selected_region)
            self.disconnect(wait=False)
            delay = min(max(0, self.settings.hma_reconnect_delay_seconds), self._time_remaining(deadline))
            if delay:
                time.sleep(delay)
            self.connect(wait=False)
            connectionstate = self.wait_for_state(
                HMA_CONNECTED,
                min(self.settings.hma_connect_timeout_seconds, self._time_remaining(deadline)),
            )
            after, new_warnings = self.ip_info()
            warnings.extend(new_warnings)
            after_ip = after.get("vpnip")
            if after_ip and after_ip != before_ip:
                changed = True
                break
            warnings.append(f"Attempt {attempt} returned the same HMA VPN IP: {after_ip}")

        data = {
            "mode": region_plan.mode,
            "country_key": region_plan.country_key,
            "requested_region": requested_region,
            "initial_region": current_region,
            "selected_region": self._selected_region,
            "missing_regions": region_plan.missing_regions,
            "tried_regions": tried_regions,
            "before": before,
            "after": after,
            "changed": changed,
            "attempts": attempt,
            "max_attempts": max_attempts,
            "refresh_timeout_seconds": self.settings.hma_refresh_timeout_seconds,
            "compare_field": "vpnip",
            "connectionstate": connectionstate,
        }
        if not changed:
            warnings.append("HMA refresh-ip finished without a new IP. It will not keep reconnecting automatically.")
        return data, self._dedupe(warnings), changed

    def _get_state_data(self) -> dict[str, Any]:
        response = self._send_message({"action": "Vpn_GetState_NmSvc"})
        data = response.get("data")
        if not isinstance(data, dict):
            raise VpnError("HMA state response was invalid", status_code=502, stderr=str(response))
        return data

    def _get_gateways(self) -> list[dict[str, Any]]:
        state = self._get_state_data()
        gateways = state.get("gateways")
        if not isinstance(gateways, list):
            return []
        return [gateway for gateway in gateways if isinstance(gateway, dict)]

    def _send_message(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._ensure_file(self.settings.hma_nm_path, "HMA native messaging executable was not found")
        command = [self.settings.hma_nm_path]
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = process.communicate(
                struct.pack("<I", len(body)) + body,
                timeout=self.settings.hma_command_timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            process.kill()
            raise VpnError("HMA command timed out", status_code=504, command=command, stderr=str(exc)) from exc
        except OSError as exc:
            raise VpnError("HMA command could not be started", status_code=503, command=command, stderr=str(exc)) from exc

        stderr_text = stderr.decode("utf-8", "replace").strip()
        if process.returncode not in (0, None):
            raise VpnError(
                "HMA command failed",
                status_code=502,
                command=command,
                stderr=stderr_text,
                returncode=process.returncode,
            )
        if len(stdout) < 4:
            raise VpnError("HMA command returned no native messaging response", status_code=502, command=command, stderr=stderr_text)

        length = struct.unpack("<I", stdout[:4])[0]
        raw_response = stdout[4 : 4 + length]
        try:
            response = json.loads(raw_response.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise VpnError("HMA command returned invalid JSON", status_code=502, command=command, stderr=raw_response.decode("utf-8", "replace")) from exc
        if not isinstance(response, dict):
            raise VpnError("HMA command returned invalid response", status_code=502, command=command, stderr=str(response))
        error = response.get("error")
        if isinstance(error, dict):
            raise VpnError(
                error.get("description") or "HMA command returned an error",
                status_code=502,
                command=command,
                stderr=str(error),
                returncode=error.get("code") if isinstance(error.get("code"), int) else None,
            )
        return response

    def _current_region_from_state(self, state: dict[str, Any]) -> str | None:
        connected_location = state.get("connectedLocationKey")
        if isinstance(connected_location, str) and connected_location:
            return connected_location
        active_gateway = state.get("activeGateway")
        if isinstance(active_gateway, dict):
            return self._gateway_id(active_gateway)
        return None

    def _gateway_id(self, gateway: dict[str, Any]) -> str | None:
        gateway_id = gateway.get("id")
        if isinstance(gateway_id, str) and gateway_id:
            return gateway_id
        city = gateway.get("city")
        if isinstance(city, dict) and isinstance(city.get("id"), str) and city["id"]:
            return city["id"]
        country = gateway.get("country")
        if isinstance(country, dict) and isinstance(country.get("id"), str) and country["id"]:
            return country["id"]
        return None

    def _ip_from_public_info(self, state: dict[str, Any], connected_only: bool) -> str | None:
        if connected_only and self._normalize_state(state.get("vpnStatus")) != HMA_CONNECTED:
            return None
        public_ip_info = state.get("publicIpInfo")
        if not isinstance(public_ip_info, dict):
            return None
        current = public_ip_info.get("current")
        if not isinstance(current, dict):
            return None
        ip_value = current.get("ip")
        return self._normalize_ip(ip_value if isinstance(ip_value, str) else None)

    def _normalize_state(self, value: Any) -> str:
        if not isinstance(value, str):
            return "unknown"
        normalized = value.strip().lower()
        if normalized in {HMA_CONNECTED, HMA_DISCONNECTED, HMA_CONNECTING, HMA_DISCONNECTING}:
            return normalized
        if normalized == "reconnecting":
            return HMA_CONNECTING
        return normalized or "unknown"

    def _validate_region(self, region: str) -> str:
        region = region.strip()
        if not region or any(char not in REGION_ALLOWED_CHARS for char in region):
            raise VpnError("Region format is invalid", status_code=400)
        return region

    def _normalize_ip(self, value: str | None) -> str | None:
        if not value:
            return None
        try:
            return str(ipaddress.ip_address(value.strip()))
        except ValueError:
            return None

    def _ensure_file(self, path: str, message: str) -> None:
        if not os.path.isfile(path):
            raise VpnError(message, status_code=503, stderr=path)

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
