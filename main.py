import os
import sqlite3
import time
import json
import uuid
from contextlib import closing
from dataclasses import dataclass
from typing import Dict, Any, List, Optional

from aiogram import Bot, Dispatcher, executor, types
from dotenv import load_dotenv

# === LangChain / GigaChat Coordinator ===
from agents.coordinator import CoordinatorAgent
from agents.assessor_agent import AssessorAgent
from agents.planner_agent import PlannerAgent
from agents.interviewer_agent import InterviewerAgent


# Инициализация координатора
coordinator = CoordinatorAgent()
assessor = AssessorAgent()
planner = PlannerAgent()
interviewer = InterviewerAgent()

# =========================
# ENV & BOT INIT
# =========================
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN не найден в .env")

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

DB_PATH = "interprep.db"

# =========================
# DB INIT (SQLite)
# =========================
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER UNIQUE,
    created_at INTEGER
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    user_id INTEGER,
    level TEXT,
    track TEXT,
    state_json TEXT,
    created_at INTEGER,
    updated_at INTEGER,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    step_index INTEGER,
    agent TEXT,
    user_text TEXT,
    agent_response TEXT,
    ts INTEGER
);

CREATE TABLE IF NOT EXISTS feedbacks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    summary_json TEXT,
    created_at INTEGER
);
"""


def db_connect():
    return sqlite3.connect(DB_PATH)


def init_db():
    with closing(db_connect()) as conn, conn, closing(conn.cursor()) as cur:
        for stmt in SCHEMA_SQL.split(";\n\n"):
            s = stmt.strip()
            if s:
                cur.execute(s)
        conn.commit()


init_db()

# =========================
# Utilities
# =========================
def now_ts() -> int:
    return int(time.time())


def ensure_user(telegram_id: int) -> int:
    with closing(db_connect()) as conn, conn, closing(conn.cursor()) as cur:
        cur.execute("SELECT id FROM users WHERE telegram_id=?", (telegram_id,))
        row = cur.fetchone()
        if row:
            return row[0]
        cur.execute(
            "INSERT INTO users (telegram_id, created_at) VALUES (?, ?)",
            (telegram_id, now_ts()),
        )
        conn.commit()
        return cur.lastrowid


def create_session(user_id: int, level: str, track: str) -> str:
    sid = str(uuid.uuid4())
    state = {
        "phase": "assess",
        "step": 0,
        "scores": {},
        "weak_topics": [],
        "plan": [],
        "questions": [],
        "q_index": 0,
    }
    with closing(db_connect()) as conn, conn, closing(conn.cursor()) as cur:
        cur.execute(
            "INSERT INTO sessions (id, user_id, level, track, state_json, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (sid, user_id, level, track, json.dumps(state), now_ts(), now_ts()),
        )
        conn.commit()
    return sid


def load_session(sid: str) -> Optional[Dict[str, Any]]:
    with closing(db_connect()) as conn, closing(conn.cursor()) as cur:
        cur.execute("SELECT state_json FROM sessions WHERE id=?", (sid,))
        row = cur.fetchone()
        if not row:
            return None
        return json.loads(row[0])


def save_session(sid: str, state: Dict[str, Any]):
    with closing(db_connect()) as conn, conn, closing(conn.cursor()) as cur:
        cur.execute(
            "UPDATE sessions SET state_json=?, updated_at=? WHERE id=?",
            (json.dumps(state), now_ts(), sid),
        )
        conn.commit()


def add_interaction(sid: str, step_index: int, agent: str, user_text: str, agent_response: str):
    with closing(db_connect()) as conn, conn, closing(conn.cursor()) as cur:
        cur.execute(
            "INSERT INTO interactions (session_id, step_index, agent, user_text, agent_response, ts)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (sid, step_index, agent, user_text, agent_response, now_ts()),
        )
        conn.commit()

# =========================
# Heuristic Agents (MVP)
# =========================
TOPIC_POOL = {
    "backend": {
        "Python": [
            "Что такое GIL в Python и как он влияет на многопоточность?",
            "Объясните разницу между списком и кортежем.",
            "Как работает контекстный менеджер (with)?",
        ],
        "Algorithms": [
            "Что такое сложность O(log n)? Пример алгоритма.",
            "Объясните разницу между BFS и DFS.",
            "Как определить, есть ли цикл в связном списке?",
        ],
    },
}


@dataclass
class AssessResult:
    scores: Dict[str, int]
    weak_topics: List[str]
    follow_up: str


def assessor_v0(level: str, track: str, free_text: str) -> AssessResult:
    text = free_text.lower()
    python_score = 80 if any(w in text for w in ["generator", "decorator", "context manager", "gil"]) else 50
    algo_score = 80 if any(w in text for w in ["complexity", "bfs", "dfs", "binary search", "hash"]) else 40

    weak = []
    if python_score < 70:
        weak.append("Python basics")
    if algo_score < 70:
        weak.append("Algorithms complexity")

    follow = "Расскажите, чем BFS отличается от DFS и где что применять?"
    return AssessResult(scores={"Python": python_score, "Algorithms": algo_score}, weak_topics=weak, follow_up=follow)


def planner_v0(scores: Dict[str, int], goal: str = "backend internship") -> List[Dict[str, Any]]:
    weeks = [
        {"week": 1, "goals": ["Освежить основы Python"], "tasks": ["Решить 5 задач на массивы", "Пройти 2 темы по ООП"]},
        {"week": 2, "goals": ["Алгоритмы и сложность"], "tasks": ["По 3 задачи BFS/DFS", "Разобрать 3 сортировки"]},
        {"week": 3, "goals": ["Практика интервью"], "tasks": ["2 мок-интервью", "Написать 2 решения с разбором"]},
        {"week": 4, "goals": ["Финализация и резюме"], "tasks": ["Повторить слабые темы", "Собрать портфолио"]},
    ]
    return weeks


def interviewer_questions_v0(track: str) -> List[Dict[str, Any]]:
    topics = TOPIC_POOL.get(track, TOPIC_POOL["backend"])
    qs = []
    for topic, bank in topics.items():
        if bank:
            qs.append({
                "topic": topic,
                "question": bank[0],
                "expected_concepts": ["ключевые понятия по теме"],
                "difficulty": "medium",
            })
    return qs[:3] if qs else []


def interviewer_score_v0(answer: str) -> Dict[str, Any]:
    text = answer.lower()
    score = min(100, max(30, len(text) // 10))
    comment = "Неплохо, но попробуйте привести 1–2 конкретных примера." if score < 70 else "Хорошо структурированный ответ!"
    return {"score": score, "comment": comment}

# =========================
# Bot Handlers
# =========================
WELCOME = (
    "Привет! Я InterPrep AI — помогу подготовиться к стажировкам.\n"
    "Давайте начнём. Напишите уровень (junior/middle) и трек (backend).\n"
    "Например: `level=junior track=backend`"
)


@dp.message_handler(commands=["start", "begin"])
async def cmd_begin(message: types.Message):
    user_id = ensure_user(message.from_user.id)
    await message.answer(WELCOME, parse_mode="Markdown")


@dp.message_handler(lambda m: m.text and m.text.lower().startswith("level="))
async def handle_level_track(message: types.Message):
    user_id = ensure_user(message.from_user.id)
    text = message.text.strip()
    level = "junior"
    track = "backend"
    for part in text.split():
        if part.startswith("level="):
            level = part.split("=", 1)[1]
        if part.startswith("track="):
            track = part.split("=", 1)[1]

    sid = create_session(user_id, level, track)
    state = load_session(sid)

    await message.answer(f"Ок! Создана сессия. id={sid[:8]}...\nКратко опишите свой опыт (1-2 предложения).")
    state["phase"] = "assess"
    save_session(sid, state)

# === MAIN ROUTER ===
@dp.message_handler()
async def main_router(message: types.Message):
    user_id = ensure_user(message.from_user.id)

    with closing(db_connect()) as conn, closing(conn.cursor()) as cur:
        cur.execute(
            "SELECT id, state_json FROM sessions WHERE user_id=? ORDER BY updated_at DESC LIMIT 1",
            (user_id,),
        )
        row = cur.fetchone()
    if not row:
        await message.answer("Начните с /begin и укажите level/track, пожалуйста.")
        return

    sid, state_json = row
    state = json.loads(state_json)
    phase = state.get("phase", "assess")

    # === Определяем агента через GigaChat ===
    route = coordinator.route(message.text)
    await message.answer(
        f"🤖 GigaChat думает, что нужен агент: {route.agent}\nКонтекст: {route.context}"
    )

    # === Assessor — анализ знаний кандидата ===
    if route.agent == "ASSESSOR":
        res = assessor.assess(message.text, topics=["Python", "Algorithms"])
        state["scores"] = res.scores
        state["weak_topics"] = res.weak_topics
        save_session(sid, state)

        add_interaction(
            sid,
            step_index=state.get("step", 0),
            agent="ASSESSOR",
            user_text=message.text,
            agent_response=json.dumps(res.dict(), ensure_ascii=False),
        )

        plan = planner_v0(res.scores)
        state["plan"] = plan
        state["phase"] = "interview"
        state["step"] = state.get("step", 0) + 1
        qs = interviewer_questions_v0(state.get("track", "backend"))
        state["questions"] = qs
        state["q_index"] = 0
        save_session(sid, state)

        plan_text = "\n".join([
            f"Неделя {w['week']}: цели — {', '.join(w['goals'])}; задачи — {', '.join(w['tasks'])}"
            for w in plan
        ])

        await message.answer(
            "📊 Результаты диагностики:\n"
            + json.dumps(res.dict(), ensure_ascii=False, indent=2)
        )
        await message.answer("🗓 Ваш персональный план:\n" + plan_text)

        q0 = qs[0]["question"] if qs else "Расскажите о своём последнем проекте."
        await message.answer(f"💬 Вопрос 1/3: {q0}")
        return

    # === Interviewer — вопросы и оценка ответов ===
    elif route.agent == "INTERVIEWER":
        q_index = state.get("q_index", 0)
        qs = state.get("questions", [])

        if not qs:
            # генерируем вопросы через GigaChat
            qs = interviewer.generate_questions("Python")
            state["questions"] = [q.dict() for q in qs]
            save_session(sid, state)

        eval_res = interviewer.evaluate_answer(message.text)
        add_interaction(
            sid,
            step_index=state.get("step", 0),
            agent="INTERVIEWER",
            user_text=message.text,
            agent_response=json.dumps(eval_res.dict(), ensure_ascii=False),
        )

        question_obj = qs[q_index]
        # если qs хранит объекты Pydantic:
        if hasattr(question_obj, "question"):
            question_text = question_obj.question
        else:
            question_text = question_obj.get("question", "—")
        await message.answer(f"💬 Вопрос {q_index + 1}/{len(qs)}: {question_text}")

        q_index += 1
        if q_index < len(qs):
            state["q_index"] = q_index
            save_session(sid, state)
            await message.answer(f"💬 Вопрос {q_index + 1}/{len(qs)}: {qs[q_index].question}")

        else:
            state["phase"] = "finish"
            save_session(sid, state)
            await message.answer("✅ Собеседование завершено! Напишите /begin чтобы начать заново.")


    # === Planner — пока просто заглушка ===
    elif route.agent == "PLANNER":
        res = planner.make_plan(message.text)
        plan_text = "\n".join([
            f"📅 Неделя {w['week']}: цели — {', '.join(w['goals'])}; задачи — {', '.join(w['tasks'])}"
            for w in res.plan
        ])
        await message.answer("🗓 Ваш персональный план:\n" + plan_text)
        await message.answer("💡 " + res.summary)


    # === Неопознанное действие ===
    else:
        await message.answer("🤔 Пока не понял, как обработать этот запрос. Попробуйте переформулировать.")
        return


if __name__ == "__main__":
    print("InterPrep AI v0.2 — polling mode (с GigaChat)")
    executor.start_polling(dp, skip_updates=True)
