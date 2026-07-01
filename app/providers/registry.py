from ..config import Settings
from ..pia import PiaClient
from .base import VpnError, VpnProvider
from .expressvpn import ExpressVpnClient
from .hma import HmaClient

_clients: dict[str, VpnProvider] = {}


def get_provider(provider: str, settings: Settings) -> VpnProvider:
    provider = provider.strip().lower()
    if not provider:
        provider = settings.default_vpn_provider.strip().lower()
    if provider in _clients:
        return _clients[provider]
    if provider == "pia":
        client: VpnProvider = PiaClient(settings)
    elif provider == "hma":
        client = HmaClient(settings)
    elif provider == "expressvpn":
        client = ExpressVpnClient(settings)
    else:
        raise VpnError("Unsupported VPN provider", status_code=404, stderr=provider)
    _clients[provider] = client
    return client
