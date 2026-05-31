"""Fix broken JavaScript string literals after em-dash bulk replace."""
from pathlib import Path

path = Path(__file__).resolve().parent.parent / "static" / "script.js"
text = path.read_text(encoding="utf-8")

FIXES = [
    ("'Saving??;", "'Saving...';"),
    ("'Saved ??updating scans??;", "'Saved. Updating scans...';"),
    ("'Gemini is reading your policy??;", "'Gemini is reading your policy...';"),
    ("return '??;", "return '...';"),
    ("'Analyzing receipt??;", "'Analyzing receipt...';"),
    ("'Loading Guardian employee data??;", "'Loading Guardian employee data...';"),
    ("'Loading purchases in this area??;", "'Loading purchases in this area...';"),
    ("'Reset to suggested ??click Save budgets to apply'", "'Reset to suggested. Click Save budgets to apply'"),
    ("'Saved ??open Budgets to see updates'", "'Saved. Open Budgets to see updates'"),
    ("'Session expired ??please sign in again.'", "'Session expired. Please sign in again.'"),
    ("'API not found ??restart the app with python app.py.'", "'API not found. Restart the app with python app.py.'"),
    ("'Ready to import ??click Apply policy with Gemini'", "'Ready to import. Click Apply policy with Gemini'"),
    ("? `Policy applied ??${changeCount}", "? `Policy applied. ${changeCount}"),
    ("'Policy applied ??review the rules below.'", "'Policy applied. Review the rules below.'"),
    ("'No card transaction matched ??you can still save this receipt'", "'No card transaction matched. You can still save this receipt'"),
    ("'Submitted ??waiting for approval.'", "'Submitted. Waiting for approval.'"),
    ("`${short.slice(0, 69)}??", "`${short.slice(0, 69)}..."),
    ("'No card transaction matched ??review the details below and save if they look correct'", "'No card transaction matched. Review the details below and save if they look correct'"),
    ("updateVoiceUiState('Thinking??);", "updateVoiceUiState('Thinking...');"),
    ("updateVoiceUiState('Listening??);", "updateVoiceUiState('Listening...');"),
    ("'Microphone blocked ??allow access in browser settings.'", "'Microphone blocked. Allow access in browser settings.'"),
    ("'Could not hear you ??try again.'", "'Could not hear you. Try again.'"),
    ("`??The Spending Oracle reveals", "`. The Spending Oracle reveals"),
    ("'Your starting point ??explore spending", "'Your starting point. Explore spending"),
    ("'Every card transaction ??search by person", "'Every card transaction. Search by person"),
    ("'Upload a photo ??we extract details", "'Upload a photo. We extract details"),
    ("'Where purchases happened ??each dot is a merchant", "'Where purchases happened. Each dot is a merchant"),
    ("'Trip expenses auto-grouped into reports ??ready for CFO sign-off.'", "'Trip expenses auto-grouped into reports, ready for CFO sign-off.'"),
    ("??open Review to approve or deny with AI recommendations.`", ". Open Review to approve or deny with AI recommendations.`"),
    ("loc.employees.length > 4 ? '?? : ''}", "loc.employees.length > 4 ? '...' : ''}"),
    ("'No proposals yet ??submit one using the form.'", "'No proposals yet. Submit one using the form.'"),
    ("|| '??)}", "|| 'N/A')}"),
    ("Peer benchmark ??${escapeHtml", "Peer benchmark, ${escapeHtml"),
    ("??? to navigate ? <kbd>A</kbd>", "Arrow keys to navigate, <kbd>A</kbd>"),
    ("${escapeHtml(p.requested_amount_fmt)} ? ${escapeHtml", "${escapeHtml(p.requested_amount_fmt)} · ${escapeHtml"),
    ("${e.employee_id} ? ${escapeHtml", "${e.employee_id} · ${escapeHtml"),
    ("${data.employee_id} ? ${escapeHtml", "${data.employee_id} · ${escapeHtml"),
]

for old, new in FIXES:
    count = text.count(old)
    if count:
        text = text.replace(old, new)
        print(f"fixed {count}x: {old[:55]!r}")

path.write_text(text, encoding="utf-8")
print("done")
