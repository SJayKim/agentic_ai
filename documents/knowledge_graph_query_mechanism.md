# Knowledge Graph 쿼리 메커니즘 상세 문서

## 개요

본 문서는 사용자 질문이 들어왔을 때, 에이전트가 Knowledge Graph(KG)에서 관련 정보를 찾아 답변을 생성하기까지의 **전체 파이프라인**을 단계별로 설명합니다.

### 기술 스택

| 구성 요소 | 사용 기술 |
|-----------|----------|
| KG 프레임워크 | [LightRAG](https://github.com/HKUDS/LightRAG) (HKUDS/LightRAG) |
| 에이전트 프레임워크 | LangGraph (ReAct + Reflexion 패턴) |
| LLM (라우팅/직접답변) | Gemini 2.5 Flash |
| LLM (추론/평가/반성) | Gemini 3 Flash Preview |
| LLM (LightRAG 내부) | Gemini 2.5 Flash |
| 임베딩 모델 | sentence-transformers/all-MiniLM-L6-v2 (384차원, 로컬) |
| 벡터 스토리지 | LightRAG 자체 JSON 기반 벡터 스토리지 |
| 그래프 스토리지 | GraphML (XML 기반 그래프 포맷) |

---

## 저장소 구조 (data/rag_storage/)

KG가 사용하는 파일들과 각각의 역할:

```
data/rag_storage/
├── graph_chunk_entity_relation.graphml   # 그래프 본체 (노드=엔티티, 엣지=관계)
├── vdb_entities.json                     # 엔티티 벡터DB (임베딩 + 메타데이터)
├── vdb_relationships.json                # 관계 벡터DB (임베딩 + 메타데이터)
├── vdb_chunks.json                       # 텍스트 청크 벡터DB
├── kv_store_full_docs.json               # 원본 문서 전체 텍스트
├── kv_store_full_entities.json           # 문서별 엔티티 매핑
├── kv_store_full_relations.json          # 문서별 관계 매핑
├── kv_store_text_chunks.json             # 텍스트 청크 (분할된 문서 조각)
├── kv_store_entity_chunks.json           # 엔티티-청크 연결 정보
├── kv_store_relation_chunks.json         # 관계-청크 연결 정보
├── kv_store_doc_status.json              # 문서 인제스트 상태
├── kv_store_llm_response_cache.json      # LLM 응답 캐시
└── document_summaries.json               # 문서 구조화 요약 캐시
```

### 벡터DB 상세

| 벡터DB | 항목 수 | 임베딩 차원 | 검색 대상 |
|--------|---------|------------|----------|
| `vdb_entities.json` | 938개 | 384 | 엔티티명 + 설명 텍스트 |
| `vdb_relationships.json` | 1,281개 | 384 | 관계 설명 텍스트 |
| `vdb_chunks.json` | 47개 | 384 | 원본 문서 텍스트 청크 |

각 벡터DB의 데이터 항목 구조:

```json
// vdb_entities.json 항목
{
  "__id__": "고유ID",
  "__created_at__": "생성일시",
  "entity_name": "PLANTYNET",
  "content": "Plantynet is an IT company based in South Korea...",
  "source_id": "청크ID",
  "file_path": "파일경로",
  "vector": [0.012, -0.034, ...]  // 384차원 임베딩
}

// vdb_relationships.json 항목
{
  "__id__": "고유ID",
  "src_id": "소스 엔티티",
  "tgt_id": "타겟 엔티티",
  "content": "paid by, payment method...",
  "source_id": "청크ID",
  "vector": [0.023, -0.045, ...]  // 384차원 임베딩
}

// vdb_chunks.json 항목
{
  "__id__": "고유ID",
  "content": "[Document: 파일명.pdf] 문서 내용...",
  "full_doc_id": "원본 문서 ID",
  "file_path": "파일경로",
  "vector": [0.015, -0.028, ...]  // 384차원 임베딩
}
```

---

## 쿼리 파이프라인 전체 흐름

사용자가 **"플랜티넷 2026년 개발 계획 알려줘"** 라고 질문한다고 가정합니다.

```
사용자 쿼리
    │
    ▼
┌──────────────────────────────────────────────────────┐
│  [1단계] Router Node (gemini-2.5-flash)              │
│  "tool_query" vs "general_chat" 분류                 │
│  → 도구 목록 기반 판단 → "tool_query"                │
└──────────────────────────────────────────────────────┘
    │ tool_query
    ▼
┌──────────────────────────────────────────────────────┐
│  [2단계] Actor Node (gemini-3-flash-preview)         │
│  ReAct 패턴: Thought → Action → Observation          │
│  → action: "query_knowledge_graph"                   │
│  → action_input: {"query": "플랜티넷 2026년 개발계획"} │
└──────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────┐
│  [3단계] Tool Executor Node                           │
│  LightRAG.aquery(query, mode="hybrid") 호출          │
│                                                      │
│  ┌─ [3-1] 키워드 추출 (LLM 호출 #1)                 │
│  │   hl_keywords: ["개발 계획", "기술 연구소"]        │
│  │   ll_keywords: ["플랜티넷", "2026년"]             │
│  │                                                   │
│  ├─ [3-2] Hybrid KG 검색                             │
│  │   ├─ Local: 엔티티 벡터 검색 → 연결 관계 확장     │
│  │   ├─ Global: 관계 벡터 검색 → 연결 엔티티 확장    │
│  │   └─ Round-Robin 병합 + 중복 제거                 │
│  │                                                   │
│  ├─ [3-3] 토큰 절단 + 청크 병합                      │
│  │                                                   │
│  └─ [3-4] 답변 생성 (LLM 호출 #2)                   │
│       컨텍스트(엔티티+관계+청크) 기반 답변             │
└──────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────┐
│  [4단계] Evaluator Node (gemini-3-flash-preview)     │
│  답변 품질 평가 → PASS / FAIL                        │
└──────────────────────────────────────────────────────┘
    │
    ├─ PASS → Actor → final_answer → 사용자에게 전달
    │
    └─ FAIL → [5단계] Reflection → Actor 재시도
```

---

## 각 단계 상세 설명

### 1단계: Router — 의도 분류

**파일:** `src/agent/router.py`
**모델:** gemini-2.5-flash
**역할:** 사용자 쿼리를 `tool_query` 또는 `general_chat`으로 분류

Router는 사용 가능한 **도구 목록 요약**을 프롬프트에 주입받고, "이 쿼리를 처리할 도구가 있는가?"를 판단합니다.

**사용 가능한 도구 (8개):**

| 도구명 | 설명 |
|--------|------|
| `query_knowledge_graph` | 지식 그래프 검색 (LightRAG hybrid 쿼리) |
| `web_search` | 웹 검색 (DuckDuckGo HTML + Naver 폴백) |
| `list_documents` | 인덱싱된 문서 목록 조회 |
| `get_document_info` | 문서 메타정보 조회 |
| `get_document_summary` | 문서 구조화 요약 조회 |
| `get_document_content` | 문서 원문 조회 |
| `list_document_summaries` | 전체 문서 요약 목록 |
| `get_system_status` | 시스템 상태 조회 |

문서/데이터 질문 → `tool_query` → Actor 노드로 이동
일상 대화/인사 → `general_chat` → Direct Answer 노드로 이동

---

### 2단계: Actor — 도구 선택 및 실행 계획

**파일:** `src/agent/nodes.py` (actor_node)
**모델:** gemini-3-flash-preview
**역할:** ReAct 패턴으로 어떤 도구를 어떤 파라미터로 호출할지 결정

Actor는 다음 JSON 형식 중 하나를 출력합니다:

```json
// 도구 호출
{
  "thought": "플랜티넷 2026년 개발 계획에 대한 정보를 찾아야 한다",
  "action": "query_knowledge_graph",
  "action_input": {"query": "플랜티넷 2026년 개발 계획"}
}

// 최종 답변 (충분한 정보 확보 시)
{
  "thought": "수집된 정보로 답변할 수 있다",
  "final_answer": "플랜티넷 2026년 개발 계획은..."
}
```

#### Actor의 도구 선택 가이드:
- 문서/데이터 질문 → `query_knowledge_graph`
- 최신 뉴스/외부 정보 → `web_search`
- 문서 목록 확인 → `list_documents`
- 특정 문서 원문 → `get_document_content`
- KG 결과 불충분 + 외부 정보 필요 → `web_search`로 보완

---

### 3단계: LightRAG 쿼리 실행 (핵심)

**파일:** `src/rag/lightrag_manager.py`
**호출:** `await rag.aquery(query, param=QueryParam(mode="hybrid"))`

이 단계가 KG 검색의 핵심이며, 내부적으로 **4개의 서브 단계**를 거칩니다.

---

#### 3-1단계: 키워드 추출 (LLM 호출 #1)

**함수:** `extract_keywords_only()`
**모델:** gemini-2.5-flash (LightRAG 내부 전용)

LLM에게 사용자 쿼리를 보내 **두 종류의 키워드**를 JSON으로 추출합니다:

```json
{
  "high_level_keywords": ["개발 계획", "기술 연구소"],
  "low_level_keywords": ["플랜티넷", "2026년"]
}
```

| 키워드 유형 | 역할 | 검색 대상 | 예시 |
|------------|------|----------|------|
| **high_level** | 상위 개념/테마 | 관계(Edge) 벡터DB | "개발 계획", "기술 연구소" |
| **low_level** | 구체적 엔티티/명사 | 엔티티(Node) 벡터DB | "플랜티넷", "2026년" |

**프롬프트 요약:**
- LightRAG 내장 `keywords_extraction` 템플릿 사용
- high_level: 쿼리의 핵심 의도, 주제 영역, 질문 유형
- low_level: 고유명사, 기술 용어, 제품명, 구체적 항목
- 캐시 지원: 동일 쿼리는 LLM 재호출 없이 캐시 반환

---

#### 3-2단계: Hybrid KG 검색

**함수:** `_perform_kg_search()`

`hybrid` 모드에서는 **Local 검색 + Global 검색**을 동시에 수행한 후 병합합니다.

##### (A) Local 검색: `_get_node_data(ll_keywords)`

low_level 키워드를 사용하여 **엔티티(노드) 중심**으로 검색합니다.

```
처리 흐름:
1. entities_vdb.query("플랜티넷, 2026년", top_k=60)
   → 938개 엔티티의 임베딩과 코사인 유사도 비교
   → 유사도 높은 엔티티 반환: ["PLANTYNET", "2026년 개발계획", "기술연구소", ...]

2. knowledge_graph_inst.get_nodes_batch(node_ids)
   → GraphML에서 해당 노드의 상세 정보 조회
   → 각 노드: entity_name, description, entity_type, source_id 등

3. knowledge_graph_inst.node_degrees_batch(node_ids)
   → 각 노드의 연결 차수(degree) 조회 → 중요도 판단에 사용

4. _find_most_related_edges_from_entities(node_datas)
   → 찾은 엔티티들과 연결된 관계(엣지)도 함께 수집
   → 그래프 탐색으로 1-hop 이웃 관계까지 확장
```

**결과:** 유사 엔티티 목록 + 연결된 관계 목록

##### (B) Global 검색: `_get_edge_data(hl_keywords)`

high_level 키워드를 사용하여 **관계(엣지) 중심**으로 검색합니다.

```
처리 흐름:
1. relationships_vdb.query("개발 계획, 기술 연구소", top_k=60)
   → 1,281개 관계의 임베딩과 코사인 유사도 비교
   → 관련 관계 반환: ["PLANTYNET→기술연구소: 소속", "개발계획→AI과제: 포함", ...]

2. knowledge_graph_inst.get_edges_batch(edge_pairs)
   → GraphML에서 관계의 상세 정보 조회
   → 각 관계: src_id, tgt_id, description, weight 등

3. _find_most_related_entities_from_relationships(edge_datas)
   → 찾은 관계의 양쪽 엔티티도 수집
   → 관계에서 출발하여 연결된 엔티티로 확장
```

**결과:** 유사 관계 목록 + 연결된 엔티티 목록

##### (C) Round-Robin 병합

Local과 Global 결과를 **교차 병합**하여 균형잡힌 최종 결과를 만듭니다:

```
final_entities = [local[0], global[0], local[1], global[1], ...]
final_relations = [local[0], global[0], local[1], global[1], ...]

→ 중복 제거 (entity_name 또는 src_id+tgt_id 기준)
```

**왜 Hybrid인가?**
- Local만 하면: 특정 엔티티에 집중하지만 큰 그림을 놓침
- Global만 하면: 상위 개념은 잡지만 구체적 사실을 놓침
- Hybrid: 둘 다 수행 후 교차 병합하여 포괄성과 구체성 모두 확보

---

#### 3-2-1단계: 그래프 확산(Expansion) 메커니즘 상세

벡터 검색으로 초기 노드/엣지를 찾은 뒤, **그래프 구조를 따라 1-hop 이웃으로 확산**하는 과정입니다.
이 확산이 전통적인 벡터 RAG와 Graph RAG의 핵심적인 차이입니다.

##### (A) Local 확산: `_find_most_related_edges_from_entities()`

벡터 검색으로 찾은 **엔티티(노드)에서 출발하여 연결된 관계(엣지)로 확산**합니다.

```
[벡터 검색 결과 노드들]
       │
       ▼
  ┌─────────────────────────────────────┐
  │  graph.edges(node_id)               │
  │  → 해당 노드에 연결된 모든 엣지 조회  │
  │  (NetworkX 1-hop 탐색)              │
  └─────────────────────────────────────┘
       │
       ▼
  ┌─────────────────────────────────────┐
  │  중복 제거 (sorted tuple trick)      │
  │  → (A→B)와 (B→A)를 동일하게 처리    │
  └─────────────────────────────────────┘
       │
       ▼
  ┌─────────────────────────────────────┐
  │  edge_degree + weight 기준 정렬      │
  │  → 가장 중요한 관계부터 반환         │
  └─────────────────────────────────────┘
```

**실제 코드 동작:**

```python
async def _find_most_related_edges_from_entities(
    node_datas: list[dict],
    knowledge_graph_inst: BaseGraphStorage
):
    # 1단계: 각 노드에 연결된 모든 엣지 수집
    all_edges = await knowledge_graph_inst.get_nodes_edges_batch(
        [dp["entity_name"] for dp in node_datas]
    )

    # 2단계: 중복 제거 — sorted tuple 기법
    all_edges_pack = set()
    for this_edges in all_edges:
        all_edges_pack.update([tuple(sorted(e)) for e in this_edges])
    # (A→B)와 (B→A)가 있어도 sorted하면 ("A","B")로 통일됨

    # 3단계: 엣지 상세 정보 + degree 동시 조회
    all_edges_pack = list(all_edges_pack)
    all_edge_datas, all_edge_degrees = await asyncio.gather(
        knowledge_graph_inst.get_edges_batch(all_edges_pack),
        knowledge_graph_inst.edge_degrees_batch(all_edges_pack),
    )

    # 4단계: rank(=edge_degree) + weight 기준 내림차순 정렬
    for i, edge_data in enumerate(all_edge_datas):
        if edge_data is not None:
            edge_data["rank"] = all_edge_degrees[i]  # edge_degree 값
    
    # rank(높을수록 중요) → weight(높을수록 중요) 순으로 정렬
    sorted_edges = sorted(
        [e for e in all_edge_datas if e is not None],
        key=lambda x: (x.get("rank", 0), x.get("weight", 0)),
        reverse=True
    )
    return sorted_edges
```

**NetworkX 내부 동작:**

```python
# get_node_edges — 그래프에서 1-hop 이웃 엣지 조회
async def get_node_edges(self, source_node_id: str):
    if self._graph.has_node(source_node_id):
        return list(self._graph.edges(source_node_id))
    return []
# graph.edges("PLANTYNET") → [("PLANTYNET","기술연구소"), ("PLANTYNET","CTO"), ...]

# edge_degree — 엣지의 중요도 계산
async def edge_degree(self, src_id: str, tgt_id: str) -> int:
    return self._graph.degree(src_id) + self._graph.degree(tgt_id)
# degree("PLANTYNET")=15, degree("기술연구소")=8 → edge_degree=23
# 양쪽 노드의 연결 수 합 = 허브 노드를 지나는 관계일수록 높은 점수
```

**확산 예시:**

```
벡터 검색으로 "PLANTYNET" 노드를 찾음 (degree=15)
    │
    ├──→ PLANTYNET ─── 소속 ──→ 기술연구소     (edge_degree=23)
    ├──→ PLANTYNET ─── 대표 ──→ CTO            (edge_degree=20)
    ├──→ PLANTYNET ─── 개발 ──→ 유해콘텐츠차단  (edge_degree=18)
    ├──→ PLANTYNET ─── 위치 ──→ 대한민국        (edge_degree=17)
    ├──→ PLANTYNET ─── 보유 ──→ AI기술          (edge_degree=15)
    ...
    └──→ (총 15개 엣지, edge_degree 내림차순 정렬)

→ 단 1번의 벡터 검색으로 "PLANTYNET"만 찾았지만,
  그래프 확산으로 기술연구소, CTO, 유해콘텐츠차단 등
  15개 관련 정보를 추가로 획득!
```

##### (B) Global 확산: `_find_most_related_entities_from_relationships()`

벡터 검색으로 찾은 **관계(엣지)에서 출발하여 연결된 엔티티(노드)로 확산**합니다.
Local 확산의 역방향입니다.

```
[벡터 검색 결과 엣지들]
       │
       ▼
  ┌─────────────────────────────────────┐
  │  각 엣지의 src_id, tgt_id 수집       │
  │  → 관계의 양쪽 끝 노드를 모두 수집   │
  └─────────────────────────────────────┘
       │
       ▼
  ┌─────────────────────────────────────┐
  │  중복 제거 후 batch 조회             │
  │  → 노드 상세 정보 일괄 로드          │
  └─────────────────────────────────────┘
```

**실제 코드 동작:**

```python
async def _find_most_related_entities_from_relationships(
    edge_datas: list[dict],
    knowledge_graph_inst: BaseGraphStorage
):
    # 1단계: 모든 엣지에서 양쪽 노드 ID 수집
    entity_names = set()
    for edge in edge_datas:
        if edge is not None:
            entity_names.add(edge.get("src_id", ""))
            entity_names.add(edge.get("tgt_id", ""))
    entity_names.discard("")  # 빈 문자열 제거

    # 2단계: 일괄 조회
    node_datas = await knowledge_graph_inst.get_nodes_batch(
        list(entity_names)
    )

    # 3단계: 유효한 노드만 반환
    return [n for n in node_datas if n is not None]
```

**확산 예시:**

```
벡터 검색으로 "개발 → AI과제: 포함" 관계를 찾음
    │
    ├── src_id: "개발계획" → 노드 상세 정보 조회
    └── tgt_id: "AI과제"   → 노드 상세 정보 조회

→ 관계 1개에서 양쪽 엔티티 2개를 추가로 획득
→ N개 관계에서 최대 2N개 엔티티를 확보 (중복 제거 후 실제는 더 적음)
```

##### (C) 확산 요약: Local vs Global

| | Local 확산 | Global 확산 |
|---|---|---|
| **출발점** | 노드 (엔티티) | 엣지 (관계) |
| **확산 방향** | 노드 → 연결된 엣지들 | 엣지 → 양쪽 노드들 |
| **확산 함수** | `_find_most_related_edges_from_entities()` | `_find_most_related_entities_from_relationships()` |
| **정렬 기준** | edge_degree + weight 내림차순 | 없음 (batch 조회만) |
| **1-hop 범위** | `graph.edges(node_id)` | `edge.src_id`, `edge.tgt_id` |
| **확산 깊이** | **1-hop만** (멀티홉 없음) | **직접 연결만** |

##### (D) edge_degree가 중요한 이유

```
edge_degree = graph.degree(src_id) + graph.degree(tgt_id)
```

- `degree` = 해당 노드에 연결된 엣지의 총 수
- **양쪽 노드가 모두 허브(많은 연결)인 관계**일수록 edge_degree가 높음
- 높은 edge_degree = **정보가 풍부한 핵심 관계**라는 의미

```
예: PLANTYNET(degree=15) ── 소속 ── 기술연구소(degree=8)
    → edge_degree = 15 + 8 = 23 (높음 → 핵심 관계!)

예: 홍길동(degree=2) ── 참석 ── 회의A(degree=1)
    → edge_degree = 2 + 1 = 3 (낮음 → 덜 중요한 관계)
```

이 정렬 덕분에 토큰 절단 시 **중요한 관계가 먼저 유지**되고, 주변부 관계가 먼저 제거됩니다.

##### (E) 왜 1-hop만 확산하는가?

LightRAG는 의도적으로 **1-hop 확산만** 수행합니다:

1. **Local + Global 조합으로 충분**: Local이 노드→엣지, Global이 엣지→노드로 확산하므로, 양쪽 결과를 합치면 실질적으로 **2-hop 효과**
2. **토큰 효율성**: 멀티홉 확산 시 정보량이 기하급수적으로 증가 → LLM 컨텍스트 윈도우 초과 위험
3. **노이즈 방지**: 홉이 깊어질수록 원래 쿼리와 관련 없는 정보가 섞일 확률 증가
4. **속도**: 1-hop은 NetworkX `graph.edges()` 한 번이면 완료 → O(degree) 시간복잡도

---

#### 3-3단계: 토큰 절단 + 청크 병합

##### 토큰 절단: `_apply_token_truncation()`

찾은 엔티티/관계가 너무 많으면 LLM 컨텍스트 윈도우에 맞게 잘라냅니다:

```
- max_entity_tokens: 엔티티 설명의 최대 토큰 수
- max_relation_tokens: 관계 설명의 최대 토큰 수
- max_total_tokens: 전체 컨텍스트 최대 토큰 수
```

우선순위: 코사인 유사도 높은 것 → 그래프 degree 높은 것 → 최신 것

##### 청크 병합: `_merge_all_chunks()`

필터링된 엔티티/관계와 연관된 **원본 텍스트 청크**를 수집합니다:

```
- kv_store_text_chunks.json (48개 청크)에서 관련 청크 로드
- 각 청크는 원본 문서의 구조화 요약 텍스트 조각
- 엔티티/관계의 source_id를 통해 어떤 청크에서 추출되었는지 추적
- 청크를 통해 엔티티 간 관계의 원래 문맥을 복원
```

---

#### 3-4단계: 컨텍스트 구성 + 답변 생성 (LLM 호출 #2)

##### 컨텍스트 구성: `_build_context_str()`

수집된 정보를 하나의 구조화된 컨텍스트 문자열로 조합합니다:

```
-----Context-----

## Knowledge Graph Data

### Entities
- PLANTYNET (Organization): IT 기업, 대한민국 소재, 유해 콘텐츠 차단 기술 개발...
- 2026년 개발계획 (Project): 기술연구소 연간 개발 계획, AI 모델 고도화...
- 기술연구소 (Organization): 플랜티넷 산하 연구 조직...

### Relationships
- PLANTYNET → 기술연구소: 소속 (weight: 3.0)
- 개발계획 → AI 모델 성능 관리: 포함 (weight: 2.5)
- 기술연구소 → SNS 유해 콘텐츠 필터링: 담당 (weight: 2.0)

## Document Chunks
[Chunk 1] [Document: 2026년_플랜티넷_기술연구소_개발계획.pdf]
문서 개요: 2026년 기술연구소 개발 계획...
주요 과제: XR 유해 콘텐츠 차단, AI 모델 성능 관리 시스템...

-----End Context-----
```

##### 답변 생성

이 컨텍스트를 `rag_response` 프롬프트와 함께 LLM에 전송합니다:

```
시스템 프롬프트: "제공된 Context 내의 정보만 사용하여 답변하세요"
사용자 쿼리: "플랜티넷 2026년 개발 계획 알려줘"
컨텍스트: (위에서 조합한 데이터)
```

**핵심 제약:**
- LLM은 **컨텍스트 안의 정보만** 사용하여 답변
- 자체 지식으로 사실을 보충하지 않음
- 참고한 청크의 reference_id를 답변에 인용

---

### 4단계: Evaluator — 답변 품질 평가

**파일:** `src/agent/nodes.py` (evaluator_node)
**모델:** gemini-3-flash-preview

2단계 평가를 수행합니다:

#### 기술적 평가 (규칙 기반, LLM 불필요)
```python
# 에러 키워드 탐지
error_indicators = ["error", "exception", "failed", "not found", "실패", "오류"]
# 빈 결과 탐지
if not observation or observation.strip() == "": → FAIL
```

#### 논리적 평가 (LLM 기반)
```
- 사용자 질문에 실제로 답변하고 있는가?
- 근거 없는 추측이 포함되어 있는가?
- 답변이 충분히 구체적인가?
```

**결과:**
- `PASS` → Actor에게 돌아가서 `final_answer` 생성
- `FAIL` → Reflection 단계로 이동

---

### 5단계: Reflection — 실패 분석 및 재시도 (조건부)

**파일:** `src/agent/nodes.py` (reflection_node)
**모델:** gemini-3-flash-preview

Evaluator가 FAIL을 반환하면 실행됩니다:

```json
{
  "lesson": "검색어가 너무 광범위했다. 구체적인 프로젝트명으로 재검색 필요",
  "analysis": "query_knowledge_graph의 결과가 관련 없는 엔티티를 포함",
  "suggestion": "query_knowledge_graph를 'XR 유해 콘텐츠 차단 개발 일정'으로 재시도"
}
```

- 학습된 교훈(lesson)은 다음 시도의 Actor에게 전달
- 최대 반복 횟수: `max_reflection=3`
- 초과 시 → `exhaustion_answer` 노드에서 부분 답변 생성

---

## 쿼리 모드 비교

LightRAG는 4가지 쿼리 모드를 지원합니다. 우리 시스템은 **hybrid**를 기본으로 사용합니다:

| 모드 | 검색 방식 | 장점 | 단점 |
|------|----------|------|------|
| **local** | 엔티티 벡터DB만 검색 → 연결 관계 확장 | 특정 엔티티 정확 | 상위 개념 놓침 |
| **global** | 관계 벡터DB만 검색 → 연결 엔티티 확장 | 큰 그림 파악 | 구체적 사실 놓침 |
| **hybrid** ✅ | Local + Global 병행 → Round-Robin 병합 | 포괄적 + 구체적 | 토큰 소모 많음 |
| **naive** | 텍스트 청크 벡터DB만 검색 (전통 RAG) | 단순, 빠름 | 그래프 구조 활용 못함 |
| **mix** | Hybrid + 청크 벡터 검색 추가 | 가장 포괄적 | 가장 느림 |

---

## 인제스트 파이프라인 (문서 → KG 저장)

쿼리를 이해하려면 데이터가 어떻게 저장되는지도 알아야 합니다:

```
원본 문서 (PDF, XLSX, DOCX, TXT, MD, HTML)
    │
    ▼
[1] Document Converter (document_converter.py)
    → 텍스트 추출 (pdfplumber, openpyxl, python-docx 등)
    → [Document: 파일명] 헤더 자동 추가
    │
    ▼
[2] Document Summarizer (document_summarizer.py)
    → LLM 구조화 요약 (gemini-2.5-flash)
    → 노이즈 제거 (OCR 오류, URL, 보일러플레이트)
    → 핵심 엔티티/관계를 명시적으로 포함
    → 요약 캐시 저장 (document_summaries.json)
    │
    ▼
[3] LightRAG ainsert (lightrag_manager.py)
    → 요약 텍스트를 청크로 분할 (1,200 토큰 단위, 100 토큰 오버랩)
    → 각 청크에서 엔티티 추출 (LLM, 2회 반복 gleaning)
    → 엔티티 간 관계 추출 (LLM)
    → 20종 커스텀 엔티티 타입 적용
    → 벡터DB 저장 + GraphML 그래프 갱신
```

### 커스텀 엔티티 타입 (20종)

```
Person, Organization, Location, Event, Concept,
Technology, Software, System,
Project, Team, Skill,
Metric, Dataset,
Product, Transaction,
Document,
Method, Data, Artifact
```

---

## LLM 호출 횟수 정리

하나의 KG 쿼리에서 발생하는 LLM 호출:

| 순서 | 단계 | 모델 | 용도 |
|------|------|------|------|
| 1 | Router | gemini-2.5-flash | 의도 분류 (tool_query / general_chat) |
| 2 | Actor | gemini-3-flash-preview | 도구 선택 + 파라미터 결정 |
| 3 | LightRAG 키워드 추출 | gemini-2.5-flash | HL/LL 키워드 분류 |
| 4 | LightRAG 답변 생성 | gemini-2.5-flash | 컨텍스트 기반 답변 |
| 5 | Evaluator | gemini-3-flash-preview | 답변 품질 평가 |
| 6 | Actor (2차) | gemini-3-flash-preview | final_answer 정리 |

**최소 6회**, FAIL 시 Reflection 추가로 **7~9회**까지 증가.

---

## 성능 최적화 포인트

### 현재 적용된 최적화

1. **구조화 요약 인제스트**: 원본 → 요약 → KG로 노이즈 감소 (KG 노드 379→305개 감소)
2. **LLM 응답 캐시**: `kv_store_llm_response_cache.json`에 동일 쿼리 결과 캐시
3. **키워드 캐시**: 동일 쿼리의 HL/LL 키워드 재추출 방지
4. **비동기 스레드 풀**: LightRAG 내부 LLM 호출은 전용 ThreadPoolExecutor에서 실행
5. **노드별 독립 LLM**: 각 노드가 독립 LLM 인스턴스 사용 → context 오염 방지
6. **임베딩 로컬 실행**: all-MiniLM-L6-v2를 로컬에서 실행 → API 호출 없이 벡터 생성

### 참고: 임베딩 모델

```python
hf_embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)
# 384차원, 영어 최적화이지만 다국어(한국어 포함) 기본 지원
# 로컬 실행 → API 비용 없음, 빠른 응답
```

---

## 요약

Knowledge Graph 쿼리는 단순한 벡터 검색이 아니라, **LLM 키워드 추출 → 벡터 유사도 검색 → 그래프 탐색 확장 → 원본 청크 매칭 → LLM 컨텍스트 기반 답변 생성**이라는 다단계 파이프라인입니다.

전통적인 RAG(벡터 검색 → LLM 답변)와의 핵심 차이점:

| | 전통 RAG | Graph RAG (LightRAG) |
|---|---|---|
| 검색 단위 | 텍스트 청크 | 엔티티 + 관계 + 청크 |
| 검색 방식 | 벡터 유사도만 | 벡터 유사도 + 그래프 탐색 |
| 정보 연결 | 없음 (독립 청크) | 엔티티 간 관계로 연결 |
| 다단계 추론 | 어려움 | 관계 체인 따라 가능 |
| 노이즈 처리 | 없음 | 구조화 요약으로 사전 제거 |
