from gigachat import GigaChat
from pydantic import BaseModel
from dotenv import load_dotenv
import os
import json

# ===============================
#  Модель данных для маршрутизации
# ===============================
class RouteResult(BaseModel):
    agent: str
    context: str
    metadata: dict

# ===============================
#  Класс координатора
# ===============================
class CoordinatorAgent:
    def __init__(self):
        load_dotenv()
        self.client_secret = os.getenv("GIGACHAT_CLIENT_SECRET")
        if not self.client_secret:
            raise ValueError("❌ Не найден GIGACHAT_CLIENT_SECRET в .env")

        # Инициализация клиента GigaChat
        self.llm = GigaChat(credentials=self.client_secret, verify_ssl_certs=False)

        # Промпт для выбора агента
        self.prompt = """
        Ты — координатор (Coordinator).
        Твоя задача — определить, какой агент должен обработать пользовательский запрос.
        Верни результат строго в формате JSON:
        {{
          "agent": "INTERVIEWER" | "ASSESSOR" | "REVIEWER" | "PLANNER",
          "context": "короткое описание контекста",
          "metadata": {{"topic": "Python", "persona": "timlead"}}
        }}

        Входной текст пользователя:
        {user_text}
        """

    def route(self, user_text: str) -> RouteResult:
        """Отправляем запрос в GigaChat и парсим JSON-ответ"""
        # Отправляем промпт напрямую без model и messages
        response = self.llm.chat(self.prompt.format(user_text=user_text))

        try:
            text = response.choices[0].message.content.strip()

            # 🧹 Очистим Markdown-блоки, которые GigaChat часто добавляет
            if text.startswith("```"):
                text = text.strip("`")
                if "json" in text[:10].lower():
                    text = text[text.find("{"):]

            # иногда модель добавляет мусор после JSON
            json_start = text.find("{")
            json_end = text.rfind("}") + 1
            text = text[json_start:json_end]

            data = json.loads(text)
            return RouteResult(**data)

        except Exception as e:
            print("Ошибка парсинга ответа:", e)
            print("Ответ модели:", response)
            return RouteResult(
                agent="INTERVIEWER",
                context="ошибка парсинга",
                metadata={"error": str(e)},
            )
