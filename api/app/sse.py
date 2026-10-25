import asyncio
import json
from collections import defaultdict

import asyncpg
from fastapi.sse import format_sse_event

from api.app.db import JobFailure, Jobs

HEARTBEAT_SECONDS = 15


class EventBus:
    def __init__(self, jobs: Jobs):
        self.jobs = jobs
        self.subscribers = defaultdict(set)

    async def emit(self, job_id, event_type, payload):
        event = await self.jobs.append(job_id, event_type, payload)
        if not isinstance(event, JobFailure):
            # Notifications are bounded wakeups; the journal supplies ordered data.
            for queue in self.subscribers.get(job_id, ()):
                if not queue.full():
                    queue.put_nowait(event)
        return event

    async def stream(self, job_id, cursor=0, *, demo_fixture=False):
        queue = asyncio.Queue(maxsize=1)
        self.subscribers[job_id].add(queue)  # Subscribe BEFORE taking the replay snapshot.
        try:
            while True:
                for event in await self.jobs.read_events(job_id, cursor):
                    if event.seq <= cursor:
                        continue
                    cursor = event.seq
                    payload = event.payload.model_dump(mode="json")
                    if demo_fixture:
                        payload["demo_fixture"] = True
                    yield format_sse_event(
                        id=str(cursor), event=event.type, data_str=json.dumps(payload)
                    )
                    if event.type == "done":
                        return
                if await self.jobs.finished(job_id, cursor):
                    return
                try:
                    await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
                except TimeoutError:
                    yield format_sse_event(comment="ping")
                    # Also recover commits from another worker or a lost notification.
        except (asyncpg.PostgresError, asyncpg.InterfaceError, OSError, TimeoutError):
            # Close for EventSource to reconnect and replay; never fabricate a durable ID.
            return
        finally:
            self.subscribers[job_id].discard(queue)
            if not self.subscribers[job_id]:
                del self.subscribers[job_id]
