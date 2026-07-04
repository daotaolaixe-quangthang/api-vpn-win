import random
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class RefreshRegionPlan:
    mode: str
    country_key: str | None
    candidates: list[str]


@dataclass
class VpnError(Exception):
    message: str
    status_code: int = 500
    command: list[str] | None = None
    stderr: str | None = None
    returncode: int | None = None

    def as_detail(self) -> dict[str, Any]:
        detail: dict[str, Any] = {"error": self.message}
        if self.command is not None:
            detail["command"] = self.command
        if self.stderr:
            detail["stderr"] = self.stderr
        if self.returncode is not None:
            detail["returncode"] = self.returncode
        return detail


def refresh_region_plan(
    requested_region: str | None,
    current_region: str | None,
    regions: list[str],
) -> RefreshRegionPlan:
    if requested_region:
        return RefreshRegionPlan("strict-region", country_key(requested_region), [requested_region])
    if not current_region:
        return RefreshRegionPlan("auto-country", None, [])
    current_country_key = country_key(current_region)
    candidates = country_candidates(current_country_key, current_region, regions)
    return RefreshRegionPlan("auto-country", current_country_key, candidates)


def country_candidates(country_key_value: str, current_region: str, regions: list[str]) -> list[str]:
    if "-" in current_region:
        candidates = [region for region in regions if region == country_key_value or region.startswith(f"{country_key_value}-")]
    else:
        candidates = [region for region in regions if region == country_key_value]
    random.shuffle(candidates)
    if current_region in candidates and len(candidates) > 1:
        candidates.remove(current_region)
        candidates.append(current_region)
    elif current_region not in candidates:
        candidates.append(current_region)
    return candidates or [current_region]


def country_key(region: str) -> str:
    if "-" not in region:
        return region
    return region.split("-", 1)[0]


class VpnProvider(Protocol):
    def launch_gui(self) -> dict[str, Any]: ...

    def enable_background(self) -> dict[str, Any]: ...

    def connect(self, wait: bool = False) -> dict[str, Any]: ...

    def disconnect(self, wait: bool = False) -> dict[str, Any]: ...

    def set_region(self, region: str) -> dict[str, Any]: ...

    def get_region(self) -> str | None: ...

    def get_regions(self) -> list[str]: ...

    def get_connection_state(self) -> str: ...

    def get_pubip(self) -> str | None: ...

    def get_vpnip(self) -> str | None: ...

    def ip_info(self) -> tuple[dict[str, Any], list[str]]: ...

    def status(self) -> tuple[dict[str, Any], list[str]]: ...

    def wait_for_state(self, expected_state: str, timeout_seconds: float) -> str: ...

    def refresh_ip(self, region: str | None = None) -> tuple[dict[str, Any], list[str], bool]: ...
