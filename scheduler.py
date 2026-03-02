import asyncio
from collections.abc import Awaitable, Callable


class Scheduler:
    """Small async scheduler with configurable parallelism."""

    def __init__(self, max_parallel: int):
        self._sema = asyncio.Semaphore(max_parallel)
        self._tasks: dict[str, asyncio.Task] = {}

    def submit(self, request_id: str, job: Callable[[], Awaitable[None]]):
        async def runner():
            async with self._sema:
                await job()

        self._tasks[request_id] = asyncio.create_task(runner())

    def cancel(self, request_id: str):
        task = self._tasks.pop(request_id, None)
        if task:
            task.cancel()

    def cancel_all(self):
        for req_id in list(self._tasks.keys()):
            self.cancel(req_id)
