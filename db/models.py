# db/models.py
from sqlalchemy import create_engine, Column, Integer, String, Text, JSON, DateTime, ForeignKey, Float, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import json

Base = declarative_base()


class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False, index=True)
    username = Column(String(100))
    first_name = Column(String(100))
    last_name = Column(String(100))
    current_level = Column(String(20), default='junior')  # junior/middle/senior
    current_track = Column(String(50), default='backend')  # backend/frontend/data/devops
    created_at = Column(DateTime, default=datetime.utcnow)
    last_active = Column(DateTime, default=datetime.utcnow)
    settings = Column(JSON, default=dict)  # Настройки пользователя

    # Связи
    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")
    assessments = relationship("Assessment", back_populates="user", cascade="all, delete-orphan")
    interview_results = relationship("InterviewResult", back_populates="user", cascade="all, delete-orphan")
    learning_plans = relationship("LearningPlan", back_populates="user", cascade="all, delete-orphan")


class Session(Base):
    __tablename__ = 'sessions'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    session_type = Column(String(50))  # 'interview', 'assessment', 'planning', 'review'
    agent = Column(String(50))  # 'interviewer', 'assessor', 'planner', 'reviewer'
    topic = Column(String(100))  # Тема сессии (Python, Algorithms и т.д.)
    status = Column(String(20), default='active')  # 'active', 'completed', 'cancelled'
    context_data = Column(JSON, default=dict)  # Контекст сессии
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    # Связи
    user = relationship("User", back_populates="sessions")
    messages = relationship("Message", back_populates="session", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            'id': self.id,
            'session_type': self.session_type,
            'agent': self.agent,
            'topic': self.topic,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None
        }


class Message(Base):
    __tablename__ = 'messages'

    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey('sessions.id', ondelete='CASCADE'), nullable=False)
    role = Column(String(20))  # 'user', 'assistant', 'system'
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    metadata = Column(JSON, default=dict)  # Дополнительные метаданные

    # Связи
    session = relationship("Session", back_populates="messages")


class Assessment(Base):
    __tablename__ = 'assessments'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    skill_name = Column(String(100), nullable=False)
    score = Column(Integer)  # 0-100
    max_score = Column(Integer, default=100)
    feedback = Column(Text)
    details = Column(JSON, default=dict)  # Детали оценки (по вопросам, критериям)
    assessed_at = Column(DateTime, default=datetime.utcnow, index=True)

    # Связи
    user = relationship("User", back_populates="assessments")


class InterviewResult(Base):
    __tablename__ = 'interview_results'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    topic = Column(String(100), nullable=False)
    level = Column(String(20))  # junior/middle/senior
    total_questions = Column(Integer, default=0)
    correct_answers = Column(Integer, default=0)
    total_score = Column(Float, default=0.0)
    details = Column(JSON, default=dict)  # Детали по каждому вопросу
    feedback = Column(Text)
    completed_at = Column(DateTime, default=datetime.utcnow)

    # Связи
    user = relationship("User", back_populates="interview_results")


class LearningPlan(Base):
    __tablename__ = 'learning_plans'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text)
    track = Column(String(50))  # backend/frontend/data
    level = Column(String(20))  # junior/middle/senior
    duration_weeks = Column(Integer, default=4)
    plan_data = Column(JSON, default=dict)  # Структурированный план
    progress = Column(Float, default=0.0)  # 0.0 - 1.0
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Связи
    user = relationship("User", back_populates="learning_plans")


class CodeReview(Base):
    __tablename__ = 'code_reviews'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    language = Column(String(50), default='python')
    code_snippet = Column(Text, nullable=False)
    context = Column(Text)
    score = Column(Integer)  # 0-100
    issues_found = Column(Integer, default=0)
    review_details = Column(JSON, default=dict)  # Детали ревью
    feedback = Column(Text)
    reviewed_at = Column(DateTime, default=datetime.utcnow)

    # Связи
    user = relationship("User")


# Инициализация БД
engine = create_engine('sqlite:///data/interprep.db', echo=False)  # echo=True для отладки
Base.metadata.create_all(engine)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db():
    """Генератор сессии БД для использования в зависимостях"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Инициализация базы данных (создание таблиц)"""
    Base.metadata.create_all(engine)
    print("✅ База данных инициализирована")
    return engine