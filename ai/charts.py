"""Render inline chat insight charts as PNG for reliable display in Friday chat."""

from __future__ import annotations

import uuid
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
from matplotlib.figure import Figure

from core.paths import ROOT

CHAT_CHARTS_DIR = ROOT / "data" / "chat_charts"
CHAT_CHARTS_DIR.mkdir(parents=True, exist_ok=True)


def _save(fig: Figure) -> Path:
    path = CHAT_CHARTS_DIR / f"{uuid.uuid4().hex}.png"
    fig.savefig(path, bbox_inches="tight", dpi=150, facecolor="white")
    plt.close(fig)
    return path


def render_insight_chart(insight: dict) -> Path | None:
    chart = insight.get("chart") if insight else None
    if not chart:
        return None

    labels = chart.get("labels") or []
    values = chart.get("values") or []
    if not labels or not values:
        return None

    title = insight.get("title") or "Spending chart"
    chart_type = chart.get("type") or "bar"

    fig, ax = plt.subplots(figsize=(10, 5))
    if chart_type == "line":
        ax.plot(labels, values, marker="o", color="#2563eb", linewidth=2)
        ax.fill_between(range(len(values)), values, alpha=0.08, color="#2563eb")
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=25, ha="right")
    else:
        colors = chart.get("colors") or ["#2563eb"] * len(labels)
        if isinstance(colors, str):
            colors = [colors] * len(labels)
        bars = ax.bar(
            labels,
            values,
            color=colors[: len(labels)],
            edgecolor="white",
            linewidth=0.5,
        )
        ax.bar_label(bars, fmt="CA$%.0f", padding=4, fontsize=9)

    ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: f"CA${x:,.0f}"))
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    plt.tight_layout()
    return _save(fig)


def insight_chart_url(insight: dict) -> str | None:
    path = render_insight_chart(insight)
    if not path:
        return None
    return f"/api/chat/chart/{path.name}"


def chat_chart_path(filename: str) -> Path:
    safe = Path(filename).name
    return CHAT_CHARTS_DIR / safe

