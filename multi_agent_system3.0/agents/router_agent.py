"""
主 Agent — LangGraph 路由编排（v2 增强版）
StateGraph 节点：
  trigger_kw → multimodal → intent → single_dispatch / multi_split / clarify
  → aggregate → fallback → END

v2 增强:
  - 新增 handle() 方法（同步包装，兼容 v2 API）
  - 接入 core/models.py RouterStateData 用于非 LangGraph 场景
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional, TypedDict, Annotated
import operator

from langgraph.graph import StateGraph, END

from config import get_settings
from core.llm_provider import get_llm_provider
from core.session_manager import Session, get_session_manager
from core.memory_manager import get_memory_manager
from core.guardrails import get_guardrails, IntentResult
from core.auth_manager import get_auth_manager
from middleware.ws_manager import get_ws_manager
from utils.logger import get_logger
from utils.helpers import generate_uuid, timestamp_now

# ============================================================
# v2 增强: 导入统一数据模型
# 来源: multi_agent_system_2.0/agents/router_agent.py
# ============================================================
from core.models import (              # @REAL_CODE: 非 LangGraph 场景使用 RouterStateData
    RouterStateData,
    RouterTask,
    AgentResult,
    AgentEvent,
    Attachment as ModelAttachment,
)

logger = get_logger(__name__)


# ── State 定义 ────────────────────────────────────

class RouterState(TypedDict):
    """Router Agent 状态"""
    session_id: str
    user_id: str
    query: str
    original_query: str              # 保留原始 query（多模态处理后可能被修改）
    multimodal_files: Optional[list[dict]]

    # 长期记忆
    memory_action: str                # "write" | "delete" | "none"
    memory_message: str               # 反馈给用户的消息

    # 意图识别
    intent_result: Optional[IntentResult]
    is_multi_intent: bool
    is_clarification: bool
    needs_fallback: bool

    # 上下文回溯
    should_reset_context: bool
    should_restore_context: bool

    # 路由结果
    target_agent: str                 # "data_query" | "data_graph" | "data_report" | "ppt_generate" | "fallback"
    sub_tasks: list[dict]             # 多意图拆分的子任务

    # 结果
    responses: Annotated[list[dict], operator.add]  # 各子Agent的返回结果
    final_response: dict              # 最终响应

    # 错误
    error: Optional[str]


# ── Router Agent ──────────────────────────────────

class RouterAgent:
    """LangGraph 主路由 Agent"""

    def __init__(self):
        settings = get_settings()
        self._llm = get_llm_provider()
        self._memory = get_memory_manager()
        self._guardrails = get_guardrails()
        self._auth = get_auth_manager()
        self._ws = get_ws_manager()
        self._session_mgr = get_session_manager()

        self._skill_registry = settings.skill_registry

        # 构建 LangGraph
        self.graph = self._build_graph()

    # ── 构建状态图 ──────────────────────────────────

    def _build_graph(self) -> StateGraph:
        """构建 LangGraph StateGraph"""
        workflow = StateGraph(RouterState)

        # 添加节点
        workflow.add_node("trigger_kw", self._trigger_kw_node)
        workflow.add_node("multimodal", self._multimodal_node)
        workflow.add_node("intent", self._intent_node)
        workflow.add_node("single_dispatch", self._single_dispatch_node)
        workflow.add_node("multi_split", self._multi_split_node)
        workflow.add_node("aggregate", self._aggregate_node)
        workflow.add_node("clarify", self._clarify_node)
        workflow.add_node("fallback", self._fallback_node)

        # 入口
        workflow.set_entry_point("trigger_kw")

        # 边
        workflow.add_edge("trigger_kw", "multimodal")
        workflow.add_edge("multimodal", "intent")

        # 条件路由
        workflow.add_conditional_edges(
            "intent",
            self._route_after_intent,
            {
                "single": "single_dispatch",
                "multi": "multi_split",
                "clarify": "clarify",
                "fallback": "fallback",
            },
        )

        workflow.add_conditional_edges(
            "single_dispatch",
            self._route_after_dispatch,
            {
                "aggregate": "aggregate",
                "fallback": "fallback",
            },
        )

        workflow.add_edge("multi_split", "aggregate")
        workflow.add_edge("aggregate", END)
        workflow.add_edge("clarify", END)
        workflow.add_edge("fallback", END)

        return workflow.compile()

    # ── Node 1: 记忆触发检测 ────────────────────────

    async def _trigger_kw_node(self, state: RouterState) -> RouterState:
        """全局必做：检测触发关键词，写入/删除长期记忆"""
        query = state["query"]
        session = self._session_mgr.get_session(state["session_id"])

        if not session:
            return state

        # 检测写入触发
        memory_msg = await self._memory.try_write_longterm_memory(query, session)
        if memory_msg:
            state["memory_action"] = "write"
            state["memory_message"] = memory_msg
            logger.info("Router: long-term memory write triggered")
            return state

        # 检测删除触发
        memory_msg = await self._memory.try_delete_longterm_memory(query, session)
        if memory_msg:
            state["memory_action"] = "delete"
            state["memory_message"] = memory_msg
            logger.info("Router: long-term memory delete triggered")
            return state

        state["memory_action"] = "none"
        return state

    # ── Node 2: 多模态理解 ──────────────────────────

    async def _multimodal_node(self, state: RouterState) -> RouterState:
        """有 image/pdf 附件时调用 Qwen VL 提取文本"""
        files = state.get("multimodal_files")
        if not files:
            return state

        extracted_texts = []
        for f in files:
            file_path = f.get("path", "")
            file_type = f.get("type", "image")
            if file_path and file_type in ("image", "pdf"):
                try:
                    text = await self._llm.understand_multimodal(
                        file_path, file_type,
                        context_query=state["query"],
                    )
                    extracted_texts.append(text)
                except Exception as e:
                    logger.error("Multimodal failed: %s", e)

        if extracted_texts:
            multimodal_text = "\n\n【文件内容】\n" + "\n---\n".join(extracted_texts)
            state["query"] = f"{state['query']}{multimodal_text}"

        return state

    # ── Node 3: 意图识别 ────────────────────────────

    async def _intent_node(self, state: RouterState) -> RouterState:
        """Embedding 相似度打分 + 边界判断 + 澄清触发 + 回溯检测"""
        intent_result = await self._guardrails.recognize_intent(state["query"])

        state["intent_result"] = intent_result
        state["should_reset_context"] = intent_result.should_reset_context
        state["should_restore_context"] = intent_result.should_restore_context
        state["is_clarification"] = intent_result.is_clarification_needed
        state["needs_fallback"] = intent_result.needs_fallback
        state["is_multi_intent"] = not intent_result.is_single_intent

        logger.info("Router intent: single=%s, multi=%s, clarify=%s, fallback=%s, best=%s",
                     intent_result.is_single_intent and not intent_result.needs_fallback,
                     not intent_result.is_single_intent,
                     intent_result.is_clarification_needed,
                     intent_result.needs_fallback,
                     intent_result.best_match.skill_name if intent_result.best_match else "none")

        # 上下文回溯处理
        session = self._session_mgr.get_session(state["session_id"])
        if session:
            if intent_result.should_reset_context:
                session.reset_context()
                logger.info("Session %s: context reset", state["session_id"])
            elif intent_result.should_restore_context:
                restored = session.restore_context()
                logger.info("Session %s: context restore=%s", state["session_id"], restored)

        return state

    # ── Node 4a: 单意图分发 ──────────────────────────

    async def _single_dispatch_node(self, state: RouterState) -> RouterState:
        """鉴权 → 路由到单个 Sub-Agent"""
        intent_result = state.get("intent_result")
        if not intent_result or not intent_result.best_match:
            state["error"] = "No intent match found"
            return state

        skill_name = intent_result.best_match.skill_name
        target = self._skill_to_agent(skill_name)
        state["target_agent"] = target

        # 鉴权检查
        has_perm = await self._auth.check_subsystem_permission(
            state["user_id"], target
        )
        if not has_perm:
            state["responses"] = [{
                "status": "error",
                "content": f"⚠️ 您没有 {target} 子系统的访问权限。",
            }]
            state["target_agent"] = "fallback"
            return state

        # 调用子 Agent
        response = await self._invoke_agent(target, state)
        state["responses"] = [response]
        return state

    # ── Node 4b: 多意图拆分 ──────────────────────────

    async def _multi_split_node(self, state: RouterState) -> RouterState:
        """拆分 Query → 并行分发到多个 Sub-Agent"""
        intent_result = state.get("intent_result")
        if not intent_result:
            state["error"] = "No intent for multi-split"
            return state

        # 构建子任务
        sub_tasks = []
        for group in intent_result.multi_intent_groups:
            for score in group:
                target = self._skill_to_agent(score.skill_name)
                sub_tasks.append({
                    "agent": target,
                    "query": state["query"],
                    "skill": score.skill_name,
                })

        if not sub_tasks:
            sub_tasks = [{"agent": "fallback", "query": state["query"], "skill": "Common_KB_QA"}]

        state["sub_tasks"] = sub_tasks

        # 并行执行
        tasks = [self._invoke_agent(t["agent"], state) for t in sub_tasks]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        responses = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                responses.append({
                    "status": "error",
                    "content": f"子任务 {sub_tasks[i]['agent']} 执行异常: {str(r)}",
                })
            else:
                responses.append(r)

        state["responses"] = responses
        return state

    # ── Node 5: 结果聚合 ────────────────────────────

    async def _aggregate_node(self, state: RouterState) -> RouterState:
        """收集所有 Sub-Agent 结果 → LLM 生成 summary"""
        responses = state.get("responses", [])

        if not responses:
            state["final_response"] = {
                "status": "error",
                "content": "未能获取任何子Agent的返回结果。",
            }
            return state

        # 单结果直接返回
        if len(responses) == 1:
            state["final_response"] = responses[0]
            return state

        # 多结果 → 聚合
        from prompts.router_prompt import AGGREGATION_PROMPT

        sub_results_text = "\n\n---\n\n".join(
            f"[Agent: {r.get('agent', 'unknown')}]\n{r.get('content', '')}"
            for r in responses
        )

        prompt = AGGREGATION_PROMPT.format(
            original_query=state["original_query"],
            sub_results=sub_results_text,
        )

        aggregated = await self._llm.chat(
            messages=[{"role": "user", "content": prompt}],
        )

        # 收集所有 URL
        urls = [r.get("download_url") for r in responses if r.get("download_url")]

        state["final_response"] = {
            "status": "success",
            "content": aggregated,
            "sub_responses": responses,
            "download_urls": urls,
        }
        return state

    # ── Node 6: 澄清 ────────────────────────────────

    async def _clarify_node(self, state: RouterState) -> RouterState:
        """返回澄清问题，流式加标识字段"""
        intent_result = state.get("intent_result")
        question = intent_result.clarification_question if intent_result else "请补充更多信息以便我更好地理解您的需求。"

        state["final_response"] = {
            "status": "clarification",
            "content": question,
            "__needs_clarification__": True,
        }
        return state

    # ── Node 7: 兜底 ────────────────────────────────

    async def _fallback_node(self, state: RouterState) -> RouterState:
        """路由到 Fallback Agent"""
        response = await self._invoke_agent("fallback", state)
        state["final_response"] = response
        return state

    # ── 条件路由函数 ─────────────────────────────────

    def _route_after_intent(self, state: RouterState) -> str:
        if state.get("is_clarification"):
            return "clarify"
        if state.get("needs_fallback"):
            return "fallback"
        if state.get("is_multi_intent"):
            return "multi"
        return "single"

    def _route_after_dispatch(self, state: RouterState) -> str:
        if state.get("error") or state.get("target_agent") == "fallback":
            return "fallback"
        return "aggregate"

    # ── 工具方法 ─────────────────────────────────────

    def _skill_to_agent(self, skill_name: str) -> str:
        """将 Skill 名称映射到 Agent 名称"""
        mapping = {
            "Common_Data_Query": "data_query",
            "Common_Graph_Generate": "data_graph",
            "Common_Data_Report_Generate": "data_report",
            "PPT_Late_Release": "ppt_generate",
            "Common_KB_QA": "fallback",
        }
        return mapping.get(skill_name, "fallback")

    async def _invoke_agent(self, agent_name: str, state: RouterState) -> dict[str, Any]:
        """调用指定的子 Agent"""
        session_id = state["session_id"]
        user_id = state["user_id"]
        query = state["query"]

        try:
            if agent_name == "data_query":
                from agents.sub_agents.data_query_update_agent import DataQueryAgent
                agent = DataQueryAgent(session_id, user_id)
            elif agent_name == "data_graph":
                from agents.sub_agents.data_graph_agent import DataGraphAgent
                agent = DataGraphAgent(session_id, user_id)
            elif agent_name == "data_report":
                from agents.sub_agents.data_report_agent import DataReportAgent
                agent = DataReportAgent(session_id, user_id)
            elif agent_name == "ppt_generate":
                from agents.sub_agents.ppt_generate_agent import PPTGenerateAgent
                agent = PPTGenerateAgent(session_id, user_id)
            else:
                from agents.sub_agents.fallback_agent import FallbackAgent
                agent = FallbackAgent(session_id, user_id)

            # 获取会话上下文
            session = self._session_mgr.get_session(session_id)
            context = session.history_text if session else ""

            result = await agent.execute(
                query=query,
                multimodal_files=state.get("multimodal_files"),
            )
            result["agent"] = agent_name
            return result

        except Exception as e:
            logger.error("Agent %s invocation failed: %s", agent_name, e)
            return {
                "status": "error",
                "content": f"{agent_name} Agent 调用失败：{str(e)}",
                "agent": agent_name,
            }

    # ── v2 兼容: 同步 handle() 方法 ────────────────────
    # ============================================================
    # @REAL_CODE: handle() 是 v2 API 兼容包装，内部调用 async route()
    # 当前状态: 同步包装 asyncio.run()，适用于 demo 和测试场景
    # 目标实现: 在生产中优先使用 async route() 方法
    # 优先级: LOW
    # ============================================================

    def handle(
        self,
        session_id: str,
        user_id: str,
        query: str,
        attachments: list | None = None,
    ) -> dict[str, Any]:
        """
        v2 兼容: 同步包装方法
        内部调用 async route()，用于 demo 和测试场景

        Args:
            session_id: 会话ID
            user_id: 用户ID
            query: 用户查询
            attachments: 附件列表（可选）

        Returns:
            与 route() 相同的 dict 结果，额外包含 planned_tasks 和 results 字段
        """
        # 转换 attachments 格式
        multimodal_files = None
        if attachments:
            multimodal_files = []
            for att in attachments:
                if isinstance(att, str):
                    multimodal_files.append({"path": att, "type": "image"})
                elif isinstance(att, dict):
                    multimodal_files.append(att)

        # 同步执行异步路由
        result = asyncio.run(
            self.route(
                query=query,
                session_id=session_id,
                user_id=user_id,
                multimodal_files=multimodal_files,
            )
        )

        # 添加 v2 兼容字段
        if "planned_tasks" not in result:
            result["planned_tasks"] = []
        if "results" not in result:
            result["results"] = result.get("sub_responses", [result])

        return result

    # ── 公开入口 ─────────────────────────────────────

    async def route(
        self,
        query: str,
        session_id: str,
        user_id: str = "anonymous",
        multimodal_files: Optional[list[dict]] = None,
    ) -> dict[str, Any]:
        """
        主路由入口
        Args:
            query: 用户查询
            session_id: 会话ID
            user_id: 用户ID
            multimodal_files: 多模态文件列表
        Returns:
            最终响应
        """
        initial_state: RouterState = {
            "session_id": session_id,
            "user_id": user_id,
            "query": query,
            "original_query": query,
            "multimodal_files": multimodal_files,
            "memory_action": "none",
            "memory_message": "",
            "intent_result": None,
            "is_multi_intent": False,
            "is_clarification": False,
            "needs_fallback": False,
            "should_reset_context": False,
            "should_restore_context": False,
            "target_agent": "",
            "sub_tasks": [],
            "responses": [],
            "final_response": {},
            "error": None,
        }

        logger.info("Router: processing query from session=%s", session_id)

        final_state = await self.graph.ainvoke(initial_state)

        # 返回最终响应 + 记忆消息
        response = final_state.get("final_response", {})
        if final_state.get("memory_message"):
            if response.get("content"):
                response["content"] = f"{final_state['memory_message']}\n\n{response['content']}"
            else:
                response["content"] = final_state["memory_message"]

        return response


# 全局单例
_router_agent: Optional[RouterAgent] = None


def get_router_agent() -> RouterAgent:
    global _router_agent
    if _router_agent is None:
        _router_agent = RouterAgent()
    return _router_agent
