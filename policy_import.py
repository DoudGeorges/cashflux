"""Import expense policy from a PDF (or text) via Gemini — digitize rules automatically."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from policy_engine import (
    DEFAULT_RULES,
    DEPT_OVERRIDE_FIELDS,
    POLICY_SCHEMA,
    list_policy_departments,
    load_policy_rules,
    normalize_rules,
    save_policy_document,
    save_policy_rules,
)


def _gemini_api_key() -> str | None:
    from dotenv import load_dotenv

    load_dotenv()
    key = os.getenv("API") or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    return key.strip() if key else None


def _safe_json(text: str) -> dict:
    if not text:
        return {}
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            return json.loads(match.group(0))
        raise


def _schema_prompt_block() -> str:
    lines = ["Rule fields to extract (use numbers in CAD unless document says otherwise):"]
    for field in POLICY_SCHEMA:
        hint = field.get("help") or field.get("label")
        if field["type"] == "boolean":
            lines.append(f'- {field["key"]} (boolean): {hint}')
        elif field["type"] == "keywords":
            lines.append(f'- {field["key"]} (string array, lowercase): {hint}')
        elif field["type"] == "numbers":
            lines.append(f'- {field["key"]} (integer array): {hint}')
        else:
            unit = field.get("unit") or ""
            lines.append(f'- {field["key"]} (number{", " + unit if unit else ""}): {hint}')

    dept_fields = ", ".join(f["key"] for f in DEPT_OVERRIDE_FIELDS)
    lines.append(
        f"- department_overrides (object): keys are department names; values may include {dept_fields}"
    )
    lines.append(
        "- role_overrides (object): keys are role names (Director, Manager, Staff); "
        "values may include manager_approval_threshold, pre_auth_threshold"
    )
    return "\n".join(lines)


def _build_import_prompt(departments: list[str]) -> str:
    dept_list = ", ".join(departments) if departments else "(none listed — only add overrides explicitly named in the PDF)"
    defaults = {k: v for k, v in DEFAULT_RULES.items() if k not in ("department_overrides", "role_overrides")}
    return f"""You are digitizing a company expense policy for an automated compliance engine.

Read the attached policy document and extract enforceable rules into JSON.

Company departments in the system: {dept_list}

{_schema_prompt_block()}

Instructions:
- Map policy language to the closest matching rule keys (e.g. "$50 pre-authorization" → pre_auth_threshold: 50).
- Split-purchase / threshold-evasion: if the policy mentions splitting charges to avoid approval limits, set split_purchase_min_charges and split_purchase_window_hours appropriately (defaults: 2 charges within 48 hours).
- Meals: distinguish solo vs team/client meals; extract tip limits (meal vs service/porterage).
- Keywords: infer alcohol, team meal, customer, personal, and prohibited expense keywords from the document text.
- restricted_merchants: vendor names explicitly banned or restricted.
- department_overrides: ONLY for departments explicitly given different limits in the PDF. Use exact department names from the list when they match.
- role_overrides: only if the PDF defines different limits by job level.
- document_markdown: a clean Markdown summary of the full policy (headings + bullets) suitable for finance managers — include all material rules, not just the JSON fields.
- import_notes: 3–8 short bullets explaining key extractions or reasonable assumptions you made.
- If a value is not mentioned, omit that key (defaults apply): {json.dumps(defaults, indent=2)}

Return ONLY valid JSON with this shape:
{{
  "rules": {{ ... }},
  "document_markdown": "...",
  "import_notes": ["...", "..."]
}}"""


def extract_policy_from_document(file_bytes: bytes, mime_type: str) -> dict[str, Any]:
    from google import genai
    from google.genai import types

    api_key = _gemini_api_key()
    if not api_key:
        return {"error": "Gemini API key not configured (set API or GEMINI_API_KEY in .env)"}

    if mime_type == "application/pdf":
        media_part = types.Part.from_bytes(data=file_bytes, mime_type=mime_type)
    elif mime_type.startswith("text/") or mime_type in ("application/json",):
        try:
            text = file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            text = file_bytes.decode("latin-1", errors="replace")
        media_part = types.Part.from_text(text=f"Policy document text:\n\n{text}")
    else:
        return {"error": "Unsupported file type — upload a PDF or text policy document"}

    departments = list_policy_departments()
    prompt = _build_import_prompt(departments)

    client = genai.Client(api_key=api_key)
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Content(
                    role="user",
                    parts=[media_part, types.Part.from_text(text=prompt)],
                )
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
            ),
        )
        payload = _safe_json(response.text or "")
    except Exception as exc:
        return {"error": f"Policy import failed: {exc}"}

    if not payload.get("rules"):
        return {"error": "Could not extract policy rules from the document. Try a clearer PDF or edit rules manually."}

    return payload


def _fmt_value(value) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, list):
        preview = ", ".join(str(v) for v in value[:6])
        if len(value) > 6:
            preview += "…"
        return preview or "—"
    if isinstance(value, dict):
        return f"{len(value)} entries"
    if isinstance(value, float) and value == int(value):
        return str(int(value))
    return str(value)


def summarize_rule_changes(before: dict, after: dict) -> list[str]:
    changes: list[str] = []
    skip = {"department_overrides", "role_overrides"}
    for key in sorted(set(before) | set(after)):
        if key in skip:
            continue
        old, new = before.get(key), after.get(key)
        if old != new:
            label = next((f["label"] for f in POLICY_SCHEMA if f["key"] == key), key)
            changes.append(f"{label}: {_fmt_value(old)} → {_fmt_value(new)}")

    old_depts = before.get("department_overrides") or {}
    new_depts = after.get("department_overrides") or {}
    for dept in sorted(set(old_depts) | set(new_depts)):
        if old_depts.get(dept) != new_depts.get(dept):
            if dept in new_depts and dept not in old_depts:
                changes.append(f"Department override added: {dept}")
            elif dept not in new_depts:
                changes.append(f"Department override removed: {dept}")
            else:
                changes.append(f"Department override updated: {dept}")

    old_roles = before.get("role_overrides") or {}
    new_roles = after.get("role_overrides") or {}
    for role in sorted(set(old_roles) | set(new_roles)):
        if old_roles.get(role) != new_roles.get(role):
            changes.append(f"Role override updated: {role}")

    return changes


def apply_imported_policy(extracted: dict) -> dict[str, Any]:
    """Persist rules + markdown document from Gemini extraction."""
    before = load_policy_rules()
    raw_rules = dict(extracted.get("rules") or {})

    normalized = normalize_rules(raw_rules)
    normalized["department_overrides"] = raw_rules.get("department_overrides") or {}
    normalized["role_overrides"] = raw_rules.get("role_overrides") or {}

    saved = save_policy_rules(normalized)

    doc = (extracted.get("document_markdown") or extracted.get("document") or "").strip()
    if doc:
        save_policy_document(doc)

    changes = summarize_rule_changes(before, saved)
    notes = list(extracted.get("import_notes") or [])
    if not notes and changes:
        notes = changes[:8]

    return {
        "rules": saved,
        "document": doc or None,
        "changes": changes,
        "import_notes": notes,
        "status": "imported",
    }
