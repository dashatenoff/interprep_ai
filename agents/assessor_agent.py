# agents/assessor_agent.py
from pydantic import BaseModel, Field
from langchain.prompts import ChatPromptTemplate


class AssessResult(BaseModel):
    """Структура оценки знаний пользователя"""
    scores: dict = Field(..., description="Оценки по темам, например {'Python': 80, 'Algorithms': 60}")
    weak_topics: list = Field(..., description="Список слабых тем для доработки")
    follow_up: str = Field(..., description="Вопрос для уточнения")


class AssessorAgent:
    """Агент, который оценивает знания пользователя"""

    def __init__(self, llm):
        self.chain = (
            ChatPromptTemplate.from_messages([
                ("system",
                 "Ты — Assessor AI. "
                 "Анализируй текст пользователя и оцени его знания по темам {topics}. "
                 "Дай честную оценку (0–100), выдели слабые темы и предложи уточняющий вопрос."),
                ("human", "{answer}")
            ])
            | llm.with_structured_output(AssessResult)
        )

    def assess(self, answer: str, topics: list) -> AssessResult:
        """Возвращает результат анализа знаний"""
        return self.chain.invoke({"answer": answer, "topics": topics})
