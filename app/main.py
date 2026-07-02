from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from app.cameras import CameraRepository
from app.player import render_player
from app.settings import get_settings
from app.streaming import StreamManager


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

settings = get_settings()
settings.hls_dir.mkdir(parents=True, exist_ok=True)
camera_repository = CameraRepository(settings.cameras_config)
stream_manager = StreamManager(camera_repository.list_enabled(), settings)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting camera stream service with %d enabled camera(s)", len(stream_manager.streams))
    await stream_manager.start()
    try:
        yield
    finally:
        logger.info("Stopping camera stream service")
        await stream_manager.stop()


app = FastAPI(
    title="Camera Stream",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/player/{camera_id}", response_class=HTMLResponse)
async def get_player(camera_id: str) -> str:
    camera = camera_repository.get(camera_id)
    if camera is None:
        logger.warning("Player requested for unknown camera: %s", camera_id)
        raise HTTPException(status_code=404, detail="Camera not found")
    return render_player(camera)


def run() -> None:
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000)
