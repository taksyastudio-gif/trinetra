"""
Storage Hardware Abstraction Layer (HAL) Interface.
Provides persistent, local-first encrypted storage for context memory,
settings, reminders, and audit records.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple


class StorageAdapterInterface(ABC):
    """
    Abstract interface for local persistence.
    Implementations:
    - JSON / File Storage (Default lightweight)
    - SQLite / SQLCipher (Encrypted relational)
    - MemoryStorageAdapter (Unit tests)
    """

    @abstractmethod
    def get(self, key: str, default: Any = None) -> Any:
        """Retrieve stored value by key."""
        pass

    @abstractmethod
    def set(self, key: str, value: Any) -> bool:
        """Persist a serializable key-value pair."""
        pass

    @abstractmethod
    def delete(self, key: str) -> bool:
        """Delete key from store."""
        pass

    @abstractmethod
    def query_prefix(self, prefix: str) -> List[Tuple[str, Any]]:
        """Return all key-value pairs matching a prefix (e.g. 'routine.', 'med.')."""
        pass

    @abstractmethod
    def flush(self) -> None:
        """Force write-through to physical disk/flash."""
        pass
