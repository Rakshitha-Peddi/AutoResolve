"""Entry point: uvicorn backend.main:app --reload  (run from the project root)."""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from backend.orchestrator.engine import set_engine
from backend import config
from backend.api.routes import register_error_handlers, router
from backend.database.session import Base, SessionLocal, engine
from backend.models import bug as _bug  # noqa: F401  (registers the table)
from backend.models.bug import FIXING, Bug
from backend.orchestrator import sheets, workflow

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("autoresolve")


async def _poll_sheet(tasks: set[asyncio.Task]) -> None:
    """Check the sheet every SHEET_POLL_SECONDS; start a fix run for each new bug."""
    while True:
        try:
            for bug_id in await asyncio.to_thread(sheets.sync_sheet):
                task = asyncio.create_task(asyncio.to_thread(workflow.run_iteration, bug_id))
                tasks.add(task)
                task.add_done_callback(tasks.discard)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # a bad poll must never stop the loop
            log.warning("Sheet sync failed: %s", exc)
        await asyncio.sleep(config.SHEET_POLL_SECONDS)



def _configure_engine() -> None:
    if not config.USE_REAL_ENGINE:
        log.info("AutoResolve using StubEngine")
        return

    from backend.orchestrator.real_engine import RealFixEngine

    set_engine(RealFixEngine())
    log.info("AutoResolve using RealFixEngine")

@asynccontextmanager
async def lifespan(_: FastAPI):
    _configure_engine()
    
    Base.metadata.create_all(bind=engine)
    tasks: set[asyncio.Task] = set()

    # Fix runs live in memory; resume any a restart cut short.
    with SessionLocal() as db:
        for bug_id in db.scalars(select(Bug.id).where(Bug.status == FIXING)):
            log.info("Resuming BUG-%s", bug_id)
            task = asyncio.create_task(asyncio.to_thread(workflow.run_iteration, bug_id))
            tasks.add(task)
            task.add_done_callback(tasks.discard)

    poller = None
    if sheets.is_enabled():
        log.info("Google Sheets intake on (every %ss)", config.SHEET_POLL_SECONDS)
        poller = asyncio.create_task(_poll_sheet(tasks))
    yield
    if poller:
        poller.cancel()


app = FastAPI(title="AutoResolve", version="1.0.0", lifespan=lifespan)
register_error_handlers(app)
app.include_router(router)

# Mounted last so it never shadows /api or /docs.
if config.FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(config.FRONTEND_DIR), html=True), name="frontend")
else:
    log.warning("Frontend folder not found at %s; serving the API only", config.FRONTEND_DIR)
