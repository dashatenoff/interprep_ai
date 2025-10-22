from agents.assessor_agent import AssessorAgent

if __name__ == "__main__":
    agent = AssessorAgent()
    result = agent.assess(
        "Я знаю Python, могу объяснить генераторы, GIL и основы алгоритмов.",
        topics=["Python", "Algorithms"]
    )
    print(result)
