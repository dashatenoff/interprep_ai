# agents/coordinator.py
from pydantic import BaseModel, Field
from langchain.prompts import ChatPromptTemplate


class RouteResult(BaseModel):
    """Результат маршрутизации между агентами"""
    agent: str = Field(..., description="Имя агента, который должен обработать сообщение: ASSESSOR, PLANNER, INTERVIEWER")
    context: str = Field(..., description="Пояснение, почему выбран именно этот агент")


class CoordinatorAgent:
    """Определяет, какому агенту передать сообщение пользователя"""

    def __init__(self, llm):
        self.chain = (
            ChatPromptTemplate.from_messages([
                ("system",
                 "Ты — Coordinator AI. "
                 "Определи, какой агент должен обработать сообщение пользователя. "
                 "Доступные варианты: ASSESSOR, PLANNER, INTERVIEWER. "
                 "Ответ верни строго в JSON формате: "
                 "{{\"agent\": \"...\", \"context\": \"...\"}}"),
                ("human", "{user_text}")
            ])
            | llm.with_structured_output(RouteResult)
        )

    def route(self, user_text: str) -> RouteResult:
        """Возвращает структуру RouteResult"""
        return self.chain.invoke({"user_text": user_text})
