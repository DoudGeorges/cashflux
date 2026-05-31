"""Repair static/script.js after em-dash bulk replace broke closing tags."""
from pathlib import Path

path = Path(__file__).resolve().parent.parent / "static" / "script.js"
text = path.read_text(encoding="utf-8")

text = text.replace("??/", "</")
text = text.replace(
    "No matches for ??{escapeHtml(query.trim())}</div>",
    'No matches for "${escapeHtml(query.trim())}"</div>',
)
text = text.replace(
    "Try a suggestion below, or ask a follow-up like ??How does that compare to Engineering?</div>",
    'Try a suggestion below, or ask a follow-up like "How does that compare to Engineering?"</div>',
)
text = text.replace("Hi ??I&apos;m Friday", "Hi, I&apos;m Friday")

path.write_text(text, encoding="utf-8")
print(f"Repaired {path}")
