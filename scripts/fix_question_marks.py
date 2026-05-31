"""Fix corrupted ? and replacement-char separators across UI copy."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EM = "\u2014"
MID = "\u00b7"


def read_text(path: Path) -> str:
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def write_utf8(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def fix_index(text: str) -> str:
    text = text.replace("\ufffd", MID)
    text = text.replace("\xb7", MID)  # lone middle-dot byte
    return text.replace(" ? ", f" {EM} ")


def fix_script(text: str) -> str:
    text = text.replace("\ufffd", MID)
    text = text.replace("\xb7", MID)
    text = text.replace(" � ", f" {MID} ")
    text = text.replace(" ? ${", f" {MID} ${{")

    pairs = [
        ("'Session expired ? please sign in again.'", f"'Session expired {EM} please sign in again.'"),
        ("'API not found ? restart the app with python app.py.'", f"'API not found {EM} restart the app with python app.py.'"),
        ("`${data.quarter} ? set how much", "`${data.quarter} " + EM + " set how much"),
        ("'Saved ? open Budgets to see updates'", f"'Saved {EM} open Budgets to see updates'"),
        ("'Reset to suggested ? click Save budgets to apply'", f"'Reset to suggested {EM} click Save budgets to apply'"),
        ("'Saved ? updating scans...'", f"'Saved {EM} updating scans...'"),
        ("Ready to import ? click Apply policy with Gemini", f"Ready to import {EM} click Apply policy with Gemini"),
        ("PDF, Markdown, or text ? max 15 MB", f"PDF, Markdown, or text {EM} max 15 MB"),
        ("? `Policy applied ? ${changeCount}", "? `Policy applied " + EM + " ${changeCount}"),
        ("'Policy applied ? review the rules below.'", f"'Policy applied {EM} review the rules below.'"),
        ("'No card transaction matched ? you can still save this receipt'", f"'No card transaction matched {EM} you can still save this receipt'"),
        ("<strong>Hi ? I&apos;m Friday.</strong>", f"<strong>Hi {EM} I&apos;m Friday.</strong>"),
        ("'No proposals yet ? submit one using the form.'", f"'No proposals yet {EM} submit one using the form.'"),
        ("'Submitted ? waiting for approval.'", f"'Submitted {EM} waiting for approval.'"),
        ("? `Budget projection ? ${fc.department}`", "? `Budget projection " + EM + " ${fc.department}`"),
        ("matched ? review the details below", f"matched {EM} review the details below"),
        ("Peer benchmark ? ${escapeHtml", "Peer benchmark " + EM + " ${escapeHtml"),
        ("'Your starting point ? explore spending", f"'Your starting point {EM} explore spending"),
        ("'Every card transaction ? search by person", f"'Every card transaction {EM} search by person"),
        ("'Upload a photo ? we extract details", f"'Upload a photo {EM} we extract details"),
        ("'Where purchases happened ? each dot is a merchant", f"'Where purchases happened {EM} each dot is a merchant"),
        ("'Trip expenses auto-grouped into reports ? ready for CFO sign-off.'", f"'Trip expenses auto-grouped into reports {EM} ready for CFO sign-off.'"),
        ("} ? open Review to approve", "} " + EM + " open Review to approve"),
        ("only ? full list uses", f"only {EM} full list uses"),
        ("removed ? sidebar + home actions", f"removed {EM} sidebar + home actions"),
        ("'Microphone blocked ? allow access in browser settings.'", f"'Microphone blocked {EM} allow access in browser settings.'"),
        ("'Could not hear you ? try again.'", f"'Could not hear you {EM} try again.'"),
        ("join(' " + MID + " ')", f"join(' {MID} ')"),
        ("' " + MID + " 1 flagged'", f"' {MID} 1 flagged'"),
        ("` " + MID + " ${item.flagged} flagged`", f"` {MID} ${{item.flagged}} flagged`"),
    ]
    for old, new in pairs:
        if old in text:
            text = text.replace(old, new)
    return text


def main() -> None:
    index = ROOT / "templates" / "index.html"
    script = ROOT / "static" / "script.js"
    write_utf8(index, fix_index(read_text(index)))
    write_utf8(script, fix_script(read_text(script)))
    print("Fixed separator punctuation")


if __name__ == "__main__":
    main()
