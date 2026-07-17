from __future__ import annotations

import os
from pathlib import Path


FRONTEND_DIR = Path(__file__).resolve().parent
BACKEND_DIR = FRONTEND_DIR.parent
NODE_SPECS_PATH = Path(
    os.getenv("KANGGAEMI_NODE_SPECS_PATH", BACKEND_DIR / "app" / "core" / "node_specs.yaml")
).resolve()

FONT_DIR = Path(
    os.getenv("KANGGAEMI_PDF_FONT_DIR", FRONTEND_DIR / "assets" / "fonts")
).resolve()


def resolve_font_path() -> Path:
    """Resolve explicit config first, then a single installed font."""
    font_dir = Path(
        os.getenv("KANGGAEMI_PDF_FONT_DIR", FRONTEND_DIR / "assets" / "fonts")
    ).resolve()
    configured_name = os.getenv("KANGGAEMI_PDF_FONT_FILE")
    if configured_name:
        return (font_dir / configured_name).resolve()

    placeholder = (font_dir / "CompanyKoreanFont.ttf").resolve()
    if placeholder.is_file():
        return placeholder
    candidates = sorted(
        path.resolve() for path in font_dir.glob("*")
        if path.is_file() and path.suffix.lower() in {".ttf", ".otf"}
    ) if font_dir.is_dir() else []
    return candidates[0] if len(candidates) == 1 else placeholder


def resolve_font_family() -> str:
    return os.getenv("KANGGAEMI_PDF_FONT_FAMILY", "Company Korean")

MOCK_DELAY_SECONDS = float(os.getenv("KANGGAEMI_MOCK_DELAY_SECONDS", "0.45"))
APP_TITLE = os.getenv("KANGGAEMI_FRONTEND_TITLE", "투자 전략 리포트 에이전트")
DEFAULT_ADAPTER = os.getenv("KANGGAEMI_AGENT_ADAPTER", "langgraph").lower()
SETUP_CHECKPOINTER = os.getenv(
    "KANGGAEMI_AGENT_SETUP_CHECKPOINTER", "false"
).lower() in {"1", "true", "yes", "on"}
