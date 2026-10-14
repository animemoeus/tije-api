"""Settings, read from environment variables (prefix TJ_) or a .env file."""

import uuid

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TJ_", env_file=".env", extra="ignore")

    # Upstream TransJakarta app backend (from BuildConfig.BASE_URL).
    base_url: str = "https://tijeapi.transjakarta.co.id"
    timeout_seconds: float = 15.0

    # Headers the Android app sends with every request (see request builder in the JS bundle).
    app_version: str = "3.0.4"
    app_os: str = "android"
    app_os_version: str = "14"
    app_platform: str = "34"
    device_model: str = "Google|Pixel 8"
    device_id: str = uuid.uuid4().hex[:16]
    lang: str = "id"
    fcm_token: str = ""

    # Auth, in order of preference:
    #   bearer_token          use this token as-is (no login, no refresh)
    #   login_email/password  log in with a TransJakarta account (POST /v1/auth/login)
    #   neither               log in as guest (POST /v1/auth/login/guest), like the app's "skip login"
    bearer_token: str = ""
    login_email: str = ""
    login_password: str = ""

    # Poll POST /v1/bus/offline for areas with a WebSocket client, and push a snapshot to them, this often.
    poll_seconds: float = 1.0
    # Forget an area asked for only via GET /buses after this long without requests.
    area_idle_seconds: float = 60.0
    # Buses with no update for this long are dropped (the app uses 5 minutes).
    bus_expiry_seconds: float = 300.0
    default_radius_km: float = 1.0
    # Upstream honours large radii (20 km around Bundaran HI: ~2,300 buses, ~1 s per poll).
    max_radius_km: float = 50.0
    # Route geometry (GET /v2/route/{code}) rarely changes; keep it this long.
    route_cache_seconds: float = 3600.0

    # Serve the map UI (app/static) at /ui. Off: API only, / opens the Swagger docs.
    serve_ui: bool = False


settings = Settings()
