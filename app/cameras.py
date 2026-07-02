from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator


CAMERA_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")
DEFAULT_INPUT_ARGS = [
    "-rtsp_transport",
    "tcp",
    "-timeout",
    "10000000",
    "-analyzeduration",
    "1000000",
    "-probesize",
    "1000000",
    "-fflags",
    "nobuffer",
    "-flags",
    "low_delay",
    "-max_delay",
    "500000",
]
DEFAULT_OUTPUT_ARGS = [
    "-map",
    "0:v:0",
    "-an",
    "-dn",
    "-sn",
    "-c:v",
    "libx264",
    "-preset",
    "veryfast",
    "-tune",
    "zerolatency",
    "-profile:v",
    "baseline",
    "-level",
    "3.1",
    "-pix_fmt",
    "yuv420p",
    "-force_key_frames",
    "expr:gte(t,n_forced*2)",
    "-sc_threshold",
    "0",
    "-avoid_negative_ts",
    "make_zero",
]


class Camera(BaseModel):
    id: str
    rtsp_url: str
    name: str | None = None
    enabled: bool = True
    input_args: list[str] = Field(default_factory=lambda: DEFAULT_INPUT_ARGS.copy())
    output_args: list[str] = Field(default_factory=lambda: DEFAULT_OUTPUT_ARGS.copy())

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not CAMERA_ID_RE.fullmatch(value):
            raise ValueError("camera id can contain only letters, digits, '_' and '-'")
        return value


class CamerasConfig(BaseModel):
    cameras: list[Camera] = Field(default_factory=list)

    @field_validator("cameras")
    @classmethod
    def validate_unique_ids(cls, cameras: list[Camera]) -> list[Camera]:
        seen: set[str] = set()
        duplicates: set[str] = set()
        for camera in cameras:
            if camera.id in seen:
                duplicates.add(camera.id)
            seen.add(camera.id)
        if duplicates:
            raise ValueError(f"duplicate camera ids: {', '.join(sorted(duplicates))}")
        return cameras


class CameraRepository:
    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path
        self._cameras = self._load()

    def list_enabled(self) -> list[Camera]:
        return [camera for camera in self._cameras.values() if camera.enabled]

    def get(self, camera_id: str) -> Camera | None:
        return self._cameras.get(camera_id)

    def _load(self) -> dict[str, Camera]:
        if not self.config_path.exists():
            raise FileNotFoundError(
                f"Camera config '{self.config_path}' was not found. "
                "Create it from config.example.yml or set CAMERAS_CONFIG."
            )

        with self.config_path.open("r", encoding="utf-8") as file:
            raw_config: Any = yaml.safe_load(file) or {}

        parsed = CamerasConfig.model_validate(raw_config)
        return {camera.id: camera for camera in parsed.cameras}
