# 프로젝트 개요

LightRAG(Graph RAG) + LangGraph 기반 ReAct + Reflexion 에이전트. 문서를 Knowledge Graph로 인제스트하여 그래프 탐색 + LLM 추론으로 답변한다. 상세는 @README.md 참조.

- 언어: Python 3.10+ (backend), Vanilla JS/CSS (frontend)
- 핵심 의존성: `langgraph`, `langchain-*`, `lightrag-hku`, `fastapi`, `sentence-transformers`
- LLM: Google Gemini (노드별 독립 구성 — `backend/config/settings.yaml`)

---

# 빌드 및 실행 명령어

모든 backend 명령은 `backend/` 에서 venv 활성화 후 실행.

```bash
# 설치
cd backend && python -m venv .venv
source .venv/Scripts/activate   # Git Bash (Windows)
pip install -r requirements.txt

# 백엔드 서버 (포트 8000)
cd backend && python main.py

# 프론트엔드 정적 서버 (포트 3000)
cd frontend && python serve.py 3000

# 단일 스트리밍 테스트
cd backend && python run_stream.py
```

> 환경변수는 `backend/.env`에 저장. `main.py` 가 import 시점에 `backend/.env` 를 우선 로드하고, 없으면 프로젝트 루트의 `.env` 를 fallback으로 로드한다.
> ```
> GOOGLE_API_KEY=...           # Gemini (기본 프로바이더)
> ANTHROPIC_API_KEY=...        # Claude (settings.yaml에서 노드별 전환 시)
> OPENAI_API_KEY=...           # GPT (settings.yaml에서 노드별 전환 시)
> ```
> 사용하지 않는 프로바이더의 키는 생략 가능. `provider.py` 가 선택된 노드에서만 키 존재를 검증한다.
> 백엔드와 프론트엔드는 **별도 터미널 2개**에서 동시 실행해야 한다.

---

# 코딩 컨벤션

- **인덴트**: 4 spaces (Python 표준)
- **네이밍**: `snake_case` (함수/변수), `PascalCase` (클래스), 모듈 파일명도 `snake_case.py`
- **Docstring**: 한국어 허용. 모듈/함수 상단에 `"""..."""` 삼중따옴표. 역할과 비자명한 동작만 기술.
- **Import 순서**: 표준 라이브러리 → 외부 패키지 → `src.*` 내부 모듈. `from src.agent.state import AgentState` 형태.
- **타입힌트**: 공개 함수 시그니처에 `Dict[str, Any]`, `List`, `BaseChatModel` 등 명시.
- **로그**: `print(...)` 를 유지 (서버 로그는 stdout 캡처). 새 구조 도입 금지.
- **주석**: 한국어 허용. `# ============ Section ============` 형태로 노드/블록 구분하는 기존 스타일 유지.
- **프롬프트**: `backend/prompts/*.yaml`의 XML 태그 구조 (`<role>`, `<task>`, `<output_format>` 등) 일관성 유지. 새 태그 추가 시 동일 계열 YAML 전체를 점검.

---

# 프로젝트 구조 요약

```
backend/
├── main.py                    # FastAPI 엔트리포인트
├── config/settings.yaml       # 노드별 LLM + 에이전트 동작 설정
├── prompts/*.yaml             # 노드별 프롬프트 (XML 태그 구조)
└── src/
    ├── agent/                 # LangGraph StateGraph (graph/nodes/router/state)
    ├── config/                # settings.yaml + prompts/*.yaml 로더
    ├── llm/provider.py        # 노드별 LLM 팩토리
    ├── memory/lessons_store.py  # Reflection 교훈 영속 저장
    ├── rag/                   # LightRAG 래퍼 (manager/converter/summarizer)
    └── tools/                 # 에이전트 도구 (KG 검색, 문서 조회, 웹 검색)

frontend/  # Vanilla JS (SSE 스트리밍 + 아코디언 UI)
data/
├── documents/                 # 업로드 문서 (원본 보존)
└── rag_storage/               # ⚠️ LightRAG 상태 — 수동 편집 금지
```

---

# 작업 시 주의사항

## 보호 파일 (⚠️ 절대 직접 수정/삭제 금지)

다음 파일은 `.claude/hooks/protect-files.sh` 훅으로 차단된다. 재생성에 긴 LLM 호출 + 비용이 필요하므로 실수 방지가 중요.

- `backend/.env` — API 키
- `data/rag_storage/**` — LightRAG 내부 상태 (graphml, vdb_*.json, kv_store_*.json)
- `data/documents/**` — 업로드된 원본 문서
- `data/document_summaries.json` — 요약 캐시 (재생성 비쌈)

KG 데이터를 완전 리셋하려면 터미널에서 직접 `rm -rf data/rag_storage/*` 를 사용자가 실행한다.

## 노드별 LLM 독립성

각 노드(`router`, `actor`, `evaluator`, `reflection`, `direct_answer`, `rag`, `summarizer`)는 **독립된 LLM 세션**을 쓴다. `settings.yaml` 편집 시 특정 노드만 바꾸고 기본값 `llm.*` 을 흔들지 말 것. `rag` 는 LightRAG 엔진의 KG 구축/쿼리 LLM, `summarizer` 는 문서 구조화 요약기에 사용된다.

## 프롬프트 수정

`backend/prompts/*.yaml` 은 XML 태그 구조를 사용한다. 태그명을 바꾸면 `nodes.py` 의 파서와 깨지므로, 태그 rename 시 `backend/src/agent/nodes.py` + `backend/src/config/prompt_loader.py` 를 함께 확인.

## 테스트

새 테스트는 `backend/tests/` 디렉터리에 역할 기반 이름(`test_kg_ingest.py` 등)으로 추가한다. `backend/` 루트에 임시 `test*.py` 스크립트를 두지 않는다.

## Windows 환경 메모

- `main.py` 가 모듈 로드 시 `sys.stdout/stderr` 를 UTF-8로 reconfigure 한다 — cp949 콘솔에서 이모지/한자 출력 시 `UnicodeEncodeError` 가 나지 않도록 하는 안전장치. 도구 출력(`utility_tools.py` 등)에 이모지가 들어 있으므로 제거하지 말 것.
- `data/*` 파일 I/O 는 항상 `encoding="utf-8"` 명시 (`lessons_store.py` 패턴 참조). 미명시 시 Windows 기본 cp949로 fallback되어 한글 깨짐.
- HuggingFace 모델 다운로드 시 기업/사내 인증서 환경에서 SSL 오류가 나면 `pip install pip-system-certs` 권장.

## LLM 프로바이더 교체

모든 노드(`router`/`actor`/`evaluator`/`reflection`/`direct_answer`/`rag`/`summarizer`)는 `src.llm.provider.get_node_llm()` 으로 LLM을 받는다. 프로바이더를 바꾸려면:

1. `backend/.env` 에 해당 API 키 추가 (`OPENAI_API_KEY` / `ANTHROPIC_API_KEY`).
2. `backend/config/settings.yaml` 의 해당 노드에서 `provider` + `model_name` 변경. 예:
   ```yaml
   actor:
     provider: "anthropic"
     model_name: "claude-sonnet-4-5"
     temperature: 0.7
     max_tokens: 8192
   ```
3. `provider.py` 는 lazy import 라 미설치 패키지(`langchain-openai` / `langchain-anthropic`)는 해당 프로바이더 선택 시점에만 `ImportError` 를 낸다 — Gemini 단독 사용 시 두 패키지는 제거 가능.

---

# 오류 대응 프로세스 (Reflection Loop)

오류(런타임/빌드/로직)가 발생하면 다음 순서를 **반드시** 지킨다:

1. **근본 원인 분석** — 표면 증상이 아닌 원인 식별. 특히 LangGraph state 전파, LightRAG async 초기화, Gemini rate limit 같은 이 프로젝트 특유 함정 주의.
2. **수정 적용** — 근본 원인을 고친다. 증상 숨기기 금지.
3. **회고** — 이 오류가 왜 발생했는가 / 어떻게 재발을 막을까 / 다른 세션에서 재사용 가능한 교훈인가?
4. **Memory 업데이트** — 회고 결과가 비자명하고 재사용 가능하면 `~/.claude/projects/C--Users-cyon1-OneDrive-Desktop-agentic-ai/memory/` 에 `feedback` 타입 메모리로 저장. 사소한 오타/일시적 네트워크 오류는 저장하지 않는다.

> ⚠️ 수정만 하고 회고 없이 넘어가지 말 것.

---

# Plan 작성 규칙

Plan을 세울 때 반드시 다음 구조를 따른다:

**(a) Checklist 분해**
- 모든 구현을 checkbox로 분해. 각 항목은 단일 책임 + 하나의 완료 조건.
- 예: `[ ] router.yaml에 새 intent 카테고리 추가`, `[ ] nodes.py 라우터 함수에 분기 추가`, `[ ] 시나리오 S-001 실행`

**(b) 재검토 패스**
- 구현 종료 후 체크리스트를 처음부터 다시 순회하며 엣지 케이스/의존성 확인.
- 발견된 누락은 새 항목으로 추가 후 수정.

**(c) Scenario 기반 검증**
- 기능 테스트 필요 시, 시나리오를 **먼저** 문서화 (`Scenario ID / 설명 / 사전 조건 / 실행 단계 / 기대 결과`).
- 시나리오는 **별도의 새 Agent 세션**에서 실행하여 확증 편향 방지.

**(d) Pass까지 반복**
- Fail → 원인 분석 → 수정 → 재실행. 모든 시나리오 Pass까지 반복.

**(e) 검증 Agent 모델 선택**
- `opus`: 복잡한 에이전트 루프/KG 쿼리 결과 정합성 같은 심층 추론.
- `sonnet`: 단위 동작 확인/명확한 Pass/Fail 시나리오.

---

# 관련 문서

- 에이전트 흐름: `images/agent_flowchart.png`
- KG 쿼리 파이프라인: `documents/knowledge_graph_query_mechanism.md`
- 비개발자용 설명: `documents/kg_query_mechanism_explained.md`
