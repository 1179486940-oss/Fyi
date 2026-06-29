"""
Tests package for multi_agent_system.

测试覆盖范围:
  - test_router.py: RouterAgent 路由逻辑测试
  - test_query_agent.py: DataQueryAgent 查询与确认测试

运行方式:
  cd multi_agent_system
  pytest tests/
  # 或
  python -m pytest tests/

注意:
  当前测试依赖 mock 模式运行，因为：
  - LLM 使用 MockProvider（无需 Beacon API key）
  - 数据库使用 Mock 数据（无需 PostgreSQL）
  - RAGFlow 使用 Mock 检索（无需 RAGFlow 服务）

  @REAL_CODE: 后续需要补充集成测试（对接真实服务）
  优先级: MEDIUM
"""
