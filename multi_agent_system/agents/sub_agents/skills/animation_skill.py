"""Skill: PPT动画效果"""
from core.agent_base import BaseAgent
class PPTAnimationSkill:
    def __init__(self, agent: BaseAgent): self.agent = agent
    async def apply(self, slides_count: int) -> dict:
        return {"animation": {"transition": "fade", "duration": 0.5, "auto_play": False}}
