"""
Multi-Agent 智能助手系统 — FastAPI 入口

API:
  POST /chat              — 单次对话
  POST /chat/stream       — 流式对话（SSE）
  WS   /ws/{session_id}   — WebSocket 双向通信
  POST /feedback          — 用户反馈提交
  POST /confirm/{id}      — 前端确认回调
  GET  /files/{id}/download — 文件下载
  GET  /health            — 健康检查
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

from config import get_settings, PROJECT_ROOT
from core.session_manager import get_session_manager
from core.feedback_system import get_feedback_system
from middleware.ws_manager import get_ws_manager
from agents.router_agent import get_router_agent
from utils.logger import setup_logging, get_logger

# ── 初始化 ────────────────────────────────────────

settings = get_settings()
setup_logging(level=settings.server.log_level)
logger = get_logger("main")

# ============================================================
# v2 增强: 确保 artifact 目录存在
# 来源: multi_agent_system_2.0/config.py → artifact_root
# ============================================================
from pathlib import Path
_artifact_dir = Path(settings.artifact_root)
_artifact_dir.mkdir(parents=True, exist_ok=True)
logger.info("Artifact directory: %s", _artifact_dir.resolve())

app = FastAPI(
    title="Multi-Agent 智能助手",
    version="0.1.0",
    description="LangGraph + LangChain 多Agent系统",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Request / Response Models ─────────────────────

class ChatRequest(BaseModel):
    query: str
    session_id: str = ""
    user_id: str = "anonymous"
    multimodal_files: Optional[list[dict]] = None

class ChatResponse(BaseModel):
    status: str
    content: str
    session_id: str = ""
    agent: str = ""
    needs_clarification: bool = False
    download_urls: list[str] = Field(default_factory=list)

class FeedbackRequest(BaseModel):
    question: str
    answer: str
    feedback: str
    session_id: str
    user_id: str = ""
    agent_name: str = ""
    rating: int = 0

class ConfirmRequest(BaseModel):
    status: str  # "confirmed" | "cancelled"
    reason: str = ""

# ── API Routes ────────────────────────────────────

@app.get("/health")
async def health():
    """健康检查"""
    ws_mgr = get_ws_manager()
    session_mgr = get_session_manager()
    return {
        "status": "ok",
        "websocket_connections": ws_mgr.connection_count,
        "pending_confirmations": ws_mgr.pending_count,
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """
    单次对话接口
    非流式，等待完整结果后返回
    """
    session_mgr = get_session_manager()
    router = get_router_agent()

    # 获取或创建会话
    session = session_mgr.get_or_create(req.session_id, req.user_id)

    # 路由
    result = await router.route(
        query=req.query,
        session_id=session.session_id,
        user_id=req.user_id,
        multimodal_files=req.multimodal_files,
    )

    return ChatResponse(
        status=result.get("status", "error"),
        content=result.get("content", ""),
        session_id=session.session_id,
        agent=result.get("agent", ""),
        needs_clarification=result.get("__needs_clarification__", False),
        download_urls=result.get("download_urls", []),
    )


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    """
    流式对话接口（SSE）
    通过 Server-Sent Events 逐步推送回复
    """
    from sse_starlette.sse import EventSourceResponse

    session_mgr = get_session_manager()
    router = get_router_agent()
    session = session_mgr.get_or_create(req.session_id, req.user_id)

    async def event_generator():
        result = await router.route(
            query=req.query,
            session_id=session.session_id,
            user_id=req.user_id,
            multimodal_files=req.multimodal_files,
        )

        content = result.get("content", "")
        is_clarification = result.get("__needs_clarification__", False)

        # 模拟流式推送
        chunk_size = 50
        for i in range(0, len(content), chunk_size):
            chunk = content[i:i + chunk_size]
            yield {
                "event": "message",
                "data": json.dumps({
                    "content": chunk,
                    "is_final": False,
                    "needs_clarification": is_clarification,
                }, ensure_ascii=False),
            }

        # 最终事件
        yield {
            "event": "done",
            "data": json.dumps({
                "content": "",
                "is_final": True,
                "session_id": session.session_id,
                "download_urls": result.get("download_urls", []),
                "needs_clarification": is_clarification,
            }, ensure_ascii=False),
        }

    return EventSourceResponse(event_generator())


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """
    WebSocket 双向通信
    用于实时推送确认弹窗和流式内容
    """
    ws_mgr = get_ws_manager()
    session_mgr = get_session_manager()
    router = get_router_agent()

    await websocket.accept()
    await ws_mgr.connect(session_id, websocket)

    # 创建或获取会话
    session = session_mgr.get_or_create(session_id)

    try:
        while True:
            # 接收前端消息
            raw = await websocket.receive_text()
            data = json.loads(raw)
            msg_type = data.get("type", "")

            if msg_type == "chat":
                # 用户发送聊天消息
                query = data.get("query", "")
                result = await router.route(
                    query=query,
                    session_id=session.session_id,
                    user_id=data.get("user_id", "anonymous"),
                    multimodal_files=data.get("multimodal_files"),
                )

                content = result.get("content", "")
                is_clarification = result.get("__needs_clarification__", False)

                # 流式推送内容
                chunk_size = 80
                for i in range(0, len(content), chunk_size):
                    chunk = content[i:i + chunk_size]
                    await ws_mgr.push_stream_chunk(
                        session_id=session_id,
                        content=chunk,
                        is_clarification=is_clarification,
                        is_final=False,
                    )

                # 最终帧
                await ws_mgr.push_stream_chunk(
                    session_id=session_id,
                    content="",
                    is_clarification=is_clarification,
                    is_final=True,
                )

            elif msg_type == "confirm":
                # 前端确认回调
                confirm_id = data.get("confirm_id", "")
                status = data.get("status", "cancelled")
                ws_mgr.resolve_confirmation(confirm_id, {"status": status})

            elif msg_type == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected: session=%s", session_id)
    except Exception as e:
        logger.error("WebSocket error for session=%s: %s", session_id, e)
    finally:
        await ws_mgr.disconnect(session_id)


@app.post("/confirm/{confirm_id}")
async def confirm_callback(confirm_id: str, req: ConfirmRequest):
    """
    前端确认 HTTP 回调（备选方案，WebSocket 不可用时使用）
    """
    ws_mgr = get_ws_manager()
    resolved = ws_mgr.resolve_confirmation(confirm_id, {
        "status": req.status,
        "reason": req.reason,
    })
    if not resolved:
        raise HTTPException(status_code=404, detail="Confirmation not found or already resolved")
    return {"status": "ok", "confirm_id": confirm_id}


@app.post("/feedback")
async def submit_feedback(req: FeedbackRequest):
    """提交用户反馈"""
    feedback_sys = get_feedback_system()
    success = await feedback_sys.record_feedback(
        question=req.question,
        answer=req.answer,
        feedback=req.feedback,
        session_id=req.session_id,
        user_id=req.user_id,
        agent_name=req.agent_name,
        rating=req.rating,
    )
    return {"status": "ok" if success else "error"}


@app.get("/files/{file_id}/download")
async def download_file(file_id: str):
    """
    文件下载
    从本地存储中查找对应的文件
    """
    storage_path = settings.storage.storage_path

    # 遍历子目录查找文件
    for subdir in ["charts", "reports", "ppts"]:
        for ext in [".html", ".png", ".xlsx", ".pptx"]:
            candidate = storage_path / subdir / f"{file_id}{ext}"
            if candidate.exists():
                media_type_map = {
                    ".html": "text/html",
                    ".png": "image/png",
                    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                }
                return FileResponse(
                    path=str(candidate),
                    media_type=media_type_map.get(ext, "application/octet-stream"),
                    filename=f"download{ext}",
                )

    raise HTTPException(status_code=404, detail="File not found")


# ── 启动 ──────────────────────────────────────────

if __name__ == "__main__":
    logger.info("Starting Multi-Agent System on %s:%d", settings.server.host, settings.server.port)
    uvicorn.run(
        "main:app",
        host=settings.server.host,
        port=settings.server.port,
        reload=settings.server.is_development,
        log_level=settings.server.log_level.lower(),
    )
