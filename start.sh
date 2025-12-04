#!/bin/bash
echo "🚀 Starting InterPrep AI Bot..."

# Создаем необходимые папки
mkdir -p data knowledge chroma_db

echo "📁 Folders created"
echo "📂 Current directory: $(pwd)"
echo "📂 Contents:"
ls -la

# Проверяем переменные окружения
echo "🔧 Environment check:"
if [ -n "$TELEGRAM_BOT_TOKEN" ]; then
    echo "✅ TELEGRAM_BOT_TOKEN: [SET]"
else
    echo "❌ TELEGRAM_BOT_TOKEN: [NOT SET]"
    exit 1
fi

# Запускаем бота
echo "🤖 Starting bot..."
exec python main.py