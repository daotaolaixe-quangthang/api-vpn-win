from dataclasses import dataclass
from typing import Any, Protocol


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
