"""
全局配置模块
使用 pydantic-settings 读取 .env 并暴露结构化配置
"""

from __future__ import annotations

import os
from pathlib import Path
from functools import lru_cache
from typing import Literal, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent


class LLMSettings(BaseSettings):
    """LLM 模型配置"""
    model_config = SettingsConfigDict(env_prefix="LLM_", env_file=".env", extra="ignore")

    provider: str = Field(default="beacon", description="LLM provider")
    base_url: str = Field(default="https://beacon-api.xxx.com/v1")
    api_key: str = Field(default="your-api-key-here")
    default_model: str = Field(default="deepseek-v4-pro")
    backup_model: str = Field(default="qwen-3.5")
    temperature: float = Field(default=0.1, description="生成温度")
    max_tokens: int = Field(default=4096)
    request_timeout: int = Field(default=60, description="请求超时(秒)")
    max_retries: int = Field(default=3, description="失败重试次数")


class MultimodalSettings(BaseSettings):
    """多模态模型配置"""
    model_config = SettingsConfigDict(env_prefix="MULTIMODAL_", env_file=".env", extra="ignore")

    model: str = Field(default="qwen3.5-397b-a17b-vl")
    base_url: str = Field(default="https://beacon-api.xxx.com/v1")
    api_key: str = Field(default="your-api-key-here")
    max_tokens: int = Field(default=2048)
    supported_types: list[str] = Field(default=["image", "pdf"])


class RAGFlowSettings(BaseSettings):
    """RAGFlow 知识库配置"""
    model_config = SettingsConfigDict(env_prefix="RAGFLOW_", env_file=".env", extra="ignore")

    base_url: str = Field(default="https://ragflow.xxx.com/api/v1")
    api_key: str = Field(default="your-ragflow-key")
    request_timeout: int = Field(default=30)

    # 四类知识库 ID
    kb_longterm_memory: str = Field(default="kb_longterm_memory_id", alias="KB_LONGTERM_MEMORY")
    kb_business: str = Field(default="kb_business_id", alias="KB_BUSINESS")
    kb_feedback: str = Field(default="kb_feedback_id", alias="KB_FEEDBACK")
    kb_database: str = Field(default="kb_database_id", alias="KB_DATABASE")

    # 检索默认参数
    default_similarity_threshold: float = Field(default=0.7, description="默认相似度阈值")
    dedup_threshold: float = Field(default=0.9, description="语义去重阈值")


class DatabaseSettings(BaseSettings):
    """PostgreSQL 数据库配置"""
    model_config = SettingsConfigDict(env_prefix="DB_", env_file=".env", extra="ignore")

    host: str = Field(default="localhost")
    port: int = Field(default=5432)
    name: str = Field(default="multi_agent_db")
    user: str = Field(default="agent_user")
    password: str = Field(default="your-db-password")
    pool_min: int = Field(default=2)
    pool_max: int = Field(default=10)

    @property
    def url(self) -> str:
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"

    @property
    def sync_url(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


class StorageSettings(BaseSettings):
    """文件存储配置"""
    model_config = SettingsConfigDict(env_prefix="STORAGE_", env_file=".env", extra="ignore")

    backend: Literal["local", "s3"] = Field(default="local")
    local_dir: str = Field(default="./storage")

    s3_endpoint: Optional[str] = Field(default=None, alias="S3_ENDPOINT")
    s3_access_key: Optional[str] = Field(default=None, alias="S3_ACCESS_KEY")
    s3_secret_key: Optional[str] = Field(default=None, alias="S3_SECRET_KEY")
    s3_bucket: Optional[str] = Field(default=None, alias="S3_BUCKET")

    @property
    def storage_path(self) -> Path:
        p = Path(self.local_dir)
        if not p.is_absolute():
            p = PROJECT_ROOT / p
        p.mkdir(parents=True, exist_ok=True)
        return p


class SessionSettings(BaseSettings):
    """会话管理配置"""
    model_config = SettingsConfigDict(env_prefix="SESSION_", env_file=".env", extra="ignore")

    backend: Literal["memory", "sqlite", "postgres"] = Field(default="memory")
    max_history_rounds: int = Field(default=15, description="短期记忆保留轮数")
    ttl_seconds: int = Field(default=3600, description="会话过期时间(秒)")
    longterm_memory_ttl_days: int = Field(default=30, description="长期记忆生命周期(天)")


class ServerSettings(BaseSettings):
    """服务配置"""
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)
    ws_heartbeat_interval: int = Field(default=30, alias="WS_HEARTBEAT_INTERVAL")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    environment: Literal["development", "staging", "production"] = Field(default="development", alias="ENVIRONMENT")

    @property
    def is_development(self) -> bool:
        return self.environment == "development"


class Settings(BaseSettings):
    """全局配置聚合"""
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm: LLMSettings = Field(default_factory=LLMSettings)
    multimodal: MultimodalSettings = Field(default_factory=MultimodalSettings)
    ragflow: RAGFlowSettings = Field(default_factory=RAGFlowSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    session: SessionSettings = Field(default_factory=SessionSettings)
    server: ServerSettings = Field(default_factory=ServerSettings)

    # 确认断点超时
    confirmation_timeout: int = Field(default=30, description="确认断点超时(秒)")

    # 首次 SELECT 展示字段数
    default_visible_fields: int = Field(default=5, description="首次查询默认展示字段数")

    # Skills 注册表 (Skill名称 → 描述)
    skill_registry: dict[str, str] = Field(default_factory=lambda: {
        "Common_Data_Query": "数据库表增删改查：查询、插入、更新、删除数据表记录。用于用户需要查看或修改具体数据内容的场景。",
        "Common_Graph_Generate": "数据分析图生成：将数据转换为柱状图、折线图、饼图、瀑布图、甘特图等可视化图表。用于用户需要数据可视化分析的场景。",
        "Common_Data_Report_Generate": "数据表格报表生成：将数据查询结果生成Excel表格报表，支持样式预设。用于用户需要下载或导出数据报表的场景。",
        "PPT_Late_Release": "PPT生成：根据用户需求生成演示文稿，支持内容撰写、排版设计、动画效果。用于用户需要制作汇报PPT的场景。",
        "Common_KB_QA": "通用知识库问答：基于业务知识库回答通用业务问题。用于不属于以上任何数据操作场景的兜底问答。",
    })

    # ============================================================
    # v2 增强配置项
    # 来源: multi_agent_system_2.0/config.py
    # ============================================================

    # 产物文件存储（v2 增强: 独立的 artifact 目录）
    artifact_root: str = Field(default="artifacts", description="产物文件存储根目录（图表/报表/PPT）")

    # 测试配置
    test_mode: bool = Field(default=False, description="测试模式：true 时使用 mock 依赖")

    # ============================================================
    # @REAL_CODE: 以下配置项需要与真实环境对齐
    # 当前状态: 使用默认值
    # 目标实现: 从 .env 文件读取生产环境实际值
    # 优先级: 各配置项独立标注
    # ============================================================

    # Embedding 动态阈值
    embedding_min_threshold: float = Field(default=0.45, description="Skill路由最低相似度阈值")

    # 长期记忆触发关键词
    longterm_memory_triggers: list[str] = Field(default_factory=lambda: [
        "记住", "长久记住", "别忘了", "以后要用", "存起来", "这个很重要", "以后会用到",
    ])
    longterm_memory_delete_triggers: list[str] = Field(default_factory=lambda: [
        "不用记住", "忘了吧",
    ])

    # 上下文回溯触发关键词
    context_reset_triggers: list[str] = Field(default_factory=lambda: [
        "算了不查了", "换个问题", "重新来",
    ])
    context_restore_triggers: list[str] = Field(default_factory=lambda: [
        "回到刚才的问题", "继续之前的",
    ])

    # 敏感字段（无权限时过滤）
    sensitive_fields: list[str] = Field(default_factory=lambda: ["key1", "key2", "key3"])


@lru_cache()
def get_settings() -> Settings:
    """获取全局配置（带缓存）"""
    return Settings()
