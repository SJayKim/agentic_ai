"""
Base Interfaces Package

메모리 시스템 추상화 인터페이스 정의.
"""

from .memory import (
    BaseMemory,
    BaseShortTermMemory,
    BaseLongTermMemory,
    MemoryItem,
    MemoryType,
)

__all__ = [
    # Memory
    "BaseMemory",
    "BaseShortTermMemory",
    "BaseLongTermMemory",
    "MemoryItem",
    "MemoryType",
]
