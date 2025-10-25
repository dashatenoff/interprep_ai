# agents/interviewer_agent.py
from pydantic import BaseModel, Field
from langchain.prompts import ChatPromptTemplate


class InterviewScore(BaseModel):
    """Оценка ответа кандидата"""
    score: int = Field(..., description="Оценка 0–100")
    comment: str = Field(..., description="Комментарий интервьюера")


class InterviewerAgent:
    """Агент, который оценивает ответы кандидата"""

    def __init__(self, llm):
        self.chain = (
            ChatPromptTemplate.from_messages([
                ("system",
                 "Ты — Interviewer AI. Проанализируй ответ кандидата по backend-направлению. "
                 "Сначала рассуждай пошагово (Chain of Thought), потом выведи JSON "
                 "{\"score\": int, \"comment\": str}."),
                ("human", "{answer}")
            ])
            | llm.with_structured_output(InterviewScore)
        )

    def evaluate_answer(self, answer: str) -> InterviewScore:
        """Возвращает оценку ответа"""
        return self.chain.invoke({"answer": answer})
