"""FastAPI routes — POST /chat, GET /chat/reset, GET /chart/{file}, GET /health"""
import os
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from agent.core import BrimAgent

router = APIRouter()
_agent = BrimAgent()


class ChatRequest(BaseModel):
    message: str
    narrate: bool = False


class ChatResponse(BaseModel):
    text: str
    chart_paths: list[str]
    audio_path: str | None
    tool_calls: list[str]


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    try:
        result = await _agent.chat(req.message, narrate=req.narrate)
        return ChatResponse(**result)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/chat/reset")
async def reset_chat():
    _agent.reset()
    return {"status": "conversation history cleared"}


@router.get("/chart/{filename}")
async def get_chart(filename: str):
    charts_dir = os.getenv("CHARTS_OUTPUT_DIR", "./charts/output")
    path = os.path.join(charts_dir, filename)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Chart not found")
    return FileResponse(path, media_type="image/png")


@router.get("/health")
async def health():
    return {"status": "ok"}
