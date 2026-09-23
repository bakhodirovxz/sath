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


# Barqaror .env joyi (CODE-06): server/ papkasi (pyproject yonida) — ishga tushirilgan joriy papkaga bog'liq emas
SERVER_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


def env_files() -> tuple[Path, ...]:
    """O'qiladigan .env fayllari (keyingisi ustun). GES_ENV_FILE berilsa — faqat u. Aks holda barqaror
    `server/.env`, keyin eski xatti-harakat uchun joriy papkadagi `.env` (bo'lsa, startda ogohlantirish)."""
    explicit = os.environ.get("GES_ENV_FILE")
    if explicit:
        return (Path(explicit),)
    cwd_env = Path.cwd() / ".env"
    if cwd_env.resolve() == SERVER_ENV_FILE:
        return (SERVER_ENV_FILE,)
    return (SERVER_ENV_FILE, cwd_env)


def legacy_cwd_env() -> Path | None:
    """Joriy papkadagi .env ishlatilyaptimi (GES_ENV_FILE siz, server/.env emas) — ogohlantirish uchun."""
    files = env_files()
    return files[-1] if len(files) > 1 and files[-1].is_file() else None


class Settings(BaseSettings):
    """Muhit o'zgaruvchilari orqali sozlanadi (GES_ prefiksi), masalan GES_DATABASE_URL. .env — env_files()."""

    model_config = SettingsConfigDict(env_prefix="GES_", env_file=None, extra="ignore")

    app_name: str = "Sath"
    # Berilmasa data_dir/secret.key dan o'qiladi yoki yaratiladi (pastga qarang)
    secret_key: str = ""
    # false — JWT kaliti umuman o'qilmaydi/yaratilmaydi (CFD worker: token chiqarmaydi, /data/secret.key ni
    # ko'rmaydi — faqat case papkasi mount qilinadi)
    secret_key_required: bool = True
    # L2: access token qisqa umrli, refresh token sessiya muddati (aylantiriladi); WS da qayta avtorizatsiya davri
    access_token_minutes: int = 15
    refresh_token_hours: float = 12
    ws_reauth_s: int = 300
    # L4: WS bo'sh turish chegarasi (klient shuncha soniya hech narsa yubormasa — 4408), foydalanuvchi bo'yicha
    # ulanish chegarasi (4429), backplane: auto (Postgres bo'lsa LISTEN/NOTIFY) | pg | off
    ws_idle_s: int = 90
    ws_max_per_user: int = 8
    live_backplane: str = "auto"
    # Parol siyosati (NIST 800-63B): minimal uzunlik; bloklash ro'yxati va login tekshiruvi doimiy
    password_min_length: int = 8
    database_url: str = "sqlite:///./data/ges.db"
    # Startda `alembic upgrade head` avtomatik; false bo'lsa sxema head da emasligi xato beradi
    auto_migrate: bool = True
    data_dir: Path = Path("./data")
    # Birinchi ishga tushishda yaratiladigan admin
    admin_username: str = "admin"
    # Bo'sh bo'lsa birinchi ishga tushishda tasodifiy parol yaratilib
    # data_dir/initial-admin-password.txt ga yoziladi va logga chiqariladi
    admin_password: str = ""
    # CODE-08: ishlab chiqish/sinov rejimi — zaif (siyosatdan o'tmaydigan) admin paroli va default DB paroli
    # faqat ogohlantirish beradi. Ishlab chiqarishda (false, default): zaif muhit admin paroli → birinchi
    # kirishda almashtirish majburiy; Postgres default/zaif paroli bilan server ishga TUSHMAYDI.
    dev_mode: bool = False
    # Web build shu papkadan tarqatiladi (bo'sh bo'lsa faqat API)
    web_dist: Path | None = None
    max_upload_mb: int = 2048
    # SEC-03: desktop paketlari imzosi — nashr qiluvchining Ed25519 ochiq kaliti (base64, 32 bayt; bo'sh —
    # server imzoni tekshirmaydi, faqat saqlab beradi). require — imzosiz/noto'g'ri imzoli paket rad etiladi.
    desktop_signing_public_key: str = ""
    desktop_require_signature: bool = False
    # L5: kichik yuklashlar chegarasi (CSV import, BCF) MB; parser sandbox rejimi: auto | bwrap | rlimit | off
    small_upload_mb: int = 50
    sandbox: str = "auto"
    # CFD (OpenFOAM): worker (default, deploy/.env.example bilan bir xil — alohida `cfd` konteyneri bajaradi,
    # API server solver ishga tushirmaydi); docker — API server o'zi `docker run` qiladi (Docker Desktop/dev);
    # local — shu muhitda OpenFOAM bor; off — o'chiq
    cfd_mode: str = "worker"
    cfd_image: str = "opencfd/openfoam-default:2406@sha256:dd5aa20630a55722663bf83ba0cb74870cba130081303e32e3865007fa2aa35a"  # CI-03: digest pin
    cfd_cpus: float = 2.0
    # docker rejimi: konteyner xotira chegarasi (OPS-05; --memory, swap siz)
    cfd_memory: str = "8g"
    # Analitik simulyatsiya: alohida jarayonda (spawn) vaqt chegarasi bilan; testlarda o'chiriladi
    sim_isolate: bool = True
    sim_timeout_s: int = 300
    # Foydalanuvchi / loyiha bo'yicha bir vaqtda navbatda/ishlayotgan simulyatsiyalar soni
    sim_max_active_per_user: int = 3
    sim_max_active_per_project: int = 10
    # Ish navbati (L3): jarayon ichidagi ishchi — bir vaqtda ishlar soni, navbat tekshiruv davri (s)
    jobs_concurrency: int = 2
    jobs_poll_s: float = 2.0
    # L8: rol — all (HTTP + fon, default) | api (faqat HTTP/WS, ko'p replika) | worker (fon sikli, ish navbati,
    # MQTT; bitta nusxa — yetakchi qulfi bilan himoyalangan)
    role: str = "all"
    cfd_timeout_s: int = 3 * 3600
    # Ixtiyoriy SMTP: smtp://user:pass@host:587?from=ges@company.uz  (smtps:// — SSL)
    smtp_url: str | None = None
    # Web manzili — email dagi havolalar uchun (masalan http://ges-server:8000)
    public_url: str = ""
    # Ixtiyoriy MQTT broker: mqtts://broker:8883 (tavsiya) yoki mqtt://localhost:1883 (dev). Parol URL da
    # emas — GES_MQTT_USERNAME/GES_MQTT_PASSWORD yoki GES_MQTT_PASSWORD_FILE (Docker secret).
    mqtt_url: str | None = None
    mqtt_username: str | None = None
    mqtt_password: str | None = None
    mqtt_password_file: Path | None = None
    # mqtts:// uchun CA majburiy (pinning); mTLS — klient sertifikati + kaliti
    mqtt_ca_file: Path | None = None
    mqtt_cert_file: Path | None = None
    mqtt_key_file: Path | None = None
    # TLS siz mqtt:// loopback bo'lmagan hostga faqat shu bilan (ochiq matn xavfi qabul qilinadi)
    mqtt_allow_insecure: bool = False
    # Obuna ruxsati: vergul bilan MQTT filtrlar, {project_id} o'rinbosari (masalan "sath/{project_id}/#")
    mqtt_topic_allow: str = "#"
    # Partiyalash: xabarlar shuncha (yoki shuncha ms) yig'ilib bitta tranzaksiyada yoziladi
    mqtt_batch_size: int = 200
    mqtt_batch_ms: int = 250
    # Historian qatlamlari (D2): xom → 1 daqiqa → 10 daqiqa → 1 soat; har birining saqlash muddati (kun),
    # 0 — o'chirilmaydi. Xom o'lchov alarm hodisasi atrofida (±1 soat) o'chirilmaydi.
    readings_retention_days: int = 90
    agg_1m_retention_days: int = 400
    agg_10m_retention_days: int = 1100
    # SOE (hodisalar ketma-ketligi) saqlash muddati, kun; 0 — o'chirilmaydi
    soe_retention_days: int = 1100
    # Jonli ingest (http/mqtt) vaqt tamg'asi oynasi: bundan eski yoki kelajakdagi qiymat rad etiladi
    ingest_max_age_days: int = 30
    ingest_future_s: int = 300
    # Yuklashdan keyin fonda QTO/clash hisoblash (katta modellarda CPU; o'chirsa — birinchi so'rovda)
    precompute_geometry: bool = True
    # IFC → fragments (.frag) konvertatsiya: Node + web/tools/ifc2frag.mjs (avto topiladi)
    fragments_enabled: bool = True
    fragments_tool: Path | None = None
    node_bin: str = "node"
    # Tashqi konverterlar papkasi (dwg2dxf, assimp, blender, ODAFileConverter) — PATH da bo'lmasa
    tools_dir: Path | None = None
    # G1: webdan yaratilgan yangi modellar sxemasi — IFC4 (default, keng mos) yoki IFC4X3_ADD2 (ISO 16739-1:2024,
    # infratuzilma entitylari: IfcFacilityPartCommon, IfcEarthworksFill, IfcGeographicElement TERRAIN)
    ifc_schema: str = "IFC4"
    # IDS (G2): yuklashda tekshiriladigan axborot talablari fayli (nisbiy — CWD, repo ildizi yoki /app)
    ids_file: Path = Path("docs/ids/sath-ges.ids")
    # Relyef (DEM) plitkalari (L7, ma'lumot joylashuvi): default tashqi AWS Terrain Tiles — so'rovda faqat plitka
    # koordinatalari (z/x/y) ketadi, lekin bu ob'ekt joylashuvini uchinchi tomonga oshkor qiladi. Yopiq tarmoqda
    # ichki ko'zgu (dem_tile_url) yoki o'chirish (dem_enabled=false); ruxsat etilgan chiquvchi kanal — security-zones.md
    dem_enabled: bool = True
    dem_tile_url: str = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
    # SRV-06: log formati json | text, darajasi; Prometheus /api/metrics — token berilsa Bearer shart, aks holda
    # faqat loopback (127.0.0.1/::1) dan
    log_format: str = "text"
    log_level: str = "INFO"
    metrics_token: str = ""
    # Fon tekshiruv davri (stale sensorlar, agregat), soniya
    monitor_interval_s: int = 30
    # Alarm shelving (ISA-18.2): default va maksimal muddat, soat
    alarm_shelve_default_h: float = 8.0
    alarm_shelve_max_h: float = 24.0
    # Buyruq watchdog: gateway olib (sent) shuncha soniyada ack/failed qaytarmasa → failed, sensor bo'shaydi
    command_sent_timeout_s: int = 120
    # Kunlik hisobot emaili (UTC soat); -1 — o'chirilgan. Muhandis/tasdiqlovchi/operatorlarga (SMTP bo'lsa)
    daily_report_hour: int = 6
    # Tezlik cheklovlari (L1), daqiqasiga; 0 — o'chirilgan. Jarayon ichida (replika boshiga).
    rate_login_per_min: int = 30  # IP bo'yicha (Argon2 CPU sarfi va brute force)
    rate_ingest_per_min: int = 600  # loyiha bo'yicha (POST readings/soe so'rovlar soni, qatorlar emas)
    rate_commands_per_min: int = 60  # foydalanuvchi bo'yicha (select/execute)
    rate_sim_per_min: int = 20  # foydalanuvchi bo'yicha (sim ishlarini yaratish)
    # Teskari proksi (Caddy) ortida X-Forwarded-For dan klient IP olinadi; to'g'ridan-to'g'ri ochiq serverda false!
    rate_trust_forwarded: bool = False
    # Hisobni bloklash: shuncha ketma-ket noto'g'ri parol/MFA → shuncha daqiqa kirish yo'q (DB da, umumiy)
    login_max_failures: int = 10
    login_lockout_minutes: int = 15
    # Administratorlar uchun TOTP MFA majburiy: yoqilmaguncha admin endpointlari 403 (profil MFA sozlashdan tashqari)
    mfa_required_for_admins: bool = False

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


def load_settings() -> Settings:
    """Muhitdan yangi Settings (keshsiz); JWT kaliti kerak bo'lsa (default) o'qiladi/yaratiladi."""
    settings = Settings(_env_file=env_files())
    if settings.secret_key_required:
        settings.ensure_secret_key()
    return settings


@lru_cache
def get_settings() -> Settings:
    return load_settings()
