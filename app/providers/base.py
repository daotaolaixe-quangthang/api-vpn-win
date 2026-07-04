import random
import re
from dataclasses import dataclass
from typing import Any, Protocol

REGION_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
ALL_REGIONS = "all"


@dataclass
class RefreshRegionPlan:
    mode: str
    country_key: str | None
    candidates: list[str]
    missing_regions: list[str] | None = None


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
    if not requested_region:
        if not current_region:
            return RefreshRegionPlan("auto-country", None, [])
        current_country_key = country_key(current_region)
        candidates = country_candidates(current_country_key, current_region, regions)
        return RefreshRegionPlan("auto-country", current_country_key, candidates)

    if requested_region == ALL_REGIONS:
        candidates = shuffled_unique(regions)
        if not candidates:
            raise VpnError("No VPN regions are available for refresh", status_code=404)
        return RefreshRegionPlan("all-regions", None, candidates)

    if "|" in requested_region:
        requested_regions = unique_regions(requested_region.split("|"))
        candidates, missing_regions = selected_region_candidates(requested_regions, regions)
        if not candidates:
            raise VpnError("None of the requested VPN regions were found", status_code=404, stderr=requested_region)
        return RefreshRegionPlan("region-list", None, candidates, missing_regions)

    if requested_region.endswith("-"):
        candidates = prefix_candidates(requested_region, regions)
        if not candidates:
            raise VpnError("No VPN regions matched the requested prefix", status_code=404, stderr=requested_region)
        return RefreshRegionPlan("prefix-regions", requested_region[:-1] or None, candidates)

    return RefreshRegionPlan("strict-region", country_key(requested_region), [requested_region])


def refresh_region_requires_regions(requested_region: str | None) -> bool:
    return not requested_region or requested_region == ALL_REGIONS or requested_region.endswith("-") or "|" in requested_region


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


def prefix_candidates(prefix: str, regions: list[str]) -> list[str]:
    return shuffled_unique(region for region in regions if region.startswith(prefix))


def selected_region_candidates(requested_regions: list[str], regions: list[str]) -> tuple[list[str], list[str]]:
    available_regions = set(regions)
    candidates = [region for region in requested_regions if region in available_regions]
    missing_regions = [region for region in requested_regions if region not in available_regions]
    return shuffled_unique(candidates), missing_regions


def unique_regions(regions: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for region in regions:
        if region and region not in seen:
            result.append(region)
            seen.add(region)
    return result


def shuffled_unique(regions: Any) -> list[str]:
    candidates = unique_regions(list(regions))
    random.shuffle(candidates)
    return candidates


def validate_refresh_region(region: str) -> str:
    region = region.strip()
    if not region:
        raise VpnError("Region format is invalid", status_code=400)
    if region == ALL_REGIONS:
        return region
    tokens = region.split("|")
    if any(not token or not REGION_TOKEN_PATTERN.fullmatch(token) for token in tokens):
        raise VpnError("Region format is invalid", status_code=400)
    return region


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
