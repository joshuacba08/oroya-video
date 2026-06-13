from __future__ import annotations

import asyncio


class JobQueue:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[str] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def _ensure_queue(self) -> asyncio.Queue[str]:
        loop = asyncio.get_running_loop()
        if self._queue is None or self._loop is not loop:
            self._queue = asyncio.Queue()
            self._loop = loop
        return self._queue

    async def enqueue(self, job_id: str) -> None:
        queue = self._ensure_queue()
        await queue.put(job_id)

    async def dequeue(self) -> str:
        queue = self._ensure_queue()
        return await queue.get()

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
