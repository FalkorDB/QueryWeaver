"""Template helper utilities for Jinja templates.

This module provides SVG inlining and a small helper to register
template helpers (filters/globals) on a Jinja environment.
"""

import os

from pathlib import Path
from typing import Any
import functools
from markupsafe import Markup

from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader, FileSystemBytecodeCache, select_autoescape

TEMPLATES_DIR = str((Path(__file__).resolve().parents[1] / "../app/templates").resolve())

TEMPLATES_CACHE_DIR = "/tmp/jinja_cache"
os.makedirs(TEMPLATES_CACHE_DIR, exist_ok=True)  # ✅ ensures the folder exists

templates = Jinja2Templates(
    env=Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        bytecode_cache=FileSystemBytecodeCache(
            directory=TEMPLATES_CACHE_DIR,
            pattern="%s.cache"
        ),
        auto_reload=True,
        autoescape=select_autoescape(['html', 'xml', 'j2'])
    )
)

def template_response(name:str, template):
    """Helper to return a TemplateResponse using the shared templates object."""
    return templates.TemplateResponse(name, template)

@functools.lru_cache(maxsize=512)
def _read_svg_file(path: str) -> str:
    """Read an SVG file from common project static locations.

    Returns the file contents or an empty string when not found.
    """
    if not path:
        return ""

    p = path.lstrip("/")
    # climb two levels to reach the project root (path/.../queryweaver)
    # file is api/helpers/template.py -> parents[0]=api/helpers, [1]=api, [2]=project root
    repo_root = Path(__file__).resolve().parents[2]
    candidates = [
        repo_root / "app" / "public" / p,
        repo_root / "app" / "static" / p,
        repo_root / "static" / p,
        repo_root / p,
    ]

    for c in candidates:
        try:
            if c.is_file():
                return c.read_text(encoding="utf-8")
        except OSError:
            continue

    return ""

def inline_svg(path: str) -> Markup:
    """Return inline SVG markup as a Markup (safe) object.

    Accepts strings like '/icons/foo.svg' or '/icons/foo.svg'.
    """
    svg = _read_svg_file(path or "")
    if not svg:
        return Markup("")

    # Strip XML prolog if present
    if svg.lstrip().startswith("<?xml"):
        idx = svg.find("?>")
        if idx != -1:
            svg = svg[idx + 2 :]

    return Markup(svg)

# Register inline-SVG helper filters/globals on the templates environment
templates.env.filters["inline_svg"] = inline_svg
templates.env.globals["inline_svg"] = inline_svg 

templates.env.globals["google_tag_manager_id"] = os.getenv("GOOGLE_TAG_MANAGER_ID")
