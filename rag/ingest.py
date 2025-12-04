# rag/ingest.py
import json
from pathlib import Path
import chromadb
from chromadb.config import Settings
import hashlib

BASE_DIR = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = BASE_DIR / "knowledge"
PERSIST_DIR = BASE_DIR / "chroma_db"
COLLECTION_NAME = "interprep_knowledge"


def load_all_knowledge():
    """Загружает все типы знаний"""
    documents = []
    doc_count = 0

    # 1. Загружаем вопросы из JSON
    questions_file = KNOWLEDGE_DIR / "interview_questions.json"
    if questions_file.exists():
        with open(questions_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            for q in data.get("questions", []):
                text = f"Вопрос: {q['question']}\nОтвет: {q['answer']}\nТема: {q['topic']} | Категория: {q['category']} | Сложность: {q['difficulty']} | Уровень: {q['level']}"

                documents.append({
                    "text": text,
                    "metadata": {
                        "type": "interview_question",
                        "topic": q["topic"],
                        "category": q["category"],
                        "difficulty": q["difficulty"],
                        "level": q["level"],
                        "company": q.get("company", "general"),
                        "agent": "interviewer"
                    }
                })
                doc_count += 1
        print(f"✅ Загружено {doc_count} вопросов")

    # 2. Загружаем примеры кода
    examples_file = KNOWLEDGE_DIR / "code_examples.json"
    if examples_file.exists():
        with open(examples_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            for ex in data.get("examples", []):
                text = f"Пример: {ex['title']}\nЯзык: {ex['language']}\nХороший код:\n{ex['good_code']}\n\nПлохой код:\n{ex['bad_code']}\n\nОбъяснение: {ex['explanation']}"

                documents.append({
                    "text": text,
                    "metadata": {
                        "type": "code_example",
                        "language": ex["language"],
                        "category": ex["category"],
                        "level": ex["level"],
                        "agent": "reviewer"
                    }
                })
                doc_count += 1
        print(f"✅ Загружено {len(data.get('examples', []))} примеров кода")

    # 3. Загружаем планы обучения
    plans_file = KNOWLEDGE_DIR / "learning_plan.json"
    if plans_file.exists():
        with open(plans_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            for plan in data.get("plans", []):
                for week in plan.get("weeks", []):
                    text = f"План обучения: {week['focus']}\nНеделя: {week['week']}\nТемы: {', '.join(week['topics'])}\nЗадачи: {', '.join(week['tasks'])}\nРесурсы: {', '.join(week['resources'])}"

                    documents.append({
                        "text": text,
                        "metadata": {
                            "type": "learning_plan",
                            "level": plan["level"],
                            "track": plan["track"],
                            "week": week["week"],
                            "focus": week["focus"],
                            "agent": "planner"
                        }
                    })
                    doc_count += 1
        print(f"✅ Загружено {len(data.get('plans', []))} планов обучения")

    # 4. Загружаем текстовые файлы (для обратной совместимости)
    for txt_file in KNOWLEDGE_DIR.glob("*.txt"):
        if txt_file.name != "interview_questions.json" and txt_file.name != "code_examples.json":
            try:
                with open(txt_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # Разбиваем на абзацы для лучшего поиска
                    paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]

                    for i, para in enumerate(paragraphs[:10]):  # Берем первые 10 абзацев
                        documents.append({
                            "text": para,
                            "metadata": {
                                "type": "text_knowledge",
                                "source": txt_file.name,
                                "paragraph": i,
                                "agent": "general"
                            }
                        })
                        doc_count += 1

                print(f"✅ Загружен текстовый файл: {txt_file.name}")
            except Exception as e:
                print(f"❌ Ошибка чтения {txt_file.name}: {e}")

    return documents


def create_knowledge_base():
    """Создает векторную базу знаний"""
    print("🚀 Создаю базу знаний InterPrep AI...")
    print("=" * 50)

    # Загружаем документы
    documents = load_all_knowledge()

    if not documents:
        print("❌ Нет данных для создания базы знаний!")
        print(f"Положите файлы в папку: {KNOWLEDGE_DIR}")
        print("Нужны: interview_questions.json, code_examples.json, learning_plan.json")
        return None

    print(f"📚 Всего документов: {len(documents)}")

    # Создаем папку для базы данных
    PERSIST_DIR.mkdir(exist_ok=True)

    # Подключаемся к ChromaDB
    client = chromadb.PersistentClient(
        path=str(PERSIST_DIR),
        settings=Settings(anonymized_telemetry=False)
    )

    # Удаляем старую коллекцию если есть
    try:
        client.delete_collection(COLLECTION_NAME)
        print("♻️  Удалена старая коллекция")
    except:
        pass

    # Создаем новую коллекцию
    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={
            "description": "InterPrep AI Knowledge Base",
            "version": "1.0",
            "documents_count": len(documents)
        }
    )

    print("📥 Добавляю документы в базу...")

    # Разбиваем на батчи для оптимизации
    batch_size = 100
    for i in range(0, len(documents), batch_size):
        batch = documents[i:i + batch_size]

        texts = [doc["text"] for doc in batch]
        metadatas = [doc["metadata"] for doc in batch]
        ids = [f"doc_{hashlib.md5(doc['text'].encode()).hexdigest()[:12]}_{j}"
               for j, doc in enumerate(batch, i)]

        collection.add(
            documents=texts,
            metadatas=metadatas,
            ids=ids
        )

        print(f"  Добавлено {min(i + batch_size, len(documents))}/{len(documents)} документов")

    print("=" * 50)
    print(f"✅ База знаний создана успешно!")
    print(f"📊 Документов: {collection.count()}")
    print(f"📁 Расположение: {PERSIST_DIR}")
    print(f"🏷️  Коллекция: {COLLECTION_NAME}")

    # Статистика по типам документов
    print("\n📈 Статистика по типам:")
    types_count = {}
    for doc in documents:
        doc_type = doc["metadata"].get("type", "unknown")
        types_count[doc_type] = types_count.get(doc_type, 0) + 1

    for doc_type, count in types_count.items():
        print(f"  {doc_type}: {count} документов")

    return collection


def test_knowledge_base():
    """Тестирует созданную базу знаний"""
    print("\n🧪 Тестирую базу знаний...")

    try:
        client = chromadb.PersistentClient(path=str(PERSIST_DIR))
        collection = client.get_collection(COLLECTION_NAME)

        # Тестовые запросы
        test_queries = [
            ("Python оператор //", "interview_question"),
            ("SQL JOIN отличие", "interview_question"),
            ("декоратор пример", "code_example"),
            ("план обучения", "learning_plan")
        ]

        for query, expected_type in test_queries:
            results = collection.query(
                query_texts=[query],
                n_results=1,
                where={"type": expected_type} if expected_type else None
            )

            if results["documents"]:
                print(f"✅ '{query}' -> найдено: {results['documents'][0][0][:80]}...")
            else:
                print(f"⚠️  '{query}' -> не найдено")

    except Exception as e:
        print(f"❌ Ошибка тестирования: {e}")


if __name__ == "__main__":
    collection = create_knowledge_base()
    if collection:
        test_knowledge_base()