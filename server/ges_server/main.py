import asyncio
import logging
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import (  # noqa: F401  (audit: sessiya hodisalari ro'yxatdan o'tsin)
    __version__,
    audit,
    ha,
    jobs,
)
from .auth.router import router as auth_router
from .auth.security import hash_password, password_problems, verify_password
from .config import SERVER_ENV_FILE, get_settings, legacy_cwd_env, write_private
from .db import SessionLocal, assert_at_head, migrate
from .http_security import SecurityHeadersMiddleware
from .models.drafts_router import router as drafts_router
from .models.router import router as models_router
from .models.twin_router import router as twin_preset_router
from .models.underlays import router as underlays_router
from .monitoring import background, backplane, mqtt_bridge
from .monitoring.cm_router import router as cm_router
from .monitoring.control import router as control_router
from .monitoring.parts import router as parts_router
from .monitoring.router import router as monitoring_router
from .monitoring.twin_router import router as twin_router
from .monitoring.workorders import router as workorders_router
from .notifications import router as notifications_router
from .orm import User
from .projects.router import router as projects_router
from .review.router import router as review_router
from .sim.catalog_router import router as sim_catalog_router
from .sim.router import router as sim_router
from .sim.router import run_job
from .system.audit_router import router as audit_router
from .system.router import router as system_router
from .uploads import MaxBodyMiddleware

log = logging.getLogger("ges_server")


def init_db() -> None:
    """Sxemani Alembic bilan head ga keltiradi va admin bo'lmasa seed qiladi."""
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    if settings.auto_migrate:
        migrate()
    else:
        assert_at_head()
    weak = admin_password_problems()
    with SessionLocal() as db:
        if weak and not settings.dev_mode:
            # Muhitdagi zaif parol bilan yaratilgan (mavjud) admin — almashtirish majburiy (CODE-08)
            u = db.query(User).filter_by(username=settings.admin_username, is_admin=True).one_or_none()
            if u is not None and not u.must_change_password and verify_password(settings.admin_password, u.password_hash):
                u.must_change_password = True
                db.commit()
        if db.query(User).filter_by(is_admin=True).first() is None:
            password = settings.admin_password
            if not password:
                password = secrets.token_urlsafe(12)
                pw_file = settings.data_dir / "initial-admin-password.txt"
                write_private(pw_file, password)
                log.warning(
                    "Admin '%s' uchun tasodifiy parol yaratildi, fayl: %s. "
                    "Kirgach parolni o'zgartiring va faylni o'chiring.",
                    settings.admin_username,
                    pw_file,
                )
            db.add(
                User(
                    username=settings.admin_username,
                    full_name="Administrator",
                    password_hash=hash_password(password),
                    is_admin=True,
                    # Fayldagi tasodifiy parol va siyosatdan o'tmagan muhit paroli (CODE-08, dev rejimidan
                    # tashqari) — birinchi kirishda almashtiriladi
                    must_change_password=not settings.admin_password or (bool(weak) and not settings.dev_mode),
                )
            )
            db.commit()


def admin_password_problems() -> list[str]:
    """GES_ADMIN_PASSWORD parol siyosatidan (uzunlik, bloklash ro'yxati, ...) o'tmasa — muammolar ro'yxati."""
    s = get_settings()
    if not s.admin_password:
        return []
    return password_problems(s.admin_password, s.admin_username)


# Postgres uchun rad etiladigan (default/namuna) parollar — compose/.env.example dagi eski default "ges" ham
WEAK_DB_PASSWORDS = frozenset({"", "ges", "postgres", "password", "changeme", "admin", "sath", "secret"})


def production_problems() -> list[str]:
    """Ishlab chiqarishda (GES_DEV_MODE=false) serverni to'xtatadigan xatolar (CODE-08)."""
    from sqlalchemy.engine import make_url

    s = get_settings()
    out = []
    try:
        url = make_url(s.database_url)
    except Exception:  # noqa: BLE001 — noto'g'ri URL ni SQLAlchemy o'zi keyinroq aytadi
        return out
    if url.get_backend_name() == "postgresql" and (url.password or "").lower() in WEAK_DB_PASSWORDS:
        out.append(
            "Postgres paroli default/zaif (masalan 'ges') — .env da kuchli POSTGRES_PASSWORD bering "
            "(yoki faqat ishlab chiqish/sinovda GES_DEV_MODE=true)"
        )
    return out


def startup_warnings() -> list[str]:
    """Konfiguratsiya ogohlantirishlari (logga; testda tekshiriladi)."""
    s = get_settings()
    out = []
    weak = admin_password_problems()
    if weak:
        out.append(
            "!!! GES_ADMIN_PASSWORD parol siyosatidan o'tmaydi (" + "; ".join(weak) + ") — "
            + ("GES_DEV_MODE: faqat sinov uchun qabul qilindi" if s.dev_mode else
               "admin birinchi kirishda parolni almashtirishi SHART; .env dan GES_ADMIN_PASSWORD ni olib tashlang")
        )
    if s.dev_mode:
        out.extend("GES_DEV_MODE: " + p for p in production_problems())
    legacy = legacy_cwd_env()
    if legacy is not None:
        out.append(
            f"Joriy papkadagi .env o'qildi ({legacy}) — ishga tushirish joyiga bog'liq. "
            f"GES_ENV_FILE=<yo'l> yoki {SERVER_ENV_FILE} ishlating (CODE-06)"
        )
    return out


@asynccontextmanager
async def lifespan(_: FastAPI):
    for w in startup_warnings():
        log.warning(w)
    problems = [] if get_settings().dev_mode else production_problems()
    if problems:
        for p in problems:
            log.error(p)
        raise RuntimeError("Xavfsiz bo'lmagan konfiguratsiya: " + " | ".join(problems))
    init_db()
    stop = asyncio.Event()
    tasks: list[asyncio.Task] = []
    log.info("rol: %s (L8)", ha.role())
    if ha.runs_background():
        mqtt_bridge.start_if_configured(get_settings())
        tasks.append(asyncio.create_task(background.loop(stop)))  # stale sensorlar, historian (yetakchi qulfi bilan)
        jobs.runner = jobs.Runner(run_job)  # ish navbati ishchisi (L3): sim va hosilaviy artefaktlar
        tasks.append(asyncio.create_task(jobs.runner.run(stop)))
    from .monitoring import live

    live.hub.loop = asyncio.get_running_loop()
    live.hub.backplane = backplane.from_settings()  # L4: ko'p replika — Postgres LISTEN/NOTIFY
    if live.hub.backplane is not None:
        await live.hub.backplane.start(live.hub.deliver)
        listening = getattr(live.hub.backplane, "listening", None)
        if listening is not None and not await asyncio.to_thread(listening.wait, 10):
            log.warning("backplane 10 s da ulanmadi — /api/ready 503 beradi, fon urinishlar davom etadi")
    yield
    if live.hub.backplane is not None:
        await live.hub.backplane.stop()
        live.hub.backplane = None
    stop.set()
    if jobs.runner is not None:
        jobs.runner.kick()
    for t in tasks:
        await t
    jobs.runner = None
    if mqtt_bridge.bridge is not None:
        mqtt_bridge.bridge.stop()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version=__version__, lifespan=lifespan)
    # L5: Content-Length chegaradan katta bo'lsa tana o'qilmasdan 413 (multipart sarlavhalari uchun +1 MB)
    app.add_middleware(MaxBodyMiddleware, max_bytes=settings.max_upload_mb * 1024 * 1024 + (1 << 20))
    # OPS-01: CSP, nosniff, X-Frame-Options, Referrer-Policy, HSTS (https) — Caddy siz ham
    app.add_middleware(SecurityHeadersMiddleware, trust_forwarded=settings.rate_trust_forwarded)

    app.include_router(auth_router)
    app.include_router(projects_router)
    app.include_router(models_router)
    app.include_router(drafts_router)
    app.include_router(underlays_router)
    app.include_router(twin_preset_router)
    app.include_router(review_router)
    app.include_router(sim_catalog_router)  # /sim/catalog — /sim/{job_id} dan oldin
    app.include_router(sim_router)
    app.include_router(monitoring_router)
    app.include_router(control_router)
    app.include_router(twin_router)
    app.include_router(workorders_router)
    app.include_router(parts_router)
    app.include_router(cm_router)
    app.include_router(system_router)
    app.include_router(notifications_router)
    app.include_router(audit_router)

    # Web build mavjud bo'lsa shu serverdan tarqatiladi (SPA fallback bilan)
    web_dist = settings.web_dist
    if web_dist is None:
        candidate = Path(__file__).resolve().parents[2] / "web" / "dist"
        web_dist = candidate if candidate.exists() else None
    web_served = bool(web_dist and (web_dist / "index.html").exists())

    @app.get("/api/health", tags=["system"])
    def health():
        # Tiriklik (liveness): jarayon javob beradi. web: shu serverdan tarqatiladimi (desktop «Webda ochish»)
        return {"status": "ok", "version": __version__, "web": web_served, "role": ha.role()}

    @app.get("/api/ready", tags=["system"])
    def ready():
        """Tayyorlik (readiness, L8): DB, sxema head, backplane, ish navbati ishchisi — 503 bo'lsa load
        balancer bu replikaga trafik yubormaydi (Caddy `health_uri /api/ready`)."""
        ok, checks = ha.readiness()
        if not ok:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, {"status": "not-ready", **checks})
        return {"status": "ready", "version": __version__, **checks}

    if web_served:
        app.mount("/assets", StaticFiles(directory=web_dist / "assets"), name="assets")

        dist_root = web_dist.resolve()

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path.startswith("api/") or path == "api":
                # noma'lum API yo'li — HTML emas, 404 (brauzer HTML ni keshlab qolmasin)
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Bunday API yo'li yo'q")
            target = (dist_root / path).resolve()
            # dist papkasidan tashqariga chiqishga yo'l qo'ymaymiz (path traversal)
            if path and target.is_relative_to(dist_root) and target.is_file():
                return FileResponse(target)
            return FileResponse(dist_root / "index.html", headers={"Cache-Control": "no-cache"})

    return app


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("ges_server.main:app", host="0.0.0.0", port=8000, reload=False)
