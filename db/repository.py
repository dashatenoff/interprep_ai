# db/repository.py
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_, or_
from .models import User, Session as DBSession, Message, Assessment, InterviewResult, LearningPlan, CodeReview
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any


class UserRepository:
    @staticmethod
    def get_or_create_user(db: Session, telegram_id: int, **kwargs):
        """Получает или создает пользователя"""
        user = db.query(User).filter(User.telegram_id == telegram_id).first()

        if not user:
            user = User(
                telegram_id=telegram_id,
                username=kwargs.get('username'),
                first_name=kwargs.get('first_name'),
                last_name=kwargs.get('last_name'),
                current_level=kwargs.get('level', 'junior'),
                current_track=kwargs.get('track', 'backend')
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        else:
            # Обновляем последнюю активность
            user.last_active = datetime.utcnow()
            if kwargs.get('username'):
                user.username = kwargs.get('username')
            db.commit()

        return user

    @staticmethod
    def update_user_settings(db: Session, telegram_id: int, settings: Dict):
        """Обновляет настройки пользователя"""
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
        if user:
            if user.settings:
                user.settings.update(settings)
            else:
                user.settings = settings
            db.commit()

    @staticmethod
    def update_user_level_track(db: Session, telegram_id: int, level: str, track: str):
        """Обновляет уровень и направление пользователя"""
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
        if user:
            user.current_level = level
            user.current_track = track
            db.commit()


class SessionRepository:
    @staticmethod
    def create_session(db: Session, telegram_id: int, session_type: str, agent: str, topic: str = None):
        """Создает новую сессию"""
        user = UserRepository.get_or_create_user(db, telegram_id)

        session = DBSession(
            user_id=user.id,
            session_type=session_type,
            agent=agent,
            topic=topic or '',
            status='active',
            context_data={}
        )

        db.add(session)
        db.commit()
        db.refresh(session)
        return session

    @staticmethod
    def add_message(db: Session, session_id: int, role: str, content: str, metadata: Dict = None):
        """Добавляет сообщение в сессию"""
        message = Message(
            session_id=session_id,
            role=role,
            content=content,
            metadata=metadata or {}
        )

        db.add(message)
        db.commit()
        return message

    @staticmethod
    def get_session_messages(db: Session, session_id: int, limit: int = 20):
        """Получает сообщения сессии"""
        messages = db.query(Message).filter(
            Message.session_id == session_id
        ).order_by(Message.timestamp.asc()).limit(limit).all()

        return [{
            'role': msg.role,
            'content': msg.content,
            'timestamp': msg.timestamp
        } for msg in messages]

    @staticmethod
    def complete_session(db: Session, session_id: int):
        """Завершает сессию"""
        session = db.query(DBSession).filter(DBSession.id == session_id).first()
        if session and session.status == 'active':
            session.status = 'completed'
            session.completed_at = datetime.utcnow()
            db.commit()

    @staticmethod
    def get_user_sessions(db: Session, telegram_id: int, limit: int = 10):
        """Получает сессии пользователя"""
        user = UserRepository.get_or_create_user(db, telegram_id)

        sessions = db.query(DBSession).filter(
            DBSession.user_id == user.id
        ).order_by(desc(DBSession.created_at)).limit(limit).all()

        return [session.to_dict() for session in sessions]


class AssessmentRepository:
    @staticmethod
    def save_assessment(db: Session, telegram_id: int, skill_data: Dict):
        """Сохраняет результат оценки"""
        user = UserRepository.get_or_create_user(db, telegram_id)

        assessment = Assessment(
            user_id=user.id,
            skill_name=skill_data.get('skill_name', 'General'),
            score=skill_data.get('score', 0),
            max_score=skill_data.get('max_score', 100),
            feedback=skill_data.get('feedback', ''),
            details=skill_data.get('details', {}),
            assessed_at=datetime.utcnow()
        )

        db.add(assessment)
        db.commit()
        return assessment

    @staticmethod
    def get_user_assessments(db: Session, telegram_id: int, limit: int = 20):
        """Получает оценки пользователя"""
        user = UserRepository.get_or_create_user(db, telegram_id)

        assessments = db.query(Assessment).filter(
            Assessment.user_id == user.id
        ).order_by(desc(Assessment.assessed_at)).limit(limit).all()

        return assessments


class InterviewRepository:
    @staticmethod
    def save_interview_result(db: Session, telegram_id: int, result_data: Dict):
        """Сохраняет результат интервью"""
        user = UserRepository.get_or_create_user(db, telegram_id)

        result = InterviewResult(
            user_id=user.id,
            topic=result_data.get('topic', 'General'),
            level=result_data.get('level', 'junior'),
            total_questions=result_data.get('total_questions', 0),
            correct_answers=result_data.get('correct_answers', 0),
            total_score=result_data.get('total_score', 0.0),
            details=result_data.get('details', {}),
            feedback=result_data.get('feedback', ''),
            completed_at=datetime.utcnow()
        )

        db.add(result)
        db.commit()
        return result

    @staticmethod
    def get_interview_stats(db: Session, telegram_id: int):
        """Получает статистику по интервью пользователя"""
        user = UserRepository.get_or_create_user(db, telegram_id)

        results = db.query(InterviewResult).filter(
            InterviewResult.user_id == user.id
        ).order_by(desc(InterviewResult.completed_at)).limit(10).all()

        if not results:
            return None

        total_interviews = len(results)
        avg_score = sum(r.total_score for r in results) / total_interviews

        return {
            'total_interviews': total_interviews,
            'average_score': round(avg_score, 1),
            'last_interview': results[0].completed_at if results else None,
            'topics_covered': list(set(r.topic for r in results))
        }


class PlanRepository:
    @staticmethod
    def save_learning_plan(db: Session, telegram_id: int, plan_data: Dict):
        """Сохраняет план обучения"""
        user = UserRepository.get_or_create_user(db, telegram_id)

        plan = LearningPlan(
            user_id=user.id,
            title=plan_data.get('title', 'План обучения'),
            description=plan_data.get('description', ''),
            track=plan_data.get('track', user.current_track),
            level=plan_data.get('level', user.current_level),
            duration_weeks=plan_data.get('duration_weeks', 4),
            plan_data=plan_data.get('plan_data', {}),
            progress=plan_data.get('progress', 0.0),
            is_active=True
        )

        db.add(plan)
        db.commit()
        return plan

    @staticmethod
    def update_plan_progress(db: Session, plan_id: int, progress: float):
        """Обновляет прогресс плана"""
        plan = db.query(LearningPlan).filter(LearningPlan.id == plan_id).first()
        if plan:
            plan.progress = min(1.0, max(0.0, progress))  # Ограничиваем 0-1
            plan.updated_at = datetime.utcnow()
            db.commit()

    @staticmethod
    def get_active_plan(db: Session, telegram_id: int):
        """Получает активный план пользователя"""
        user = UserRepository.get_or_create_user(db, telegram_id)

        plan = db.query(LearningPlan).filter(
            and_(
                LearningPlan.user_id == user.id,
                LearningPlan.is_active == True
            )
        ).order_by(desc(LearningPlan.created_at)).first()

        return plan


class ReviewRepository:
    @staticmethod
    def save_code_review(db: Session, telegram_id: int, review_data: Dict):
        """Сохраняет результат code review"""
        user = UserRepository.get_or_create_user(db, telegram_id)

        review = CodeReview(
            user_id=user.id,
            language=review_data.get('language', 'python'),
            code_snippet=review_data.get('code_snippet', ''),
            context=review_data.get('context', ''),
            score=review_data.get('score', 0),
            issues_found=review_data.get('issues_found', 0),
            review_details=review_data.get('review_details', {}),
            feedback=review_data.get('feedback', ''),
            reviewed_at=datetime.utcnow()
        )

        db.add(review)
        db.commit()
        return review


def get_user_stats(db: Session, telegram_id: int) -> Dict[str, Any]:
    """Получает полную статистику пользователя"""
    user = UserRepository.get_or_create_user(db, telegram_id)

    # Количество сессий по типам
    session_types = db.query(
        DBSession.session_type,
        DBSession.agent
    ).filter(DBSession.user_id == user.id).all()

    # Последние оценки
    latest_assessments = db.query(Assessment).filter(
        Assessment.user_id == user.id
    ).order_by(desc(Assessment.assessed_at)).limit(5).all()

    # Активный план
    active_plan = PlanRepository.get_active_plan(db, telegram_id)

    # Статистика по интервью
    interview_stats = InterviewRepository.get_interview_stats(db, telegram_id)

    return {
        'user': {
            'username': user.username,
            'level': user.current_level,
            'track': user.current_track,
            'created_at': user.created_at,
            'last_active': user.last_active
        },
        'sessions_by_type': {
            session_type: len([s for s in session_types if s[0] == session_type])
            for session_type in set(st[0] for st in session_types)
        },
        'latest_assessments': [
            {'skill': a.skill_name, 'score': a.score, 'date': a.assessed_at}
            for a in latest_assessments
        ],
        'active_plan': {
            'title': active_plan.title if active_plan else None,
            'progress': active_plan.progress if active_plan else 0
        },
        'interview_stats': interview_stats
    }