import asyncio
import logging
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .auth.router import router as auth_router
from .auth.security import hash_password
from .config import get_settings, write_private
from .db import Base, SessionLocal, engine, ensure_columns
from .models.drafts_router import router as drafts_router
from .models.router import router as models_router
from .models.twin_router import router as twin_preset_router
from .models.underlays import router as underlays_router
from .monitoring import background, mqtt_bridge
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
from .system.audit_router import router as audit_router
from .system.router import router as system_router

log = logging.getLogger("ges_server")


def init_db() -> None:
    """Jadvallarni yaratadi va admin bo'lmasa seed qiladi."""
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    ensure_columns()  # mavjud jadvallarga yangi ustunlar
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
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
                )
            )
            db.commit()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    mqtt_bridge.start_if_configured(get_settings().mqtt_url)
    stop = asyncio.Event()
    task = asyncio.create_task(background.loop(stop))  # stale sensorlar, historian
    yield
    stop.set()
    await task
    if mqtt_bridge.bridge is not None:
        mqtt_bridge.bridge.stop()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version=__version__, lifespan=lifespan)

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
        # web: shu serverdan tarqatiladimi (desktop «Webda ochish» shunga qarab manzil tanlaydi)
        return {"status": "ok", "version": __version__, "web": web_served}

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
