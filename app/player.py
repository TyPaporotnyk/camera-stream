from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.cameras import Camera


TEMPLATE_DIR = Path(__file__).parent / "templates"
template_env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=select_autoescape(("html", "xml")),
)


def render_player(camera: Camera) -> str:
    template = template_env.get_template("player.html")
    return template.render(
        cam_name=camera.name or camera.id,
        stream_path=f"/streams/{camera.id}/index.m3u8",
    )
