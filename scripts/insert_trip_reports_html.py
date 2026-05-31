"""Insert employee trip reports section into index.html."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "templates" / "index.html"

BLOCK = """
                <div id="insight-trip-reports" class="insight-view">
                    <p class="page-help">Select the card purchases from a business trip, add a short description, and submit for finance review. Approved reports appear in the admin <strong>Review</strong> queue.</p>
                    <div class="proposal-layout trip-report-layout">
                        <div class="panel-card proposal-form-card">
                            <h3 class="panel-title">New trip report</h3>
                            <p class="panel-subtitle" id="trip-report-txn-hint">Loading your eligible purchases…</p>
                            <form id="trip-report-form" class="proposal-form">
                                <label class="proposal-field">
                                    <span>Trip name</span>
                                    <input type="text" id="trip-report-name" maxlength="200" placeholder="e.g. Q2 Toronto client visit" required>
                                </label>
                                <label class="proposal-field">
                                    <span>Purpose &amp; justification</span>
                                    <textarea id="trip-report-purpose" rows="4" placeholder="Who did you meet, what was the business purpose, and why should these expenses be reimbursed?" required></textarea>
                                </label>
                                <fieldset class="proposal-field trip-report-txn-field">
                                    <legend>Purchases on this trip</legend>
                                    <p class="proposal-colleagues-help">Check every purchase that belongs to the same trip. Purchases already on another report are hidden.</p>
                                    <p class="trip-report-txn-total" id="trip-report-txn-total" hidden></p>
                                    <div id="trip-report-txn-list" class="trip-txn-list">
                                        <div class="guardian-item">Loading purchases…</div>
                                    </div>
                                </fieldset>
                                <footer class="proposal-form-footer">
                                    <span class="proposal-form-status" id="trip-report-form-status"></span>
                                    <button type="submit" class="btn-sm btn-dark" id="trip-report-submit-btn">Submit trip report</button>
                                </footer>
                            </form>
                        </div>
                        <div class="panel-card proposal-history-card">
                            <h3 class="panel-title">Your trip reports</h3>
                            <p class="panel-subtitle">Track pending and past decisions</p>
                            <div id="trip-report-list" class="proposal-list">
                                <div class="guardian-item">Loading…</div>
                            </div>
                        </div>
                    </div>
                </div>

"""

MARKER = '<div id="insight-reports" class="insight-view">'
text = INDEX.read_text(encoding="utf-8")
if "insight-trip-reports" in text:
    print("Already present")
elif MARKER not in text:
    raise SystemExit("Marker not found")
else:
    INDEX.write_text(text.replace(MARKER, BLOCK + MARKER, 1), encoding="utf-8")
    print("Inserted trip reports section")
