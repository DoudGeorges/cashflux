"""Replace corrupted middle-dot placeholders (?) with proper · separators."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MID = "\u00b7"  # ·
EM = "\u2014"  # —


def fix_script(text: str) -> str:
    text = text.replace(" ? ${", f" {MID} ${{")
    text = text.replace(f".toFixed(1)}} ? CA$", f".toFixed(1)}} {MID} CA$")
    text = text.replace("} ? set how much", f"}} {EM} set how much")
    text = text.replace("text ? max 15 MB", f"text {EM} max 15 MB")
    text = text.replace("PDF ? ${formatFileSize", f"PDF {MID} ${{formatFileSize")
    text = text.replace("Image ? ${formatFileSize", f"Image {MID} ${{formatFileSize")
    text = text.replace("projection ? ${fc.department}", f"projection {EM} ${{fc.department}}")
    text = text.replace("Meal ? party of", f"Meal {MID} party of")
    text = text.replace(" ? with ${", f" {MID} with ${{")
    text = text.replace("' ? 1 flagged'", f"' {MID} 1 flagged'")
    text = text.replace(" ? Score <strong", f" {MID} Score <strong")
    text = text.replace(" ? Credit score ", f" {MID} Credit score ")
    text = text.replace(" spent ? ${escapeHtml(p.remaining", f" spent {MID} ${{escapeHtml(p.remaining")
    text = text.replace("transaction ? ${escapeHtml(matched", f"transaction {MID} ${{escapeHtml(matched")
    text = text.replace("transactions ? ${escapeHtml(r.date_range", f"transactions {MID} ${{escapeHtml(r.date_range")
    text = text.replace("merchants ? ${loc.transactions}", f"merchants {MID} ${{loc.transactions}}")
    text = text.replace("in view ? ${data.total_in_view}", f"in view {MID} ${{data.total_in_view}}")
    text = text.replace("areas ? ${data.mapped_spend_fmt}", f"areas {MID} ${{data.mapped_spend_fmt}}")
    text = text.replace(" ? Using saved ", f" {MID} Using saved ")
    text = text.replace("restaurant / caf?", "restaurant / café")
    return text


def fix_html(text: str) -> str:
    text = text.replace("on track ? <span", f"on track {MID} <span")
    text = text.replace("closely ? <span", f"closely {MID} <span")
    text = text.replace("PDF ? max 10 MB", f"PDF {EM} max 10 MB")
    text = text.replace("PDF ? max 15 MB", f"PDF {EM} max 15 MB")
    text = text.replace("PNG, JPG, or PDF ? max 10 MB", f"PNG, JPG, or PDF {EM} max 10 MB")
    text = text.replace("restaurant / caf?", "restaurant / café")
    return text


def main() -> None:
    script = ROOT / "static" / "script.js"
    index = ROOT / "templates" / "index.html"
    script.write_text(fix_script(script.read_text(encoding="utf-8")), encoding="utf-8")
    index.write_text(fix_html(index.read_text(encoding="utf-8")), encoding="utf-8")
    print("Fixed middle-dot separators")


if __name__ == "__main__":
    main()
