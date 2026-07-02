from __future__ import annotations

import asyncio
import logging
import re
import shutil
import subprocess
from collections import deque
from collections.abc import Iterable
from urllib.parse import urlsplit, urlunsplit

from app.cameras import Camera
from app.settings import Settings


logger = logging.getLogger(__name__)
RTSP_URL_RE = re.compile(r"rtsp://\S+")


def redact_url(value: str) -> str:
    parts = urlsplit(value)
    if not parts.password:
        return value

    username = parts.username or ""
    hostname = parts.hostname or ""
    port = f":{parts.port}" if parts.port else ""
    netloc = f"{username}:***@{hostname}{port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def redact_command(command: list[str]) -> list[str]:
    return [redact_url(part) if part.startswith("rtsp://") else part for part in command]


def redact_line(value: str) -> str:
    return RTSP_URL_RE.sub(lambda match: redact_url(match.group(0)), value)


class FfmpegCommandBuilder:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def build(self, camera: Camera) -> list[str]:
        output_dir = self.settings.hls_dir / camera.id
        return [
            self.settings.ffmpeg_path,
            "-hide_banner",
            "-loglevel",
            "warning",
            *camera.input_args,
            "-i",
            camera.rtsp_url,
            *camera.output_args,
            "-f",
            "hls",
            "-hls_time",
            str(self.settings.hls_segment_time),
            "-hls_list_size",
            str(self.settings.hls_list_size),
            "-hls_flags",
            "delete_segments+program_date_time+independent_segments",
            "-hls_segment_filename",
            str(output_dir / "segment_%05d.ts"),
            str(output_dir / "index.m3u8"),
        ]


class CameraStream:
    def __init__(self, camera: Camera, settings: Settings, command_builder: FfmpegCommandBuilder) -> None:
        self.camera = camera
        self.settings = settings
        self.command_builder = command_builder
        self.process: subprocess.Popen[bytes] | None = None
        self._stderr_tail: deque[str] = deque(maxlen=20)
        self._stop_requested = False

    async def start(self) -> None:
        if self.is_running:
            return
        if shutil.which(self.settings.ffmpeg_path) is None:
            raise RuntimeError(f"ffmpeg executable not found: {self.settings.ffmpeg_path}")

        self._prepare_hls_dir()
        self._stop_requested = False
        self._stderr_tail.clear()
        command = self.command_builder.build(self.camera)
        logger.info("Starting stream for camera %s", self.camera.id)
        logger.debug("ffmpeg command for camera %s: %s", self.camera.id, " ".join(redact_command(command)))
        self.process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        logger.info("Started ffmpeg for camera %s with pid %s", self.camera.id, self.process.pid)
        asyncio.create_task(self._capture_stderr(self.process))
        asyncio.create_task(self._restart_when_crashed())

    async def stop(self) -> None:
        self._stop_requested = True
        if not self.process or not self.is_running:
            return

        logger.info("Stopping stream for camera %s", self.camera.id)
        self.process.terminate()
        try:
            await asyncio.wait_for(asyncio.to_thread(self.process.wait), timeout=10)
        except asyncio.TimeoutError:
            logger.warning("Killing ffmpeg for camera %s after graceful stop timeout", self.camera.id)
            self.process.kill()
            await asyncio.to_thread(self.process.wait)
        logger.info("Stopped stream for camera %s", self.camera.id)

    @property
    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def _prepare_hls_dir(self) -> None:
        output_dir = self.settings.hls_dir / self.camera.id
        output_dir.mkdir(parents=True, exist_ok=True)
        for path in output_dir.glob("*"):
            if path.suffix in {".m3u8", ".ts"}:
                path.unlink(missing_ok=True)

    async def _capture_stderr(self, process: subprocess.Popen[bytes]) -> None:
        if process.stderr is None:
            return

        await asyncio.to_thread(self._read_stderr_tail, process.stderr)

    def _read_stderr_tail(self, stderr: Iterable[bytes]) -> None:
        for raw_line in stderr:
            line = redact_line(raw_line.decode(errors="replace").strip())
            if line:
                self._stderr_tail.append(line)

    async def _restart_when_crashed(self) -> None:
        process = self.process
        if process is None:
            return

        await asyncio.to_thread(process.wait)
        if self._stop_requested:
            return

        logger.warning(
            "ffmpeg for camera %s exited with code %s; restarting in %s second(s)",
            self.camera.id,
            process.returncode,
            self.settings.stream_restart_delay,
        )
        if self._stderr_tail:
            logger.warning("Last ffmpeg messages for camera %s: %s", self.camera.id, " | ".join(self._stderr_tail))
        await asyncio.sleep(self.settings.stream_restart_delay)
        await self.start()


class StreamManager:
    def __init__(self, cameras: list[Camera], settings: Settings) -> None:
        command_builder = FfmpegCommandBuilder(settings)
        self.streams = [
            CameraStream(camera=camera, settings=settings, command_builder=command_builder)
            for camera in cameras
        ]

    async def start(self) -> None:
        await asyncio.gather(*(stream.start() for stream in self.streams))

    async def stop(self) -> None:
        await asyncio.gather(*(stream.stop() for stream in self.streams))
