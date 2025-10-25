import os
import time
import sqlite3
import json
import uuid
from contextlib import closing
from typing import Dict, Any, Optional
from dataclasses import dataclass

from aiogram import Bot, Dispatcher, executor, types
from dotenv import load_dotenv

# === LangChain Imports ===
from langchain_gigachat import GigaChat
from langchain.prompts import ChatPromptTemplate
from langchain.chains import LLMChain
from langgraph.graph import StateGraph, END

# === Agents ===
from agents.assessor_agent import AssessorAgent
from agents.planner_agent import PlannerAgent
from agents.interviewer_agent import InterviewerAgent
from agents.coordinator import CoordinatorAgent

# ========================================
# INIT
# ========================================
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

# LLM initialization (LangChain GigaChat)
llm = GigaChat(
    credentials=os.getenv("GIGACHAT_CLIENT_SECRET"),
    verify_ssl_certs=False
)


# Agents
assessor = AssessorAgent(llm)
planner = PlannerAgent(llm)
interviewer = InterviewerAgent(llm)
coordinator = CoordinatorAgent(llm)

# ========================================
# DB
# ========================================
DB_PATH = "interprep.db"

def db_connect():
    return sqlite3.connect(DB_PATH)

# ========================================
# LangGraph Pipeline
# ========================================

class IState(dict):
    """Состояние графа"""
    answer: str
    scores: Optional[dict]
    plan: Optional[list]
    interview_score: Optional[dict]

graph = StateGraph(IState)

def node_assess(state: IState):
    """Шаг оценки знаний"""
    result = assessor.assess(state["answer"], topics=["Python", "Algorithms"])
    state["scores"] = result.scores
    return state

def node_plan(state: IState):
    """Шаг планирования обучения"""
    plan = planner.make_plan(state["scores"])
    state["plan"] = plan.plan  # если возвращаешь Pydantic-модель
    return state

def node_interview(state: IState):
    """Шаг оценки ответа"""
    result = interviewer.evaluate_answer(state["answer"])
    state["interview_score"] = result.dict()
    return state

graph.add_node("assess", node_assess)
graph.add_node("plan", node_plan)
graph.add_node("interview", node_interview)
graph.set_entry_point("assess")
graph.add_edge("assess", "plan")
graph.add_edge("plan", "interview")

app = graph.compile()

# ========================================
# Telegram Logic
# ========================================
WELCOME = (
    "👋 Привет! Я InterPrep AI (vLangChain).\n"
    "Напиши уровень и трек, например:\n"
    "`level=junior track=backend`"
)

@dp.message_handler(commands=["start", "begin"])
async def start_cmd(message: types.Message):
    await message.answer(WELCOME, parse_mode="Markdown")

@dp.message_handler()
async def main_router(message: types.Message):
    """Основная логика общения"""
    user_text = message.text.strip()

    route = coordinator.route(user_text)
    await message.answer(f"🤖 LangChain думает, что нужен агент: {route.agent}")

    if route.agent == "ASSESSOR":
        result = app.invoke({"answer": user_text})
        await message.answer(f"📊 Результаты:\n{result['scores']}")
        await message.answer(f"🗓 План:\n{result['plan']}")
        await message.answer("💬 Теперь давай ответ на вопрос из собеседования!")
    elif route.agent == "INTERVIEWER":
        res = interviewer.evaluate_answer(user_text)
        await message.answer(f"Оценка: {res.score}/100\nКомментарий: {res.comment}")
    else:
        await message.answer("Пока не понял, что делать с этим запросом 🤔")

if __name__ == "__main__":
    print("🚀 InterPrep AI (LangChain version) запущен")
    executor.start_polling(dp, skip_updates=True)
