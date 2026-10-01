from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from backend.database.session import Base, engine
from backend.models import bug  # noqa: F401
from backend.api.routes import router

Base.metadata.create_all(bind=engine)
app = FastAPI(title="AutoResolve", version="1.0.0")
app.include_router(router)
frontend = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/", StaticFiles(directory=str(frontend), html=True), name="frontend")
