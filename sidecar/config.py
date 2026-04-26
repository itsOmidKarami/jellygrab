import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    jellyfin_url: str
    jellyfin_api_key: str
    jellyfin_user_id: str
    download_dir: Path
    sidecar_host: str
    sidecar_port: int
    nama_base_url: str
    nama_cookie: str
    nama_cookies_file: Path | None
    nama_user_agent: str
    plugin_dir: Path
    keepalive_interval_sec: int


def load_settings() -> Settings:
    return Settings(
        jellyfin_url=os.getenv("JELLYFIN_URL", "http://jellyfin:8096").rstrip("/"),
        jellyfin_api_key=os.getenv("JELLYFIN_API_KEY", ""),
        jellyfin_user_id=os.getenv("JELLYFIN_USER_ID", ""),
        download_dir=Path(os.getenv("DOWNLOAD_DIR", "/media/downloads")),
        sidecar_host=os.getenv("SIDECAR_HOST", "0.0.0.0"),
        sidecar_port=int(os.getenv("SIDECAR_PORT", "8765")),
        nama_base_url=os.getenv("NAMA_BASE_URL", "https://30nama.com").rstrip("/"),
        nama_cookie=os.getenv("NAMA_COOKIE", ""),
        nama_cookies_file=Path(os.environ["NAMA_COOKIES_FILE"]) if os.getenv("NAMA_COOKIES_FILE") else None,
        nama_user_agent=os.getenv(
            "NAMA_USER_AGENT",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        ),
        plugin_dir=Path(os.getenv("PLUGIN_DIR", "/app/jellyfin-plugin")),
        keepalive_interval_sec=int(os.getenv("KEEPALIVE_INTERVAL_SEC", "1800")),
    )


settings = load_settings()
