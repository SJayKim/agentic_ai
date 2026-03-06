"""
Base Memory Interface - 모든 메모리 시스템의 추상 인터페이스

Reflexion 아키텍처의 메모리 시스템들이 상속받아야 하는 기본 인터페이스.
- Trajectory (단기 메모리): 현재 에피소드의 action-observation 시퀀스
- Experience (장기 메모리): 학습된 교훈들

설계 원칙:
- 저장소 교체 용이 (JSON → Redis → Vector DB)
- 검색 전략 추상화 (키워드 → 의미론적 검색)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Generic, List, Optional, TypeVar
from enum import Enum


class MemoryType(Enum):
    """메모리 유형"""
    SHORT_TERM = "short_term"   # Trajectory - 현재 세션
    LONG_TERM = "long_term"     # Experience - 영구 저장
    EPISODIC = "episodic"       # 에피소드별 기억
    SEMANTIC = "semantic"       # 의미론적 기억 (Vector DB)


@dataclass
class MemoryItem:
    """메모리 항목 기본 구조"""
    id: str
    content: Any
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


T = TypeVar("T", bound=MemoryItem)


class BaseMemory(ABC, Generic[T]):
    """
    메모리 시스템 추상 인터페이스
    
    모든 메모리 구현체(ContextManager, LessonsStore, VectorMemory)는
    이 인터페이스를 구현해야 함.
    
    Usage:
        memory = LessonsStore(storage_path="data/lessons.json")
        memory.add(lesson)
        relevant = memory.search("로그인 실패")
    """
    
    def __init__(self, memory_type: MemoryType = MemoryType.SHORT_TERM):
        self.memory_type = memory_type
        self._items: List[T] = []
    
    @abstractmethod
    def add(self, item: T) -> T:
        """
        항목 추가
        
        Args:
            item: 추가할 메모리 항목
            
        Returns:
            추가된 항목 (ID 포함)
        """
        pass
    
    @abstractmethod
    def get(self, item_id: str) -> Optional[T]:
        """
        ID로 항목 조회
        
        Args:
            item_id: 항목 ID
            
        Returns:
            메모리 항목 또는 None
        """
        pass
    
    @abstractmethod
    def search(
        self,
        query: str,
        limit: int = 5,
        **filters
    ) -> List[T]:
        """
        검색
        
        Args:
            query: 검색 쿼리
            limit: 최대 결과 수
            **filters: 추가 필터 조건
            
        Returns:
            관련 항목 리스트
        """
        pass
    
    @abstractmethod
    def update(self, item_id: str, updates: Dict[str, Any]) -> Optional[T]:
        """
        항목 업데이트
        
        Args:
            item_id: 항목 ID
            updates: 업데이트할 필드들
            
        Returns:
            업데이트된 항목 또는 None
        """
        pass
    
    @abstractmethod
    def delete(self, item_id: str) -> bool:
        """
        항목 삭제
        
        Args:
            item_id: 항목 ID
            
        Returns:
            삭제 성공 여부
        """
        pass
    
    @abstractmethod
    def clear(self) -> None:
        """모든 항목 삭제"""
        pass
    
    @abstractmethod
    def save(self) -> None:
        """영구 저장소에 저장"""
        pass
    
    @abstractmethod
    def load(self) -> None:
        """영구 저장소에서 로드"""
        pass
    
    def get_all(self) -> List[T]:
        """모든 항목 반환"""
        return self._items.copy()
    
    def count(self) -> int:
        """항목 개수"""
        return len(self._items)
    
    def is_empty(self) -> bool:
        """비어있는지 확인"""
        return len(self._items) == 0


class BaseShortTermMemory(BaseMemory[T]):
    """
    단기 메모리 추상 인터페이스
    
    Trajectory (action-observation 시퀀스) 등 현재 세션 내에서만 유효한 메모리.
    최대 크기 제한, 자동 정리 기능 포함.
    """
    
    def __init__(self, max_size: int = 100):
        super().__init__(memory_type=MemoryType.SHORT_TERM)
        self.max_size = max_size
    
    def add(self, item: T) -> T:
        """항목 추가 (크기 제한 적용)"""
        self._items.append(item)
        self._enforce_size_limit()
        return item
    
    def _enforce_size_limit(self) -> None:
        """크기 제한 적용 (오래된 항목 제거)"""
        if len(self._items) > self.max_size:
            self._items = self._items[-self.max_size:]
    
    @abstractmethod
    def get_recent(self, n: int = 10) -> List[T]:
        """최근 N개 항목 반환"""
        pass
    
    @abstractmethod
    def get_context_string(self) -> str:
        """LLM 프롬프트용 컨텍스트 문자열 반환"""
        pass


class BaseLongTermMemory(BaseMemory[T]):
    """
    장기 메모리 추상 인터페이스
    
    Experience (학습된 교훈) 등 영구적으로 저장되는 메모리.
    관련성 검색, 성공 횟수 추적 등 기능 포함.
    """
    
    def __init__(self, storage_path: Optional[str] = None):
        super().__init__(memory_type=MemoryType.LONG_TERM)
        self.storage_path = storage_path
    
    @abstractmethod
    def find_relevant(
        self,
        context: str,
        limit: int = 3
    ) -> List[T]:
        """
        컨텍스트와 관련된 항목 검색
        
        Args:
            context: 현재 상황/컨텍스트
            limit: 최대 결과 수
            
        Returns:
            관련성 높은 항목들
        """
        pass
    
    @abstractmethod
    def mark_useful(self, item_id: str) -> None:
        """항목이 유용했음을 표시 (성공 횟수 증가)"""
        pass
    
    @abstractmethod
    def get_for_prompt(self, context: str, limit: int = 3) -> str:
        """LLM 프롬프트용 문자열 반환"""
        pass
