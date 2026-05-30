"""Chart generation — returns a file path to a saved PNG."""
import os
import uuid
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick

OUTPUT_DIR = os.getenv("CHARTS_OUTPUT_DIR", "./charts/output")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def _save(fig):
    path = os.path.join(OUTPUT_DIR, f"{uuid.uuid4().hex}.png")
    fig.savefig(path, bbox_inches="tight", dpi=150)
    plt.close(fig)
    return path


def bar_chart(labels, values, title="", xlabel="", ylabel="Amount (USD)", color="#4F8EF7"):
    fig, ax = plt.subplots(figsize=(10, 5))
    bars = ax.bar(labels, values, color=color, edgecolor="white", linewidth=0.5)
    ax.bar_label(bars, fmt="$%.0f", padding=4, fontsize=9)
    ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: f"${x:,.0f}"))
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    plt.xticks(rotation=25, ha="right")
    plt.tight_layout()
    return _save(fig)


def comparison_bar_chart(groups, series, title="", xlabel="", ylabel="Amount (USD)"):
    import numpy as np
    x = np.arange(len(groups))
    width = 0.8 / len(series)
    colors = ["#4F8EF7", "#F7874F", "#4FF78E", "#F74F8E"]

    fig, ax = plt.subplots(figsize=(11, 5))
    for i, (name, vals) in enumerate(series.items()):
        offset = (i - len(series) / 2 + 0.5) * width
        ax.bar(x + offset, vals, width, label=name, color=colors[i % len(colors)])

    ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda v, _: f"${v:,.0f}"))
    ax.set_xticks(x)
    ax.set_xticklabels(groups, rotation=20, ha="right")
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.legend()
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    plt.tight_layout()
    return _save(fig)


def line_chart(x_labels, series, title="", ylabel="Amount (USD)"):
    colors = ["#4F8EF7", "#F7874F", "#4FF78E", "#F74F8E"]
    fig, ax = plt.subplots(figsize=(11, 5))
    for i, (name, vals) in enumerate(series.items()):
        ax.plot(x_labels, vals, marker="o", label=name, color=colors[i % len(colors)], linewidth=2)
    ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda v, _: f"${v:,.0f}"))
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.set_ylabel(ylabel)
    ax.legend()
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    plt.xticks(rotation=20, ha="right")
    plt.tight_layout()
    return _save(fig)


def ranked_table_chart(rows, title="Top Vendors"):
    import pandas as pd
    df = pd.DataFrame(rows)
    if "total" in df.columns:
        df["total"] = df["total"].map("${:,.2f}".format)

    fig, ax = plt.subplots(figsize=(8, max(3, len(df) * 0.5 + 1)))
    ax.axis("off")
    table = ax.table(cellText=df.values, colLabels=df.columns, cellLoc="center", loc="center")
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1.2, 1.6)
    ax.set_title(title, fontsize=13, fontweight="bold", pad=10)
    plt.tight_layout()
    return _save(fig)
