"""Skill: PPT内容生成"""
from core.agent_base import BaseAgent

class PPTContentSkill:
    def __init__(self, agent: BaseAgent):
        self.agent = agent
    async def generate(self, topic: str, context: str) -> dict:
        prompt = f"为PPT生成内容大纲：{topic}\n上下文：{context}"
        content = await self.agent._llm.chat([{"role":"user","content":prompt}])
        return {"slides_content": content}
