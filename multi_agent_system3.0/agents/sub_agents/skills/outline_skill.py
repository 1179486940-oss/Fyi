"""Skill: PPT大纲生成"""
from core.agent_base import BaseAgent

class PPTOutlineSkill:
    def __init__(self, agent: BaseAgent): self.agent = agent
    async def generate(self, topic: str, context: str) -> dict:
        prompt = f"为以下主题生成PPT大纲结构：{topic}\n参考：{context}\n返回章节标题列表。"
        content = await self.agent._llm.chat([{"role":"user","content":prompt}])
        return {"outline": content}
