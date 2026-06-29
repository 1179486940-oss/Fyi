# Multi-Agent 智能助手系统 — 完整说明文档

> **版本**: v0.1.0 | **技术栈**: LangGraph + LangChain + FastAPI + RAGFlow  
> **设计依据**: 紫微三合 × 中州派 命理方法论（设计手册.docx / agent设计手册.docx）

---

## 目录

1. [系统架构总览](#1-系统架构总览)
2. [快速开始](#2-快速开始)
3. [核心层详解](#3-核心层详解)
   - [3.1 LLM 统一接入 (llm_provider.py)](#31-llm-统一接入)
   - [3.2 知识库管理 (knowledge_manager.py)](#32-知识库管理)
   - [3.3 会话管理 (session_manager.py)](#33-会话管理)
   - [3.4 记忆管理 (memory_manager.py)](#34-记忆管理)
   - [3.5 Agent 基类 (agent_base.py)](#35-agent-基类)
   - [3.6 鉴权管理 (auth_manager.py)](#36-鉴权管理)
   - [3.7 边界判断 (guardrails.py)](#37-边界判断)
   - [3.8 反馈系统 (feedback_system.py)](#38-反馈系统)
4. [中间件层详解](#4-中间件层详解)
   - [4.1 WebSocket 管理器 (ws_manager.py)](#41-websocket-管理器)
   - [4.2 确认断点中间件 (confirmation_middleware.py)](#42-确认断点中间件)
5. [MCP 工具层详解](#5-mcp-工具层详解)
6. [Sub-Agent 详解](#6-sub-agent-详解)
   - [6.1 Agent 1: Data_Query_Agent](#61-agent-1-data_query_agent)
   - [6.2 Agent 2: Data_Graph_Agent](#62-agent-2-data_graph_agent)
   - [6.3 Agent 3: Data_Report_Agent](#63-agent-3-data_report_agent)
   - [6.4 Agent 4: PPT_Generate_Agent](#64-agent-4-ppt_generate_agent)
   - [6.5 Agent 5: Fallback_Agent](#65-agent-5-fallback_agent)
7. [主路由 Agent 详解](#7-主路由-agent-详解)
8. [API 接口文档](#8-api-接口文档)
9. [配置指南](#9-配置指南)
10. [扩展开发指南](#10-扩展开发指南)

---

## 1. 系统架构总览

```
                          ┌─────────────────────────┐
                          │     用户 / 前端           │
                          │  HTTP POST  /  WebSocket │
                          └───────────┬─────────────┘
                                      │
                          ┌───────────▼─────────────┐
                          │   main.py (FastAPI)      │
                          │   /chat  /ws  /feedback  │
                          └───────────┬─────────────┘
                                      │
                    ┌─────────────────▼─────────────────┐
                    │     Router Agent (LangGraph)       │
                    │                                    │
                    │  trigger_kw → multimodal → intent  │
                    │       │           │          │      │
                    │       ▼           ▼          ▼      │
                    │  single_dispatch  multi    clarify  │
                    │       │           │          │      │
                    │       ▼           ▼          ▼      │
                    │   aggregate ←──┘          END      │
                    │       │                             │
                    │       ▼                             │
                    │   fallback → END                    │
                    └───┬───────┬───────┬───────┬───────┘
                        │       │       │       │
              ┌─────────▼┐ ┌────▼──┐ ┌──▼────┐ ┌▼────────┐
              │Data_Query│ │Data_  │ │Data_  │ │PPT_      │  ┌──────────┐
              │Agent     │ │Graph  │ │Report │ │Generate  │  │Fallback  │
              │          │ │Agent  │ │Agent  │ │Agent     │  │Agent     │
              └────┬─────┘ └───┬───┘ └───┬───┘ └────┬─────┘  └────┬─────┘
                   │           │         │          │             │
        ┌──────────▼───────────▼─────────▼──────────▼─────────────▼──────┐
        │                       MCP Servers                              │
        │  db_mcp  │  auth_mcp  │  chart_mcp  │  excel_mcp  │  ppt_mcp  │
        └──────────┴────────────┴─────────────┴─────────────┴───────────┘
                                      │
        ┌─────────────────────────────▼──────────────────────────────┐
        │                    RAGFlow 知识库                           │
        │  长期记忆KB │ 业务KB │ 反馈KB │ 数据库KB                     │
        └────────────────────────────────────────────────────────────┘
```

**核心设计原则**：
- **主 Agent 只管路由**，不处理任何业务逻辑，不生成任何回答
- **子 Agent 各司其职**，通过 Skill 组织业务能力，通过 MCP Server 调用外部资源
- **中间件统一拦截**写入操作，发送确认弹窗等待用户决策
- **知识库按需检索**，必检 + 可选模式，按权重拼接上下文

---

## 2. 快速开始

### 2.1 环境要求

- Python >= 3.10, < 3.13（推荐 3.11）
- PostgreSQL（开发阶段可使用 Mock 模式跳过）
- RAGFlow 平台（知识库存储与检索）

### 2.2 安装

```bash
cd multi_agent_system
pip install -r requirements.txt
```

### 2.3 配置

编辑 `.env` 文件，填入实际的服务地址和密钥：

```bash
# 必填项
LLM_API_KEY=your-beacon-api-key
RAGFLOW_API_KEY=your-ragflow-key
RAGFLOW_BASE_URL=https://ragflow.your-company.com/api/v1
KB_DATABASE=your-database-kb-id
KB_BUSINESS=your-business-kb-id
KB_FEEDBACK=your-feedback-kb-id
KB_LONGTERM_MEMORY=your-memory-kb-id
```

### 2.4 启动

```bash
python main.py
# 访问 http://localhost:8000/docs 查看 Swagger API 文档
# 访问 http://localhost:8000/health 健康检查
```

---

## 3. 核心层详解

### 3.1 LLM 统一接入

**文件**: `core/llm_provider.py`

#### 功能描述
统一管理所有 LLM 调用，屏蔽不同模型的差异，提供一致的 `chat()` 和 `chat_stream()` 接口。

#### 实现流程

```
调用方
  │
  ├─ chat(messages, model?) ──────► 1. 从缓存取模型实例
  │                                 2. 转换 messages → LangChain BaseMessage
  │                                 3. llm.ainvoke(messages)
  │                                 4. 返回 response.content
  │
  ├─ chat_stream(messages) ───────► 1. 同上
  │                                 2. llm.astream(messages)
  │                                 3. yield chunk.content (AsyncIterator)
  │
  ├─ understand_multimodal(file) ─► 1. 读取文件 → base64
  │                                 2. 构造 data: URL
  │                                 3. 调用 Qwen VL 模型（多模态）
  │                                 4. 返回提取的文本
  │
  └─ get_embedding(text) ────────► 1. 调用 text-embedding-3-small
                                    2. 返回 float[]
```

#### 使用方法

```python
from core.llm_provider import get_llm_provider

llm = get_llm_provider()

# 单次对话
response = await llm.chat(
    messages=[{"role": "user", "content": "查询销售额"}],
    model="deepseek-v4-pro",      # 可选，默认配置
    system_prompt="你是数据分析助手",
)

# 流式对话
async for chunk in await llm.chat_stream(messages):
    print(chunk, end="")

# 多模态理解（图片/PDF）
text = await llm.understand_multimodal(
    file_path="/path/to/report.pdf",
    file_type="pdf",
    context_query="提取报表中的销售数据",
)

# Embedding 向量化
embedding = await llm.get_embedding("数据查询")
similarity = llm.compute_similarity(vec1, vec2)  # 余弦相似度
```

#### 重试机制
使用 `tenacity` 库，失败自动重试 3 次（指数退避 1s→2s→4s）。

---

### 3.2 知识库管理

**文件**: `core/knowledge_manager.py`

#### 功能描述
封装 RAGFlow 检索接口，管理四类知识库的检索、语义去重、上下文拼接。

#### 四类知识库

| KB 类型 | top_k | 权重 | 生命周期 | 检索方式 | 触发条件 |
|---------|-------|------|---------|---------|---------|
| 数据库KB | 1 | 0.9 | 永久 | 语义+关键词 | 必检（数据类Agent） |
| 业务KB | 3-5 | 0.8 | 永久 | 语义+关键词 | 必检（PPT/Fallback） |
| 反馈KB | 3 | 1.0 | 永久 | 语义+关键词 | 触发才检 |
| 长期记忆KB | 3 | 0.7 | TTL 30天 | 语义+关键词 | 触发才检 |

#### 上下文拼接流程

```
原始 chunks (来自不同KB)
  │
  ├─ Step 1: 按权重降序排序
  │   反馈(1.0) > 数据库(0.9) > 业务(0.8) > 长期记忆(0.7)
  │
  ├─ Step 2: 语义去重
  │   相似度 > 0.9 的保留权重高的，删除权重低的
  │
  ├─ Step 3: 按拼接顺序分组
  │   原生KB → 长期记忆 → 反馈 → 数据库信息
  │
  ├─ Step 4: 拼接对话历史
  │   最终: 对话历史 + 原生KB + 长期记忆 + 反馈 + 数据库
  │
  └─ 注意: 没触发的KB对应段落不拼接
```

#### 使用方法

```python
from core.knowledge_manager import get_knowledge_manager

km = get_knowledge_manager()

# 单KB检索
chunks = await km.search("database", query="销售数据表", top_k=1)

# 多KB并行检索
results = await km.multi_search(
    kb_types=["database", "longterm_memory", "feedback"],
    query="上个月销售额",
    top_k_map={"database": 1, "longterm_memory": 3, "feedback": 3},
)

# 语义去重
deduped = km.deduplicate(all_chunks, threshold=0.9)

# 上下文拼接
context = km.assemble_context(deduped, conversation_history="...")

# 写入长期记忆
await km.write_to_longterm_memory(
    content="用户喜欢用折线图查看销售数据",
    summary="用户偏好：销售数据用折线图",
    session_id="sess_123",
    trigger_keyword="记住",
)

# 删除长期记忆
await km.delete_from_longterm_memory(
    session_id="sess_123",
    query="折线图偏好",
)
```

---

### 3.3 会话管理

**文件**: `core/session_manager.py`

#### 功能描述
管理用户会话的全生命周期：创建、查询、删除、权限更新、TTL 过期清理。每个会话独立隔离，通过 `session_id` 标识。

#### 会话数据结构

```python
Session:
  session_id: str          # 唯一会话ID (UUID7)
  user_id: str             # 用户ID
  history: list[dict]      # 对话历史 [{role, content}, ...]
  permissions: dict        # 子系统权限 {subsystem: bool}
  archived_history: list   # 上下文回溯时的存档
  is_clarifying: bool      # 是否处于澄清状态
  is_waiting_confirmation: bool  # 是否等待确认
```

#### 短期记忆窗口机制

```
对话轮次:  1  2  3  4  5  6  7  8  9 10 11 12 13 14 15 16 17 18 ...
                               ├────────── 窗口 (10-15轮) ──────┤
                               保留最近 20-30 条消息
                               超过窗口的最早消息自动丢弃
```

#### 使用方法

```python
from core.session_manager import get_session_manager

sm = get_session_manager()

# 创建会话
session = sm.create_session(
    user_id="user_001",
    permissions={"data_query": True, "data_graph": True, "data_report": False},
)

# 获取/创建（幂等）
session = sm.get_or_create(session_id, user_id="user_001")

# 权限检查
can_query = sm.has_permission(session.session_id, "data_query")

# 更新权限
sm.update_permissions(session_id, {"data_query": True, "ppt_generate": True})

# 清理过期会话
cleaned = sm.cleanup_expired()

# 删除会话
sm.delete_session(session_id)
```

---

### 3.4 记忆管理

**文件**: `core/memory_manager.py`

#### 功能描述
管理短期记忆（对话历史窗口）和长期记忆（RAGFlow 触发写入）。

#### 长期记忆触发机制

```
用户输入
  │
  ├─ 包含"记住"/"别忘了"/"以后要用"等触发词？
  │   YES → 1. 提取用户原话
  │         2. 生成摘要
  │         3. 写入 RAGFlow 长期记忆KB
  │         4. 返回 "✅ 已记住：xxx"
  │         5. 继续正常路由流程
  │
  ├─ 包含"不用记住"/"忘了吧"？
  │   YES → 1. 从 RAGFlow 检索相关内容
  │         2. 删除匹配的文档
  │         3. 返回 "✅ 已忘记相关内容"
  │
  └─ 无触发词 → 跳过，正常路由
```

#### 上下文回溯机制

```
用户说 "算了不查了" / "换个问题" / "重新来"
  → 检测到重置触发词
  → 存档当前历史到 archived_history
  → 清空 history（只保留当前Query）
  → 重新路由

用户说 "回到刚才的问题" / "继续之前的"
  → 检测到恢复触发词
  → 从 archived_history 恢复到 history
  → 继续路由
```

#### 使用方法

```python
from core.memory_manager import get_memory_manager

mm = get_memory_manager()

# 检测触发关键词
trigger = mm.detect_longterm_memory_trigger("请记住我喜欢饼图")
# 返回: "记住"

# 检测删除触发
trigger = mm.detect_delete_trigger("忘了上面的偏好设置")
# 返回: "忘了吧"

# 获取短期记忆上下文
context = mm.get_short_term_context(session)
# 返回: "用户: 查一下销售数据\n助手: 好的，已查询..."

# 添加一轮对话
mm.add_to_short_term(session, user_query="查数据", assistant_response="查询结果...")

# 写入长期记忆（含触发检测）
msg = await mm.try_write_longterm_memory("记住我喜欢蓝色主题", session)
# 返回: "✅ 已记住：我喜欢蓝色主题"

# 删除长期记忆
msg = await mm.try_delete_longterm_memory("忘了蓝色主题", session)
# 返回: "✅ 已忘记相关内容"

# 检测上下文重置/恢复
mm.detect_context_reset("重新来")   # True
mm.detect_context_restore("继续之前的")  # True
```

---

### 3.5 Agent 基类

**文件**: `core/agent_base.py`

#### 功能描述
所有子 Agent 的抽象基类，采用**模板方法模式**定义统一的执行骨架。子类只需覆写 `process()` 方法即可。

#### 执行流程（模板方法）

```
用户 Query
  │
  ▼
execute(query, multimodal_files?)        ← 模板方法入口
  │
  ├─ 1. 获取/创建会话 (SessionManager)
  │
  ├─ 2. 多模态处理 (如有图片/PDF)
  │     └── 调用 Qwen VL 提取文本 → 拼入 Query
  │
  ├─ 3. 加载上下文 load_context()
  │     ├── 短期记忆 (最近 10-15 轮对话)
  │     └── 知识库检索 (按子类配置)
  │
  ├─ 4. 核心业务处理 process()          ← 子类覆写
  │     └── 返回 {"status": ..., "content": ...}
  │
  ├─ 5. 更新短期记忆
  │     └── 添加 user/assistant 消息到会话历史
  │
  └─ 6. 返回结果
```

#### 子类需要覆写的属性/方法

```python
class MyAgent(BaseAgent):
    agent_name = "my_agent"                  # Agent 名称
    agent_description = "处理XXX业务"         # 功能描述

    # 知识库检索配置
    kb_search_config = {
        "database": {"top_k": 1, "required": True},       # 必检
        "longterm_memory": {"top_k": 3, "required": False}, # 触发才检
        "feedback": {"top_k": 3, "required": False},
    }

    async def process(self, query, context) -> dict:
        # 核心业务逻辑
        return {"status": "success", "content": "..."}
```

#### 内置便捷方法

```python
# 确认断点
confirmed = await self._breakpoint_confirm(
    operation="UPDATE",
    table="sales_data",
    found_data=[{"id": 1, "status": "运行中"}],
    changes={"status": "终止"},
)
# 返回 True/False

# LLM 调用
response = await self._call_llm(context, user_query, system_prompt="...")
async for chunk in self._call_llm_stream(context, query):
    await self.push_stream(chunk)

# 思考过程展示
self.display_thought("分析中...")   # → <thinking>分析中...</thinking>
self.display_url("http://...")      # → <url>http://...</url>

# 消息推送
await self.push_stream("部分内容", is_final=False)
await self.push_clarification("请问您要查哪个时间段的数据？")
```

---

### 3.6 鉴权管理

**文件**: `core/auth_manager.py`

#### 实现流程

```
用户请求
  │
  ├─ 开发环境 (ENVIRONMENT=development)
  │   └── 自动通过所有鉴权，不做过滤
  │
  └─ 正式环境
      │
      ├─ 子系统级鉴权
      │   └── 调用 SSO 鉴权接口 → 检查用户对子系统的权限
      │
      ├─ 数据字段级鉴权
      │   └── 无权限时过滤 key1 / key2 / key3 敏感字段
      │
      └─ 鉴权失败
          └── 返回 "⚠️ 没有访问权限"，终止后续流程
```

#### 使用方法

```python
from core.auth_manager import get_auth_manager

auth = get_auth_manager()

# 子系统权限检查
has_access = await auth.check_subsystem_permission("user_001", "data_query")

# 会话权限检查
can_access = auth.check_session_permission("session_123", "data_graph")

# 敏感字段过滤
filtered = auth.filter_sensitive_fields(
    records=[{"name": "张三", "key1": "敏感1", "key2": "敏感2"}],
    user_id="user_001",
    table="employees",
)
# 返回: [{"name": "张三"}]  ← key1, key2 被移除
```

---

### 3.7 边界判断

**文件**: `core/guardrails.py`

#### 意图识别全流程

```
用户 Query
  │
  ├─ Step 0: 上下文回溯检测
  │   包含"重新来/换个问题" → 标记重置
  │   包含"继续/回到刚才"  → 标记恢复
  │
  ├─ Step 1: 多意图检测
  │   包含"然后/同时/另外/还有" → 拆分为多个子意图
  │
  ├─ Step 2: Embedding 相似度打分
  │   用户Query ⇄ 每个Skill的description 计算余弦相似度
  │   Common_Data_Query        → 0.82
  │   Common_Graph_Generate    → 0.34
  │   Common_Data_Report_Generate → 0.28
  │   PPT_Late_Release         → 0.12
  │
  ├─ Step 3: 动态阈值过滤
  │   max_score > 0.8 → 阈值提高至 0.55（精准匹配）
  │   max_score < 0.4 → 阈值降低至 0.30（防止漏网）
  │   否则 → 默认阈值 0.45
  │
  ├─ Step 4: 边界消歧
  │   Top1 和 Top2 差距 < 0.05？
  │   YES → 用 LLM 分析 Skill description 界定文字区分
  │
  ├─ Step 5: 澄清判断
  │   全部低于阈值？
  │   YES → 检查：Query < 5字？包含模糊词？
  │         → 必要时触发澄清
  │         → 否则走兜底
  │
  └─ Step 6: 返回 IntentResult
```

#### 使用方法

```python
from core.guardrails import get_guardrails

gr = get_guardrails()

# 意图识别
result = await gr.recognize_intent("把上个月销售数据做成柱状图")

print(result.is_single_intent)      # True
print(result.best_match.skill_name) # "Common_Graph_Generate"
print(result.best_match.similarity) # 0.76
print(result.needs_fallback)        # False
print(result.is_clarification_needed) # False

# 多意图
result = await gr.recognize_intent("查销售数据然后生成报表")
print(result.is_single_intent)  # False
print(len(result.multi_intent_groups))  # 2
```

---

### 3.8 反馈系统

**文件**: `core/feedback_system.py`

#### 实现流程

```
前端 feedback 按钮
  │
  ├─ 用户点击 👍 / 👎 或输入文字反馈
  │
  ├─ POST /feedback {question, answer, feedback, session_id}
  │
  ├─ FeedbackSystem.record_feedback()
  │   ├── 构造 FeedbackRecord
  │   └── 写入 RAGFlow 反馈KB (chunk格式)
  │       {question, answer, feedback, rating, session_id, agent_name, timestamp}
  │
  └─ 反馈内容在后续对话中作为上下文
      触发关键词匹配时检索 top_k=3
      权重 1.0（最高优先级）
```

#### 使用方法

```python
from core.feedback_system import get_feedback_system

fs = get_feedback_system()

# 记录反馈
await fs.record_feedback(
    question="上个月销售额是多少",
    answer="上个月销售额为 1,234,567 元",
    feedback="thumbs_up",      # 或 "thumbs_down" 或具体文字
    session_id="sess_123",
    user_id="user_001",
    agent_name="data_query",
    rating=5,
)

# 检索历史反馈
chunks = await fs.search_feedback("销售额查询", top_k=3)
```

---

## 4. 中间件层详解

### 4.1 WebSocket 管理器

**文件**: `middleware/ws_manager.py`

#### 核心机制：asyncio.Future 挂起/唤醒

这是确认断点的底层实现基础。整个机制依赖 Python 的异步 Future：

```
后端                                    前端
  │                                       │
  │── push_to_user(confirmation_payload)──► 弹出确认弹窗
  │                                       │
  │── Future挂起 (await future)            │  用户看到弹窗
  │   ...等待最多30秒...                    │  点击"确认"或"取消"
  │                                       │
  │◄── POST /confirm/{id} ────────────────│  回调
  │                                       │
  │── future.set_result({status})          │
  │── 唤醒，返回 confirmed/cancelled       │
```

#### WebSocket 连接生命周期

```
前端连接 WS /ws/{session_id}
  │
  ├─ ws_manager.connect(session_id, websocket)
  │   ├── 关闭该 session 的旧连接（如有）
  │   └── 注册到连接池
  │
  ├─ 双向消息循环
  │   ├── type: "chat"    → 路由到 Router Agent
  │   ├── type: "confirm" → 唤醒对应的 Future
  │   └── type: "ping"    → 回复 pong
  │
  └─ 断开连接
      └── ws_manager.disconnect(session_id)
          ├── 关闭 WebSocket
          └── 清理该 session 的所有待确认请求
```

#### 使用方法

```python
from middleware.ws_manager import get_ws_manager

ws = get_ws_manager()

# 推送消息
await ws.push_to_user(session_id, {"type": "info", "content": "处理中..."})

# 确认断点 (会挂起等待)
result = await ws.request_confirmation(
    session_id="sess_123",
    operation_type="UPDATE",
    table="sales",
    affected_data=[{"id": 1, "status": "运行中"}],
    changes={"status": "终止"},
    timeout=30,
)
# result: {"status": "confirmed"} or {"status": "cancelled"} or {"status": "timeout"}

# 前端回调 (由 HTTP API 调用)
ws.resolve_confirmation(confirm_id, {"status": "confirmed"})

# 流式内容推送
await ws.push_stream_chunk(session_id, "正在为您查询数据", is_final=False)
await ws.push_stream_chunk(session_id, "", is_final=True)

# 推送澄清问题
await ws.push_stream_chunk(session_id, "请问您要查哪个时间段？", is_clarification=True)
```

---

### 4.2 确认断点中间件

**文件**: `middleware/confirmation_middleware.py`

#### 设计依据

采用**方案 A + 方案 C** 组合：

| 方案 | 位置 | 作用 |
|------|------|------|
| 方案 A | 子 Agent 内部 | Agent 在 execute() 中调用 `_breakpoint_confirm()` |
| 方案 C | 中间件拦截层 | ConfirmationMiddleware 统一管理确认逻辑 |

#### 完整确认流程

```
用户: "把状态表里运行中改为终止"
  │
  ▼
Router Agent → 意图识别 → data_query_agent
  │
  ▼
Data_Query_Agent.process()
  │
  ├─ 1. 检索数据KB → 获取表结构
  ├─ 2. LLM 生成 SQL: UPDATE status_table SET status='终止' WHERE status='运行中'
  ├─ 3. 检测到 UPDATE → 进入确认断点
  │
  ├─ 4. 先执行 SELECT 预览受影响数据
  │     SELECT * FROM status_table WHERE status='运行中'
  │     → 找到 5 条记录
  │
  ├─ 5. 调用 confirmation_middleware.intercept()
  │     ├── 生成 confirm_id
  │     ├── 构造 payload:
  │     │   {type: "confirmation_request",
  │     │    operation: "UPDATE",
  │     │    table: "status_table",
  │     │    affected_data: [{id:1, name:"A", status:"运行中"}, ...(前5条)],
  │     │    changes: {status: "终止"}}
  │     ├── WebSocket 推送到前端 ──────► 前端弹窗显示
  │     └── asyncio.Future 挂起等待
  │
  ├─ 6a. 用户点击「确认」
  │     ├── POST /confirm/{id} status=confirmed
  │     ├── Future 被唤醒
  │     └── 返回 ConfirmationResult(status="confirmed")
  │         → 执行 UPDATE
  │
  ├─ 6b. 用户点击「取消」
  │     └── 返回 ConfirmationResult(status="cancelled")
  │         → 终止操作，返回 "❌ 操作已取消"
  │
  └─ 6c. 30秒超时
        └── 返回 ConfirmationResult(status="timeout")
            → 自动取消，返回 "⏰ 操作已超时取消"
```

#### 展示规则

- **批量修改**：只展示要变更的字段 + 索引字段，其余字段省略
- **批量显示**：超过 5 条记录只展示前 5 条作为示例，标记 "共 X 条"
- **表头过长**：只展示要变更的字段和索引字段

#### 使用方法

```python
from middleware.confirmation_middleware import get_confirmation_middleware

cf = get_confirmation_middleware()

# 通用拦截
result = await cf.intercept(
    operation_type="UPDATE",
    table="employees",
    affected_data=[{"id": 1, "name": "张三", "dept": "技术部"}],
    changes={"dept": "产品部"},
    session_id="sess_123",
)
if result.is_confirmed:
    # 执行写操作
    pass
else:
    # 返回取消消息
    pass

# 便捷方法
result = await cf.confirm_update("sales", affected, changes, session_id)
result = await cf.confirm_insert("sales", new_data, session_id)
result = await cf.confirm_delete("sales", affected, session_id)
```

---

## 5. MCP 工具层详解

### 5.1 工具总览

| MCP Server | 文件 | 核心方法 | 产出 |
|------------|------|---------|------|
| DB MCP | `mcp/db_mcp.py` | `execute_query()`, `execute_write()`, `get_table_schema()` | 数据结果 |
| Auth MCP | `mcp/auth_mcp.py` | `check_data_permission()`, `filter_fields()` | 鉴权结果 |
| Chart MCP | `mcp/chart_mcp.py` | `generate_line_chart()`, `generate_bar_chart()`, `generate_pie_chart()` | PNG/HTML 图表 |
| Excel MCP | `mcp/excel_mcp.py` | `generate_excel()` | .xlsx 文件 |
| PPT Query MCP | `mcp/ppt_query_mcp.py` | `query_ppt_data()`, `get_template_list()` | PPT 数据 |
| PPT Generate MCP | `mcp/ppt_generate_mcp.py` | `generate_ppt()` | .pptx 文件 |

### 5.2 DB MCP 使用示例

```python
from agents.sub_agents.mcp.db_mcp import DatabaseMCP

db = DatabaseMCP()

# 查询
result = await db.execute_query(
    "SELECT * FROM sales WHERE date >= '2026-06-01'",
    max_preview_fields=5,  # 默认展示前5个字段
)
# result: {"columns": [...], "rows": [...], "preview": "表格文本", "full_table": "..."}

# 写操作（确认后调用）
result = await db.execute_write("UPDATE sales SET status='done' WHERE id=1")
# result: {"status": "success", "rows_affected": 1, "message": "UPDATE 1"}

# 获取表结构
schema = await db.get_table_schema("sales")

# 列出所有表
tables = await db.list_tables()

# Mock 模式（开发阶段自动使用）
result = await db.mock_execute("SELECT * FROM sales")
```

### 5.3 Chart MCP 使用示例

```python
from agents.sub_agents.mcp.chart_mcp import ChartMCP

chart = ChartMCP()

# 生成折线图
result = await chart.generate_line_chart(
    data=[{"date": "2026-06-01", "sales": 1000}, ...],
    x_field="date",
    y_field="sales",
    title="6月销售趋势",
    output_format="html",  # html (交互) 或 png (静态)
)
# result: {"status": "success", "download_url": "http://...", "format": "html"}

# 生成柱状图
result = await chart.generate_bar_chart(data, "dept", "count", "部门统计")

# 生成饼图
result = await chart.generate_pie_chart(data, "category", "amount", "占比分析")
```

### 5.4 Excel MCP 使用示例

```python
from agents.sub_agents.mcp.excel_mcp import ExcelMCP

excel = ExcelMCP()

# 生成 Excel
result = await excel.generate_excel(
    data=[{"name": "产品A", "sales": 1000}, ...],
    sheet_name="销售数据",
    title="2026年6月销售报表",
    style_preset="executive",  # standard / compact / colorful
)

# 添加自定义样式预设
excel.add_style_preset("my_style", {
    "font_size": 14,
    "header_color": "FF0000",
    "border": True,
})

# 列出所有预设
presets = excel.list_presets()
# ['default', 'compact', 'colorful']
```

### 5.5 MCP 注册中心

```python
from tools.mcp_servers import get_mcp_registry

registry = get_mcp_registry()

# 查看所有已注册的 MCP Server
print(registry.registered_names)

# 获取特定 Server
db = registry.get("db_mcp")
```

---

## 6. Sub-Agent 详解

### 6.1 Agent 1: Data_Query_Agent

**文件**: `agents/sub_agents/data_query_update_agent.py`

#### 核心职责
数据表增删改查 — 整个系统的数据操作核心。

#### 双 Skill 架构

```
Data_Query_Agent
  │
  ├─ Skill: NSG_Borrow_Data_Process
  │   (处理 NSG 数据表的标准 CRUD 流程)
  │   模块一: 检索数据KB (必检 top_k=1)
  │   模块二: 触发关键词 → 可选长期记忆 + 反馈 KB
  │   模块三: 上下文拼接
  │   模块四: 数据鉴权 + 敏感字段过滤
  │   模块五: Text2SQL 生成与执行
  │   模块六: 首次查询展示前5个字段
  │
  └─ Skill: Comment_Data_Process
      (处理 Comment 数据表的 CRUD 流程)
      同 NSG，但针对 Comment 表的特定逻辑
```

#### 完整执行流程

```
用户: "查询上个月的销售记录"
  │
  ▼
Step 1: 判断流程类型
  检测关键词 "评论/留言/回复" → Comment 流程
  否则 → NSG 流程
  │
  ▼
Step 2: 检索数据KB (top_k=1)
  RAGFlow → 返回 sales 表 DDL + 字段含义 + 示例数据
  │
  ▼
Step 3: 触发关键词检测
  "查询上个月的销售记录" → 无触发词 → 跳过
  (如果是 "记住我喜欢查销售表" → 写入长期记忆)
  │
  ▼
Step 4: 鉴权
  检查用户是否有 data_query 子系统权限
  无权限 → 返回错误提示
  有权限 → 继续
  │
  ▼
Step 5: Text2SQL
  LLM 根据表结构和用户Query生成 SQL:
  SELECT * FROM sales WHERE date >= '2026-05-01' AND date < '2026-06-01'
  │
  ▼
Step 6: 执行
  判断 SQL 类型:
  ├─ SELECT → 直接执行
  │   └── 返回结果（默认展示前5个字段）
  │       "id | name | amount | date | status | ... (+8字段)"
  │       "💡 共 13 个字段，当前展示前 5 个。如需查看其他字段，请追问。"
  │
  └─ UPDATE/INSERT/DELETE → 进入确认断点
      ├── 先执行 SELECT 预览受影响数据
      ├── 推确认弹窗到前端
      ├── 等待用户确认
      ├── 确认 → 执行写操作
      └── 取消 → 终止操作
```

#### 使用方法

```python
from agents.sub_agents.data_query_update_agent import DataQueryAgent

agent = DataQueryAgent(session_id="sess_123", user_id="user_001")

result = await agent.execute(
    query="查询销售表里上个月的数据",
    multimodal_files=None,  # 可选，上传文件时传入
)

# result:
# {
#   "status": "success",
#   "content": "<thinking>意图：数据查询 → SQL: SELECT * FROM sales...</thinking>\n\n
#               查询结果：\n\nid | name | amount | date | status | ... (+8字段)\n
#               💡 共 13 个字段，当前展示前 5 个。如需查看其他字段，请追问。",
#   "sql": "SELECT * FROM sales WHERE date >= '2026-05-01'...",
#   "data": {"columns": [...], "rows": [...], "row_count": 42}
# }
```

#### 首次查询展示规则

```
字段数 ≤ 5:   全部展示
字段数 6-10:  展示前5个 + 提示追问
字段数 > 10:  展示前5个 + 标注隐藏字段数 + 引导追问
```

---

### 6.2 Agent 2: Data_Graph_Agent

**文件**: `agents/sub_agents/data_graph_agent.py`

#### 核心职责
根据数据查询结果生成数据分析图（柱状图、折线图、饼图、瀑布图、甘特图）。

#### Report Version 匹配流程（核心特色）

这是 Data_Graph_Agent 区别于其他 Agent 的独有机制：

```
用户: "上个月A12车型SW22周的效率数据用折线图展示"
  │
  ▼
Step 1: 数据鉴权
  │
  ▼
Step 2: 提取三要素
  正则提取:
  ├─ 日期:  20260611  (8位数字)
  ├─ 车型:  A12       (字母+数字)
  └─ 周数:  SW22      (SW+数字)
  │
  ▼
Step 3: 查询 Report Version 全集
  SELECT DISTINCT "Report Version" FROM report_data
  → ["20260611_A12_SW22", "20260611_A13_SW22",
     "20260611_A12_SW23", "20260610_A12_SW22", "20260611_A14_SW21"]
  │
  ▼
Step 4: 模糊匹配打分
  20260611_A12_SW22: 日期✓ + 车型✓ + 周数✓ = 3分 → 精确命中！
  20260611_A13_SW22: 日期✓ + 周数✓ = 2分
  20260611_A12_SW23: 日期✓ + 车型✓ = 2分
  20260610_A12_SW22: 车型✓ + 周数✓ = 2分
  20260611_A14_SW21: 日期✓ = 1分
  │
  ▼
Step 5: 分支
  ├─ 精确命中 (≥3分) → 直接使用该 Report Version
  │
  └─ 无精确命中 → Top 3 候选
      ├── 中断确认 (double confirm)
      ├── 弹窗展示 Top 3 候选供用户选择
      ├── 用户点选 → 确定 Report Version
      └── 继续后续流程
  │
  ▼
Step 6: 以 Report Version 查询数据
  SELECT * FROM report_data WHERE "Report Version" = '20260611_A12_SW22'
  │
  ▼
Step 7: 生成图表
  自动判断图表类型:
  "折线图" → CommonGraphGenerate.generate(chart_type="line")
  ├── 复用 CommonDataQuery 查数据
  ├── 调用 chart_mcp 生成图表
  └── 返回 PNG/HTML 下载链接
```

#### 使用方法

```python
from agents.sub_agents.data_graph_agent import DataGraphAgent

agent = DataGraphAgent(session_id="sess_123", user_id="user_001")

result = await agent.execute(
    query="20260611 A12 SW22 的效率数据用折线图展示",
)
# result:
# {
#   "status": "success",
#   "content": "<thinking>数据查询完成（42条）→ 生成line图</thinking>\n\n
#               📊 图表已生成 [<url>http://localhost:8000/files/xxx/download</url>](http://...)",
#   "download_url": "http://localhost:8000/files/xxx/download",
#   "chart_type": "line"
# }

# 模糊匹配场景（需要用户选择时）
# result:
# {
#   "status": "need_confirm",
#   "content": "请选择一个 Report Version：\n1. 20260611_A12_SW22\n2. 20260611_A13_SW22\n3. 20260611_A12_SW23",
#   "candidates": ["20260611_A12_SW22", "20260611_A13_SW22", "20260611_A12_SW23"]
# }
```

---

### 6.3 Agent 3: Data_Report_Agent

**文件**: `agents/sub_agents/data_report_agent.py`

#### 核心职责
根据数据查询结果生成 Excel 表格报表，支持样式预设。

#### 完整执行流程

```
用户: "生成上个月销售数据的高管简报"
  │
  ▼
Step 1: 鉴权
  │
  ▼
Step 2: 类型范围分析 (TypeRangeJudgment)
  LLM 分析用户Query → 提取:
  {
    "data_type": "销售数据",
    "time_range": "上个月",
    "group_by": "按日期",
    "order_by": "降序",
    "filters": []
  }
  │
  ▼
Step 3: 复用 CommonDataQuery 查询数据
  检索数据KB → 生成SQL → 执行查询
  │
  ▼
Step 4: 样式预设匹配 (PresetManager)
  "高管简报" → 匹配 executive 预设
  {
    name: "高管简报",
    style: "compact",      ← 传给 Excel MCP
    columns: "key",        ← 关键字段
    sort: "desc"           ← 降序
  }
  │
  ▼
Step 5: 生成 Excel
  调用 excel_mcp.generate_excel(data, style_preset="compact")
  ↓
  产出 .xlsx 文件 → 存储到本地/S3 → 返回下载链接
  │
  ▼
Step 6: 返回结果
  📊 报表已生成 [下载链接]
  样式：高管简报 | 数据量：42 条
```

#### 三种样式预设

| 预设 | 场景 | 字号 | 表头色 | 特点 |
|------|------|------|--------|------|
| standard | 日常报表 | 11pt | 蓝色 | 适合日常数据报表 |
| executive | 高管简报 | 10pt | 深蓝 | 紧凑排版，重点突出 |
| colorful | 详细分析 | 12pt | 橙色 | 彩色标注，适合深度分析 |

#### 使用方法

```python
from agents.sub_agents.data_report_agent import DataReportAgent

agent = DataReportAgent(session_id="sess_123", user_id="user_001")

result = await agent.execute(
    query="生成一份上个月的销售详细分析报表",
)
# result:
# {
#   "status": "success",
#   "content": "<thinking>数据查询（42条）→ 应用 详细分析 样式 → 生成 Excel</thinking>\n\n
#               📊 报表已生成 [<url>...</url>](...)\n样式：详细分析 | 数据量：42 条",
#   "download_url": "http://localhost:8000/files/xxx/download",
#   "row_count": 42,
#   "preset": {"name": "详细分析", "style": "colorful"}
# }
```

---

### 6.4 Agent 4: PPT_Generate_Agent

**文件**: `agents/sub_agents/ppt_generate_agent.py`

#### 核心职责
根据用户需求生成 PPT，通过 BA 提供的两个 MCP Server（接口1数据查询 + 接口2 PPT生成）实现。

#### 模板边界判断机制

```
用户Query
  │
  ▼
关键词匹配 (边界判断规则)
  │
  ├─ "汇报/工作/总结/周报/月报/年报" → 工作汇报模板 (10页)
  ├─ "数据/分析/图表/统计/指标"    → 数据分析模板 (8页)
  ├─ "方案/策划/计划/规划/提案"    → 方案策划模板 (12页)
  ├─ "产品/介绍/展示/演示/说明"    → 产品介绍模板 (6页)
  └─ 都不匹配                     → 通用模板 (默认)
```

#### 完整执行流程

```
用户: "做一个产品介绍的PPT"
  │
  ▼
Step 1: 鉴权 → 检查 PPT 子系统权限
  │
  ▼
Step 2: 模板匹配 (边界判断)
  ├── 查询模板列表 (ppt_query_mcp)
  ├── 关键词 "产品/介绍" → 匹配 "产品介绍" 模板 (tpl_004)
  └── 获取模板详情
  │
  ▼
Step 3: 业务KB检索 (必检 top_k=3)
  检索相关业务知识作为PPT内容参考
  │
  ▼
Step 4: 生成大纲 (OutlineSkill)
  LLM 根据 Query + 模板 + 业务知识 → 生成PPT大纲
  │
  ▼
Step 5: 查询PPT数据 (ppt_query_mcp / 接口1)
  调用 BA 接口1 → 获取生成PPT所需的业务数据
  │
  ▼
Step 6: 生成PPT (ppt_generate_mcp / 接口2)
  调用 BA 接口2 → 传入 模板ID + 大纲 + 数据
  │
  ▼
Step 7: 返回下载链接
  📊 PPT 已生成 [下载链接]
  模板：产品介绍
```

#### 5个配套 Skill

| Skill | 文件 | 职责 |
|-------|------|------|
| Content | `content_skill.py` | PPT 内容撰写 |
| Outline | `outline_skill.py` | PPT 大纲结构生成 |
| Design | `design_skill.py` | 设计排版（主题/配色） |
| Layout | `layout_skill.py` | 布局设计（封面/目录/分页） |
| Animation | `animation_skill.py` | 动画效果配置 |

#### 使用方法

```python
from agents.sub_agents.ppt_generate_agent import PPTGenerateAgent

agent = PPTGenerateAgent(session_id="sess_123", user_id="user_001")

result = await agent.execute(
    query="做一个产品介绍的PPT，重点讲产品的核心功能",
)
# result:
# {
#   "status": "success",
#   "content": "<thinking>选用模板「产品介绍」→ 生成大纲 → 调用PPT生成接口</thinking>\n\n
#               📊 PPT 已生成 [<url>...</url>](...)\n模板：产品介绍",
#   "download_url": "http://localhost:8000/files/xxx/download",
#   "template": {"id": "tpl_004", "name": "产品介绍", "category": "产品展示", "pages": 6}
# }
```

---

### 6.5 Agent 5: Fallback_Agent

**文件**: `agents/sub_agents/fallback_agent.py`

#### 核心职责
当用户 Query 不属于任何业务 Agent 的场景时，走通用知识库问答路线。

#### 触发条件

```
所有 Skill 的 Embedding 相似度都低于动态阈值
  │
  └── Router 判断: 这不是任何业务场景
      │
      ├── Query 模糊? → 进入澄清状态 (Clarify Node)
      └── Query 清晰但不匹配? → 路由到 Fallback_Agent
```

#### 执行流程

```
Fallback_Agent.process()
  │
  ├─ 模块一: 必检业务KB (top_k=5)
  │   RAGFlow → 业务知识库检索
  │
  ├─ 模块二: 触发关键词检测
  │   有触发词 → 可选检索长期记忆KB + 反馈KB (top_k=3)
  │   无触发词 → 跳过
  │
  ├─ 模块三: 上下文拼接
  │   权重排序: 反馈(1.0) > 业务(0.8) > 长期记忆(0.7)
  │   语义去重 (>0.9)
  │   拼接顺序: 原生KB → 长期记忆 → 反馈
  │   ⚠️ 注意: Fallback不检索数据库KB
  │
  ├─ LLM 生成回答
  │
  └─ 如果连业务KB都没有内容
      → 引导用户尝试其他业务功能
```

#### 与其他 Agent 的知识库差异

| | Data_Query | Data_Graph | Data_Report | PPT_Generate | Fallback |
|------|-----------|-----------|------------|-------------|---------|
| 数据KB | ✅ top_k=1 | ✅ top_k=1 | ✅ top_k=1 | ❌ | ❌ |
| 业务KB | ❌ | ❌ | ❌ | ✅ top_k=3 | ✅ top_k=5 |
| 长期记忆 | 触发 top_k=3 | 触发 top_k=3 | 触发 top_k=3 | 触发 top_k=3 | 触发 top_k=3 |
| 反馈KB | 触发 top_k=3 | 触发 top_k=3 | 触发 top_k=3 | 触发 top_k=3 | 触发 top_k=3 |

#### 使用方法

```python
from agents.sub_agents.fallback_agent import FallbackAgent

agent = FallbackAgent(session_id="sess_123", user_id="user_001")

result = await agent.execute(
    query="公司的核心价值观是什么？",  # 不属于任何业务场景
)
# → 从业务KB检索 → LLM 基于业务知识回答
```

---

## 7. 主路由 Agent 详解

**文件**: `agents/router_agent.py`

### 7.1 LangGraph 状态图

Router Agent 是整个系统的调度中枢，使用 LangGraph 构建 **7 节点状态图**：

```
                         ┌─────────────┐
                         │   START     │
                         └──────┬──────┘
                                │
                    ┌───────────▼───────────┐
                    │  Node 1: trigger_kw   │ ← 全局必做
                    │  检测"记住/忘了"关键词  │
                    │  写入/删除长期记忆KB    │
                    └───────────┬───────────┘
                                │
                    ┌───────────▼───────────┐
                    │  Node 2: multimodal   │ ← 有文件时执行
                    │  Qwen VL 提取图片/PDF  │
                    │  文本拼入 Query        │
                    └───────────┬───────────┘
                                │
                    ┌───────────▼───────────┐
                    │  Node 3: intent       │ ← 核心决策
                    │  Embedding 相似度打分   │
                    │  边界判断/澄清/回溯     │
                    └───────────┬───────────┘
                                │
                  ┌─────────────┼─────────────┐
                  │             │             │
        ┌─────────▼──┐  ┌──────▼──────┐  ┌───▼──────────┐
        │ Node 4a:   │  │ Node 4b:    │  │ Node 6:      │
        │ single_    │  │ multi_      │  │ clarify      │
        │ dispatch   │  │ split       │  │ 返回澄清问题   │
        │ 鉴权→单路由 │  │ 拆分→并行分发 │  │ +标识字段     │
        └─────┬──────┘  └──────┬──────┘  └──────────────┘
              │                │
              │         ┌──────▼──────┐
              │         │ Node 5:     │
              └─────────► aggregate   │ ← 结果聚合
                        │ LLM Summary │
                        └──────┬──────┘
                               │
              ┌────────────────▼────────────────┐
              │  Node 7: fallback               │ ← 兜底
              │  所有 Skill 都低于阈值 → KB-QA   │
              └────────────────┬────────────────┘
                               │
                         ┌─────▼─────┐
                         │   END     │
                         └───────────┘
```

### 7.2 各节点详解

#### Node 1: trigger_kw（全局必做）

**执行时机**：每次用户输入都经过此节点，优先级最高。

**功能**：
1. 检测 Query 中是否包含记忆触发关键词
2. 如果包含"记住"类关键词 → 提取内容 → 写入 RAGFlow → 返回"✅ 已记住"
3. 如果包含"忘了吧"类关键词 → 删除相关内容 → 返回"✅ 已忘记"
4. **不影响后续路由**——记忆写入和意图识别是独立的

#### Node 2: multimodal（按需执行）

**执行时机**：当用户上传了 image 或 PDF 文件时。

**功能**：
1. 对每个文件调用 Qwen VL 模型提取文本
2. 提取的文本拼接到用户 Query 后
3. 拼接后的 Query 进入后续节点
4. 文件文本也会参与知识库检索

#### Node 3: intent（核心决策）

**执行时机**：每次请求的核心节点。

**功能**：
1. **上下文回溯检测**：识别"重新来/继续之前"等指令
2. **Embedding 打分**：对每个 Skill 的 description 计算余弦相似度
3. **动态阈值过滤**：根据最高分动态调整阈值
4. **边界消歧**：多 Skill 相似时用 LLM 做界定
5. **澄清判断**：模糊问题时触发澄清
6. **条件路由**：决定走单意图/多意图/澄清/兜底

**输出的条件路由**：

| 条件 | 目标节点 | 说明 |
|------|---------|------|
| 单意图 + 有匹配 Skill | Node 4a: single_dispatch | 鉴权后分发到1个 Agent |
| 多意图（含"然后/同时"） | Node 4b: multi_split | 拆分后并行分发 |
| 需要澄清 | Node 6: clarify | 返回澄清问题 |
| 全部低于阈值 | Node 7: fallback | 走兜底 KB-QA |

#### Node 4a: single_dispatch

1. 将 Skill 名称映射到 Agent（如 Common_Data_Query → data_query）
2. 调用鉴权检查用户权限
3. 实例化对应的 Agent 并执行
4. 结果送入 aggregate

#### Node 4b: multi_split

1. 将用户 Query 拆分为多个子任务
2. **并行**调用多个 Agent（asyncio.gather）
3. 所有结果送入 aggregate

#### Node 5: aggregate

1. 单结果 → 直接返回
2. 多结果 → LLM 合成 summary，保留所有 URL

#### Node 6: clarify

- 返回澄清问题，附带 `__needs_clarification__: True` 标识
- 前端收到后展示为待确认状态

#### Node 7: fallback

- 路由到 Fallback Agent
- 走通用 KB-QA 路线

### 7.3 使用方法

```python
from agents.router_agent import get_router_agent

router = get_router_agent()

# 调用路由
result = await router.route(
    query="查询上个月的销售数据然后做成柱状图",
    session_id="sess_123",
    user_id="user_001",
    multimodal_files=None,  # 可选: [{"path": "/tmp/photo.png", "type": "image"}]
)

# result:
# {
#   "status": "success",
#   "content": "以下是整合结果：\n1. 销售数据查询结果...\n2. 柱状图已生成...",
#   "download_urls": ["http://.../chart.html"],
#   "sub_responses": [...]
# }
```

---

## 8. API 接口文档

### 8.1 POST /chat — 单次对话

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "query": "查询销售表里上个月的数据",
    "session_id": "sess_123",
    "user_id": "user_001"
  }'
```

**响应**:
```json
{
  "status": "success",
  "content": "<thinking>...</thinking>\n\n查询结果：\n...",
  "session_id": "sess_123",
  "agent": "data_query",
  "needs_clarification": false,
  "download_urls": []
}
```

### 8.2 POST /chat/stream — SSE 流式对话

```bash
curl -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"query": "生成销售趋势折线图", "session_id": "sess_123"}'
```

**响应 (SSE 事件流)**:
```
event: message
data: {"content": "正在分析", "is_final": false, "needs_clarification": false}

event: message
data: {"content": "您的需求...", "is_final": false, "needs_clarification": false}

event: done
data: {"content": "", "is_final": true, "download_urls": ["http://..."]}
```

### 8.3 WS /ws/{session_id} — WebSocket 双向通信

```javascript
const ws = new WebSocket("ws://localhost:8000/ws/sess_123");

// 发送聊天消息
ws.send(JSON.stringify({
  type: "chat",
  query: "把状态表里运行中改为终止",
  user_id: "user_001"
}));

// 监听流式响应
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  // data.type: "stream_chunk" / "confirmation_request" / "error"
  // data.content: 流式文本块
  // data.is_final: 是否为最后一块
  // data.__needs_clarification__: 是否为澄清消息
};

// 发送确认响应
ws.send(JSON.stringify({
  type: "confirm",
  confirm_id: "confirm_abc123",
  status: "confirmed"  // 或 "cancelled"
}));
```

### 8.4 POST /confirm/{confirm_id} — 确认回调（HTTP 备选）

```bash
curl -X POST http://localhost:8000/confirm/confirm_abc123 \
  -H "Content-Type: application/json" \
  -d '{"status": "confirmed", "reason": ""}'
```

### 8.5 POST /feedback — 提交反馈

```bash
curl -X POST http://localhost:8000/feedback \
  -H "Content-Type: application/json" \
  -d '{
    "question": "上个月销售额是多少",
    "answer": "上个月销售额为 1,234,567 元",
    "feedback": "thumbs_up",
    "session_id": "sess_123",
    "user_id": "user_001",
    "agent_name": "data_query",
    "rating": 4
  }'
```

### 8.6 GET /files/{file_id}/download — 文件下载

```bash
curl -O http://localhost:8000/files/a1b2c3d4e5f6/download
# 返回生成的图表/Excel/PPT 文件
```

### 8.7 GET /health — 健康检查

```bash
curl http://localhost:8000/health
# {"status": "ok", "websocket_connections": 3, "pending_confirmations": 1}
```

---

## 9. 配置指南

### 9.1 环境变量完整清单

```bash
# ===== LLM 配置 =====
LLM_PROVIDER=beacon                    # LLM 提供商
LLM_BASE_URL=https://beacon-api.xxx.com/v1
LLM_API_KEY=your-api-key-here
LLM_DEFAULT_MODEL=deepseek-v4-pro      # 默认模型
LLM_BACKUP_MODEL=qwen-3.5             # 备用模型
LLM_TEMPERATURE=0.1                    # 生成温度 (0-1)
LLM_MAX_TOKENS=4096                    # 最大 token
LLM_REQUEST_TIMEOUT=60                 # 请求超时(秒)
LLM_MAX_RETRIES=3                      # 重试次数

# ===== 多模态模型 =====
MULTIMODAL_MODEL=qwen3.5-397b-a17b-vl
MULTIMODAL_BASE_URL=https://beacon-api.xxx.com/v1
MULTIMODAL_API_KEY=your-api-key-here

# ===== RAGFlow 知识库 =====
RAGFLOW_BASE_URL=https://ragflow.xxx.com/api/v1
RAGFLOW_API_KEY=your-ragflow-key
KB_LONGTERM_MEMORY=kb_memory_id       # 长期记忆KB
KB_BUSINESS=kb_business_id            # 业务KB
KB_FEEDBACK=kb_feedback_id            # 反馈KB
KB_DATABASE=kb_database_id            # 数据库KB

# ===== 数据库 (PostgreSQL) =====
DB_HOST=localhost
DB_PORT=5432
DB_NAME=multi_agent_db
DB_USER=agent_user
DB_PASSWORD=your-db-password
DB_POOL_MIN=2
DB_POOL_MAX=10

# ===== 文件存储 =====
STORAGE_BACKEND=local                  # local 或 s3
STORAGE_LOCAL_DIR=./storage

# ===== 会话 =====
SESSION_BACKEND=memory                 # memory / sqlite / postgres
SESSION_MAX_HISTORY_ROUNDS=15          # 短期记忆保留轮数
SESSION_TTL_SECONDS=3600               # 会话过期时间

# ===== 服务 =====
HOST=0.0.0.0
PORT=8000
LOG_LEVEL=INFO
ENVIRONMENT=development               # development / staging / production
```

### 9.2 开发/生产环境差异

| 特性 | 开发环境 | 生产环境 |
|------|---------|---------|
| 鉴权 | 全部自动通过 | 调用 SSO + MCP 鉴权 |
| 数据库 | Mock 数据 | 真实 PostgreSQL |
| 敏感字段过滤 | 不过滤 | 过滤 key1/key2/key3 |
| 文件存储 | 本地目录 | S3 (MinIO/AWS) |
| 日志级别 | DEBUG/INFO | WARNING |
| 热重载 | ✅ uvicorn reload | ❌ |

---

## 10. 扩展开发指南

### 10.1 添加新的 Sub-Agent

```python
# 1. 创建 Agent 文件: agents/sub_agents/my_new_agent.py
from core.agent_base import BaseAgent

class MyNewAgent(BaseAgent):
    agent_name = "my_new_agent"
    agent_description = "处理XXX业务"

    kb_search_config = {
        "database": {"top_k": 1, "required": True},
        "longterm_memory": {"top_k": 3, "required": False},
    }

    async def process(self, query, context):
        # 实现业务逻辑
        return {"status": "success", "content": "处理完成"}

# 2. 在 config.py 的 skill_registry 中注册
skill_registry = {
    ...
    "My_New_Skill": "处理XXX业务：...",
}

# 3. 在 router_agent.py 的 _skill_to_agent() 中添加映射
def _skill_to_agent(self, skill_name):
    mapping = {
        ...
        "My_New_Skill": "my_new_agent",
    }

# 4. 在 router_agent.py 的 _invoke_agent() 中添加分支
```

### 10.2 添加新的 MCP Server

```python
# 1. 创建 MCP 文件: agents/sub_agents/mcp/my_mcp.py
class MyMCP:
    async def my_method(self, ...):
        # 实现
        pass

# 2. 在 tools/mcp_servers.py 中注册
from agents.sub_agents.mcp.my_mcp import MyMCP
registry.register("my_mcp", MyMCP())

# 3. 在 Agent 中使用
mcp = get_mcp_registry().get("my_mcp")
result = await mcp.my_method(...)
```

### 10.3 添加新的知识库

```python
# 1. 在 config.py 中添加 KB ID 配置
class RAGFlowSettings:
    kb_my_new: str = "my_kb_id"

# 2. 在 knowledge_manager.py 中配置权重和拼接顺序
self.kb_weights["my_new"] = 0.75
# splice_order 中添加 "my_new"

# 3. 在 Agent 的 kb_search_config 中使用
kb_search_config = {
    "my_new": {"top_k": 5, "required": True},
}
```

### 10.4 添加新的样式预设

```python
from agents.sub_agents.mcp.excel_mcp import ExcelMCP

excel = ExcelMCP()
excel.add_style_preset("christmas", {
    "font_size": 14,
    "header_color": "C41E3A",
    "border": True,
})
# 之后用户说 "生成圣诞风格的报表" → 匹配此预设
```

---

## 附录 A: 错误处理策略

| 场景 | 处理方式 |
|------|---------|
| LLM 调用失败 | tenacity 自动重试 3 次 → 返回错误消息 |
| RAGFlow 检索失败 | 降级：跳过该 KB，只用其他 KB 的上下文 |
| 数据库连接失败 | 开发环境降级到 Mock；生产返回错误 |
| WebSocket 断开 | 清理该 Session 的待确认请求和连接 |
| 确认超时 | 30 秒自动取消，终止操作 |
| 鉴权失败 | 阻断流程，返回无权限提示 |
| 多意图某个子任务失败 | 其他子任务继续执行，失败的标记 error |

## 附录 B: 依赖关系图

```
main.py
  ├── config.py
  ├── core/llm_provider.py
  ├── core/session_manager.py
  ├── core/feedback_system.py
  │     └── core/knowledge_manager.py
  ├── middleware/ws_manager.py
  └── agents/router_agent.py
        ├── core/guardrails.py
        │     └── core/llm_provider.py
        ├── core/memory_manager.py
        │     ├── core/knowledge_manager.py
        │     └── core/session_manager.py
        ├── core/auth_manager.py
        └── agents/sub_agents/*
              ├── core/agent_base.py
              │     ├── core/llm_provider.py
              │     ├── core/knowledge_manager.py
              │     ├── core/session_manager.py
              │     ├── core/memory_manager.py
              │     └── middleware/*
              ├── agents/sub_agents/skills/*
              └── agents/sub_agents/mcp/*
```

---

> 📄 本系统基于四份设计文档构建：`设计手册.docx` / `agent设计手册.docx` / `中断式确认机制调研.docx` / `matplotlib.docx`  
> 🔧 如有疑问或需要扩展，请参考设计文档中的详细方案描述。
