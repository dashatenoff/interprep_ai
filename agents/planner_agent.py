# agents/planner_agent.py
from gigachat import GigaChat
from dotenv import load_dotenv
from pydantic import BaseModel
import os, json

load_dotenv()

class PlanResult(BaseModel):
    plan: list
    summary: str

class PlannerAgent:
    def __init__(self):
        self.llm = GigaChat(credentials=os.getenv("GIGACHAT_CLIENT_SECRET"), verify_ssl_certs=False)

        self.prompt_template = """
        Ты — AI-планировщик. 
        Пользователь описал свои знания: "{user_text}".
        Составь программу обучения на 4 недели, чтобы улучшить навыки по Python и алгоритмам.
        Верни результат строго в JSON:
        {{
          "plan": [
            {{"week": 1, "goals": ["..."], "tasks": ["..."]}},
            {{"week": 2, "goals": ["..."], "tasks": ["..."]}},
            {{"week": 3, "goals": ["..."], "tasks": ["..."]}},
            {{"week": 4, "goals": ["..."], "tasks": ["..."]}}
          ],
          "summary": "Краткое объяснение логики плана."
        }}
        """

    def make_plan(self, user_text: str) -> PlanResult:
        prompt = self.prompt_template.format(user_text=user_text)
        response = self.llm.chat(prompt)
        try:
            text = response.choices[0].message.content
            json_start = text.find("{")
            json_end = text.rfind("}") + 1
            data = json.loads(text[json_start:json_end])
            return PlanResult(**data)
        except Exception as e:
            print("Ошибка парсинга плана:", e)
            print("Ответ модели:", response)
            return PlanResult(plan=[], summary="Ошибка парсинга или неполный ответ модели.")
