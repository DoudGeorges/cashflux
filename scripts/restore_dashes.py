"""Restore em dashes in user-facing copy (replaces corrupted ?? placeholders)."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EM = "\u2014"  # —
MID = "\u00b7"  # ·


def restore_html(text: str) -> str:
    text = text.replace(" ?? ", f" {EM} ")
    text = re.sub(r" \?\?([A-Za-z\"'])", lambda m: f" {EM}{m.group(1)}", text)
    text = text.replace("Friday, your spending assistant", f"Friday {EM} your spending assistant")
    text = text.replace(
        "Follow up questions work too, for example",
        f"Follow-up questions work too {EM} for example",
    )
    text = text.replace(
        "Arrow keys navigate, A approve, D deny",
        f"\u2191\u2193 navigate {MID} A approve {MID} D deny",
    )
    return text


def restore_script(text: str) -> str:
    pairs = [
        ("only ??full list", f"only {EM} full list"),
        ("removed ??sidebar", f"removed {EM} sidebar"),
        ("Session expired. Please sign in again.", f"Session expired {EM} please sign in again."),
        ("API not found. Restart the app with python app.py.", f"API not found {EM} restart the app with python app.py."),
        ("Saved. Open Budgets to see updates", f"Saved {EM} open Budgets to see updates"),
        ("Reset to suggested. Click Save budgets to apply", f"Reset to suggested {EM} click Save budgets to apply"),
        ("Saved. Updating scans...", f"Saved {EM} updating scans..."),
        ("Ready to import. Click Apply policy with Gemini", f"Ready to import {EM} click Apply policy with Gemini"),
        ("? `Policy applied. ${changeCount}", "? `Policy applied " + EM + " ${changeCount}"),
        ("'Policy applied. Review the rules below.'", "'Policy applied " + EM + " review the rules below.'"),
        ("No card transaction matched. You can still save this receipt", f"No card transaction matched {EM} you can still save this receipt"),
        ("No card transaction matched. Review the details below and save if they look correct", f"No card transaction matched {EM} review the details below and save if they look correct"),
        ("Submitted. Waiting for approval.", f"Submitted {EM} waiting for approval."),
        ("No proposals yet. Submit one using the form.", f"No proposals yet {EM} submit one using the form."),
        ("Microphone blocked. Allow access in browser settings.", f"Microphone blocked {EM} allow access in browser settings."),
        ("Could not hear you. Try again.", f"Could not hear you {EM} try again."),
        ("Your starting point. Explore spending", f"Your starting point {EM} explore spending"),
        ("Every card transaction. Search by person", f"Every card transaction {EM} search by person"),
        ("Upload a photo. We extract details", f"Upload a photo {EM} we extract details"),
        ("Where purchases happened. Each dot is a merchant", f"Where purchases happened {EM} each dot is a merchant"),
        ("Trip expenses auto-grouped into reports, ready for CFO sign-off.", f"Trip expenses auto-grouped into reports {EM} ready for CFO sign-off."),
        ("} . Open Review to approve", "} " + EM + " open Review to approve"),
        ("Peer benchmark, ${escapeHtml", "Peer benchmark " + EM + " ${escapeHtml"),
        ("`. The Spending Oracle reveals", f"`{EM} The Spending Oracle reveals"),
        ("<strong>Hi, I&apos;m Friday.</strong>", f"<strong>Hi {EM} I&apos;m Friday.</strong>"),
        ("Arrow keys to navigate, <kbd>A</kbd> approve ? <kbd>D</kbd> deny", f"\u2191\u2193 to navigate {MID} <kbd>A</kbd> approve {MID} <kbd>D</kbd> deny"),
        ("parts.join(' ? ')", f"parts.join(' {MID} ')"),
        ("parts.filter(Boolean).join(' ? ')", f"parts.filter(Boolean).join(' {MID} ')"),
    ]
    for old, new in pairs:
        text = text.replace(old, new)
    return text


def main() -> None:
    index_path = ROOT / "templates" / "index.html"
    script_path = ROOT / "static" / "script.js"

    index_path.write_text(restore_html(index_path.read_text(encoding="utf-8")), encoding="utf-8")
    script_path.write_text(restore_script(script_path.read_text(encoding="utf-8")), encoding="utf-8")
    print("Restored em dashes in index.html and script.js")


if __name__ == "__main__":
    main()
