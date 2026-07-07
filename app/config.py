from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    pia_ctl_path: str = Field(
        default=r"C:\Program Files\Private Internet Access\piactl.exe",
        alias="PIA_CTL_PATH",
    )
    pia_gui_path: str = Field(
        default=r"C:\Program Files\Private Internet Access\pia-client.exe",
        alias="PIA_GUI_PATH",
    )
    command_timeout_seconds: int = Field(default=30, alias="PIA_COMMAND_TIMEOUT_SECONDS")
    connect_timeout_seconds: int = Field(default=90, alias="PIA_CONNECT_TIMEOUT_SECONDS")
    reconnect_delay_seconds: int = Field(default=3, alias="PIA_RECONNECT_DELAY_SECONDS")
    refresh_max_attempts: int = Field(default=0, alias="PIA_REFRESH_MAX_ATTEMPTS")
    refresh_timeout_seconds: int = Field(default=180, alias="PIA_REFRESH_TIMEOUT_SECONDS")
    default_vpn_provider: str = Field(default="pia", alias="DEFAULT_VPN_PROVIDER")
    hma_nm_path: str = Field(
        default=r"C:\Program Files\Privax\HMA VPN\VpnNM.exe",
        alias="HMA_NM_PATH",
    )
    hma_gui_path: str = Field(
        default=r"C:\Program Files\Privax\HMA VPN\Vpn.exe",
        alias="HMA_GUI_PATH",
    )
    hma_service_name: str = Field(default="HmaProVpn", alias="HMA_SERVICE_NAME")
    hma_command_timeout_seconds: int = Field(default=30, alias="HMA_COMMAND_TIMEOUT_SECONDS")
    hma_connect_timeout_seconds: int = Field(default=90, alias="HMA_CONNECT_TIMEOUT_SECONDS")
    hma_reconnect_delay_seconds: int = Field(default=3, alias="HMA_RECONNECT_DELAY_SECONDS")
    hma_refresh_max_attempts: int = Field(default=1, alias="HMA_REFRESH_MAX_ATTEMPTS")
    hma_refresh_timeout_seconds: int = Field(default=180, alias="HMA_REFRESH_TIMEOUT_SECONDS")
    expressvpn_ctl_path: str = Field(
        default=r"C:\Program Files\ExpressVPN\expressvpnctl.exe",
        alias="EXPRESSVPN_CTL_PATH",
    )
    expressvpn_gui_path: str = Field(
        default=r"C:\Program Files\ExpressVPN\expressvpn-client.exe",
        alias="EXPRESSVPN_GUI_PATH",
    )
    expressvpn_command_timeout_seconds: int = Field(default=30, alias="EXPRESSVPN_COMMAND_TIMEOUT_SECONDS")
    expressvpn_connect_timeout_seconds: int = Field(default=90, alias="EXPRESSVPN_CONNECT_TIMEOUT_SECONDS")
    expressvpn_reconnect_delay_seconds: int = Field(default=3, alias="EXPRESSVPN_RECONNECT_DELAY_SECONDS")
    expressvpn_refresh_max_attempts: int = Field(default=0, alias="EXPRESSVPN_REFRESH_MAX_ATTEMPTS")
    expressvpn_refresh_timeout_seconds: int = Field(default=180, alias="EXPRESSVPN_REFRESH_TIMEOUT_SECONDS")
    proton_openvpn_path: str = Field(
        default=r"C:\Program Files\Proton\VPN\v4.4.1\Resources\openvpn.exe",
        alias="PROTON_OPENVPN_PATH",
    )
    proton_ovpn_config_path: str = Field(default="", alias="PROTON_OVPN_CONFIG_PATH")
    proton_ovpn_config_dir: str = Field(default="", alias="PROTON_OVPN_CONFIG_DIR")
    proton_openvpn_auth_file: str = Field(default="", alias="PROTON_OPENVPN_AUTH_FILE")
    proton_openvpn_pid_file: str = Field(default=".proton-openvpn.pid", alias="PROTON_OPENVPN_PID_FILE")
    proton_openvpn_cleanup_orphan_processes: bool = Field(default=False, alias="PROTON_OPENVPN_CLEANUP_ORPHAN_PROCESSES")
    proton_command_timeout_seconds: int = Field(default=30, alias="PROTON_COMMAND_TIMEOUT_SECONDS")
    proton_connect_timeout_seconds: int = Field(default=90, alias="PROTON_CONNECT_TIMEOUT_SECONDS")
    proton_reconnect_delay_seconds: int = Field(default=3, alias="PROTON_RECONNECT_DELAY_SECONDS")
    proton_refresh_max_attempts: int = Field(default=0, alias="PROTON_REFRESH_MAX_ATTEMPTS")
    proton_refresh_timeout_seconds: int = Field(default=180, alias="PROTON_REFRESH_TIMEOUT_SECONDS")
    proton_ip_check_url: str = Field(default="https://api.ipify.org", alias="PROTON_IP_CHECK_URL")
    api_host: str = Field(default="127.0.0.1", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")
    api_key: str = Field(default="", alias="API_KEY")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
