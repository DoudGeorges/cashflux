content = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Fraud Hunter</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: system-ui, sans-serif; background: #0f1117; color: #e2e8f0; height: 100vh; display: flex; flex-direction: column; }
header { background: #1a1d2e; padding: 12px 24px; display: flex; align-items: center; gap: 24px; border-bottom: 1px solid #2d3148; }
header h1 { font-size: 18px; font-weight: 700; color: #f87171; }
.stats { display: flex; gap: 16px; font-size: 13px; }
.stat { background: #252840; padding: 4px 12px; border-radius: 6px; }
.stat span { font-weight: 700; color: #60a5fa; }
.threshold-bar { display: flex; align-items: center; gap: 10px; margin-left: auto; font-size: 13px; }
input[type=range] { width: 120px; accent-color: #f87171; }
main { display: flex; flex: 1; overflow: hidden; }
#queue { width: 340px; border-right: 1px solid #2d3148; overflow-y: auto; background: #13151f; }
.queue-item { padding: 14px 16px; border-bottom: 1px solid #1e2133; cursor: pointer; transition: background 0.15s; }
.queue-item:hover, .queue-item.active { background: #1e2133; }
.queue-item .score { float: right; font-weight: 700; font-size: 13px; }
.queue-item .tid { font-size: 11px; color: #64748b; margin-top: 2px; }
.queue-item .merchant { font-size: 14px; font-weight: 600; }
.queue-item .amount { color: #f87171; font-weight: 600; }
.badge { display: inline-block; font-size: 10px; padding: 2px 6px; border-radius: 4px; margin-top: 4px; }
.badge.pending { background: #1e3a5f; color: #60a5fa; }
.badge.approved { background: #14532d; color: #4ade80; }
.badge.dismissed { background: #1c1917; color: #a8a29e; }
.badge.escalated { background: #4c1d1d; color: #f87171; }
.score-high { color: #f87171; }
.score-med { color: #fb923c; }
.score-low { color: #facc15; }
#detail { flex: 1; padding: 32px; overflow-y: auto; }
#detail h2 { font-size: 22px; font-weight: 700; margin-bottom: 6px; }
.subtitle { color: #64748b; font-size: 14px; margin-bottom: 24px; }
.fields { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 16px; margin-bottom: 28px; }
.field { background: #1a1d2e; padding: 12px 16px; border-radius: 8px; }
.field label { font-size: 11px; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; display: block; margin-bottom: 4px; }
.explanation { background: #1a1d2e; border-left: 3px solid #f87171; padding: 14px 18px; border-radius: 0 8px 8px 0; margin-bottom: 28px; font-size: 14px; line-height: 1.6; }
.explanation strong { display: block; margin-bottom: 6px; color: #f87171; }
.actions { display: flex; gap: 12px; align-items: center; }
button { padding: 10px 24px; border-radius: 8px; border: none; font-size: 14px; font-weight: 600; cursor: pointer; transition: opacity 0.15s; }
button:hover { opacity: 0.85; }
#btn-approve { background: #16a34a; color: white; }
#btn-dismiss { background: #374151; color: #d1d5db; }
#btn-escalate { background: #dc2626; color: white; }
#btn-undo { background: #1e2133; color: #94a3b8; border: 1px solid #2d3148; }
.shortcut { font-size: 11px; color: #64748b; margin-top: 16px; }
.shortcut kbd { background: #1e2133; border: 1px solid #374151; border-radius: 4px; padding: 2px 6px; font-size: 11px; }
</style>
</head>
<body>
<header>
  <h1>Fraud Hunter</h1>
  <div class="stats" id="stats"></div>
  <div class="threshold-bar">
    <label>Sensitivity</label>
    <input type="range" id="threshold" min="0.1" max="0.9" step="0.05" value="0.4">
    <span id="threshold-val">0.40</span>
  </div>
</header>
<main>
  <div id="queue"></div>
  <div id="detail"><div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;color:#64748b;gap:8px"><h2 style="color:#e2e8f0">Select a transaction</h2><p>Click any flagged item to review it.</p></div></div>
</main>
<script>
let transactions = [];
let currentIdx = 0;
let currentId = null;

async function loadFlagged() {
  const res = await fetch('/api/flagged');
  transactions = await res.json();
  renderQueue();
  loadStats();
  if (transactions.length > 0) showTransaction(0);
}

async function loadStats() {
  const res = await fetch('/api/stats');
  const s = await res.json();
  document.getElementById('stats').innerHTML =
    '<div class="stat">Total <span>' + s.total + '</span></div>' +
    '<div class="stat">Flagged <span>' + s.flagged + '</span></div>' +
    '<div class="stat">Pending <span style="color:#60a5fa">' + s.pending + '</span></div>' +
    '<div class="stat">Escalated <span style="color:#f87171">' + s.escalated + '</span></div>' +
    '<div class="stat">Resolved <span style="color:#4ade80">' + (s.approved + s.dismissed) + '</span></div>';
}

function scoreColor(score) {
  if (score >= 0.6) return 'score-high';
  if (score >= 0.35) return 'score-med';
  return 'score-low';
}

function renderQueue() {
  document.getElementById('queue').innerHTML = transactions.map(function(t, i) {
    return '<div class="queue-item ' + (i === currentIdx ? 'active' : '') + '" onclick="showTransaction(' + i + ')">' +
      '<span class="score ' + scoreColor(t.fraud_score) + '">' + (t.fraud_score * 100).toFixed(0) + '%</span>' +
      '<div class="merchant">' + t.merchant_name + '</div>' +
      '<div class="amount">$' + t.amount.toFixed(2) + ' CAD</div>' +
      '<div class="tid">' + t.transaction_id + ' - ' + t.card_id + '</div>' +
      '<span class="badge ' + t.review_status + '">' + t.review_status + '</span>' +
      '</div>';
  }).join('');
}

function showTransaction(idx) {
  currentIdx = idx;
  const t = transactions[idx];
  currentId = t.transaction_id;
  renderQueue();
  const reasons = t.explanation.split(' | ').map(function(r) { return '<li>' + r + '</li>'; }).join('');
  document.getElementById('detail').innerHTML =
    '<h2>' + t.merchant_name + '</h2>' +
    '<div class="subtitle">' + t.transaction_id + ' - ' + t.timestamp + ' - <strong class="' + scoreColor(t.fraud_score) + '">Score: ' + (t.fraud_score * 100).toFixed(1) + '%</strong></div>' +
    '<div class="fields">' +
      '<div class="field"><label>Amount</label><div>$' + t.amount.toFixed(2) + ' CAD</div></div>' +
      '<div class="field"><label>Card</label><div>' + t.card_id + '</div></div>' +
      '<div class="field"><label>Category</label><div>' + t.merchant_category + '</div></div>' +
      '<div class="field"><label>Channel</label><div>' + t.channel + '</div></div>' +
      '<div class="field"><label>Card Country</label><div>' + t.cardholder_country + '</div></div>' +
      '<div class="field"><label>Merchant Country</label><div>' + t.merchant_country + '</div></div>' +
      '<div class="field"><label>Device</label><div>' + (t.device_id || '-') + '</div></div>' +
      '<div class="field"><label>IP</label><div>' + (t.ip_address || '-') + '</div></div>' +
      '<div class="field"><label>Status</label><div class="badge ' + t.review_status + '">' + t.review_status + '</div></div>' +
    '</div>' +
    '<div class="explanation"><strong>Why flagged:</strong><ul style="padding-left:18px">' + reasons + '</ul></div>' +
    '<div class="actions">' +
      '<button id="btn-approve" onclick="review(\\'approved\\')">Approve (A)</button>' +
      '<button id="btn-dismiss" onclick="review(\\'dismissed\\')">Dismiss (D)</button>' +
      '<button id="btn-escalate" onclick="review(\\'escalated\\')">Escalate (E)</button>' +
      '<button id="btn-undo" onclick="undo()">Undo (Z)</button>' +
      '<a href="/api/export" style="margin-left:auto;color:#64748b;font-size:13px">Export CSV</a>' +
    '</div>' +
    '<div class="shortcut">Keyboard: <kbd>A</kbd> Approve <kbd>D</kbd> Dismiss <kbd>E</kbd> Escalate <kbd>Z</kbd> Undo <kbd>Up/Down</kbd> Navigate</div>';
}

async function review(action) {
  await fetch('/api/review', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ transaction_id: currentId, action: action })
  });
  transactions[currentIdx].review_status = action;
  renderQueue();
  loadStats();
  const next = transactions.findIndex(function(t, i) { return i > currentIdx && t.review_status === 'pending'; });
  if (next !== -1) showTransaction(next); else showTransaction(currentIdx);
}

async function undo() {
  await fetch('/api/undo', { method: 'POST' });
  await loadFlagged();
}

document.addEventListener('keydown', function(e) {
  if (e.target.tagName === 'INPUT') return;
  if (e.key === 'a' || e.key === 'A') review('approved');
  if (e.key === 'd' || e.key === 'D') review('dismissed');
  if (e.key === 'e' || e.key === 'E') review('escalated');
  if (e.key === 'z' || e.key === 'Z') undo();
  if (e.key === 'ArrowDown') showTransaction(Math.min(currentIdx + 1, transactions.length - 1));
  if (e.key === 'ArrowUp') showTransaction(Math.max(currentIdx - 1, 0));
});

const slider = document.getElementById('threshold');
slider.addEventListener('input', function() { document.getElementById('threshold-val').textContent = parseFloat(slider.value).toFixed(2); });
slider.addEventListener('change', async function() {
  await fetch('/api/threshold', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ threshold: parseFloat(slider.value) }) });
  await loadFlagged();
});

loadFlagged();
</script>
</body>
</html>"""

with open('/mnt/c/Users/sorkw/projects/mpc-hacks/fraud-hunter/frontend/index.html', 'w') as f:
    f.write(content)
print("done")
