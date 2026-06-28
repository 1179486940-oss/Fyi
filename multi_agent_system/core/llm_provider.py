"""
LLM 统一接入层
- 多模型切换（DeepSeek V4 Pro / Qwen 3.5）
- 多模态理解（Qwen3.5-397B-A17B-VL）
- 统一 chat() / chat_stream() 接口
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator, Literal, Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, AIMessage
from langchain_openai import ChatOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from config import get_settings
from utils.logger import get_logger

logger = get_logger(__name__)


class LLMProvider:
    """LLM 统一接入"""

    def __init__(self):
        settings = get_settings()
        self._llm_config = settings.llm
        self._multimodal_config = settings.multimodal

        # 缓存模型实例
        self._models: dict[str, BaseChatModel] = {}

    # ── 模型获取 ────────────────────────────────────────

    def get_model(self, model_name: Optional[str] = None) -> BaseChatModel:
        """获取 LLM 模型实例（带缓存）"""
        name = model_name or self._llm_config.default_model
        if name not in self._models:
            self._models[name] = ChatOpenAI(
                model=name,
                base_url=self._llm_config.base_url,
                api_key=self._llm_config.api_key,
                temperature=self._llm_config.temperature,
                max_tokens=self._llm_config.max_tokens,
                timeout=self._llm_config.request_timeout,
                max_retries=0,  # 我们自己用 tenacity 控制重试
            )
            logger.info("LLM model initialized: %s @ %s", name, self._llm_config.base_url)
        return self._models[name]

    def get_multimodal_model(self) -> BaseChatModel:
        """获取多模态模型（Qwen VL）"""
        name = self._multimodal_config.model
        if name not in self._models:
            self._models[name] = ChatOpenAI(
                model=name,
                base_url=self._multimodal_config.base_url,
                api_key=self._multimodal_config.api_key,
                temperature=0.0,  # 多模态理解温度低
                max_tokens=self._multimodal_config.max_tokens,
                timeout=120,
                max_retries=0,
            )
        return self._models[name]

    # ── 对话接口 ────────────────────────────────────────

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def chat(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ) -> str:
        """
        单次对话（非流式）
        Args:
            messages: [{"role": "user/assistant", "content": "..."}, ...]
            model: 模型名，默认用配置的 default_model
            system_prompt: 可选 system prompt
        Returns:
            LLM 生成的文本
        """
        llm = self.get_model(model)
        lc_messages: list[BaseMessage] = []

        if system_prompt:
            lc_messages.append(SystemMessage(content=system_prompt))

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "user":
                lc_messages.append(HumanMessage(content=content))
            elif role == "assistant":
                lc_messages.append(AIMessage(content=content))
            else:
                lc_messages.append(HumanMessage(content=content))

        logger.debug("LLM chat: %d messages, model=%s", len(lc_messages), llm.model_name)
        response = await llm.ainvoke(lc_messages)
        return response.content

    async def chat_stream(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """
        流式对话
        """
        llm = self.get_model(model)
        lc_messages: list[BaseMessage] = []

        if system_prompt:
            lc_messages.append(SystemMessage(content=system_prompt))

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "user":
                lc_messages.append(HumanMessage(content=content))
            elif role == "assistant":
                lc_messages.append(AIMessage(content=content))
            else:
                lc_messages.append(HumanMessage(content=content))

        async for chunk in llm.astream(lc_messages):
            if chunk.content:
                yield chunk.content

    # ── 多模态理解 ──────────────────────────────────────

    async def understand_multimodal(
        self,
        file_path: str,
        file_type: Literal["image", "pdf"],
        context_query: str = "请详细描述文件中的内容，包括所有文字、表格和关键信息。",
    ) -> str:
        """
        多模态理解：提取图片/PDF中的文本内容
        Args:
            file_path: 文件本地路径
            file_type: image 或 pdf
            context_query: 上下文提示
        Returns:
            提取的文本内容
        """
        import base64
        import mimetypes

        with open(file_path, "rb") as f:
            file_data = base64.b64encode(f.read()).decode("utf-8")

        mime_type, _ = mimetypes.guess_type(file_path)
        if not mime_type:
            mime_type = "image/png" if file_type == "image" else "application/pdf"

        data_url = f"data:{mime_type};base64,{file_data}"

        llm = self.get_multimodal_model()
        message = HumanMessage(
            content=[
                {"type": "text", "text": context_query},
                {"type": "image_url", "image_url": {"url": data_url}},
            ]
        )

        logger.info("Multimodal understanding: file=%s, type=%s", file_path, file_type)
        response = await llm.ainvoke([message])
        return response.content

    # ── 工具方法 ────────────────────────────────────────

    async def get_embedding(self, text: str, model: Optional[str] = None) -> list[float]:
        """获取文本的 Embedding 向量"""
        from langchain_openai import OpenAIEmbeddings

        embeddings = OpenAIEmbeddings(
            model=model or "text-embedding-3-small",
            base_url=self._llm_config.base_url,
            api_key=self._llm_config.api_key,
        )
        return await embeddings.aembed_query(text)

    def compute_similarity(self, embedding1: list[float], embedding2: list[float]) -> float:
        """计算两个向量的余弦相似度"""
        import numpy as np
        a = np.array(embedding1)
        b = np.array(embedding2)
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


# 全局单例
_llm_provider: Optional[LLMProvider] = None


def get_llm_provider() -> LLMProvider:
    """获取 LLM Provider 全局单例"""
    global _llm_provider
    if _llm_provider is None:
        _llm_provider = LLMProvider()
    return _llm_provider
