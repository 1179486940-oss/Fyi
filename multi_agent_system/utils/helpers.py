"""
通用工具函数
"""

from __future__ import annotations

import uuid
import re
import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# ---- 唯一标识 ----

def generate_uuid() -> str:
    """生成 UUID7 (时间有序UUID，兼容标准库)"""
    return str(uuid.uuid4())


def generate_confirm_id() -> str:
    """生成确认断点的唯一ID"""
    return f"confirm_{uuid.uuid4().hex[:12]}"


# ---- 时间 ----

def timestamp_now() -> str:
    """当前UTC时间 ISO格式"""
    return datetime.now(timezone.utc).isoformat()


def timestamp_cn() -> str:
    """当前北京时间字符串"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---- 文本处理 ----

def truncate_text(text: str, max_length: int = 500) -> str:
    """截断文本，超出部分加省略号"""
    if len(text) <= max_length:
        return text
    return text[:max_length] + "…"


def extract_keywords(text: str, keywords: list[str]) -> list[str]:
    """从文本中提取匹配的关键词"""
    matched = []
    for kw in keywords:
        if kw in text:
            matched.append(kw)
    return matched


def safe_json_parse(raw: str) -> Dict[str, Any]:
    """安全解析JSON，失败返回空dict"""
    import json
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


def wrap_thinking(content: str) -> str:
    """将思考过程用标签包裹"""
    return f"<thinking>{content}</thinking>"


def wrap_url(url: str) -> str:
    """将URL用标签包裹"""
    return f"<url>{url}</url>"


# ---- 数据转换 ----

def dict_to_table_preview(
    records: list[dict],
    max_fields: int = 5,
    max_rows: int = 3,
) -> str:
    """
    将查询结果转换为表格预览文本
    默认只展示前 max_fields 个字段和前 max_rows 行
    """
    if not records:
        return "(无结果)"

    fields = list(records[0].keys())
    shown_fields = fields[:max_fields]
    hidden_count = len(fields) - max_fields

    lines = []
    # 表头
    header = " | ".join(shown_fields)
    if hidden_count > 0:
        header += f" | ... (+{hidden_count} 字段)"
    lines.append(header)
    lines.append("-" * len(header))

    # 数据行
    for row in records[:max_rows]:
        values = [str(row.get(f, "")) for f in shown_fields]
        line = " | ".join(values)
        lines.append(line)

    if len(records) > max_rows:
        lines.append(f"... 共 {len(records)} 条记录，仅展示前 {max_rows} 条")

    if hidden_count > 0:
        lines.append(f"\n💡 共 {len(fields)} 个字段，当前展示前 {max_fields} 个。如需查看其他字段请追问。")

    return "\n".join(lines)


def dict_to_full_table(records: list[dict]) -> str:
    """将查询结果转换为完整表格（展示全部字段）"""
    if not records:
        return "(无结果)"

    fields = list(records[0].keys())
    lines = []
    header = " | ".join(fields)
    lines.append(header)
    lines.append("-" * len(header))

    for row in records:
        values = [str(row.get(f, "")) for f in fields]
        lines.append(" | ".join(values))

    lines.append(f"\n共 {len(records)} 条记录")
    return "\n".join(lines)


# ---- Hash ----

def content_hash(content: str) -> str:
    """生成内容MD5哈希，用于去重"""
    return hashlib.md5(content.encode("utf-8")).hexdigest()


# ---- SQL 安全 ----

def is_write_operation(sql: str) -> bool:
    """判断 SQL 是否是写操作"""
    sql_upper = sql.strip().upper()
    write_keywords = ("INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE", "CREATE")
    return any(sql_upper.startswith(kw) for kw in write_keywords)


def has_delete_keywords(sql: str) -> bool:
    """判断 SQL 是否包含危险操作"""
    sql_upper = sql.strip().upper()
    dangerous = ("DROP", "TRUNCATE", "ALTER")
    return any(sql_upper.startswith(kw) for kw in dangerous)
