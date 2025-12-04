# db/init_db.py
import os
from pathlib import Path
from .models import init_db, SessionLocal, User
from .repository import UserRepository


def setup_database():
    """Инициализирует базу данных и создает необходимые папки"""

    # Создаем папку data если нет
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)

    # Инициализируем БД
    engine = init_db()

    print("✅ База данных готова")
    print(f"📁 Файл БД: {os.path.abspath('data/interprep.db')}")

    # Проверяем соединение
    with SessionLocal() as db:
        user_count = db.query(User).count()
        print(f"👥 Пользователей в БД: {user_count}")

    return engine


if __name__ == "__main__":
    setup_database()