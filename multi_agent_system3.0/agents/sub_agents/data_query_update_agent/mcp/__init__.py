"""
DataQueryUpdateAgent - MCP Servers 子包

MCP 映射:
  - db_mcp   → ../../mcp/db_mcp.py
  - auth_mcp → ../../mcp/auth_mcp.py

@REAL_CODE: 将 MCP 实现迁移到本目录下
当前状态: MCP 实现位于父级 ../../mcp/ 集中目录
目标实现: 按 Agent 隔离，每个 Agent 的 MCP 实现在自己的 mcp/ 子目录
优先级: MEDIUM
"""
