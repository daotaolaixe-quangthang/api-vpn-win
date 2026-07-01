from typing import Annotated

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Query

from .config import Settings, get_settings
from .pia import PiaClient, PiaError
from .providers.base import VpnError, VpnProvider
from .providers.registry import get_provider
from .schemas import ApiResponse, RegionRequest

app = FastAPI(title="Multi VPN API", version="1.1.0")


def get_pia_client(settings: Annotated[Settings, Depends(get_settings)]) -> PiaClient:
    return PiaClient(settings)


def get_vpn_client(provider: str, settings: Settings) -> VpnProvider:
    return get_provider(provider, settings)


def require_api_key(
    settings: Annotated[Settings, Depends(get_settings)],
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> None:
    if settings.api_key and x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail={"error": "Invalid API key"})


def pia_response(data: dict | None = None, warnings: list[str] | None = None, ok: bool = True) -> ApiResponse:
    return ApiResponse(ok=ok, data=data, warnings=warnings or [])


def raise_vpn_error(error: VpnError) -> None:
    raise HTTPException(status_code=error.status_code, detail=error.as_detail())


def raise_pia_error(error: PiaError) -> None:
    raise_vpn_error(error)


def launch_provider(client: VpnProvider, provider: str | None = None) -> ApiResponse:
    data = client.launch_gui()
    if provider:
        data = {"provider": provider, **data}
    return pia_response(data)


def enable_provider_background(client: VpnProvider, provider: str | None = None) -> ApiResponse:
    data = client.enable_background()
    if provider:
        data = {"provider": provider, **data}
    return pia_response(data)


def connect_provider(client: VpnProvider, wait: bool = False, provider: str | None = None, region: str | None = None) -> ApiResponse:
    if region:
        client.set_region(region)
    data = client.connect(wait=wait)
    if provider:
        data = {"provider": provider, **data}
    return pia_response(data)


def disconnect_provider(client: VpnProvider, wait: bool = False, provider: str | None = None) -> ApiResponse:
    data = client.disconnect(wait=wait)
    if provider:
        data = {"provider": provider, **data}
    return pia_response(data)


def status_provider(client: VpnProvider, provider: str | None = None) -> ApiResponse:
    data, warnings = client.status()
    if provider:
        data = {"provider": provider, **data}
    return pia_response(data, warnings)


def ip_provider(client: VpnProvider, provider: str | None = None) -> ApiResponse:
    data, warnings = client.ip_info()
    if provider:
        data = {"provider": provider, **data}
    return pia_response(data, warnings)


def regions_provider(client: VpnProvider, provider: str | None = None) -> ApiResponse:
    data = {"regions": client.get_regions()}
    if provider:
        data = {"provider": provider, **data}
    return pia_response(data)


def region_provider(client: VpnProvider, provider: str | None = None) -> ApiResponse:
    region = client.get_region()
    data = {"region": region}
    if region is None:
        data["message"] = "No active or selected VPN region is available for this provider"
    if provider:
        data = {"provider": provider, **data}
    return pia_response(data)


def set_provider_region(client: VpnProvider, region: str, provider: str | None = None) -> ApiResponse:
    data = client.set_region(region)
    if provider:
        data = {"provider": provider, **data}
    return pia_response(data)


def refresh_provider_ip(client: VpnProvider, region: str | None = None, provider: str | None = None) -> ApiResponse:
    data, warnings, changed = client.refresh_ip(region=region)
    if provider:
        data = {"provider": provider, **data}
    return pia_response(data, warnings, ok=changed)


@app.get("/health", response_model=ApiResponse)
def health() -> ApiResponse:
    return pia_response({"service": "multi-vpn-api"})


@app.post("/pia/launch", response_model=ApiResponse, dependencies=[Depends(require_api_key)])
def launch_pia(client: Annotated[PiaClient, Depends(get_pia_client)]) -> ApiResponse:
    try:
        return launch_provider(client)
    except PiaError as error:
        raise_pia_error(error)


@app.post("/pia/background/enable", response_model=ApiResponse, dependencies=[Depends(require_api_key)])
def enable_background(client: Annotated[PiaClient, Depends(get_pia_client)]) -> ApiResponse:
    try:
        return enable_provider_background(client)
    except PiaError as error:
        raise_pia_error(error)


@app.post("/pia/connect", response_model=ApiResponse, dependencies=[Depends(require_api_key)])
def connect_pia(
    client: Annotated[PiaClient, Depends(get_pia_client)],
    wait: bool = Query(default=False),
) -> ApiResponse:
    try:
        return connect_provider(client, wait=wait)
    except PiaError as error:
        raise_pia_error(error)


@app.post("/pia/disconnect", response_model=ApiResponse, dependencies=[Depends(require_api_key)])
def disconnect_pia(
    client: Annotated[PiaClient, Depends(get_pia_client)],
    wait: bool = Query(default=False),
) -> ApiResponse:
    try:
        return disconnect_provider(client, wait=wait)
    except PiaError as error:
        raise_pia_error(error)


@app.get("/pia/status", response_model=ApiResponse, dependencies=[Depends(require_api_key)])
@app.post("/pia/status", response_model=ApiResponse, dependencies=[Depends(require_api_key)])
def get_status(client: Annotated[PiaClient, Depends(get_pia_client)]) -> ApiResponse:
    try:
        return status_provider(client)
    except PiaError as error:
        raise_pia_error(error)


@app.get("/pia/ip", response_model=ApiResponse, dependencies=[Depends(require_api_key)])
@app.post("/pia/ip", response_model=ApiResponse, dependencies=[Depends(require_api_key)])
def get_ip(client: Annotated[PiaClient, Depends(get_pia_client)]) -> ApiResponse:
    try:
        return ip_provider(client)
    except PiaError as error:
        raise_pia_error(error)


@app.get("/pia/regions", response_model=ApiResponse, dependencies=[Depends(require_api_key)])
@app.post("/pia/regions", response_model=ApiResponse, dependencies=[Depends(require_api_key)])
def get_regions(client: Annotated[PiaClient, Depends(get_pia_client)]) -> ApiResponse:
    try:
        return regions_provider(client)
    except PiaError as error:
        raise_pia_error(error)


@app.get("/pia/region", response_model=ApiResponse, dependencies=[Depends(require_api_key)])
def get_region(client: Annotated[PiaClient, Depends(get_pia_client)]) -> ApiResponse:
    try:
        return region_provider(client)
    except PiaError as error:
        raise_pia_error(error)


@app.post("/pia/region", response_model=ApiResponse, dependencies=[Depends(require_api_key)])
def set_region(
    request: RegionRequest,
    client: Annotated[PiaClient, Depends(get_pia_client)],
) -> ApiResponse:
    try:
        return set_provider_region(client, request.region)
    except PiaError as error:
        raise_pia_error(error)


@app.post("/pia/refresh-ip", response_model=ApiResponse, dependencies=[Depends(require_api_key)])
def refresh_ip(
    client: Annotated[PiaClient, Depends(get_pia_client)],
    region: str | None = Query(default=None, min_length=1),
) -> ApiResponse:
    try:
        return refresh_provider_ip(client, region=region)
    except PiaError as error:
        raise_pia_error(error)


@app.post("/vpn/{provider}/launch", response_model=ApiResponse, dependencies=[Depends(require_api_key)])
def launch_vpn(
    provider: str,
    settings: Annotated[Settings, Depends(get_settings)],
) -> ApiResponse:
    try:
        return launch_provider(get_vpn_client(provider, settings), provider=provider.lower())
    except VpnError as error:
        raise_vpn_error(error)


@app.post("/vpn/{provider}/background/enable", response_model=ApiResponse, dependencies=[Depends(require_api_key)])
def enable_vpn_background(
    provider: str,
    settings: Annotated[Settings, Depends(get_settings)],
) -> ApiResponse:
    try:
        return enable_provider_background(get_vpn_client(provider, settings), provider=provider.lower())
    except VpnError as error:
        raise_vpn_error(error)


@app.post("/vpn/{provider}/connect", response_model=ApiResponse, dependencies=[Depends(require_api_key)])
def connect_vpn(
    provider: str,
    settings: Annotated[Settings, Depends(get_settings)],
    wait: bool = Query(default=False),
    region: str | None = Query(default=None, min_length=1),
) -> ApiResponse:
    try:
        return connect_provider(get_vpn_client(provider, settings), wait=wait, provider=provider.lower(), region=region)
    except VpnError as error:
        raise_vpn_error(error)


@app.post("/vpn/{provider}/disconnect", response_model=ApiResponse, dependencies=[Depends(require_api_key)])
def disconnect_vpn(
    provider: str,
    settings: Annotated[Settings, Depends(get_settings)],
    wait: bool = Query(default=False),
) -> ApiResponse:
    try:
        return disconnect_provider(get_vpn_client(provider, settings), wait=wait, provider=provider.lower())
    except VpnError as error:
        raise_vpn_error(error)


@app.get("/vpn/{provider}/status", response_model=ApiResponse, dependencies=[Depends(require_api_key)])
@app.post("/vpn/{provider}/status", response_model=ApiResponse, dependencies=[Depends(require_api_key)])
def get_vpn_status(
    provider: str,
    settings: Annotated[Settings, Depends(get_settings)],
) -> ApiResponse:
    try:
        return status_provider(get_vpn_client(provider, settings), provider=provider.lower())
    except VpnError as error:
        raise_vpn_error(error)


@app.get("/vpn/{provider}/ip", response_model=ApiResponse, dependencies=[Depends(require_api_key)])
@app.post("/vpn/{provider}/ip", response_model=ApiResponse, dependencies=[Depends(require_api_key)])
def get_vpn_ip(
    provider: str,
    settings: Annotated[Settings, Depends(get_settings)],
) -> ApiResponse:
    try:
        return ip_provider(get_vpn_client(provider, settings), provider=provider.lower())
    except VpnError as error:
        raise_vpn_error(error)


@app.get("/vpn/{provider}/regions", response_model=ApiResponse, dependencies=[Depends(require_api_key)])
@app.post("/vpn/{provider}/regions", response_model=ApiResponse, dependencies=[Depends(require_api_key)])
def get_vpn_regions(
    provider: str,
    settings: Annotated[Settings, Depends(get_settings)],
) -> ApiResponse:
    try:
        return regions_provider(get_vpn_client(provider, settings), provider=provider.lower())
    except VpnError as error:
        raise_vpn_error(error)


@app.get("/vpn/{provider}/region", response_model=ApiResponse, dependencies=[Depends(require_api_key)])
def get_vpn_region(
    provider: str,
    settings: Annotated[Settings, Depends(get_settings)],
) -> ApiResponse:
    try:
        return region_provider(get_vpn_client(provider, settings), provider=provider.lower())
    except VpnError as error:
        raise_vpn_error(error)


@app.post("/vpn/{provider}/region", response_model=ApiResponse, dependencies=[Depends(require_api_key)])
def set_vpn_region(
    provider: str,
    settings: Annotated[Settings, Depends(get_settings)],
    request: RegionRequest | None = Body(default=None),
) -> ApiResponse:
    try:
        client = get_vpn_client(provider, settings)
        if request is None:
            return region_provider(client, provider=provider.lower())
        return set_provider_region(client, request.region, provider=provider.lower())
    except VpnError as error:
        raise_vpn_error(error)


@app.post("/vpn/{provider}/refresh-ip", response_model=ApiResponse, dependencies=[Depends(require_api_key)])
def refresh_vpn_ip(
    provider: str,
    settings: Annotated[Settings, Depends(get_settings)],
    region: str | None = Query(default=None, min_length=1),
) -> ApiResponse:
    try:
        return refresh_provider_ip(get_vpn_client(provider, settings), region=region, provider=provider.lower())
    except VpnError as error:
        raise_vpn_error(error)
