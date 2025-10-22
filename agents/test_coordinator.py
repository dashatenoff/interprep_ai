from agents.coordinator import CoordinatorAgent

if __name__ == "__main__":
    router = CoordinatorAgent()
    result = router.route("Проведи собеседование по Python")
    print(result)
