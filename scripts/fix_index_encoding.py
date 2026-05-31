"""Repair templates/index.html after PowerShell encoding corruption."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
path = ROOT / "templates" / "index.html"
raw = path.read_bytes()
text = raw.decode("latin-1")

text = text.replace("\x9c", '"')
text = text.replace("\x93", "-")
text = text.replace("\x91", "\u2191")

text = text.replace("??/", "</")
text = text.replace("???/", "</")

text = text.replace("?? autocomplete", '" autocomplete')
text = text.replace("policy??>", 'policy">')
text = text.replace("what to do??e.g.", "what to do, e.g.")

text = text.replace(
    """                    <div class="page-guide page-guide--compact" id="home-guide">
                        <div class="page-guide-icon"><i class="fa-solid fa-circle-info"></i></div>
                        <div class="page-guide-body">
                            {% if is_admin_view %}
                            <strong>Your finance cockpit</strong>
                            <p>Start with <strong>Friday</strong> to explore spending, then work through the <strong>Review queue</strong> for approvals. Red badges in the sidebar mean something needs a decision.</p>
                            {% else %}
                            <strong>Your spending hub</strong>
                            <p>See your purchases, upload receipts, and ask <strong>Friday</strong> questions like "How much did I spend on meals this month?"</p>
                            {% endif %}
                        </div>
                    </div>""",
    """                    {% if not is_admin_view %}
                    <div class="page-guide page-guide--compact" id="home-guide">
                        <div class="page-guide-icon"><i class="fa-solid fa-circle-info"></i></div>
                        <div class="page-guide-body">
                            <strong>Your spending hub</strong>
                            <p>See your purchases, upload receipts, and ask <strong>Friday</strong> questions like "How much did I spend on meals this month?"</p>
                        </div>
                    </div>
                    {% endif %}""",
)

text = re.sub(
    r"\s*{% if is_admin_view %}\s*<div class=\"ux-workflow panel-card\">.*?</div>\s*{% endif %}\s*",
    "\n",
    text,
    count=1,
    flags=re.DOTALL,
)

text = text.replace(
    'Follow-up questions work ?"How does that compare to Engineering?"</p>',
    'Follow-up questions work too, for example "How does that compare to Engineering?"</p>',
)
text = text.replace("Friday ??your spending assistant", "Friday, your spending assistant")

text = re.sub(
    r'<span class="review-howto-keys">.*?</span>',
    '<span class="review-howto-keys">Arrow keys navigate, A approve, D deny</span>',
    text,
    count=1,
)

path.write_text(text, encoding="utf-8")
path.read_text(encoding="utf-8")
print(f"Repaired {path} ({len(text)} chars), valid UTF-8")
