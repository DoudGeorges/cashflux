"""Wire Brim Guardian agent into the Flask app using CSV data."""
from __future__ import annotations

import asyncio
import os
import sys
import types
from pathlib import Path

from paths import BRIM_CHARTS_DIR, BRIM_ROOT

CHARTS_DIR = BRIM_CHARTS_DIR

_agent = None
_available = None
_patched = False


def _configure_environment():
    os.environ.setdefault("GEMINI_API_KEY", os.getenv("API", os.getenv("GEMINI_API_KEY", "")))
    os.environ.setdefault("GEMINI_MODEL", os.getenv("GEMINI_MODEL", "gemini-2.0-flash"))
    os.environ["CHARTS_OUTPUT_DIR"] = str(CHARTS_DIR)
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)


def is_available() -> bool:
    global _available
    if _available is not None:
        return _available

    from company_data import get_company_paths

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("API")
    data_file = get_company_paths().scored_tx
    _available = bool(api_key) and data_file.is_file()
    return _available


def _patch_queries():
    global _patched
    if _patched:
        return

    import brim_csv_queries

    if str(BRIM_ROOT) not in sys.path:
        sys.path.insert(0, str(BRIM_ROOT))

    query_names = (
        "get_spending_by_department",
        "get_top_vendors",
        "get_employee_credit_score",
        "get_flags_for_employee",
        "get_department_budget",
        "get_monthly_trend",
        "get_transactions_by_location",
        "get_spending_by_country",
        "get_db",
    )

    queries_mod = types.ModuleType("db.queries")
    for name in query_names:
        setattr(queries_mod, name, getattr(brim_csv_queries, name))
    sys.modules["db.queries"] = queries_mod

    async def _close_client():
        return None

    connection_mod = types.ModuleType("db.connection")
    connection_mod.get_db = brim_csv_queries.get_db
    connection_mod.close_client = _close_client
    sys.modules["db.connection"] = connection_mod

    narrator_mod = types.ModuleType("voice.narrator")
    narrator_mod.narrate = lambda text, voice_id=None: None
    sys.modules["voice"] = types.ModuleType("voice")
    sys.modules["voice.narrator"] = narrator_mod

    _patched = True


def get_agent():
    global _agent
    if _agent is not None:
        return _agent

    if not is_available():
        raise RuntimeError("Brim Guardian is not available (missing API key or scored CSV data).")

    _configure_environment()
    _patch_queries()

    from agent.core import BrimAgent

    try:
        from charts import generator as chart_gen

        chart_gen.OUTPUT_DIR = os.environ["CHARTS_OUTPUT_DIR"]
        os.makedirs(chart_gen.OUTPUT_DIR, exist_ok=True)
    except ImportError:
        pass

    _agent = BrimAgent()
    return _agent


def run_chat(message: str, history: list[dict] | None = None, narrate: bool = False) -> dict:
    agent = get_agent()
    if history is not None:
        agent._history = []
        for msg in history:
            role = msg.get("role", "user")
            gemini_role = "user" if role == "user" else "model"
            agent._history.append({"role": gemini_role, "parts": [msg.get("text", "")]})
    return asyncio.run(agent.chat(message, narrate=narrate))


def reset_chat():
    if _agent is not None:
        _agent.reset()


def chart_filename(chart_path: str) -> str:
    return Path(chart_path).name


def chart_file_path(filename: str) -> Path:
    safe = Path(filename).name
    candidates = [
        CHARTS_DIR / safe,
        Path.cwd() / "charts" / "output" / safe,
    ]
    for path in candidates:
        if path.is_file():
            return path
    return candidates[0]
