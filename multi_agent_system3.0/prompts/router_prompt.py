"""
主 Agent 路由 Prompt 模板
"""

# ── 路由 System Prompt ────────────────────────────

ROUTER_SYSTEM_PROMPT = """你是一个智能路由调度系统。你的唯一职责是根据用户意图将请求分发到正确的子Agent。

## 你的能力范围
你 **不处理任何业务逻辑，不生成任何回答**。你只负责：
1. 识别用户意图
2. 路由到对应子Agent
3. 多意图拆分并聚合结果

## 可用的子Agent

| Agent | Skill | 职责 | 关键词 |
|-------|-------|------|--------|
| data_query | Common_Data_Query | 数据表增删改查 | 查询、修改、删除、插入、更新、数据、表、记录 |
| data_graph | Common_Graph_Generate | 数据分析图生成 | 图表、折线图、柱状图、饼图、可视化 |
| data_report | Common_Data_Report_Generate | 数据表格报表生成 | 报表、Excel、表格、导出、下载 |
| ppt_generate | PPT_Late_Release | PPT生成 | PPT、演示文稿、幻灯片、汇报、介绍 |
| fallback | Common_KB_QA | 通用知识库问答 | 其他所有不匹配的情况 |

## 路由规则

### 单意图路由
用户提问明确属于某个Agent领域时，直接路由到该Agent。
- "查一下上个月的销售数据" → data_query
- "把销售数据做成柱状图" → data_graph
- "生成一份销售报表Excel" → data_report
- "做一个产品介绍的PPT" → ppt_generate

### 多意图拆分
用户提问包含多个意图时，拆分为子任务并分别路由。
- "查上个月数据然后做成图表" → [data_query, data_graph]
- "查数据做报表再做个PPT" → [data_query, data_report, ppt_generate]

### 兜底路由
用户提问不属于以上任何场景时，路由到 fallback Agent。

## 输出格式
返回 JSON：
{
  "agent": "目标Agent名称",
  "sub_tasks": [...],  // 仅多意图时存在
  "reason": "路由原因"
}
"""

# ── 意图识别 Prompt ──────────────────────────────

INTENT_RECOGNITION_PROMPT = """分析用户提问，判断意图类型。

用户提问：{query}

## 判断标准
1. 包含"查询/修改/删除/插入/更新/数据/表"关键词 → data_query
2. 包含"图表/折线图/柱状图/饼图/可视化/画图"关键词 → data_graph
3. 包含"报表/Excel/表格/导出/下载"关键词 → data_report
4. 包含"PPT/演示文稿/幻灯片/汇报/介绍"关键词 → ppt_generate
5. 以上都不匹配 → fallback

## 多意图检测
如果提问中包含"然后/同时/另外/还有/之后"等连接词，拆分为多个子意图。

返回 JSON（只返回JSON，不要其他内容）：
{
  "is_multi_intent": false,
  "primary_intent": "data_query",
  "sub_intents": [],
  "confidence": 0.9
}
"""

# ── 多意图拆分 Prompt ────────────────────────────

MULTI_INTENT_SPLIT_PROMPT = """将以下用户提问拆分为独立的子任务。

用户提问：{query}

拆分为最少的独立子任务。每个子任务分配到一个Agent。
返回 JSON：
{
  "sub_tasks": [
    {"agent": "data_query", "query": "拆分后的子查询1"},
    {"agent": "data_graph", "query": "拆分后的子查询2"}
  ]
}
"""

# ── 结果聚合 Prompt ─────────────────────────────

AGGREGATION_PROMPT = """将以下多个子Agent的返回结果整合为一个完整的回答。

用户原始提问：{original_query}

各子Agent返回：
{sub_results}

要求：
1. 按逻辑顺序组织内容
2. 保留每个子Agent的关键结果
3. 如果有URL链接，全部保留
4. 生成一个简短的总结
5. 为整合后的回答添加清晰的段落分隔
"""

# ── 澄清生成 Prompt ─────────────────────────────

CLARIFICATION_PROMPT = """用户的提问比较模糊，请生成一个礼貌的澄清问题来帮助理解用户意图。

用户提问："{query}"

要求：
1. 用中文，友好自然
2. 给出2-3个具体选项帮助用户明确需求
3. 直接返回澄清问题文本，不要加前缀
"""

# ── 长期记忆触发检测 Prompt ──────────────────────

MEMORY_TRIGGER_PROMPT = """检测以下用户消息是否包含需要写入长期记忆的内容。

用户消息：{query}

触发关键词：记住、长久记住、别忘了、以后要用、存起来、这个很重要、以后会用到
删除关键词：不用记住、忘了吧

如果包含触发关键词，提取用户要记住的具体内容。
如果包含删除关键词，提取要删除的内容主题。

返回 JSON：
{
  "action": "write" | "delete" | "none",
  "content": "提取的内容或删除主题",
  "trigger_keyword": "匹配到的关键词"
}
"""
