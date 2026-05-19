#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import re
import shutil
import subprocess
from pathlib import Path

from weasyprint import CSS, HTML

ROOT = Path(__file__).resolve().parents[2]
RESEARCH_DIR = ROOT / 'research'
SRC = RESEARCH_DIR / 'alg_pro.md'
OUT = RESEARCH_DIR / 'alg_pro.pdf'
ROOT_OUT = ROOT / 'alg_pro.pdf'
KATEX_PACKAGE = Path('/tmp/alg_pro_katex/node_modules/katex')
KATEX_CSS = KATEX_PACKAGE / 'dist/katex.min.css'
RENDERER = RESEARCH_DIR / 'helpers/render_katex_batch.cjs'


def render_inline(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r'`([^`]+)`', lambda m: f'<code>{m.group(1)}</code>', escaped)
    return escaped


def parse_source() -> tuple[list[dict], list[str]]:
    blocks: list[dict] = []
    formulas: list[str] = []
    lines = SRC.read_text(encoding='utf-8').splitlines()
    paragraph: list[str] = []
    i = 0

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            text = ' '.join(part.strip() for part in paragraph if part.strip())
            if text:
                blocks.append({'type': 'p', 'text': text})
            paragraph = []

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped == '$$':
            flush_paragraph()
            i += 1
            formula_lines = []
            while i < len(lines) and lines[i].strip() != '$$':
                formula_lines.append(lines[i])
                i += 1
            formula = '\n'.join(formula_lines).strip()
            blocks.append({'type': 'formula', 'index': len(formulas)})
            formulas.append(formula)
        elif stripped.startswith('### '):
            flush_paragraph()
            blocks.append({'type': 'h3', 'text': stripped[4:]})
        elif stripped.startswith('## '):
            flush_paragraph()
            blocks.append({'type': 'h2', 'text': stripped[3:]})
        elif stripped.startswith('# '):
            flush_paragraph()
            blocks.append({'type': 'h1', 'text': stripped[2:]})
        elif not stripped:
            flush_paragraph()
        else:
            paragraph.append(line)
        i += 1
    flush_paragraph()
    return blocks, formulas


def render_formulas(formulas: list[str]) -> list[str]:
    proc = subprocess.run(
        ['node', str(RENDERER), str(KATEX_PACKAGE)],
        input=json.dumps(formulas, ensure_ascii=False),
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(proc.stdout)


def build_html(blocks: list[dict], rendered_formulas: list[str]) -> str:
    body: list[str] = []
    first_h1 = True
    for block in blocks:
        kind = block['type']
        if kind == 'h1':
            klass = 'doc-title' if first_h1 else 'section-title'
            body.append(f'<h1 class="{klass}">{render_inline(block["text"])}</h1>')
            first_h1 = False
        elif kind == 'h2':
            body.append(f'<h2>{render_inline(block["text"])}</h2>')
        elif kind == 'h3':
            body.append(f'<h3>{render_inline(block["text"])}</h3>')
        elif kind == 'p':
            text = block['text']
            css_class = 'note' if text.startswith('Что переписать в диссертации:') else ''
            class_attr = f' class="{css_class}"' if css_class else ''
            body.append(f'<p{class_attr}>{render_inline(text)}</p>')
        elif kind == 'formula':
            body.append(f'<div class="formula">{rendered_formulas[block["index"]]}</div>')
    return f'''<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <title>alg_pro</title>
</head>
<body>
  <article class="document">
    {''.join(body)}
  </article>
</body>
</html>
'''


def main() -> None:
    if not SRC.exists():
        raise SystemExit(f'Source file not found: {SRC}')
    if not KATEX_CSS.exists():
        raise SystemExit(f'KaTeX CSS not found: {KATEX_CSS}')

    blocks, formulas = parse_source()
    rendered_formulas = render_formulas(formulas)
    html_doc = build_html(blocks, rendered_formulas)

    css = CSS(string='''
        @page {
            size: A4;
            margin: 20mm 16mm 18mm 18mm;
            @bottom-center {
                content: counter(page);
                font-family: "Liberation Serif", "Times New Roman", serif;
                font-size: 10pt;
                color: #6b7280;
            }
        }
        body {
            font-family: "Liberation Serif", "Times New Roman", serif;
            font-size: 11.5pt;
            line-height: 1.45;
            color: #17202a;
        }
        .document {
            max-width: 100%;
        }
        .doc-title {
            text-align: center;
            font-size: 19pt;
            margin: 0 0 10mm;
            font-weight: 700;
        }
        h2 {
            font-size: 15pt;
            margin: 10mm 0 4mm;
            padding-bottom: 1.4mm;
            border-bottom: 0.4pt solid #cbd5e1;
            page-break-after: avoid;
        }
        h3 {
            font-size: 12.8pt;
            margin: 5mm 0 2.5mm;
            font-weight: 700;
            page-break-after: avoid;
        }
        p {
            margin: 0 0 3.2mm;
            text-align: justify;
            orphans: 3;
            widows: 3;
        }
        p.note {
            padding-left: 3mm;
            border-left: 1.5pt solid #94a3b8;
            color: #334155;
        }
        .formula {
            margin: 3.5mm 0 4.5mm;
            text-align: center;
            page-break-inside: avoid;
        }
        .formula .katex-display {
            margin: 0;
        }
        code {
            font-family: "DejaVu Sans Mono", "Liberation Mono", monospace;
            font-size: 0.92em;
            background: #f3f4f6;
            padding: 0.1em 0.32em;
            border-radius: 3px;
        }
    ''' )

    HTML(string=html_doc, base_url=str(RESEARCH_DIR)).write_pdf(
        str(OUT),
        stylesheets=[CSS(filename=str(KATEX_CSS)), css],
    )
    shutil.copy2(OUT, ROOT_OUT)
    print(f'Written {OUT}')
    print(f'Written {ROOT_OUT}')


if __name__ == '__main__':
    main()
