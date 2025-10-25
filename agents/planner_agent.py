# agents/planner_agent.py
from pydantic import BaseModel, Field
from langchain.prompts import ChatPromptTemplate

class PlanWeek(BaseModel):
    """Неделя плана"""
    week: int = Field(..., description="Номер недели обучения")
    goals: list[str] = Field(..., description="Цели недели")
    tasks: list[str] = Field(..., description="Задачи недели")

class PlannerAgent:
    """Агент, который создаёт учебный план"""
    def __init__(self, llm):
        planner_prompt = ChatPromptTemplate.from_messages([
            ("system",
             "Ты — AI-планировщик. Составь 4-недельный учебный план "
             "для подготовки к стажировке по направлению {track}, "
             "исходя из уровня {level}. Верни список в JSON: [{week, goals, tasks}]"),
            ("human", "{user_text}")
        ])
        self.chain = planner_prompt | llm.with_structured_output(list[PlanWeek])

    def make_plan(self, user_text: str, level: str = "junior", track: str = "backend"):
        """Создаёт учебный план"""
        try:
            result = self.chain.invoke({
                "user_text": user_text,
                "level": level,
                "track": track
            })
            return result
        except Exception as e:
            print("Ошибка в PlannerAgent:", e)
            return []
