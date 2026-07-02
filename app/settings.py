from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from starlette.config import Config


config = Config(".env" if Path(".env").exists() else None)


@dataclass(frozen=True)
class Settings:
    cameras_config: Path
    hls_dir: Path
    ffmpeg_path: str
    hls_segment_time: int
    hls_list_size: int
    stream_restart_delay: int


def get_settings() -> Settings:
    return Settings(
        cameras_config=Path(config("CAMERAS_CONFIG", default="config.yml")),
        hls_dir=Path(config("HLS_DIR", default="/var/lib/camera-stream/hls")),
        ffmpeg_path=config("FFMPEG_PATH", default="ffmpeg"),
        hls_segment_time=config("HLS_SEGMENT_TIME", cast=int, default=2),
        hls_list_size=config("HLS_LIST_SIZE", cast=int, default=6),
        stream_restart_delay=config("STREAM_RESTART_DELAY", cast=int, default=5),
    )
