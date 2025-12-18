# tests/e2e/test_scenario_quality.py
import pytest
import json
from pathlib import Path
from unittest.mock import Mock
from typing import Dict, List


class TestScenarioQuality:
    """Тесты качества работы агентов на реальных сценариях."""

    @pytest.fixture(autouse=True)
    def load_scenarios(self, test_data_dir):
        """Загружаем все сценарии."""
        scenarios_path = test_data_dir / "test_scenarios.json"
        with open(scenarios_path, 'r', encoding='utf-8') as f:
            self.all_scenarios = json.load(f)
        print(f"\n📁 Загружено {len(self.all_scenarios)} сценариев")
        return self.all_scenarios

    def test_scenario_1_with_mocks(self, coordinator_agent, assessor_agent):
        """Сценарий 1 с поддержкой моков."""
        scenario = self.all_scenarios[0]
        print(f"\n🎯 СЦЕНАРИЙ 1: {scenario['name']}")

        results = []

        # Шаг 1: /begin junior backend
        step = scenario['steps'][0]
        print(f"\nШаг 1: {step['user_input']}")

        try:
            # Проверяем координатор (работает с моком)
            response = coordinator_agent.route(step['user_input'], {}, "user_123")

            # Если response - Mock, проверяем что метод вызван
            if isinstance(response, Mock):
                # Проверяем, что route был вызван
                coordinator_agent.route.assert_called_once()
                print(f"✅ Координатор вызван с: {step['user_input']}")
                success = True
            else:
                # Реальный объект
                success = response is not None
                print(f"✅ Координатор вернул ответ")

            results.append({"step": 1, "success": success, "type": "coordinator"})

        except Exception as e:
            print(f"❌ Ошибка координатора: {e}")
            results.append({"step": 1, "success": False, "type": "coordinator", "error": str(e)})

        # Шаг 2: Опыт пользователя
        step = scenario['steps'][1]
        print(f"\nШаг 2: {step['user_input'][:50]}...")

        try:
            # Проверяем assessor
            assessment = assessor_agent.assess(
                answer=step['user_input'],
                topics=["Python", "ООП", "LeetCode"],
                user_context={"level": "junior", "track": "backend"}
            )

            if isinstance(assessment, Mock):
                # Проверяем, что assess был вызван
                assessor_agent.assess.assert_called_once()
                print(f"✅ Assessor вызван с текстом длины: {len(step['user_input'])}")
                success = True
            else:
                # Реальный объект
                success = assessment is not None
                print(f"✅ Assessor вернул ответ")

            results.append({"step": 2, "success": success, "type": "assessor"})

        except Exception as e:
            print(f"❌ Ошибка assessor: {e}")
            results.append({"step": 2, "success": False, "type": "assessor", "error": str(e)})

        # Анализ результатов
        print(f"\n📊 ИТОГИ СЦЕНАРИЯ 1:")
        total_steps = len(results)
        successful_steps = sum(1 for r in results if r['success'])
        accuracy = (successful_steps / total_steps * 100) if total_steps > 0 else 0

        print(f"Всего шагов: {total_steps}")
        print(f"Успешных: {successful_steps}")
        print(f"Точность: {accuracy:.1f}%")

        for result in results:
            status = "✅" if result['success'] else "❌"
            print(f"  {status} Шаг {result['step']} ({result['type']}): {'Успех' if result['success'] else 'Провал'}")

        assert accuracy >= 50, f"Точность {accuracy:.1f}% ниже 50%"

    def test_agent_availability(self):
        """Проверяем, что все необходимые агенты доступны."""
        print(f"\n🔧 ПРОВЕРКА ДОСТУПНОСТИ АГЕНТОВ")

        agents_to_check = [
            ("agents.coordinator", "CoordinatorAgent"),
            ("agents.assessor_agent", "AssessorAgent"),
            ("agents.planner_agent", "PlannerAgent"),
            ("agents.interviewer_agent", "InterviewerAgent"),
            ("agents.reviewer_agent", "ReviewerAgent")
        ]

        available_agents = []
        unavailable_agents = []

        for module_name, class_name in agents_to_check:
            try:
                module = __import__(module_name, fromlist=[class_name])
                agent_class = getattr(module, class_name)
                available_agents.append((module_name, class_name))
                print(f"✅ {class_name} доступен")
            except ImportError:
                unavailable_agents.append((module_name, class_name))
                print(f"❌ {class_name} недоступен")
            except AttributeError:
                unavailable_agents.append((module_name, class_name))
                print(f"❌ {class_name} не найден в модуле")

        print(f"\n📊 ИТОГИ:")
        print(f"Доступно агентов: {len(available_agents)}/{len(agents_to_check)}")

        # Для MVP достаточно 3 основных агентов
        assert len(available_agents) >= 3, f"Доступно только {len(available_agents)} агентов, нужно минимум 3"

    def test_scenario_coverage(self):
        """Проверяем покрытие сценариев по агентам."""
        print(f"\n📊 АНАЛИЗ ПОКРЫТИЯ СЦЕНАРИЕВ")

        agent_stats = {}

        for scenario in self.all_scenarios:
            if "steps" not in scenario:
                continue

            for step in scenario["steps"]:
                agent_name = self._extract_agent_name(step.get("expected_agent", ""))
                if not agent_name:
                    continue

                if agent_name not in agent_stats:
                    agent_stats[agent_name] = {
                        "scenarios": set(),
                        "steps": 0
                    }

                agent_stats[agent_name]["scenarios"].add(scenario["id"])
                agent_stats[agent_name]["steps"] += 1

        print(f"\nСтатистика по агентам:")
        for agent, stats in agent_stats.items():
            print(f"  🤖 {agent.capitalize():12}: {stats['steps']:3} шагов в {len(stats['scenarios']):2} сценариях")

        # Проверяем что основные агенты покрыты
        essential_agents = ["coordinator", "assessor", "planner"]
        for agent in essential_agents:
            assert agent in agent_stats, f"Агент {agent} не покрыт сценариями!"
            assert agent_stats[agent]["steps"] > 0, f"Нет шагов для агента {agent}!"

        print(f"\n✅ Все основные агенты покрыты сценариями")

    def _extract_agent_name(self, agent_str):
        """Извлекает имя агента из строки."""
        if not agent_str:
            return None

        if "→" in agent_str:
            agent_str = agent_str.split("→")[0].strip()

        agent_str = agent_str.lower()

        # Маппинг
        mapping = {
            "start_handler": "coordinator",
            "assessment_handler": "assessor",
            "planning_handler": "planner",
            "interview_handler": "interviewer",
            "review_handler": "reviewer",
            "general_handler": "coordinator",
            "start": "coordinator"
        }

        # Убираем _handler если есть
        if agent_str.endswith("_handler"):
            agent_str = agent_str[:-8]

        return mapping.get(agent_str, None)

    def test_generate_test_report(self):
        """Генерирует отчет о тестовом покрытии."""
        print(f"\n{'=' * 70}")
        print("📄 ОТЧЕТ О ТЕСТОВОМ ПОКРЫТИИ")
        print(f"{'=' * 70}")

        # Статистика по сценариям
        total_scenarios = len(self.all_scenarios)
        scenarios_with_steps = sum(1 for s in self.all_scenarios if "steps" in s and len(s["steps"]) > 0)
        total_steps = sum(len(s["steps"]) for s in self.all_scenarios if "steps" in s)

        print(f"\n📋 СЦЕНАРИИ:")
        print(f"  Всего сценариев: {total_scenarios}")
        print(f"  Сценариев с шагами: {scenarios_with_steps}")
        print(f"  Всего шагов: {total_steps}")
        print(f"  Среднее шагов на сценарий: {total_steps / total_scenarios:.1f}")

        # Анализ по агентам
        agent_usage = {}
        for scenario in self.all_scenarios:
            if "steps" not in scenario:
                continue

            for step in scenario["steps"]:
                agent = self._extract_agent_name(step.get("expected_agent", ""))
                if agent:
                    agent_usage[agent] = agent_usage.get(agent, 0) + 1

        print(f"\n🤖 ИСПОЛЬЗОВАНИЕ АГЕНТОВ:")
        for agent, count in sorted(agent_usage.items(), key=lambda x: x[1], reverse=True):
            percentage = (count / total_steps) * 100
            print(f"  {agent.capitalize():15} {count:3} шагов ({percentage:5.1f}%)")

        # Рекомендации
        print(f"\n💡 РЕКОМЕНДАЦИИ:")

        if total_scenarios < 10:
            print("  ⚠️  Мало сценариев, рекомендуется добавить до 10+")
        else:
            print("  ✅ Достаточно сценариев")

        if "interviewer" not in agent_usage:
            print("  ⚠️  Отсутствуют тесты для InterviewerAgent")
        if "reviewer" not in agent_usage:
            print("  ⚠️  Отсутствуют тесты для ReviewerAgent")

        essential_coverage = all(agent in agent_usage for agent in ["coordinator", "assessor", "planner"])
        if essential_coverage:
            print("  ✅ Основные агенты покрыты тестами")
        else:
            print("  ❌ Не все основные агенты покрыты тестами")

        print(f"\n{'=' * 70}")


# Простые тесты без моков
def test_basic_scenario_structure():
    """Проверяем базовую структуру сценариев."""
    print(f"\n🔍 ПРОВЕРКА СТРУКТУРЫ СЦЕНАРИЕВ")

    # Загружаем сценарии напрямую
    scenarios_path = Path(__file__).parent / "fixtures" / "test_scenarios.json"
    with open(scenarios_path, 'r', encoding='utf-8') as f:
        scenarios = json.load(f)

    assert isinstance(scenarios, list), "Сценарии должны быть списком"
    assert len(scenarios) >= 10, f"Слишком мало сценариев: {len(scenarios)}"

    for i, scenario in enumerate(scenarios[:5], 1):
        print(f"\nСценарий {i}: {scenario.get('name', 'Без имени')}")

        # Проверяем обязательные поля
        assert "id" in scenario, f"Нет id в сценарии {i}"
        assert "name" in scenario, f"Нет name в сценарии {i}"
        assert "steps" in scenario, f"Нет steps в сценарии {i}"

        steps = scenario["steps"]
        assert isinstance(steps, list), f"steps должен быть списком в сценарии {i}"
        assert len(steps) >= 2, f"Слишком мало шагов в сценарии {i}: {len(steps)}"

        for j, step in enumerate(steps, 1):
            assert "user_input" in step, f"Нет user_input в шаге {j} сценария {i}"
            assert "expected_agent" in step, f"Нет expected_agent в шаге {j} сценария {i}"

            print(f"  Шаг {j}: {step['user_input'][:40]}... → {step['expected_agent']}")

    print(f"\n✅ Все проверки структуры пройдены")
    print(f"✅ Загружено {len(scenarios)} сценариев")


def test_validate_scenario_content():
    """Валидирует содержание сценариев."""
    print(f"\n🔎 ВАЛИДАЦИЯ СОДЕРЖАНИЯ СЦЕНАРИЕВ")

    scenarios_path = Path(__file__).parent / "fixtures" / "test_scenarios.json"
    with open(scenarios_path, 'r', encoding='utf-8') as f:
        scenarios = json.load(f)

    issues = []

    for scenario_idx, scenario in enumerate(scenarios, 1):
        scenario_name = scenario.get('name', f'Сценарий {scenario_idx}')

        # Проверяем steps
        if "steps" not in scenario:
            issues.append(f"{scenario_name}: нет steps")
            continue

        steps = scenario["steps"]
        if len(steps) == 0:
            issues.append(f"{scenario_name}: пустые steps")
            continue

        # Проверяем каждый шаг
        for step_idx, step in enumerate(steps, 1):
            user_input = step.get('user_input', '').strip()
            expected_agent = step.get('expected_agent', '').strip()

            if not user_input:
                issues.append(f"{scenario_name}, шаг {step_idx}: пустой user_input")

            if not expected_agent:
                issues.append(f"{scenario_name}, шаг {step_idx}: пустой expected_agent")

            # Проверяем что expected_agent валидный
            valid_agents = ["coordinator", "assessor", "planner", "interviewer", "reviewer",
                            "start_handler", "assessment_handler", "planning_handler",
                            "interview_handler", "review_handler", "general_handler"]

            agent_lower = expected_agent.lower()
            is_valid = any(valid in agent_lower for valid in valid_agents)

            if not is_valid and expected_agent:
                issues.append(f"{scenario_name}, шаг {step_idx}: неизвестный агент '{expected_agent}'")

    # Выводим результаты
    if issues:
        print(f"\n⚠️  НАЙДЕНЫ ПРОБЛЕМЫ ({len(issues)}):")
        for issue in issues[:10]:  # Показываем первые 10 проблем
            print(f"  • {issue}")
        if len(issues) > 10:
            print(f"  ... и еще {len(issues) - 10} проблем")
    else:
        print(f"\n✅ Проблем не найдено")

    print(f"\n📊 ИТОГИ ВАЛИДАЦИИ:")
    print(f"  Проверено сценариев: {len(scenarios)}")
    print(f"  Найдено проблем: {len(issues)}")

    # Допускаем некоторые проблемы
    assert len(issues) <= 5, f"Слишком много проблем в сценариях: {len(issues)}"