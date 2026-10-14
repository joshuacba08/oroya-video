from __future__ import annotations

import asyncio
import itertools

# Menor = antes. Las vistas previas en movimiento (REQ-043) pasan por delante de los exports
# en espera; dentro de una misma prioridad se respeta el orden de llegada.
PRIORITY_PREVIEW = 0
PRIORITY_NORMAL = 1


class JobQueue:
    def __init__(self) -> None:
        self._queue: asyncio.PriorityQueue[tuple[int, int, str]] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._counter = itertools.count()

    def _ensure_queue(self) -> asyncio.PriorityQueue[tuple[int, int, str]]:
        loop = asyncio.get_running_loop()
        if self._queue is None or self._loop is not loop:
            self._queue = asyncio.PriorityQueue()
            self._loop = loop
        return self._queue

    async def enqueue(self, job_id: str, priority: int = PRIORITY_NORMAL) -> None:
        queue = self._ensure_queue()
        await queue.put((priority, next(self._counter), job_id))

    async def dequeue(self) -> str:
        queue = self._ensure_queue()
        _, _, job_id = await queue.get()
        return job_id

    def task_done(self) -> None:
        if self._queue is not None:
            self._queue.task_done()

    def size(self) -> int:
        if self._queue is None:
            return 0
        return self._queue.qsize()

    def clear(self) -> None:
        if self._queue is None:
            return
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except asyncio.QueueEmpty:
                break
        self._queue = None
        self._loop = None


job_queue = JobQueue()
