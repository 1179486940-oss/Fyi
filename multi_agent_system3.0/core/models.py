"""
统一数据模型层（从 v2 迁移增强）
定义系统内所有核心结构体，保证不同模块之间传输的数据格式统一。
所有模块间通信统一使用这些 dataclass，消除裸 dict 传递。

来源: multi_agent_system_2.0/core/models.py
适配: v1 生产环境（LangGraph + FastAPI + RAGFlow + PostgreSQL）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

# ============================================================
# 事件类型枚举
# ============================================================
EventType = Literal[
    "answer",           # 普通回答
    "clarification",    # 澄清问题
    "confirmation",     # 确认弹窗
    "artifact_ready",   # 产物就绪（图表/报表/PPT）
    "error",            # 错误
    "trace",            # 追踪日志
]

# ============================================================
# 9 个核心数据结构
# ============================================================

# ── 1. Attachment ────────────────────────────────────

@dataclass(slots=True)
class Attachment:
    """用户上传的文件"""
    name: str                       # 文件名
    content_type: str               # MIME 类型 (image/png, application/pdf)
    path: str                       # 文件路径（本地或临时路径）

    # ============================================================
    # @REAL_CODE: 对接真实文件上传服务
    # 当前状态: 仅支持本地路径
    # 目标实现: 支持 S3/MinIO 上传后的远程 URL + 本地缓存路径
    # 对接服务: S3 / MinIO 对象存储
    # 参考文档: config.py StorageSettings
    # 优先级: MEDIUM
    # ============================================================


# ── 2. MemoryRecord ──────────────────────────────────

@dataclass(slots=True)
class MemoryRecord:
    """一条记忆记录（短期/长期/反馈/KB）"""
    key: str                                    # 记忆唯一标识
    content: str                                # 记忆内容
    source: Literal["short_term", "long_term", "feedback", "kb"]
    metadata: dict[str, Any] = field(default_factory=dict)  # session_id, timestamp 等

    # ============================================================
    # @REAL_CODE: 对接 RAGFlow 长期记忆 KB 的 CRUD
    # 当前状态: 通过 RAGFlow API 写入/检索/删除
    # 目标实现: memory_manager 中 try_write_longterm_memory /
    #          try_delete_longterm_memory 已对接 RAGFlow
    # 对接服务: RAGFlow 长期记忆KB (KB_LONGTERM_MEMORY)
    # 参考文档: 设计手册.docx → 记忆管理章节
    # 优先级: LOW (已基本实现)
    # ============================================================


# ── 3. RetrievalChunk ────────────────────────────────

@dataclass(slots=True)
class RetrievalChunk:
    """一条知识库检索结果"""
    kb_type: Literal["database", "business", "longterm_memory", "feedback"]
    content: str                                # 检索到的文本
    score: float                                # 相似度分数 (0-1)
    metadata: dict[str, Any] = field(default_factory=dict)  # document_id, chunk_index 等

    # ============================================================
    # @REAL_CODE: 对接 RAGFlow 检索 API
    # 当前状态: knowledge_manager.search() 已对接 RAGFlow /api/v1/retrieval
    # 目标实现: 四类 KB (database/business/feedback/longterm_memory)
    #          的语义+关键词混合检索
    # 对接服务: RAGFlow (RAGFLOW_BASE_URL)
    # 参考文档: 设计手册.docx → 知识库管理章节
    # 优先级: LOW (已基本实现)
    # ============================================================


# ── 4. ConfirmationPayload ───────────────────────────

@dataclass(slots=True)
class ConfirmationPayload:
    """写操作确认卡片的数据"""
    confirmation_id: str                        # 唯一确认ID (confirm_xxxxxxxxxxxx)
    operation: str                              # INSERT / UPDATE / DELETE
    summary: str                                # 操作概述（展示给用户）
    sql: str                                    # 即将执行的 SQL
    preview_rows: list[dict[str, Any]] = field(default_factory=list)  # 受影响数据预览
    metadata: dict[str, Any] = field(default_factory=dict)  # table_name, session_id 等

    # ============================================================
    # @REAL_CODE: 确认弹窗的数据结构已完备
    # 当前状态: ConfirmationMiddleware 使用此结构构造确认弹窗
    # 目标实现: WebSocket 推送到前端 → 用户确认/取消 → Future 唤醒
    # 对接服务: WebSocket (ws_manager.py)
    # 参考文档: 中断式确认机制调研.docx
    # 优先级: LOW (已实现)
    # ============================================================


# ── 5. AgentEvent ────────────────────────────────────

@dataclass(slots=True)
class AgentEvent:
    """Agent 执行过程中的事件"""
    type: EventType
    message: str                                # 事件描述
    payload: dict[str, Any] = field(default_factory=dict)  # 附加数据

    # ============================================================
    # @REAL_CODE: Agent 执行过程中应实时推送事件到前端
    # 当前状态: 通过 WebSocket 流式推送 thinking/content/url 标签
    # 目标实现: 统一使用 AgentEvent 类型，前端按 type 渲染不同 UI
    # 对接服务: WebSocket (ws_manager.push_stream_chunk)
    # 参考文档: agent设计手册.docx → 前端事件协议
    # 优先级: MEDIUM
    # ============================================================


# ── 6. Artifact ──────────────────────────────────────

@dataclass(slots=True)
class Artifact:
    """生成的产物文件（图表/报表/PPT）"""
    name: str                                   # 产物名称
    artifact_type: Literal["image", "html", "excel", "ppt"]
    path: str                                   # 本地存储路径
    url: str                                    # 下载 URL
    metadata: dict[str, Any] = field(default_factory=dict)  # chart_type, row_count 等

    # ============================================================
    # @REAL_CODE: 对接真实对象存储（S3/MinIO）
    # 当前状态: 文件存储在本地 STORAGE_LOCAL_DIR，通过 /files/{id}/download 下载
    # 目标实现: 生成后上传到 S3，返回预签名 URL
    # 对接服务: S3 / MinIO (STORAGE_BACKEND=s3)
    # 参考文档: config.py StorageSettings
    # 优先级: HIGH
    # ============================================================


# ── 7. AgentResult ───────────────────────────────────

@dataclass(slots=True)
class AgentResult:
    """每个子 Agent 的统一返回结构（替代裸 dict）"""
    status: Literal["success", "clarification_required", "confirmation_required", "error"]
    agent_name: str                             # 处理的 Agent 名称
    summary: str                                # 回答摘要
    data: dict[str, Any] = field(default_factory=dict)
    table_preview: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[Artifact] = field(default_factory=list)
    confirmation_required: bool = False
    clarification_required: bool = False
    events: list[AgentEvent] = field(default_factory=list)
    trace: list[str] = field(default_factory=list)
    confirmation_payload: ConfirmationPayload | None = None

    def to_dict(self) -> dict[str, Any]:
        """兼容旧代码：转为 dict（过渡期使用）"""
        result: dict[str, Any] = {
            "status": self.status,
            "agent_name": self.agent_name,
            "content": self.summary,
        }
        if self.data:
            result["data"] = self.data
        if self.table_preview:
            result["table_preview"] = self.table_preview
        if self.artifacts:
            result["download_urls"] = [a.url for a in self.artifacts]
            result["download_url"] = self.artifacts[0].url if self.artifacts else ""
        if self.confirmation_required:
            result["confirmation_required"] = True
            if self.confirmation_payload:
                result["confirmation_payload"] = {
                    "confirmation_id": self.confirmation_payload.confirmation_id,
                    "operation": self.confirmation_payload.operation,
                    "summary": self.confirmation_payload.summary,
                    "sql": self.confirmation_payload.sql,
                    "preview_rows": self.confirmation_payload.preview_rows,
                }
        if self.clarification_required:
            result["__needs_clarification__"] = True
        return result

    # ============================================================
    # @REAL_CODE: 逐步将所有 Agent.process() 返回值从 dict 迁移到 AgentResult
    # 当前状态: 各 Agent 的 process() 仍返回 dict，通过 to_dict() 兼容
    # 目标实现: 所有 Agent 直接返回 AgentResult 实例
    # 对接服务: N/A（纯内部重构）
    # 参考文档: 本文档 → AgentResult 定义
    # 优先级: HIGH (逐步迁移，先新 Agent 后旧 Agent)
    # ============================================================


# ── 8. RouterTask ────────────────────────────────────

@dataclass(slots=True)
class RouterTask:
    """Router 规划出的一个子任务"""
    agent_name: str                             # 目标 Agent
    user_query: str                             # 该子任务的查询文本
    dependency_on: str | None = None            # 依赖的前置任务 agent_name（用于 DAG 调度）
    metadata: dict[str, Any] = field(default_factory=dict)

    # ============================================================
    # @REAL_CODE: 支持 DAG 任务依赖调度
    # 当前状态: 多意图场景使用 asyncio.gather 并行执行，无依赖关系
    # 目标实现: 根据 dependency_on 字段构建 DAG，按拓扑序执行
    # 对接服务: N/A（纯内部逻辑）
    # 参考文档: agent设计手册.docx → 多意图调度
    # 优先级: MEDIUM
    # ============================================================


# ── 9. RouterState (Dataclass 版) ────────────────────

@dataclass(slots=True)
class RouterStateData:
    """
    Router 执行过程中的完整上下文（Dataclass 版）
    注意: LangGraph 节点使用 TypedDict 版 RouterState，
    此 Dataclass 用于非 LangGraph 场景和序列化。
    """
    session_id: str
    user_id: str
    query: str
    attachments: list[Attachment] = field(default_factory=list)
    normalized_query: str = ""
    multimodal_context: str = ""
    memory_context: list[MemoryRecord] = field(default_factory=list)
    retrieval_context: list[RetrievalChunk] = field(default_factory=list)
    planned_tasks: list[RouterTask] = field(default_factory=list)
    events: list[AgentEvent] = field(default_factory=list)
    checkpoints: list[str] = field(default_factory=list)
    error: str | None = None

    # ============================================================
    # @REAL_CODE: LangGraph TypedDict 与 Dataclass 的双轨过渡
    # 当前状态: router_agent.py 使用 TypedDict RouterState (LangGraph 要求)
    #          本 Dataclass 提供结构化替代方案
    # 目标实现: 非 LangGraph 场景统一使用 RouterStateData
    # 对接服务: N/A（纯内部重构）
    # 参考文档: agents/router_agent.py → RouterState TypedDict
    # 优先级: LOW
    # ============================================================
