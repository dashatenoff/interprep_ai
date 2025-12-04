#!/bin/bash
echo "🤖 InterPrep AI Bot - Railway Deployment (Python 3.11)"

# 1. Проверяем версию Python
echo "🐍 Python version:"
python --version

# 2. Создаем папки
mkdir -p data

# 3. Логируем окружение
echo "📁 Current dir: $(pwd)"
echo "📂 Files:"
ls -la

# 4. Проверяем токен
if [ -z "$TELEGRAM_BOT_TOKEN" ]; then
    echo "❌ ERROR: TELEGRAM_BOT_TOKEN not set!"
    exit 1
fi
echo "✅ Token is set"

# 5. Устанавливаем зависимости
echo "📦 Installing dependencies from requirements.txt..."
pip install --no-cache-dir -r requirements.txt

# 6. Проверяем установленные пакеты
echo "🔍 Installed packages:"
pip list | grep -E "(aiogram|aiohttp|sqlalchemy|python-dotenv)"

# 7. Запускаем бота
echo "🚀 Starting bot..."
exec python main.py