import os
import secrets
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def write_private(path: Path, text: str) -> None:
    """Faylni faqat egasi o'qiy oladigan (0600) qilib yozadi."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(text)


class Settings(BaseSettings):
    """Muhit o'zgaruvchilari orqali sozlanadi (GES_ prefiksi), masalan GES_DATABASE_URL."""

    model_config = SettingsConfigDict(env_prefix="GES_", env_file=".env", extra="ignore")

    app_name: str = "Sath"
    # Berilmasa data_dir/secret.key dan o'qiladi yoki yaratiladi (pastga qarang)
    secret_key: str = ""
    access_token_minutes: int = 60 * 12
    database_url: str = "sqlite:///./data/ges.db"
    data_dir: Path = Path("./data")
    # Birinchi ishga tushishda yaratiladigan admin
    admin_username: str = "admin"
    # Bo'sh bo'lsa birinchi ishga tushishda tasodifiy parol yaratilib
    # data_dir/initial-admin-password.txt ga yoziladi va logga chiqariladi
    admin_password: str = ""
    # Web build shu papkadan tarqatiladi (bo'sh bo'lsa faqat API)
    web_dist: Path | None = None
    max_upload_mb: int = 2048
    # CFD (OpenFOAM): docker — API server o'zi `docker run` qiladi (Docker Desktop/dev);
    # local — shu muhitda OpenFOAM bor; worker — alohida ges-worker konteyneri bajaradi; off — o'chiq
    cfd_mode: str = "docker"
    cfd_image: str = "opencfd/openfoam-default:2406"
    cfd_cpus: float = 2.0
    cfd_timeout_s: int = 3 * 3600
    # Ixtiyoriy SMTP: smtp://user:pass@host:587?from=ges@company.uz  (smtps:// — SSL)
    smtp_url: str | None = None
    # Web manzili — email dagi havolalar uchun (masalan http://ges-server:8000)
    public_url: str = ""
    # Ixtiyoriy MQTT broker: mqtt://user:pass@host:1883 — SCADA/gateway o'lchovlari uchun
    mqtt_url: str | None = None
    # Historian: xom o'lchovlar shuncha kun saqlanadi (soatlik agregat abadiy); 0 — o'chirilmaydi
    readings_retention_days: int = 90
    # Yuklashdan keyin fonda QTO/clash hisoblash (katta modellarda CPU; o'chirsa — birinchi so'rovda)
    precompute_geometry: bool = True
    # IFC → fragments (.frag) konvertatsiya: Node + web/tools/ifc2frag.mjs (avto topiladi)
    fragments_enabled: bool = True
    fragments_tool: Path | None = None
    node_bin: str = "node"
    # Tashqi konverterlar papkasi (dwg2dxf, assimp, blender, ODAFileConverter) — PATH da bo'lmasa
    tools_dir: Path | None = None
    # Fon tekshiruv davri (stale sensorlar, agregat), soniya
    monitor_interval_s: int = 30
    # Kunlik hisobot emaili (UTC soat); -1 — o'chirilgan. Muhandis/tasdiqlovchi/operatorlarga (SMTP bo'lsa)
    daily_report_hour: int = 6

    @property
    def files_dir(self) -> Path:
        return self.data_dir / "files"

    def ensure_secret_key(self) -> str:
        """Muhitda kalit bo'lmasa, data papkada doimiy tasodifiy kalit saqlaydi."""
        if self.secret_key:
            return self.secret_key
        key_file = self.data_dir / "secret.key"
        if key_file.exists():
            self.secret_key = key_file.read_text().strip()
        else:
            self.secret_key = secrets.token_urlsafe(48)
            write_private(key_file, self.secret_key)
        return self.secret_key


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_secret_key()
    return settings
