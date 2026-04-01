"""Asyncio-backed in-process event dispatch for the trader runtime."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

EventHandler = Callable[[object], Awaitable[None]]
_STOP_SENTINEL = object()


@dataclass(slots=True, frozen=True)
class EventSubscription:
    """Describe a single event-bus subscription."""

    subscription_id: int
    event_type: type[object]
    handler_name: str


@dataclass(slots=True)
class _HandlerBinding:
    subscription: EventSubscription
    handler: EventHandler


class InProcessEventBus:
    """Dispatch events to async subscribers through an internal asyncio queue."""

    def __init__(
        self,
        *,
        queue_maxsize: int = 0,
        dispatcher_name: str = "trader-event-bus",
    ) -> None:
        self._queue: asyncio.Queue[object] = asyncio.Queue(maxsize=queue_maxsize)
        self._dispatcher_name = dispatcher_name
        self._bindings_by_type: dict[type[object], list[_HandlerBinding]] = defaultdict(list)
        self._next_subscription_id = 1
        self._dispatcher_task: asyncio.Task[None] | None = None
        self._stopping = False

    @property
    def is_running(self) -> bool:
        """Return whether the dispatcher task is active."""
        return self._dispatcher_task is not None and not self._dispatcher_task.done()

    @property
    def pending_count(self) -> int:
        """Expose the current queue backlog for health and readiness checks."""
        return self._queue.qsize()

    @property
    def subscription_count(self) -> int:
        """Return the total number of active subscriptions."""
        return sum(len(bindings) for bindings in self._bindings_by_type.values())

    def subscribe(
        self,
        event_type: type[object],
        handler: EventHandler,
        *,
        name: str | None = None,
    ) -> EventSubscription:
        """Register a handler for events matching the given type."""
        subscription = EventSubscription(
            subscription_id=self._next_subscription_id,
            event_type=event_type,
            handler_name=name or getattr(handler, "__qualname__", repr(handler)),
        )
        self._next_subscription_id += 1
        self._bindings_by_type[event_type].append(
            _HandlerBinding(subscription=subscription, handler=handler)
        )
        return subscription

    def unsubscribe(self, subscription: EventSubscription) -> None:
        """Remove a previously registered subscription."""
        bindings = self._bindings_by_type.get(subscription.event_type)
        if not bindings:
            return

        remaining = [
            binding
            for binding in bindings
            if binding.subscription.subscription_id != subscription.subscription_id
        ]
        if remaining:
            self._bindings_by_type[subscription.event_type] = remaining
            return

        self._bindings_by_type.pop(subscription.event_type, None)

    async def start(self) -> None:
        """Start the dispatcher loop."""
        if self.is_running:
            raise RuntimeError("event bus is already running")

        self._stopping = False
        self._dispatcher_task = asyncio.create_task(
            self._dispatch_loop(),
            name=self._dispatcher_name,
        )

    async def publish(self, event: object) -> None:
        """Enqueue an event for asynchronous dispatch."""
        if not self.is_running:
            raise RuntimeError("event bus must be started before publishing events")
        if self._stopping:
            raise RuntimeError("event bus is stopping and no longer accepts new events")
        await self._queue.put(event)

    async def stop(self) -> None:
        """Drain queued work, stop the dispatcher, and await its completion."""
        if self._dispatcher_task is None:
            return

        dispatcher_task = self._dispatcher_task
        self._stopping = True

        try:
            if dispatcher_task.done():
                await dispatcher_task
            else:
                await self._queue.join()
                await self._queue.put(_STOP_SENTINEL)
                await dispatcher_task
        finally:
            self._dispatcher_task = None
            self._stopping = False

    async def wait_until_stopped(self) -> None:
        """Wait until the dispatcher task exits."""
        if self._dispatcher_task is None:
            return
        await asyncio.shield(self._dispatcher_task)

    async def _dispatch_loop(self) -> None:
        while True:
            event = await self._queue.get()
            try:
                if event is _STOP_SENTINEL:
                    return

                for binding in self._matching_bindings(event):
                    await binding.handler(event)
            finally:
                self._queue.task_done()

    def _matching_bindings(self, event: object) -> list[_HandlerBinding]:
        bindings: list[_HandlerBinding] = []
        for event_type, registered in self._bindings_by_type.items():
            if isinstance(event, event_type):
                bindings.extend(registered)
        return bindings
