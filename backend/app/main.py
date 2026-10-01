"""AgentPost main application - FastAPI server + daemon."""
from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.config import load_settings
from app.boxfs.paths import init_root
from app.registry.models import Registry
from app.router.resolver import Router
from app.events.bus import EventBus
from app.audit.logger import AuditLogger
from app.daemon.engine import DeliveryEngine


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("agentpost")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - startup and shutdown."""
    settings = load_settings()
    root = settings.root_path

    logger.info(f"AgentPost starting, root={root}, domain={settings.domain}")

    if settings.auto_init:
        init_root(root)

    registry = Registry(root, settings.domain)
    router = Router(registry, settings.domain)
    events = EventBus()
    audit = AuditLogger(root / "logs")

    engine = DeliveryEngine(
        root=root,
        registry=registry,
        router=router,
        events=events,
        audit=audit,
        domain=settings.domain,
        watch_interval_ms=settings.watch_interval_ms,
        max_attachment_bytes=settings.max_attachment_bytes,
    )

    app.state.settings = settings
    app.state.registry = registry
    app.state.router = router
    app.state.events = events
    app.state.audit = audit
    app.state.engine = engine
    app.state.ready = False
    app.state.start_time = time.time()

    await engine.start()
    app.state.ready = True
    logger.info("AgentPost ready")

    yield

    logger.info("AgentPost shutting down...")
    app.state.ready = False
    await engine.stop()
    logger.info("AgentPost stopped")


def create_app() -> FastAPI:
    settings = load_settings()
    app = FastAPI(
        title="AgentPost",
        version=__version__,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.api.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from app.api.routes.system import router as system_router
    from app.api.routes.boxes import router as boxes_router
    from app.api.routes.mail import router as mail_router
    from app.api.routes.queue import router as queue_router
    from app.api.routes.files import router as files_router
    from app.api.routes.websocket import router as ws_router

    app.include_router(system_router, prefix="/api/v1", tags=["system"])
    app.include_router(boxes_router, prefix="/api/v1", tags=["boxes"])
    app.include_router(mail_router, prefix="/api/v1", tags=["mail"])
    app.include_router(queue_router, prefix="/api/v1", tags=["queue"])
    app.include_router(files_router, prefix="/api/v1", tags=["files"])
    app.include_router(ws_router, prefix="/api/v1", tags=["events"])

    return app


app = create_app()
