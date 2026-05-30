"""
BrimAgent — Gemini-powered agentic chat loop.

Multi-turn: history is kept so follow-up questions like
"how does that compare to Engineering?" work without re-explaining.
Tool loop: Gemini calls tools in sequence until it has enough data to answer.
"""
import json
import os
from typing import Any

import google.generativeai as genai
from google.generativeai.types import FunctionDeclaration, Tool

from agent.tools import TOOL_DECLARATIONS, dispatch
from voice.narrator import narrate as tts_narrate


SYSTEM_PROMPT = """
You are Brim Guardian — an intelligent financial watchdog for a 50-person company.
You have real-time tools to query the expense database, compute credit scores, and generate charts.

Rules:
- Lead every answer with the key number or finding.
- When data would be clearer as a chart, ALWAYS call the chart tool and mention it.
- For comparisons between departments, use generate_comparison_chart.
- For trends over time, call get_monthly_trend then generate a line chart using generate_bar_chart.
- For "top vendors" questions, call get_top_vendors then generate_ranked_table.
- For credit score questions, explain what drove the score (violations).
- Never make up numbers — always fetch from a tool first.
- Keep answers concise and dollar amounts explicit.
""".strip()


def _build_tools():
    declarations = [
        FunctionDeclaration(
            name=t["name"],
            description=t["description"],
            parameters=t.get("parameters", {}),
        )
        for t in TOOL_DECLARATIONS
    ]
    return [Tool(function_declarations=declarations)]


class BrimAgent:
    def __init__(self, model_name=None):
        genai.configure(api_key=os.environ["GEMINI_API_KEY"])
        model_id = model_name or os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        self._model = genai.GenerativeModel(
            model_name=model_id,
            tools=_build_tools(),
            system_instruction=SYSTEM_PROMPT,
        )
        self._history = []

    async def chat(self, user_message: str, narrate: bool = False) -> dict[str, Any]:
        """
        Returns:
          text        — Gemini's final reply
          chart_paths — list of generated PNG paths
          audio_path  — ElevenLabs MP3 path (or None)
          tool_calls  — list of tool names that were invoked
        """
        self._history.append({"role": "user", "parts": [user_message]})
        chart_paths = []
        tool_calls_made = []

        session = self._model.start_chat(history=self._history[:-1])
        response = session.send_message(user_message)

        # Tool loop
        while True:
            fn_calls = [
                part.function_call
                for candidate in response.candidates
                for part in candidate.content.parts
                if part.function_call.name
            ]
            if not fn_calls:
                break

            tool_results = []
            for fn in fn_calls:
                name = fn.name
                args = dict(fn.args)
                tool_calls_made.append(name)

                result = await dispatch(name, args)
                if isinstance(result, dict) and "chart_path" in result:
                    chart_paths.append(result["chart_path"])

                tool_results.append(
                    genai.protos.Part(
                        function_response=genai.protos.FunctionResponse(
                            name=name,
                            response={"result": json.dumps(result, default=str)},
                        )
                    )
                )

            response = session.send_message(tool_results)

        final_text = response.text.strip()
        self._history.append({"role": "model", "parts": [final_text]})

        audio_path = None
        if narrate and final_text:
            audio_path = tts_narrate(final_text)

        return {
            "text": final_text,
            "chart_paths": chart_paths,
            "audio_path": audio_path,
            "tool_calls": tool_calls_made,
        }

    def reset(self):
        self._history = []
