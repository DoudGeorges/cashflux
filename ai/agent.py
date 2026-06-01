"""Friday agent: Gemini tool loop for spending Q&A and app actions."""

from __future__ import annotations

from google import genai
from google.genai import types

from ai.tools import FridayContext, dispatch_tool, tool_declarations

MAX_TOOL_ROUNDS = 8


def _build_gemini_tools() -> list[types.Tool]:
    decls = [
        types.FunctionDeclaration(
            name=d["name"],
            description=d["description"],
            parameters_json_schema=d["parameters"],
        )
        for d in tool_declarations()
    ]
    return [types.Tool(function_declarations=decls)]


def run_friday_chat(
    client: genai.Client,
    *,
    history: list[dict],
    system_prompt: str,
    ctx: FridayContext,
    model: str = "gemini-2.5-flash",
) -> dict:
    """
    Run Gemini with tools until a final text reply.
    Returns {reply, tool_calls, actions, engine}.
    """
    contents = list(history)
    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        tools=_build_gemini_tools(),
    )

    tool_calls: list[str] = []
    reply = ""

    for _ in range(MAX_TOOL_ROUNDS):
        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=config,
        )

        if not response.function_calls:
            reply = (response.text or "").strip()
            break

        model_content = response.candidates[0].content if response.candidates else None
        if model_content:
            contents.append(model_content)

        result_parts: list[types.Part] = []
        for fc in response.function_calls:
            tool_calls.append(fc.name)
            try:
                args = dict(fc.args) if fc.args else {}
            except (TypeError, ValueError):
                args = {}
            result = dispatch_tool(ctx, fc.name, args)
            result_parts.append(
                types.Part(
                    function_response=types.FunctionResponse(
                        name=fc.name,
                        response=result,
                    )
                )
            )

        contents.append(types.Content(role="user", parts=result_parts))
    else:
        reply = (
            reply
            or "I completed the requested actions. Let me know if you need anything else."
        )

    return {
        "reply": reply,
        "tool_calls": tool_calls + ctx.tool_calls,
        "actions": ctx.actions,
        "engine": "friday-agent",
    }
