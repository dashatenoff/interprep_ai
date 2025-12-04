# bot/middleware/agents_middleware.py
from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery


class AgentsMiddleware(BaseMiddleware):
    """Middleware для передачи агентов и флага RAG в хендлеры"""

    def __init__(self, agents: dict, use_rag: bool):
        super().__init__()
        self.agents = agents
        self.use_rag = use_rag

    async def __call__(
            self,
            handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
            event: Message,
            data: Dict[str, Any]
    ) -> Any:
        # Добавляем агенты и флаг RAG в данные
        data['agents'] = self.agents
        data['use_rag'] = self.use_rag
        return await handler(event, data)