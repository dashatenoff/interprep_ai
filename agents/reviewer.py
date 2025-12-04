# agents/reviewer_agent.py
import json
import sys
from pathlib import Path
from pydantic import BaseModel
from gigachat import GigaChat
from dotenv import load_dotenv
import os
from typing import List, Optional, Dict
import re

# Добавляем путь для импорта RAG
sys.path.append(str(Path(__file__).resolve().parent.parent))

# Импортируем RAG
try:
    from rag.retriever import retrieve_context, search_similar

    RAG_AVAILABLE = True
except ImportError:
    print("⚠️  RAG модуль не найден. Reviewer будет работать без базы знаний.")
    RAG_AVAILABLE = False


    def retrieve_context(query: str, k: int = 4) -> List[str]:
        return []


    def search_similar(query: str, k: int = 5) -> List[Dict]:
        return []

load_dotenv()


# ===============================
#  Модели данных
# ===============================
class Issue(BaseModel):
    type: str  # "bug" | "style" | "performance" | "security" | "architecture" | "best_practice"
    line: Optional[int] = None
    description: str
    recommendation: str
    severity: str = "medium"  # low, medium, high, critical
    code_snippet: Optional[str] = None


class ReviewResult(BaseModel):
    summary: str
    issues: List[Issue]
    score: int  # 0-100
    follow_up: str
    strengths: List[str]
    improvements: List[str]
    similar_solutions: Optional[List[str]] = None
    rag_context_used: bool = False


# ===============================
#  Основной класс Reviewer с RAG
# ===============================
class ReviewerAgent:
    def __init__(self, use_rag: bool = True):
        self.llm = GigaChat(
            credentials=os.getenv("GIGACHAT_CLIENT_SECRET"),
            verify_ssl_certs=False
        )

        self.use_rag = use_rag and RAG_AVAILABLE

        # Промпты
        self.review_prompt_without_rag = """
        Ты — Senior Code Reviewer. Проведи строгое ревью кода.

        Язык: {language}
        Контекст задачи: {context}

        Код:
        {code}

        Проанализируй по критериям:
        1. Корректность и баги
        2. Производительность и оптимизация
        3. Читаемость и стиль
        4. Архитектура и дизайн
        5. Безопасность (если применимо)

        Формат ответа строго JSON:
        {{
          "summary": "общая оценка кода",
          "issues": [
            {{
              "type": "bug|style|performance|security|architecture|best_practice",
              "line": номер строки или null,
              "description": "описание проблемы",
              "recommendation": "как исправить",
              "severity": "low|medium|high|critical"
            }}
          ],
          "score": 0-100,
          "follow_up": "уточняющий вопрос",
          "strengths": ["сильная сторона 1", "сильная сторона 2"],
          "improvements": ["общее улучшение 1", "общее улучшение 2"]
        }}
        """

        self.review_prompt_with_rag = """
        Ты — Senior Code Reviewer с доступом к базе знаний о лучших практиках.

        КОНТЕКСТ ИЗ БАЗЫ ЗНАНИЙ (лучшие практики, антипаттерны, примеры):
        {rag_context}

        Язык: {language}
        Контекст задачи: {context}

        Код для ревью:
        {code}

        Проведи детальный анализ кода с использованием контекста из базы знаний.
        Ищи не только ошибки, но и возможности для улучшения в соответствии с best practices.

        Формат ответа строго JSON:
        {{
          "summary": "детальная оценка с ссылками на best practices",
          "issues": [
            {{
              "type": "тип проблемы",
              "line": номер строки,
              "description": "детальное описание с объяснением почему это проблема",
              "recommendation": "конкретное исправление с примером",
              "severity": "low|medium|high|critical",
              "code_snippet": "фрагмент проблемного кода"
            }}
          ],
          "score": 0-100,
          "follow_up": "вопрос для углубленного анализа",
          "strengths": ["что хорошо сделано"],
          "improvements": ["общие рекомендации по архитектуре"],
          "similar_solutions": ["похожие подходы или паттерны"]
        }}
        """

    def _get_rag_context_for_review(self, code: str, language: str, context: str) -> Dict[str, str]:
        """Получает контекст из RAG для code review"""
        if not self.use_rag:
            return {"rag_context": "", "similar_patterns": ""}

        try:
            # Извлекаем ключевые слова из кода и контекста
            keywords = self._extract_keywords_from_code(code, language)

            # Ищем лучшие практики по языку
            query = f"{language} best practices code review patterns"
            context_chunks = retrieve_context(query, k=4)

            # Ищем похожие решения
            similar_solutions = []
            if keywords:
                for keyword in keywords[:3]:
                    similar = search_similar(f"{keyword} {language} решение", k=1)
                    for result in similar:
                        similar_solutions.append(result.get('text', '')[:200] + "...")

            # Ищем антипаттерны
            anti_patterns_query = f"{language} anti-patterns common mistakes"
            anti_patterns = retrieve_context(anti_patterns_query, k=2)

            combined_context = []

            if context_chunks:
                combined_context.append("📚 **Лучшие практики:**")
                for i, chunk in enumerate(context_chunks):
                    combined_context.append(f"{i + 1}. {chunk[:250]}...")

            if anti_patterns:
                combined_context.append("\n⚠️  **Распространенные ошибки:**")
                for i, chunk in enumerate(anti_patterns):
                    combined_context.append(f"{i + 1}. {chunk[:250]}...")

            if similar_solutions:
                combined_context.append("\n🔍 **Похожие решения:**")
                for i, solution in enumerate(similar_solutions[:2]):
                    combined_context.append(f"{i + 1}. {solution}")

            return {
                "rag_context": "\n".join(combined_context) if combined_context else "Нет релевантного контекста",
                "similar_patterns": "\n".join(similar_solutions) if similar_solutions else ""
            }

        except Exception as e:
            print(f"⚠️  Ошибка RAG в Reviewer: {e}")
            return {"rag_context": "", "similar_patterns": ""}

    def _extract_keywords_from_code(self, code: str, language: str) -> List[str]:
        """Извлекает ключевые слова из кода"""
        keywords = []

        # Ключевые слова по языкам
        language_keywords = {
            "python": ["def ", "class ", "import ", "from ", "try:", "except ", "with ", "async ", "await "],
            "javascript": ["function ", "const ", "let ", "var ", "class ", "import ", "export ", "async ", "await "],
            "java": ["public ", "private ", "class ", "interface ", "import ", "try ", "catch "],
            "cpp": ["#include ", "using ", "namespace ", "class ", "public:", "private:"]
        }

        # Ищем ключевые слова языка
        lang_keys = language_keywords.get(language.lower(), [])
        for keyword in lang_keys:
            if keyword in code:
                # Извлекаем контекст вокруг ключевого слова
                lines = code.split('\n')
                for i, line in enumerate(lines):
                    if keyword in line:
                        # Добавляем имя функции/класса как ключевое слово
                        if keyword in ["def ", "class ", "function "]:
                            parts = line.split(keyword)
                            if len(parts) > 1:
                                name_part = parts[1].split('(')[0].split(':')[0].strip()
                                if name_part:
                                    keywords.append(name_part)

        # Добавляем общие паттерны
        patterns = [
            ("for ", "цикл"),
            ("while ", "цикл"),
            ("if ", "условие"),
            ("else", "условие"),
            ("return ", "возврат"),
            ("print(", "вывод"),
            ("console.log", "вывод"),
            ("System.out", "вывод")
        ]

        for pattern, label in patterns:
            if pattern in code:
                keywords.append(label)

        return list(set(keywords))[:10]  # Убираем дубликаты, берем 10

    def _extract_json(self, text: str) -> dict:
        """Извлекает JSON из ответа"""
        # Очистка
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

    def review(self, code: str, context: str = "", language: str = "python") -> ReviewResult:
        """Проводит code review"""

        # Получаем контекст из RAG
        rag_context = self._get_rag_context_for_review(code, language, context)

        # Выбираем промпт
        if self.use_rag and rag_context["rag_context"] and "Лучшие практики" in rag_context["rag_context"]:
            prompt = self.review_prompt_with_rag.format(
                code=code,
                context=context,
                language=language,
                rag_context=rag_context["rag_context"]
            )
            rag_used = True
        else:
            prompt = self.review_prompt_without_rag.format(
                code=code,
                context=context,
                language=language
            )
            rag_used = False

        try:
            response = self.llm.chat(prompt)
            data = self._extract_json(response.choices[0].message.content)

            # Создаем объекты Issue
            issues = []
            for issue_data in data.get("issues", []):
                issues.append(Issue(
                    type=issue_data.get("type", "style"),
                    line=issue_data.get("line"),
                    description=issue_data.get("description", ""),
                    recommendation=issue_data.get("recommendation", ""),
                    severity=issue_data.get("severity", "medium"),
                    code_snippet=issue_data.get("code_snippet")
                ))

            return ReviewResult(
                summary=data.get("summary", "Review completed"),
                issues=issues,
                score=data.get("score", 50),
                follow_up=data.get("follow_up", "Any specific concerns?"),
                strengths=data.get("strengths", []),
                improvements=data.get("improvements", []),
                similar_solutions=data.get("similar_solutions", []),
                rag_context_used=rag_used
            )

        except Exception as e:
            print(f"❌ Ошибка code review: {e}")

            # Basic fallback analysis
            return ReviewResult(
                summary="Basic code analysis completed",
                issues=[],
                score=50,
                follow_up="Could you provide more context about this code?",
                strengths=["Code structure is readable"],
                improvements=["Add more comments", "Consider error handling"],
                rag_context_used=False
            )

    def extract_code_from_message(self, message: str) -> dict:
        """Извлекает код из сообщения пользователя"""
        lines = message.split('\n')
        code_lines = []
        context_lines = []
        in_code_block = False
        detected_language = "python"  # default

        for line in lines:
            stripped = line.strip()

            # Проверяем начало/конец блока кода
            if stripped.startswith('```'):
                if not in_code_block:
                    # Извлекаем язык из маркера
                    lang_part = stripped[3:].strip()
                    if lang_part:
                        detected_language = lang_part.split()[0]  # Берем первое слово
                in_code_block = not in_code_block
                continue

            if in_code_block:
                code_lines.append(line)
            else:
                context_lines.append(line)

        # Если не нашли блок кода, пробуем эвристически
        if not code_lines:
            return self._find_code_heuristic(message)

        return {
            "code": '\n'.join(code_lines).strip(),
            "context": '\n'.join(context_lines).strip(),
            "language": detected_language
        }

    def _find_code_heuristic(self, message: str) -> dict:
        """Эвристический поиск кода в сообщении"""
        code_indicators = [
            ('def ', 'python'), ('class ', 'python'), ('import ', 'python'),
            ('function ', 'javascript'), ('const ', 'javascript'), ('let ', 'javascript'),
            ('public ', 'java'), ('private ', 'java'), ('class ', 'java'),
            ('#include ', 'cpp'), ('using ', 'cpp'),
            ('<?php', 'php'), ('echo ', 'php'),
            ('SELECT ', 'sql'), ('INSERT ', 'sql'), ('UPDATE ', 'sql')
        ]

        lines = message.split('\n')
        code_lines = []
        context_lines = []
        detected_language = "python"

        for line in lines:
            is_code = False
            for indicator, language in code_indicators:
                if indicator in line:
                    is_code = True
                    detected_language = language
                    break

            if is_code:
                code_lines.append(line)
            else:
                context_lines.append(line)

        return {
            "code": '\n'.join(code_lines),
            "context": '\n'.join(context_lines),
            "language": detected_language
        }

    def format_review_response(self, result: ReviewResult) -> str:
        """Форматирует результат ревью для пользователя"""
        response = [
            "🔍 **Результат Code Review**",
            "",
            f"📊 **Общая оценка:** {result.score}/100",
            f"📝 **Резюме:** {result.summary}",
            f"📚 **Использована база знаний:** {'✅ Да' if result.rag_context_used else '❌ Нет'}",
            ""
        ]

        if result.strengths:
            response.append("✅ **Сильные стороны:**")
            for strength in result.strengths[:3]:  # Показываем 3 главные
                response.append(f"   • {strength}")
            response.append("")

        if result.issues:
            response.append("❌ **Найденные проблемы:**")

            # Группируем проблемы по типу
            issues_by_type = {}
            for issue in result.issues:
                if issue.type not in issues_by_type:
                    issues_by_type[issue.type] = []
                issues_by_type[issue.type].append(issue)

            # Выводим проблемы по группам
            for issue_type, issues in issues_by_type.items():
                response.append(f"")
                response.append(f"**{issue_type.upper()}** ({len(issues)}):")

                for i, issue in enumerate(issues[:3], 1):  # Показываем по 3 каждого типа
                    response.append(f"   {i}. {issue.description}")
                    if issue.line:
                        response.append(f"      📍 Строка {issue.line}")
                    response.append(f"      💡 **Рекомендация:** {issue.recommendation}")

                    if issue.code_snippet:
                        response.append(f"      📝 **Код:** `{issue.code_snippet[:100]}...`")

                    response.append(f"      ⚠️  **Важность:** {issue.severity}")
        else:
            response.append("✅ **Проблем не обнаружено! Отличная работа!**")
            response.append("")

        if result.improvements:
            response.append("")
            response.append("🚀 **Рекомендации по улучшению:**")
            for improvement in result.improvements[:3]:
                response.append(f"   • {improvement}")

        if result.similar_solutions:
            response.append("")
            response.append("🔍 **Похожие подходы:**")
            for solution in result.similar_solutions[:2]:
                response.append(f"   • {solution[:150]}...")

        response.append("")
        response.append(f"💭 **Вопрос для уточнения:** {result.follow_up}")

        return "\n".join(response)

    def process_message(self, message: str) -> str:
        """Основной метод для обработки сообщения с кодом"""
        try:
            # Извлекаем код из сообщения
            extracted = self.extract_code_from_message(message)

            if not extracted["code"] or len(extracted["code"].strip()) < 10:
                return """
                ❌ **Код не найден или слишком короткий**

                Пожалуйста, отправьте код в формате:
                ```
                ваш код здесь
                ```

                Или опишите задачу и приложите код в том же сообщении.
                """

            # Проводим ревью
            review_result = self.review(
                code=extracted["code"],
                context=extracted["context"],
                language=extracted["language"]
            )

            # Форматируем ответ
            return self.format_review_response(review_result)

        except Exception as e:
            print(f"❌ Ошибка в process_message: {e}")
            return "❌ Произошла ошибка при анализе кода. Пожалуйста, проверьте формат и попробуйте еще раз."

    def get_quick_feedback(self, code: str, language: str = "python") -> str:
        """Быстрая обратная связь по коду (без детального анализа)"""
        prompt = f"""
        Дай быструю обратную связь по коду (максимум 3 предложения):

        Язык: {language}
        Код: {code[:500]}...

        Ответь одним абзацем.
        """

        try:
            response = self.llm.chat(prompt)
            return response.choices[0].message.content
        except:
            return "Код выглядит работоспособным. Рекомендую добавить комментарии и обработку ошибок."