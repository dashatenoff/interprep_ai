import os
from sqlalchemy import create_engine, Column, Integer, String, Text, JSON, DateTime, ForeignKey, Float, Boolean
from sqlalchemy.orm import DeclarativeBase, sessionmaker, relationship, Mapped, mapped_column
from datetime import datetime
from typing import Optional, List, Dict, Any

# Создаем папку для данных, если её нет
DATA_DIR = "data"
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

# Базовый класс для всех моделей
class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(100))
    first_name: Mapped[Optional[str]] = mapped_column(String(100))
    last_name: Mapped[Optional[str]] = mapped_column(String(100))
    current_level: Mapped[str] = mapped_column(String(20), default='junior')
    current_track: Mapped[str] = mapped_column(String(50), default='backend')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_active: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    settings: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)

    # Связи
    sessions: Mapped[List["Session"]] = relationship("Session", back_populates="user", cascade="all, delete-orphan")
    assessments: Mapped[List["Assessment"]] = relationship("Assessment", back_populates="user", cascade="all, delete-orphan")
    interview_results: Mapped[List["InterviewResult"]] = relationship("InterviewResult", back_populates="user", cascade="all, delete-orphan")
    learning_plans: Mapped[List["LearningPlan"]] = relationship("LearningPlan", back_populates="user", cascade="all, delete-orphan")


class Session(Base):
    __tablename__ = 'sessions'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    session_type: Mapped[Optional[str]] = mapped_column(String(50))
    agent: Mapped[Optional[str]] = mapped_column(String(50))
    topic: Mapped[Optional[str]] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default='active')
    context_data: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Связи
    user: Mapped["User"] = relationship("User", back_populates="sessions")
    messages: Mapped[List["Message"]] = relationship("Message", back_populates="session", cascade="all, delete-orphan")

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

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey('sessions.id', ondelete='CASCADE'), nullable=False)
    role: Mapped[Optional[str]] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    message_metadata: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)

    # Связи
    session: Mapped["Session"] = relationship("Session", back_populates="messages")


class Assessment(Base):
    __tablename__ = 'assessments'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    skill_name: Mapped[str] = mapped_column(String(100), nullable=False)
    score: Mapped[Optional[int]] = mapped_column(Integer)
    max_score: Mapped[int] = mapped_column(Integer, default=100)
    feedback: Mapped[Optional[str]] = mapped_column(Text)
    details: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    assessed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    # Связи
    user: Mapped["User"] = relationship("User", back_populates="assessments")


class InterviewResult(Base):
    __tablename__ = 'interview_results'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    topic: Mapped[str] = mapped_column(String(100), nullable=False)
    level: Mapped[Optional[str]] = mapped_column(String(20))
    total_questions: Mapped[int] = mapped_column(Integer, default=0)
    correct_answers: Mapped[int] = mapped_column(Integer, default=0)
    total_score: Mapped[float] = mapped_column(Float, default=0.0)
    details: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    feedback: Mapped[Optional[str]] = mapped_column(Text)
    completed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Связи
    user: Mapped["User"] = relationship("User", back_populates="interview_results")


class LearningPlan(Base):
    __tablename__ = 'learning_plans'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    track: Mapped[Optional[str]] = mapped_column(String(50))
    level: Mapped[Optional[str]] = mapped_column(String(20))
    duration_weeks: Mapped[int] = mapped_column(Integer, default=4)
    plan_data: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Связи
    user: Mapped["User"] = relationship("User", back_populates="learning_plans")


class CodeReview(Base):
    __tablename__ = 'code_reviews'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    language: Mapped[str] = mapped_column(String(50), default='python')
    code_snippet: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[Optional[str]] = mapped_column(Text)
    score: Mapped[Optional[int]] = mapped_column(Integer)
    issues_found: Mapped[int] = mapped_column(Integer, default=0)
    review_details: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    feedback: Mapped[Optional[str]] = mapped_column(Text)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Связи
    user: Mapped["User"] = relationship("User")


# Инициализация БД
DB_PATH = os.path.join(DATA_DIR, "interprep.db")
engine = create_engine(f'sqlite:///{DB_PATH}', echo=False)
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
    print(f"✅ База данных инициализирована: {DB_PATH}")
    return engine


if __name__ == "__main__":
    # При прямом запуске файла
    init_db()
    print("✅ Таблицы созданы успешно!")