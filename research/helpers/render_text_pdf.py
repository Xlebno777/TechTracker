from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont

PAGE_W = 1240
PAGE_H = 1754
MARGIN_X = 90
MARGIN_Y = 90
CONTENT_W = PAGE_W - MARGIN_X * 2

FONT_REG = "/usr/share/fonts/liberation/LiberationSerif-Regular.ttf"
FONT_BOLD = "/usr/share/fonts/liberation/LiberationSerif-Bold.ttf"
FONT_ITALIC = "/usr/share/fonts/TTF/DejaVuSerif-Italic.ttf"
FONT_MONO = "/usr/share/fonts/TTF/DejaVuSansMono.ttf"

STYLES = {
    "h1": {"font": FONT_BOLD, "size": 32, "spacing_before": 0, "spacing_after": 26},
    "h2": {"font": FONT_BOLD, "size": 24, "spacing_before": 20, "spacing_after": 14},
    "h3": {"font": FONT_BOLD, "size": 19, "spacing_before": 16, "spacing_after": 10},
    "p": {"font": FONT_REG, "size": 18, "spacing_before": 0, "spacing_after": 10},
    "bullet": {"font": FONT_REG, "size": 18, "spacing_before": 0, "spacing_after": 8},
    "code": {"font": FONT_MONO, "size": 15, "spacing_before": 4, "spacing_after": 8},
    "formula": {"font": FONT_ITALIC, "size": 22, "spacing_before": 10, "spacing_after": 14},
    "note": {"font": FONT_REG, "size": 15, "spacing_before": 2, "spacing_after": 8},
}


def load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size=size)


def wrap_text(text: str, font: ImageFont.FreeTypeFont, width: int, draw: ImageDraw.ImageDraw) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if draw.textlength(candidate, font=font) <= width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def wrap_preserving_indent(text: str, font: ImageFont.FreeTypeFont, width: int, draw: ImageDraw.ImageDraw) -> list[str]:
    leading = len(text) - len(text.lstrip(" "))
    prefix = text[:leading]
    stripped = text.strip()
    if not stripped:
        return [""]
    lines = wrap_text(stripped, font, max(10, width - int(draw.textlength(prefix, font=font))), draw)
    return [prefix + lines[0]] + [prefix + line for line in lines[1:]]


def parse_blocks(lines: Iterable[str]) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    paragraph: list[str] = []
    in_code = False
    code_lines: list[str] = []
    in_formula = False
    formula_lines: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            text = " ".join(part.strip() for part in paragraph if part.strip())
            if text:
                blocks.append(("p", text))
            paragraph = []

    def flush_code() -> None:
        nonlocal code_lines
        if code_lines:
            for line in code_lines:
                blocks.append(("code", line.rstrip()))
            code_lines = []

    def flush_formula() -> None:
        nonlocal formula_lines
        if formula_lines:
            blocks.append(("formula", "\n".join(line.rstrip() for line in formula_lines)))
            formula_lines = []

    for raw in lines:
        line = raw.rstrip("\n")
        if line.strip() == "$$":
            flush_paragraph()
            flush_code()
            if in_formula:
                flush_formula()
                in_formula = False
            else:
                in_formula = True
            continue
        if line.strip() == "```":
            flush_paragraph()
            if in_code:
                flush_code()
                in_code = False
            else:
                in_code = True
            continue
        if in_code:
            code_lines.append(line)
            continue
        if in_formula:
            formula_lines.append(line)
            continue
        if not line.strip():
            flush_paragraph()
            blocks.append(("blank", ""))
            continue
        if line.startswith("# "):
            flush_paragraph()
            blocks.append(("h1", line[2:].strip()))
            continue
        if line.startswith("## "):
            flush_paragraph()
            blocks.append(("h2", line[3:].strip()))
            continue
        if line.startswith("### "):
            flush_paragraph()
            blocks.append(("h3", line[4:].strip()))
            continue
        if line.startswith("- "):
            flush_paragraph()
            blocks.append(("bullet", "• " + line[2:].strip()))
            continue
        paragraph.append(line)

    flush_paragraph()
    if in_code:
        flush_code()
    if in_formula:
        flush_formula()
    return blocks


def render_document(text: str, out_path: Path) -> None:
    draft = Image.new("RGB", (PAGE_W, PAGE_H), "white")
    draft_draw = ImageDraw.Draw(draft)
    fonts = {key: load_font(cfg["font"], cfg["size"]) for key, cfg in STYLES.items()}

    pages: list[Image.Image] = []
    page = Image.new("RGB", (PAGE_W, PAGE_H), "white")
    draw = ImageDraw.Draw(page)
    y = MARGIN_Y

    def new_page() -> None:
        nonlocal page, draw, y
        footer_font = fonts["note"]
        footer = f"{len(pages) + 1}"
        draw.text(
            (PAGE_W - MARGIN_X - draw.textlength(footer, font=footer_font), PAGE_H - MARGIN_Y + 18),
            footer,
            fill="#5b6470",
            font=footer_font,
        )
        pages.append(page)
        page = Image.new("RGB", (PAGE_W, PAGE_H), "white")
        draw = ImageDraw.Draw(page)
        y = MARGIN_Y

    def line_height(font: ImageFont.FreeTypeFont) -> int:
        bbox = font.getbbox("Ag")
        return (bbox[3] - bbox[1]) + 4

    for kind, value in parse_blocks(text.splitlines()):
        if kind == "blank":
            y += 8
            continue

        style = STYLES[kind]
        font = fonts[kind]
        y += style["spacing_before"]

        if kind in {"h1", "h2", "h3", "p"}:
            lines = wrap_text(value, font, CONTENT_W, draw)
            x = MARGIN_X
        elif kind == "bullet":
            lines = wrap_preserving_indent(value, font, CONTENT_W, draw)
            x = MARGIN_X
        elif kind == "formula":
            lines = value.splitlines() or [""]
            x = MARGIN_X
        else:
            lines = [value]
            x = MARGIN_X + 18

        needed = len(lines) * line_height(font) + style["spacing_after"]
        if kind == "formula":
            needed += 28
        if y + needed > PAGE_H - MARGIN_Y:
            new_page()

        if kind == "formula":
            box_top = y
            box_height = len(lines) * line_height(font) + 28
            draw.rounded_rectangle(
                (MARGIN_X + 40, box_top, PAGE_W - MARGIN_X - 40, box_top + box_height),
                radius=16,
                fill="#f7f8fb",
                outline="#d9dde5",
                width=2,
            )
            y += 14
            for line in lines:
                line_w = draw.textlength(line, font=font)
                fx = MARGIN_X + (CONTENT_W - line_w) / 2
                draw.text((fx, y), line, fill="#18212f", font=font)
                y += line_height(font)
        else:
            fill = "#111827"
            if kind == "note":
                fill = "#5b6470"
            for line in lines:
                draw.text((x, y), line, fill=fill, font=font)
                y += line_height(font)
        y += style["spacing_after"]

    footer_font = fonts["note"]
    footer = f"{len(pages) + 1}"
    draw.text(
        (PAGE_W - MARGIN_X - draw.textlength(footer, font=footer_font), PAGE_H - MARGIN_Y + 18),
        footer,
        fill="#5b6470",
        font=footer_font,
    )
    pages.append(page)
    pages[0].save(out_path, "PDF", resolution=150.0, save_all=True, append_images=pages[1:])


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Usage: render_text_pdf.py <input.md> <output.pdf>")
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2])
    render_document(src.read_text(encoding="utf-8"), dst)
