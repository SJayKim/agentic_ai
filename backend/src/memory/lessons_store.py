"""
Lessons Store - Reflection 결과 저장 및 활용

BaseLongTermMemory를 상속받아 구현.
학습된 교훈들을 영구 저장하고 관련 상황에서 검색.

검색 전략:
1. 시맨틱 검색 (sentence-transformers, 선택) — 의미 기반 유사도
2. 키워드 매칭 (기본) — 단어 겹침 기반
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid

from src.base.memory import BaseLongTermMemory, MemoryItem, MemoryType
from src.config.config_loader import ConfigLoader


@dataclass
class Lesson(MemoryItem):
    """학습된 교훈 (MemoryItem 상속)"""
    category: str = "general"  # tool_selection, parameter_extraction, error_handling
    problem: str = ""          # 발생한 문제
    solution: str = ""         # 해결 방법
    context: str = ""          # 어떤 상황에서
    success_count: int = 0     # 이 교훈이 도움이 된 횟수
    
    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())[:8]
        # content는 problem + solution 조합
        if not self.content:
            self.content = f"{self.problem}: {self.solution}"
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "category": self.category,
            "problem": self.problem,
            "solution": self.solution,
            "context": self.context,
            "success_count": self.success_count,
        })
        return base
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Lesson":
        """딕셔너리에서 Lesson 생성"""
        return cls(
            id=data.get("id", ""),
            content=data.get("content", ""),
            category=data.get("category", "general"),
            problem=data.get("problem", ""),
            solution=data.get("solution", ""),
            context=data.get("context", ""),
            created_at=data.get("created_at", ""),
            success_count=data.get("success_count", 0),
            metadata=data.get("metadata", {})
        )


class SemanticSearchIndex:
    """
    선택적 시맨틱 검색 인덱스 (sentence-transformers)
    
    사용 가능한 경우 의미 기반 유사도로 교훈을 검색합니다.
    sentence-transformers가 없으면 graceful하게 비활성화됩니다.
    """
    
    def __init__(self):
        self._model = None
        self._embeddings = None  # numpy array (N, D)
        self._ids: List[str] = []
        self._available = False
        self._init_model()
    
    def _init_model(self):
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer("all-MiniLM-L6-v2")
            self._available = True
        except ImportError:
            self._available = False
    
    @property
    def available(self) -> bool:
        return self._available
    
    def build_index(self, lessons: List[Lesson]) -> None:
        """교훈 목록에서 인덱스 빌드"""
        if not self._available or not lessons:
            return
        
        import numpy as np
        texts = [f"{l.problem} {l.solution} {l.context}" for l in lessons]
        self._embeddings = self._model.encode(texts, normalize_embeddings=True,
                                               show_progress_bar=False)
        self._ids = [l.id for l in lessons]
    
    def add_item(self, lesson: Lesson) -> None:
        """단일 교훈 추가"""
        if not self._available:
            return
        
        import numpy as np
        text = f"{lesson.problem} {lesson.solution} {lesson.context}"
        embedding = self._model.encode([text], normalize_embeddings=True,
                                        show_progress_bar=False)
        
        if self._embeddings is not None and len(self._embeddings) > 0:
            self._embeddings = np.vstack([self._embeddings, embedding])
        else:
            self._embeddings = embedding
        self._ids.append(lesson.id)
    
    def search(self, query: str, limit: int = 5) -> List[tuple]:
        """
        시맨틱 검색
        
        Returns:
            [(lesson_id, similarity_score), ...]
        """
        if not self._available or self._embeddings is None or len(self._embeddings) == 0:
            return []
        
        import numpy as np
        q_emb = self._model.encode([query], normalize_embeddings=True,
                                    show_progress_bar=False)
        similarities = (self._embeddings @ q_emb.T).flatten()
        
        top_indices = np.argsort(similarities)[::-1][:limit]
        results = []
        for idx in top_indices:
            if similarities[idx] > 0.3:  # 최소 임계값
                results.append((self._ids[idx], float(similarities[idx])))
        return results
    
    def remove_item(self, lesson_id: str) -> None:
        """인덱스에서 항목 제거"""
        if not self._available or lesson_id not in self._ids:
            return
        
        import numpy as np
        idx = self._ids.index(lesson_id)
        self._ids.pop(idx)
        if self._embeddings is not None:
            self._embeddings = np.delete(self._embeddings, idx, axis=0)


class LessonsStore(BaseLongTermMemory[Lesson]):
    """
    Lessons 저장소 - BaseLongTermMemory 구현체
    
    - Reflection 결과 저장
    - 유사 상황에서 교훈 검색
    - 성공/실패 패턴 학습
    """
    
    def __init__(self, storage_path: Optional[str] = None):
        # 설정 로드
        config = ConfigLoader()
        
        if storage_path:
            path = storage_path
        else:
            storage_file = config.get("lessons.storage_file", "data/lessons.json")
            path = str(Path(__file__).parent.parent.parent / storage_file)
        
        super().__init__(storage_path=path)
        
        self.max_lessons = config.get("lessons.max_lessons", 100)
        self._storage_file = Path(path)
        self._storage_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 시맨틱 검색 인덱스
        self._semantic_index = SemanticSearchIndex()
        
        # 저장소에서 로드
        self.load()
        
        # 로드 후 시맨틱 인덱스 빌드
        if self._items:
            self._semantic_index.build_index(self._items)
    
    # ============ BaseMemory 구현 ============
    
    def add(self, item: Lesson) -> Lesson:
        """교훈 추가 (중복 체크)"""
        # 중복 체크
        for lesson in self._items:
            if lesson.problem == item.problem and lesson.solution == item.solution:
                return lesson
        
        self._items.append(item)
        
        # 시맨틱 인덱스에 추가
        self._semantic_index.add_item(item)
        
        # 최대 개수 제한
        if len(self._items) > self.max_lessons:
            # 가장 오래되고 사용 횟수 적은 것 제거
            self._items.sort(key=lambda x: (x.success_count, x.created_at))
            self._items = self._items[-(self.max_lessons):]
        
        self.save()
        return item
    
    def get(self, item_id: str) -> Optional[Lesson]:
        """ID로 교훈 조회"""
        for lesson in self._items:
            if lesson.id == item_id:
                return lesson
        return None
    
    def search(self, query: str, limit: int = 5, **filters) -> List[Lesson]:
        """교훈 검색"""
        category = filters.get("category")
        return self.find_relevant_lessons(query, category=category, limit=limit)
    
    def update(self, item_id: str, updates: Dict[str, Any]) -> Optional[Lesson]:
        """교훈 업데이트"""
        for lesson in self._items:
            if lesson.id == item_id:
                for key, value in updates.items():
                    if hasattr(lesson, key):
                        setattr(lesson, key, value)
                lesson.updated_at = datetime.now().isoformat()
                self.save()
                return lesson
        return None
    
    def delete(self, item_id: str) -> bool:
        """교훈 삭제"""
        for i, lesson in enumerate(self._items):
            if lesson.id == item_id:
                self._semantic_index.remove_item(item_id)
                del self._items[i]
                self.save()
                return True
        return False
    
    def clear(self) -> None:
        """모든 교훈 삭제"""
        self._items = []
        self._semantic_index = SemanticSearchIndex()
        self.save()
    
    def save(self) -> None:
        """영구 저장소에 저장"""
        data = [lesson.to_dict() for lesson in self._items]
        self._storage_file.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    
    def load(self) -> None:
        """영구 저장소에서 로드"""
        if self._storage_file.exists():
            try:
                data = json.loads(self._storage_file.read_text())
                self._items = [Lesson.from_dict(item) for item in data]
            except (json.JSONDecodeError, KeyError):
                self._items = []
        else:
            self._items = []
        
        # 시맨틱 인덱스 재빌드
        if self._items and hasattr(self, '_semantic_index'):
            self._semantic_index.build_index(self._items)
    
    # ============ BaseLongTermMemory 구현 ============
    
    def find_relevant(self, context: str, limit: int = 3) -> List[Lesson]:
        """컨텍스트와 관련된 교훈 검색"""
        return self.find_relevant_lessons(context, limit=limit)
    
    def mark_useful(self, item_id: str) -> None:
        """교훈이 유용했음을 표시"""
        self.mark_success(item_id)
    
    def get_for_prompt(self, context: str, limit: int = 3) -> str:
        """LLM 프롬프트용 문자열"""
        return self.get_lessons_for_prompt(context, limit=limit)
    
    # ============ 편의 메서드 ============
    
    @property
    def lessons(self) -> List[Lesson]:
        """기존 코드 호환성을 위한 프로퍼티"""
        return self._items
    
    def add_lesson(
        self,
        problem: str,
        solution: str,
        category: str = "general",
        context: str = ""
    ) -> Lesson:
        """새 교훈 추가"""
        lesson = Lesson(
            id="",
            content="",
            category=category,
            problem=problem,
            solution=solution,
            context=context,
        )
        return self.add(lesson)
    
    def add_from_reflection(self, reflection: dict) -> Optional[Lesson]:
        """Reflection 결과에서 교훈 추출"""
        problem = reflection.get("problem", reflection.get("analysis", ""))
        solution = reflection.get("improvement", reflection.get("solution", reflection.get("lesson", "")))
        
        if not problem or not solution:
            return None
        
        # 카테고리 추론
        category = "general"
        problem_lower = problem.lower()
        if "tool" in problem_lower or "선택" in problem:
            category = "tool_selection"
        elif "param" in problem_lower or "파라미터" in problem:
            category = "parameter_extraction"
        elif "error" in problem_lower or "오류" in problem or "실패" in problem:
            category = "error_handling"
        
        return self.add_lesson(
            problem=problem,
            solution=solution,
            category=category,
            context=reflection.get("context", "")
        )
    
    def find_relevant_lessons(
        self,
        query: str,
        category: Optional[str] = None,
        limit: int = 3
    ) -> List[Lesson]:
        """관련 교훈 검색 (시맨틱 + 키워드 하이브리드)"""
        # --- 1) 시맨틱 검색 ---
        semantic_scores: Dict[str, float] = {}
        if self._semantic_index._available:
            for lesson_id, sim in self._semantic_index.search(query, limit=limit * 2):
                semantic_scores[lesson_id] = sim
        
        # --- 2) 키워드 검색 ---
        keyword_scores: Dict[str, float] = {}
        query_lower = query.lower()
        for lesson in self._items:
            score = 0.0
            if query_lower in lesson.problem.lower():
                score += 2.0
            if query_lower in lesson.solution.lower():
                score += 1.0
            if query_lower in lesson.context.lower():
                score += 1.0
            query_words = set(query_lower.split())
            problem_words = set(lesson.problem.lower().split())
            score += len(query_words & problem_words)
            if score > 0:
                keyword_scores[lesson.id] = score
        
        # --- 3) 점수 통합 (RRF 방식) ---
        all_ids = set(semantic_scores) | set(keyword_scores)
        combined: List[tuple] = []
        for lid in all_ids:
            sem = semantic_scores.get(lid, 0.0)
            kw = keyword_scores.get(lid, 0.0)
            # 키워드 점수를 0-1로 정규화
            max_kw = max(keyword_scores.values()) if keyword_scores else 1.0
            kw_norm = kw / max_kw if max_kw > 0 else 0.0
            # 시맨틱 70% + 키워드 30% 가중합
            final = sem * 0.7 + kw_norm * 0.3
            combined.append((lid, final))
        
        combined.sort(key=lambda x: -x[1])
        
        # --- 4) 카테고리 필터 및 결과 반환 ---
        id_to_lesson = {l.id: l for l in self._items}
        results = []
        for lid, _ in combined:
            lesson = id_to_lesson.get(lid)
            if not lesson:
                continue
            if category and lesson.category != category:
                continue
            results.append(lesson)
            if len(results) >= limit:
                break
        
        # 시맨틱 검색 불가 시 키워드 전용 폴백
        if not results and not semantic_scores:
            fallback = sorted(keyword_scores.items(), key=lambda x: -x[1])[:limit]
            for lid, _ in fallback:
                lesson = id_to_lesson.get(lid)
                if lesson and (not category or lesson.category == category):
                    results.append(lesson)
        
        return results
    
    def mark_success(self, lesson_id: str) -> None:
        """교훈이 도움이 됨을 표시"""
        for lesson in self._items:
            if lesson.id == lesson_id:
                lesson.success_count += 1
                self.save()
                break
    
    def get_lessons_for_prompt(self, query: str, limit: int = 3) -> str:
        """LLM 프롬프트용 lessons 문자열"""
        relevant = self.find_relevant_lessons(query, limit=limit)
        
        if not relevant:
            return ""
        
        lines = ["## 이전 학습 내용"]
        for lesson in relevant:
            lines.append(f"- 문제: {lesson.problem}")
            lines.append(f"  해결: {lesson.solution}")
        
        return "\n".join(lines)
    
    def get_all_lessons(self) -> List[Lesson]:
        """모든 lessons 반환"""
        return self._items
