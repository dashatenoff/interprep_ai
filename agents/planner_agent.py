# agents/planner_agent.py
import json
import sys
from pathlib import Path
from pydantic import BaseModel
from gigachat import GigaChat
from dotenv import load_dotenv
import os
from typing import List, Dict, Optional
from datetime import datetime, timedelta

# Добавляем путь для импорта RAG
sys.path.append(str(Path(__file__).resolve().parent.parent))

# Импортируем RAG
try:
    from rag.retriever import retrieve_context, search_similar

    RAG_AVAILABLE = True
except ImportError:
    print("⚠️  RAG модуль не найден. Planner будет работать без базы знаний.")
    RAG_AVAILABLE = False


    def retrieve_context(query: str, k: int = 4) -> List[str]:
        return []


    def search_similar(query: str, k: int = 5) -> List[Dict]:
        return []

load_dotenv()


# ===============================
#  Модели данных
# ===============================
class LearningGoal(BaseModel):
    week: int
    title: str
    description: str
    topics: List[str]
    tasks: List[str]
    resources: List[str]
    estimated_hours: int
    success_criteria: List[str]


class PlanResult(BaseModel):
    plan: List[LearningGoal]
    summary: str
    total_weeks: int
    total_hours: int
    focus_areas: List[str]
    rag_context_used: bool = False


# ===============================
#  Основной класс Planner с RAG
# ===============================
class PlannerAgent:
    def __init__(self, use_rag: bool = True):
        self.llm = GigaChat(
            credentials=os.getenv("GIGACHAT_CLIENT_SECRET"),
            verify_ssl_certs=False
        )

        self.use_rag = use_rag and RAG_AVAILABLE

        # Промпты
        self.planning_prompt_without_rag = """
        Ты — AI-планировщик для подготовки к техническим собеседованиям.

        Создай детальный план обучения на {weeks} недель для пользователя с описанием: "{user_text}"
        Уровень: {level}
        Направление: {track}

        Формат ответа строго JSON:
        {{
          "plan": [
            {{
              "week": 1,
              "title": "Название недели",
              "description": "Описание целей недели",
              "topics": ["тема1", "тема2"],
              "tasks": ["задача1", "задача2"],
              "resources": ["ресурс1", "ресурс2"],
              "estimated_hours": 10,
              "success_criteria": ["критерий1", "критерий2"]
            }}
          ],
          "summary": "Краткое описание плана",
          "total_weeks": {weeks},
          "total_hours": 40,
          "focus_areas": ["основная область 1", "основная область 2"]
        }}
        """

        self.planning_prompt_with_rag = """
        Ты — AI-планировщик с доступом к базе знаний о подготовке к собеседованиям.

        КОНТЕКСТ ИЗ БАЗЫ ЗНАНИЙ (материалы, ресурсы, советы):
        {rag_context}

        Создай персонализированный план обучения на {weeks} недель.

        Информация о пользователе:
        - Описание: {user_text}
        - Уровень: {level}
        - Направление: {track}
        - Цели: {goals}

        Используй контекст из базы знаний для подбора актуальных ресурсов и тем.
        План должен быть реалистичным и сфокусированным на слабых местах.

        Формат ответа строго JSON:
        {{
          "plan": [
            {{
              "week": номер недели,
              "title": "Название недели",
              "description": "Детальное описание целей",
              "topics": ["конкретные темы для изучения"],
              "tasks": ["практические задачи и упражнения"],
              "resources": ["ссылки на материалы из контекста или известные ресурсы"],
              "estimated_hours": число часов,
              "success_criteria": ["измеримые критерии успеха"]
            }}
          ],
          "summary": "Детальное обоснование плана",
          "total_weeks": {weeks},
          "total_hours": общее количество часов,
          "focus_areas": ["ключевые области для фокуса"]
        }}
        """

    def _get_rag_context_for_planning(self, user_text: str, level: str, track: str) -> Dict[str, str]:
        """Получает контекст из RAG для планирования"""
        if not self.use_rag:
            return {"rag_context": "", "resources": ""}

        try:
            # Поиск материалов по направлению и уровню
            query = f"{track} {level} подготовка обучение материалы ресурсы"
            context_chunks = retrieve_context(query, k=5)

            # Поиск конкретных ресурсов
            resources_query = f"{track} книги курсы статьи"
            resources_results = search_similar(resources_query, k=3)

            resources_list = []
            for result in resources_results:
                text = result.get('text', '')
                if "ресурс" in text.lower() or "курс" in text.lower() or "книга" in text.lower():
                    resources_list.append(text[:150] + "...")

            return {
                "rag_context": "\n".join([
                    f"📚 Материал {i + 1}: {chunk[:250]}..."
                    for i, chunk in enumerate(context_chunks)
                ]),
                "resources": "\n".join(resources_list[:3]) if resources_list else "Нет специфических ресурсов"
            }

        except Exception as e:
            print(f"⚠️  Ошибка RAG в Planner: {e}")
            return {"rag_context": "", "resources": ""}

    def _extract_json(self, text: str) -> dict:
        """Безопасно извлекает JSON из ответа"""
        # Очистка от Markdown
        import re

        if text.startswith("```json"):
            text = text[7:].strip()
        elif text.startswith("```"):
            text = text[3:].strip()

        if text.endswith("```"):
            text = text[:-3].strip()

        # Поиск JSON
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except:
                pass

        # Попытка распарсить весь текст
        try:
            return json.loads(text)
        except:
            raise ValueError("Не удалось извлечь JSON")

    def make_plan(self, user_text: str, level: str = "junior",
                  track: str = "backend", weeks: int = 4,
                  goals: str = "") -> PlanResult:
        """Создает план обучения"""

        # Получаем контекст из RAG
        rag_context = self._get_rag_context_for_planning(user_text, level, track)

        # Выбираем промпт
        if self.use_rag and rag_context["rag_context"]:
            prompt = self.planning_prompt_with_rag.format(
                user_text=user_text,
                level=level,
                track=track,
                weeks=weeks,
                goals=goals,
                rag_context=rag_context["rag_context"]
            )
            rag_used = True
        else:
            prompt = self.planning_prompt_without_rag.format(
                user_text=user_text,
                level=level,
                track=track,
                weeks=weeks
            )
            rag_used = False

        try:
            # Генерируем план
            response = self.llm.chat(prompt)
            data = self._extract_json(response.choices[0].message.content)

            # Создаем объекты LearningGoal
            plan_items = []
            for item_data in data.get("plan", []):
                plan_items.append(LearningGoal(
                    week=item_data.get("week", 1),
                    title=item_data.get("title", f"Неделя {item_data.get('week', 1)}"),
                    description=item_data.get("description", ""),
                    topics=item_data.get("topics", []),
                    tasks=item_data.get("tasks", []),
                    resources=item_data.get("resources", []),
                    estimated_hours=item_data.get("estimated_hours", 10),
                    success_criteria=item_data.get("success_criteria", [])
                ))

            # Сортируем по неделям
            plan_items.sort(key=lambda x: x.week)

            return PlanResult(
                plan=plan_items,
                summary=data.get("summary", "План обучения создан"),
                total_weeks=data.get("total_weeks", weeks),
                total_hours=data.get("total_hours", weeks * 10),
                focus_areas=data.get("focus_areas", [track, "алгоритмы", "системный дизайн"]),
                rag_context_used=rag_used
            )

        except Exception as e:
            print(f"❌ Ошибка создания плана: {e}")

            # Fallback план
            fallback_plan = self._create_fallback_plan(level, track, weeks)

            return PlanResult(
                plan=fallback_plan,
                summary=f"Базовый план для {track} разработчика уровня {level}",
                total_weeks=weeks,
                total_hours=weeks * 10,
                focus_areas=[track, "базовые концепции", "практика"],
                rag_context_used=False
            )

    def _create_fallback_plan(self, level: str, track: str, weeks: int) -> List[LearningGoal]:
        """Создает базовый план на случай ошибки"""
        plans = []

        base_topics = {
            "backend": ["Python/Java", "Базы данных", "API", "Микросервисы"],
            "frontend": ["JavaScript", "React/Vue", "CSS", "State Management"],
            "devops": ["Docker", "Kubernetes", "CI/CD", "Мониторинг"],
            "data": ["Python", "SQL", "Pandas", "ML основы"]
        }

        topics = base_topics.get(track, ["Программирование", "Алгоритмы", "Системный дизайн"])

        for week in range(1, weeks + 1):
            if week == 1:
                title = "Основы и базовая теория"
                description = f"Изучение основных концепций {track}"
                week_topics = [topics[0], "Основы алгоритмов"]
                tasks = ["Пройти базовый курс", "Решить 10 простых задач"]
            elif week == 2:
                title = "Углубление в технологии"
                description = f"Погружение в ключевые технологии {track}"
                week_topics = topics[1:3]
                tasks = ["Изучить документацию", "Создать небольшой проект"]
            elif week == 3:
                title = "Практика и проекты"
                description = "Применение знаний на практике"
                week_topics = ["Практическое применение", "Оптимизация"]
                tasks = ["Реализовать проект", "Оптимизировать код"]
            else:
                title = "Подготовка к собеседованию"
                description = "Мокапы и повторение"
                week_topics = ["Mock интервью", "Вопросы с собеседований"]
                tasks = ["Пройти 3 mock интервью", "Повторить слабые темы"]

            plans.append(LearningGoal(
                week=week,
                title=title,
                description=description,
                topics=week_topics,
                tasks=tasks,
                resources=["LeetCode", "Habr", "Official Documentation"],
                estimated_hours=10,
                success_criteria=[f"Завершить задачи недели {week}"]
            ))

        return plans

    def adjust_plan(self, original_plan: PlanResult, feedback: str) -> PlanResult:
        """Корректирует план на основе фидбека"""
        prompt = f"""
        Исходный план обучения:
        {json.dumps([goal.dict() for goal in original_plan.plan], indent=2, ensure_ascii=False)}

        Фидбек пользователя: {feedback}

        Скорректируй план с учетом фидбека. Сохрани общую структуру.

        Формат ответа такой же JSON как в исходном плане.
        """

        try:
            response = self.llm.chat(prompt)
            data = self._extract_json(response.choices[0].message.content)

            plan_items = []
            for item_data in data.get("plan", []):
                plan_items.append(LearningGoal(**item_data))

            return PlanResult(
                plan=plan_items,
                summary=data.get("summary", "Скорректированный план"),
                total_weeks=data.get("total_weeks", original_plan.total_weeks),
                total_hours=data.get("total_hours", original_plan.total_hours),
                focus_areas=data.get("focus_areas", original_plan.focus_areas),
                rag_context_used=original_plan.rag_context_used
            )

        except Exception as e:
            print(f"❌ Ошибка корректировки плана: {e}")
            return original_plan

    def format_plan_response(self, plan_result: PlanResult) -> str:
        """Форматирует план для вывода пользователю"""
        response = [
            "📋 **Ваш персонализированный план обучения**",
            "",
            f"📊 **Общая информация:**",
            f"   • Недель: {plan_result.total_weeks}",
            f"   • Всего часов: {plan_result.total_hours}",
            f"   • Фокус-области: {', '.join(plan_result.focus_areas)}",
            f"   • Использована база знаний: {'✅ Да' if plan_result.rag_context_used else '❌ Нет'}",
            "",
            f"📝 **Описание:** {plan_result.summary}",
            ""
        ]

        for goal in plan_result.plan:
            response.append(f"**🎯 Неделя {goal.week}: {goal.title}**")
            response.append(f"   {goal.description}")
            response.append(f"   ⏰ Часов: {goal.estimated_hours}")
            response.append("")

            response.append(f"   📚 **Темы:**")
            for topic in goal.topics:
                response.append(f"      • {topic}")
            response.append("")

            response.append(f"   ✅ **Задачи:**")
            for task in goal.tasks:
                response.append(f"      • {task}")
            response.append("")

            if goal.resources:
                response.append(f"   🔗 **Ресурсы:**")
                for resource in goal.resources[:3]:  # Показываем только 3 ресурса
                    response.append(f"      • {resource}")
                response.append("")

            response.append(f"   🎯 **Критерии успеха:**")
            for criterion in goal.success_criteria:
                response.append(f"      • {criterion}")
            response.append("")

        return "\n".join(response)