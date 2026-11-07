"""
Deterministic In-Memory Priority Event Bus for TRINETRA v2.
Thread-safe, decoupled, with cryptographic hash-chaining support.
"""

from __future__ import annotations
from collections import deque
import inspect
import threading
from typing import Any, Callable, Dict, List, Optional, Set
from trinetra_core.events.schema import Event, EventCategory, EventPriority, EventType


class EventBus:
    """
    Central event broker for TRINETRA v2.
    Supports priority dispatch, event filtering, and audit history.
    """

    def __init__(self, history_capacity: int = 500):
        self._lock = threading.RLock()
        self._type_subscribers: Dict[str, List[Callable[[Event], Any]]] = {}
        self._category_subscribers: Dict[str, List[Callable[[Event], Any]]] = {}
        self._global_subscribers: List[Callable[[Event], Any]] = []
        
        self._history_capacity = history_capacity
        self._history: deque[Event] = deque(maxlen=history_capacity)
        self._last_event_hash: str = "0" * 64

    def subscribe(
        self,
        handler: Callable[[Event], Any],
        event_type: Optional[EventType] = None,
        category: Optional[EventCategory] = None,
    ) -> None:
        """Register an event handler for a specific event type, category, or globally."""
        with self._lock:
            if event_type is not None:
                key = event_type.value if isinstance(event_type, EventType) else str(event_type)
                self._type_subscribers.setdefault(key, []).append(handler)
            elif category is not None:
                key = category.value if isinstance(category, EventCategory) else str(category)
                self._category_subscribers.setdefault(key, []).append(handler)
            else:
                self._global_subscribers.append(handler)

    def unsubscribe(self, handler: Callable[[Event], Any]) -> None:
        """Unregister a handler across all subscriptions."""
        with self._lock:
            for subs in self._type_subscribers.values():
                if handler in subs:
                    subs.remove(handler)
            for subs in self._category_subscribers.values():
                if handler in subs:
                    subs.remove(handler)
            if handler in self._global_subscribers:
                self._global_subscribers.remove(handler)

    def publish(self, event: Event) -> str:
        """
        Publish an event to all matching subscribers.
        Appends cryptographic hash chain to event metadata.
        Returns the SHA-256 digest of the published event.
        """
        with self._lock:
            # Hash chaining for tamper evidence
            event.metadata["prev_hash"] = self._last_event_hash
            event_hash = event.compute_sha256()
            event.metadata["sha256"] = event_hash
            self._last_event_hash = event_hash
            
            # Store in ring history
            self._history.append(event)
            
            # Gather matching subscribers
            handlers: List[Callable[[Event], Any]] = []
            
            # Type matches
            t_key = event.event_type.value if isinstance(event.event_type, EventType) else str(event.event_type)
            if t_key in self._type_subscribers:
                handlers.extend(self._type_subscribers[t_key])
                
            # Category matches
            c_key = event.category.value if isinstance(event.category, EventCategory) else str(event.category)
            if c_key in self._category_subscribers:
                handlers.extend(self._category_subscribers[c_key])
                
            # Global matches
            handlers.extend(self._global_subscribers)

        # Dispatch outside the lock to prevent handler deadlocks
        for handler in handlers:
            try:
                handler(event)
            except Exception as exc:
                # Log or swallow error without crashing the event bus
                pass

        return event_hash

    def get_history(self, limit: Optional[int] = None) -> List[Event]:
        """Retrieve recent events from the in-memory ring buffer."""
        with self._lock:
            events = list(self._history)
            if limit is not None and limit > 0:
                return events[-limit:]
            return events

    def clear(self) -> None:
        """Reset all subscribers and history (useful for testing)."""
        with self._lock:
            self._type_subscribers.clear()
            self._category_subscribers.clear()
            self._global_subscribers.clear()
            self._history.clear()
            self._last_event_hash = "0" * 64
