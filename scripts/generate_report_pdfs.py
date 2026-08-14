#!/usr/bin/env python3
"""
Generate PDFs from GSIP report Markdown files.

Usage:
  pip install markdown fpdf2
  python scripts/generate_report_pdfs.py

Output:
  docs/reports/GSIP_Technical_Report.pdf
  docs/reports/GSIP_Business_Report.pdf
  docs/reports/GSIP_Questions.pdf

Optional: pip install weasyprint for HTML-based PDFs (may need GTK on Windows).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# Project root
ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = ROOT / "docs" / "reports"


def ensure_reports_dir() -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    return REPORTS_DIR


def read_md(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def md_to_blocks(md: str) -> list[tuple[str, str]]:
    """Parse markdown into (block_type, content) list. block_type: h1, h2, h3, h4, p, code."""
    blocks: list[tuple[str, str]] = []
    lines = md.replace("\r\n", "\n").split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        if line.startswith("# "):
            blocks.append(("h1", stripped[2:].strip()))
            i += 1
            continue
        if line.startswith("## "):
            blocks.append(("h2", stripped[3:].strip()))
            i += 1
            continue
        if line.startswith("### "):
            blocks.append(("h3", stripped[4:].strip()))
            i += 1
            continue
        if line.startswith("#### "):
            blocks.append(("h4", stripped[5:].strip()))
            i += 1
            continue
        if stripped.startswith("```"):
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            if i < len(lines):
                i += 1
            blocks.append(("code", "\n".join(code_lines)))
            continue
        # Paragraph: collect until blank or next header/code
        para_lines = [stripped]
        i += 1
        while i < len(lines):
            next_line = lines[i]
            if not next_line.strip():
                i += 1
                break
            if next_line.startswith("#") or next_line.strip().startswith("```"):
                break
            para_lines.append(next_line.strip())
            i += 1
        blocks.append(("p", " ".join(para_lines)))
    return blocks


def strip_md_inline(text: str) -> str:
    """Remove markdown bold/italic/code from text for plain PDF."""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)
    return text


def _ascii_safe(s: str) -> str:
    """Replace non-ASCII chars so Helvetica works."""
    return "".join(c if ord(c) < 128 else " " for c in s)


def write_pdf_fpdf2(blocks: list[tuple[str, str]], out_path: Path, title: str) -> None:
    try:
        from fpdf import FPDF
    except ImportError:
        print("Install fpdf2: pip install fpdf2")
        raise

    class PDF(FPDF):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.set_auto_page_break(auto=True, margin=20)

        def header(self):
            self.set_font("Helvetica", "", 8)
            self.set_text_color(128, 128, 128)
            self.cell(0, 8, f"GSIP Report - {title}", align="C")
            self.ln(10)

        def footer(self):
            self.set_y(-15)
            self.set_font("Helvetica", "", 8)
            self.set_text_color(128, 128, 128)
            self.cell(0, 10, f"Page {self.page_no()}", align="C")

    pdf = PDF()
    pdf.set_margins(20, 25, 20)
    pdf.add_page()
    pdf.set_auto_page_break(True, margin=25)
    cw = 170  # cell width (mm) for multi_cell to avoid layout issues

    for block_type, content in blocks:
        content = strip_md_inline(content)
        if not content and block_type != "code":
            continue
        if block_type == "h1":
            pdf.ln(6)
            pdf.set_font("Helvetica", "B", 16)
            pdf.set_text_color(0, 0, 0)
            pdf.multi_cell(cw, 8, _ascii_safe(content[:200]))
            pdf.ln(2)
        elif block_type == "h2":
            pdf.ln(4)
            pdf.set_font("Helvetica", "B", 14)
            pdf.set_text_color(0, 0, 0)
            pdf.multi_cell(cw, 7, _ascii_safe(content[:200]))
            pdf.ln(2)
        elif block_type == "h3":
            pdf.ln(3)
            pdf.set_font("Helvetica", "B", 12)
            pdf.set_text_color(0, 0, 0)
            pdf.multi_cell(cw, 6, _ascii_safe(content[:200]))
            pdf.ln(1)
        elif block_type == "h4":
            pdf.ln(2)
            pdf.set_font("Helvetica", "B", 11)
            pdf.set_text_color(0, 0, 0)
            pdf.multi_cell(cw, 6, _ascii_safe(content[:200]))
            pdf.ln(1)
        elif block_type == "code":
            pdf.set_font("Courier", "", 8)
            pdf.set_text_color(60, 60, 60)
            for code_line in content.split("\n")[:40]:  # limit code block size
                safe_line = _ascii_safe(code_line[:100]).strip()
                if safe_line:
                    pdf.multi_cell(cw, 5, safe_line)
            pdf.ln(2)
        else:  # p
            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(0, 0, 0)
            content = _ascii_safe(content)
            # Truncate very long words to avoid "not enough horizontal space"
            words = []
            for w in content.replace("\n", " ").split():
                words.append(w[:80] if len(w) > 80 else w)
            line = []
            length = 0
            for w in words:
                if length + len(w) + 1 > 90:
                    if line:
                        pdf.multi_cell(cw, 5, " ".join(line))
                    line = [w]
                    length = len(w)
                else:
                    line.append(w)
                    length += len(w) + 1
            if line:
                txt = " ".join(line)
                pdf.multi_cell(cw, 5, txt)
            pdf.ln(2)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(out_path))
    print(f"Wrote: {out_path}")


def main() -> int:
    ensure_reports_dir()

    reports = [
        ("GSIP_Technical_Report.md", "GSIP_Technical_Report.pdf", "Technical Report"),
        ("GSIP_Business_Report.md", "GSIP_Business_Report.pdf", "Business Report"),
        ("GSIP_Questions.md", "GSIP_Questions.pdf", "Questions"),
    ]

    for md_name, pdf_name, title in reports:
        md_path = REPORTS_DIR / md_name
        if not md_path.exists():
            print(f"Skip (not found): {md_path}")
            continue
        md_content = read_md(md_path)
        blocks = md_to_blocks(md_content)
        pdf_path = REPORTS_DIR / pdf_name
        write_pdf_fpdf2(blocks, pdf_path, title)

    print("Done. PDFs are in docs/reports/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
