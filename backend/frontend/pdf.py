from __future__ import annotations

import html
import re
from datetime import datetime
from pathlib import Path

from frontend.config import FRONTEND_DIR, resolve_font_family, resolve_font_path


class FontConfigurationError(RuntimeError):
    pass


class PdfGenerationError(RuntimeError):
    pass


def validate_font(font_path: Path | None = None) -> Path:
    font_path = font_path or resolve_font_path()
    if not font_path.is_file() or font_path.suffix.lower() not in {".ttf", ".otf"}:
        raise FontConfigurationError(
            "PDF용 한글 폰트를 찾을 수 없습니다. "
            f"TTF/OTF 파일을 '{font_path}'에 넣거나 "
            "KANGGAEMI_PDF_FONT_DIR, KANGGAEMI_PDF_FONT_FILE 환경변수를 설정하세요."
        )
    return font_path.resolve()


def markdown_to_pdf(
    markdown_text: str,
    *,
    title: str = "투자 전략 리포트",
    font_path: Path | None = None,
    font_family: str | None = None,
) -> bytes:
    font = validate_font(font_path)
    font_family = font_family or resolve_font_family()
    try:
        import markdown
        from weasyprint import CSS, HTML
        from weasyprint.text.fonts import FontConfiguration
    except (ImportError, OSError) as exc:
        raise PdfGenerationError(
            "PDF 라이브러리를 불러오지 못했습니다. frontend/README.md의 "
            "WeasyPrint 설치 안내를 확인하세요."
        ) from exc

    body = markdown.markdown(
        markdown_text,
        extensions=["extra", "sane_lists", "tables"],
        output_format="html5",
    )
    document = (
        "<!doctype html><html lang='ko'><head><meta charset='utf-8'>"
        f"<title>{html.escape(title)}</title></head><body>{body}</body></html>"
    )
    escaped_family = font_family.replace("\\", "\\\\").replace('"', '\\"')
    css = f"""
        @font-face {{
            font-family: "{escaped_family}";
            src: url("{font.as_uri()}");
            font-style: normal;
            font-weight: 100 900;
        }}
        @page {{ size: A4; margin: 20mm 18mm 22mm; }}
        html {{ font-family: "{escaped_family}"; color: #172033; line-height: 1.65; }}
        body {{ font-size: 10.5pt; }}
        h1 {{ font-size: 22pt; margin: 0 0 18pt; color: #0f2942; }}
        h2 {{ font-size: 15pt; margin: 20pt 0 8pt; color: #123f66;
              border-bottom: 1px solid #d9e3ec; padding-bottom: 4pt; }}
        h3 {{ font-size: 12pt; color: #1c527d; }}
        h1, h2, h3 {{ page-break-after: avoid; }}
        p, li {{ overflow-wrap: anywhere; }}
        blockquote {{ margin: 8pt 0; padding: 5pt 10pt; border-left: 3px solid #88a9c4;
                      background: #f4f8fb; color: #34495e; }}
        table {{ width: 100%; border-collapse: collapse; margin: 10pt 0; }}
        th, td {{ border: 1px solid #cfd9e2; padding: 5pt; text-align: left; }}
        th {{ background: #eef4f8; }}
        code {{ background: #eef2f5; padding: 1pt 3pt; border-radius: 2pt; }}
        a {{ color: #175f91; }}
    """
    try:
        font_config = FontConfiguration()
        stylesheet = CSS(string=css, font_config=font_config)
        return HTML(string=document, base_url=str(FRONTEND_DIR)).write_pdf(
            stylesheets=[stylesheet], font_config=font_config,
        )
    except Exception as exc:
        raise PdfGenerationError(f"PDF 생성에 실패했습니다: {exc}") from exc


def make_pdf_filename(query: str, generated_at: datetime | None = None) -> str:
    timestamp = (generated_at or datetime.now()).strftime("%Y%m%d_%H%M%S")
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "", query.strip())
    stem = re.sub(r"\s+", "_", stem).strip("._")[:40] or "투자전략리포트"
    return f"{stem}_{timestamp}.pdf"
