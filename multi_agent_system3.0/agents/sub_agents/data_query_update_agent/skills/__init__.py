"""
DataQueryUpdateAgent - Skills 子包

Skills 映射关系:
  - NSG_Borrow_Data_Process → ../../skills/nsg_borrow_data_process.py
  - Comment_Data_Process   → ../../skills/comment_data_process.py
  - Common_Data_Query      → ../../skills/common_data_query_skill.py
  - Type_Range_Judgment    → ../../skills/type_range_skill.py
  - Preset_Matcher         → ../../skills/preset_skill.py

@REAL_CODE: 将 skills 实现迁移到本目录下
当前状态: skills 实现位于父级 ../../skills/ 集中目录
目标实现: 按 Agent 隔离，每个 Agent 的 skills 实现在自己的 skills/ 子目录
优先级: MEDIUM
"""
