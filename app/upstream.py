"""Client for the TransJakarta app backend (tijeapi).

Endpoints and payloads come from the app's Hermes bundle (v3.0.4):
  guestLogin           POST /v1/auth/login/guest {} -> {token, refresh_token, token_valid_until, ...}
  token refresh        POST /v1/auth/token/refresh {refresh_token}
  getBusNearestOffline POST /v1/bus/offline {latitude, longitude, radius, event:"change_loc"} -> data: [bus, ...]
  getSearchBusStopNew  GET  /v2/bus-stop?latitude&longitude&radius
  getRouteDetail       GET  /v2/route/{route_code} -> data: {route, inbound, outbound, loop}

  login                POST /v1/auth/login {email, password} -> same token fields as guest login

Every call except login/refresh needs `Authorization: Bearer <token>` (401 "token is required" otherwise).
Without TJ_BEARER_TOKEN the client logs in with TJ_LOGIN_EMAIL/TJ_LOGIN_PASSWORD, or as a guest.
"""

import asyncio
import logging
import time
from typing import Any
from urllib.parse import quote

import httpx

from .config import Settings

log = logging.getLogger(__name__)

# Renew this many seconds before token_valid_until.
TOKEN_MARGIN_SECONDS = 300


class UpstreamError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class TJClient:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self._http = httpx.AsyncClient(
            base_url=settings.base_url,
            timeout=settings.timeout_seconds,
            headers=self._headers(),
            transport=transport,
        )
        self._auth_lock = asyncio.Lock()
        self._token = settings.bearer_token
        self._token_valid_until = float("inf") if settings.bearer_token else 0.0
        self._refresh_token = ""
        self._refresh_valid_until = 0.0
        self._logged_in_as = ""  # "user" or "guest", whichever produced the current token
        self.last_auth_error = ""

    def _headers(self) -> dict[str, str]:
        s = self.settings
        headers = {
            "X-App-Version": s.app_version,
            "X-Device-ID": s.device_id,
            "X-Lang": s.lang,
            "X-FCM-Token": s.fcm_token,
            "X-App-OS": s.app_os,
            "X-App-OS-Version": s.app_os_version,
            "X-App-Platform": s.app_platform,
            "X-Device-Model": s.device_model,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        return headers

    async def aclose(self) -> None:
        await self._http.aclose()

    # ---- Auth ------------------------------------------------------------

    @property
    def auth_mode(self) -> str:
        s = self.settings
        if s.bearer_token:
            return "static"
        return "user" if s.login_email and s.login_password else "guest"

    def token_info(self) -> dict[str, Any]:
        """Auth status for /health. Never includes tokens or the password."""
        return {
            "mode": self.auth_mode,
            "logged_in_as": "static" if self.settings.bearer_token else self._logged_in_as or None,
            "email": self.settings.login_email or None,
            "has_token": bool(self._token),
            "valid_until": None if self._token_valid_until == float("inf") else int(self._token_valid_until) or None,
            "last_error": self.last_auth_error or None,
        }

    def _store_tokens(self, body: Any) -> None:
        # Guest login returns the fields at top level; accept a {data: {...}} wrapper too.
        d = body.get("data") if isinstance(body, dict) and isinstance(body.get("data"), dict) else body
        token = (d or {}).get("token")
        if not token:
            raise UpstreamError("auth response has no token")
        self._token = token
        self._token_valid_until = float(d.get("token_valid_until") or time.time() + 3600)
        self._refresh_token = d.get("refresh_token") or self._refresh_token
        self._refresh_valid_until = float(d.get("refresh_token_valid_until") or 0)

    async def _ensure_token(self, force: bool = False) -> str:
        if self.settings.bearer_token:
            return self.settings.bearer_token
        async with self._auth_lock:
            now = time.time()
            if not force and self._token and now < self._token_valid_until - TOKEN_MARGIN_SECONDS:
                return self._token
            if self._refresh_token and now < self._refresh_valid_until - 60:
                try:
                    body = await self._send("POST", "/v1/auth/token/refresh", json={"refresh_token": self._refresh_token})
                    self._store_tokens(body)
                    log.info("upstream token refreshed")
                    return self._token
                except UpstreamError as e:
                    log.warning("token refresh failed (%s); logging in again", e)
            if self.auth_mode == "user":
                try:
                    body = await self._send(
                        "POST", "/v1/auth/login",
                        json={"email": self.settings.login_email, "password": self.settings.login_password},
                    )
                    self._store_tokens(body)
                    self._logged_in_as, self.last_auth_error = "user", ""
                    log.info("logged in as %s, token valid until %s", self.settings.login_email, int(self._token_valid_until))
                    return self._token
                except UpstreamError as e:
                    # Keep the public features working; /health shows why the account login failed.
                    self.last_auth_error = f"account login failed: {e}"
                    log.error("%s; falling back to guest", self.last_auth_error)
            self._store_tokens(await self._send("POST", "/v1/auth/login/guest", json={}))
            self._logged_in_as = "guest"
            log.info("logged in as guest, token valid until %s", int(self._token_valid_until))
            return self._token

    @property
    def is_user_session(self) -> bool:
        return self._logged_in_as == "user" or bool(self.settings.bearer_token)

    async def request(self, method: str, url: str, **kwargs: Any) -> Any:
        """Authenticated call to any tijeapi path (for endpoints that need a logged-in account)."""
        return await self._request(method, url, **kwargs)

    # ---- HTTP ------------------------------------------------------------

    async def _send(self, method: str, url: str, headers: dict[str, str] | None = None, **kwargs: Any) -> Any:
        try:
            resp = await self._http.request(method, url, headers=headers, **kwargs)
        except httpx.HTTPError as e:
            raise UpstreamError(f"{method} {url}: {e}") from e
        if resp.status_code >= 400:
            raise UpstreamError(f"{method} {url}: HTTP {resp.status_code} {resp.text[:200]}", resp.status_code)
        try:
            return resp.json()
        except ValueError as e:
            raise UpstreamError(f"{method} {url}: response is not JSON") from e

    async def _request(self, method: str, url: str, **kwargs: Any) -> Any:
        token = await self._ensure_token()
        try:
            return await self._send(method, url, headers={"Authorization": f"Bearer {token}"}, **kwargs)
        except UpstreamError as e:
            # Token revoked or expired early: get a new one once and retry.
            if e.status != 401 or self.settings.bearer_token:
                raise
            token = await self._ensure_token(force=True)
            return await self._send(method, url, headers={"Authorization": f"Bearer {token}"}, **kwargs)

    @staticmethod
    def _area_payload(lat: float, lon: float, radius_km: float) -> dict[str, Any]:
        return {"latitude": lat, "longitude": lon, "radius": radius_km, "event": "change_loc"}

    async def get_offline_buses(self, lat: float, lon: float, radius_km: float) -> Any:
        body = await self._request("POST", "/v1/bus/offline", json=self._area_payload(lat, lon, radius_km))
        return (body or {}).get("data")

    async def get_bus_stops(self, lat: float, lon: float, radius_km: float) -> Any:
        params = {"latitude": lat, "longitude": lon, "radius": radius_km}
        body = await self._request("GET", "/v2/bus-stop", params=params)
        return (body or {}).get("data")

    async def get_route(self, route_code: str) -> Any:
        """Route detail with stops and polyline per direction. Unknown codes give HTTP 404."""
        body = await self._request("GET", f"/v2/route/{quote(route_code, safe='')}")
        return (body or {}).get("data")
