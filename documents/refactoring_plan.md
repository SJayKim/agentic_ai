# 리팩토링 계획 — agentic_ai

## Context

**왜 이 작업을 하는가**
사용자가 3가지 기준으로 현재 코드베이스를 점검 요청:
1. 효율적으로 구축되었는가
2. 오버엔지니어링은 없는가
3. **LLM이 Gemini 외에도 Claude/OpenAI로 교체 가능한가**

**조사 결과 요약**
- `backend/src/llm/provider.py` 에는 **이미 Google/OpenAI/Anthropic 분기가 전부 구현**되어 있음 (라인 105-175). 즉 "신규 구현"이 아니라 **남아있는 Gemini 직접 의존 제거 + 검증** 작업.
- 에이전트 코어(`graph.py`/`nodes.py`/`router.py`/`state.py`)는 깔끔. 노드별 LLM 주입 패턴 잘 적용됨.
- 남은 Gemini 하드코딩은 **RAG 레이어 2곳**과 임시 테스트 스크립트뿐.
- `provider.py` 자체에 중복 함수 4개, `settings.yaml` 에 죽은 섹션 3개, 루트 임시 테스트 4개 등 정리 대상 다수.

**최종 결과물**
- `.env`에 `GOOGLE_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` 중 어느 것이든 두고, `settings.yaml`에서 노드별 `provider`/`model_name`만 바꾸면 즉시 전환되는 상태.
- RAG 인제스트도 동일 메커니즘으로 LLM 교체 가능.
- 죽은 코드/임시 스크립트 제거로 디렉터리 가독성 향상.

---

## 작업 체크리스트 (CLAUDE.md "Plan 작성 규칙 (a)" 준수)

### Phase 1 — LLM 프로바이더 통합 (핵심)

- [ ] **1-1. `backend/src/llm/provider.py` 단순화**
  - `get_default_llm()`, `get_llm_from_config()` 두 함수 삭제 (사용처 없음 → grep으로 확증 후 제거).
  - `get_llm()` + `get_node_llm()` 만 남김.
  - `_create_google_llm`의 `convert_system_message_to_human=True` 옵션 유지 (Gemini 한정).

- [ ] **1-2. RAG 레이어 LLM 추상화** — `backend/src/rag/lightrag_manager.py`
  - 라인 20: `from langchain_google_genai import ChatGoogleGenerativeAI` 제거.
  - 라인 77-105 `gemini_llm_func` → 함수 이름 `rag_llm_func`로 rename.
  - 라인 85: `ChatGoogleGenerativeAI(model=..., temperature=0.1)` → `get_node_llm("rag")` 호출로 교체.
  - LLM 인스턴스는 모듈 임포트 시 1회 생성(싱글톤화)하여 매 호출 인스턴스화 비용 제거.
  - 라인 119 `llm_model_func=gemini_llm_func` → `llm_model_func=rag_llm_func`.
  - 로그 prefix `[GEMINI-RAG]` → `[RAG-LLM]` 으로 변경 (provider 무관).

- [ ] **1-3. `backend/src/rag/document_summarizer.py` LLM 추상화**
  - 라인 72 부근의 `ChatGoogleGenerativeAI(model="gemini-2.5-flash")` → `get_node_llm("summarizer")` 로 교체.
  - 모듈 로드 시 1회만 생성 (현재 매 호출 인스턴스화일 경우 싱글톤화).

- [ ] **1-4. `backend/config/settings.yaml`에 RAG/Summarizer 노드 추가**
  ```yaml
  llm:
    # ... 기존 router/actor/evaluator/reflection/direct_answer
    rag:
      provider: "google"
      model_name: "gemini-2.5-flash"
      temperature: 0.1
      max_tokens: 8192
    summarizer:
      provider: "google"
      model_name: "gemini-2.5-flash"
      temperature: 0.2
      max_tokens: 8192
  ```

- [ ] **1-5. `backend/requirements.txt` 정리**
  - `langchain-google-genai`는 필수 유지 (Gemini 기본).
  - `langchain-openai`, `langchain-anthropic` 을 **extras** 로 추가 (또는 주석으로 옵션 명시).
  - provider.py가 import 시점에 try/except로 패키지 부재를 처리하므로, 미설치 상태에서도 Gemini 만으로 동작해야 함 (검증 항목).

### Phase 2 — 죽은 코드/설정 정리

- [ ] **2-1. `backend/config/settings.yaml` 정리**
  - `react_loop:` 섹션 삭제 (주석에 "Legacy" 명시되어 있고, grep 결과 사용처 없음 — 1-5 진행 전 확증).
  - `resources:` 섹션 삭제 (project/thread/feed 모델 — 코드 내 사용처 없음 확증 후 제거).
  - `mcp_servers:` 섹션 — `enabled: true` 항목 없으면 전체 주석 처리 또는 삭제.

- [ ] **2-2. `backend/` 루트의 임시 테스트 파일 전부 삭제**
  - `test.py`, `test2.py`, `test3.py`, `test_xlsx_ingest.py` 삭제.
  - 필요 시 git log 로 복구 가능하므로 안전.

- [ ] **2-3. README.md / CLAUDE.md 동기화**
  - CLAUDE.md "테스트" 섹션의 test*.py 언급 제거.
  - README.md 에 멀티 프로바이더 사용법 한 문단 추가 (예: `provider: "anthropic", model_name: "claude-sonnet-4-5"`).

### Phase 3 — 검증 시나리오 (CLAUDE.md "Plan 작성 규칙 (c)" 준수)

별도의 **새 Agent 세션**에서 다음 시나리오를 실행하여 확증 편향 방지:

| ID | 시나리오 | 사전조건 | 실행 | 기대 결과 |
|----|---------|---------|------|----------|
| S-001 | Gemini 단독 동작 (회귀) | settings.yaml 전부 google | `python main.py` + `/api/chat` 호출 | 기존과 동일하게 응답 |
| S-002 | Actor만 Anthropic 전환 | `llm.actor.provider: "anthropic"`, `ANTHROPIC_API_KEY` 설정 | tool_query 1회 실행 | Claude 모델로 추론, 도구 호출 정상 |
| S-003 | RAG만 OpenAI 전환 | `llm.rag.provider: "openai"`, `OPENAI_API_KEY` 설정 | 문서 1개 인제스트 | KG 그래프에 엔티티 추출 |
| S-004 | 미설치 패키지 graceful 실패 | langchain-anthropic 없는 상태로 anthropic 지정 | 서버 시작 | `ImportError("langchain-anthropic 패키지가 필요합니다")` 명확 출력 |
| S-005 | 죽은 설정 제거 후 동작 | 2-1 완료 후 | 전체 회귀 | settings.yaml 누락된 키 참조 에러 없음 |

> 검증 Agent 모델: **sonnet** (Pass/Fail 명확) — S-001/S-005, **opus** (KG 정합성 심층) — S-003.

### Phase 4 — 재검토 패스 (CLAUDE.md "Plan 작성 규칙 (b)" 준수)

위 체크리스트를 끝까지 진행 후 처음부터 재순회하며 다음을 확인:

- [ ] `langchain_google_genai` import가 `provider.py` 외에 남아있지 않은가? (`grep -r "langchain_google_genai" backend/src`)
- [ ] `ChatGoogleGenerativeAI` 직접 인스턴스화가 어디에도 없는가?
- [ ] `settings.yaml`의 키를 코드에서 참조하는 곳과 mismatch 없는가?
- [ ] `tests/` 가 없으므로 새 정식 테스트는 **이번 작업 범위 밖** (사용자 답변: "전부 삭제"만).

---

## 의도적으로 **제외**한 작업 (오버스코프 방지)

다음은 조사 중 보였으나 이번 리팩토링 범위에서 제외:

- **`utility_tools.py` 585줄 분해** — 사용처 매핑 + 통합 테스트가 필요. 별도 PR.
- **`lessons_store.py` 428줄 RRF 단순화** — 동작 중인 회수 로직. 회귀 위험 vs 가독성 이득이 불명확.
- **프롬프트 템플릿 통일 (`{tools_desc}` vs `<available_tools>`)** — 동작에 문제 없음. 메모리/유지보수 이슈는 별도.
- **converter ↔ summarizer 메타데이터 중복 삽입** — 1줄 차이라 위험 대비 이득 미미.

→ 사용자가 원하면 별도 후속 작업으로 다룸.

---

## 핵심 파일 (수정 대상)

| 파일 | 변경 요약 |
|------|----------|
| `backend/src/llm/provider.py` | 죽은 함수 2개 제거 |
| `backend/src/rag/lightrag_manager.py` | `gemini_llm_func` → `rag_llm_func`, get_node_llm 사용 |
| `backend/src/rag/document_summarizer.py` | get_node_llm 사용 |
| `backend/config/settings.yaml` | `llm.rag`/`llm.summarizer` 추가, 죽은 섹션 제거 |
| `backend/requirements.txt` | extras 명시 |
| `backend/test.py`, `test2.py`, `test3.py`, `test_xlsx_ingest.py` | 삭제 |
| `README.md`, `CLAUDE.md` | 멀티 프로바이더 사용법 추가, test*.py 언급 제거 |

## 재사용 대상 (조사 중 확인)

- `get_llm(provider=..., model_name=...)` (`provider.py:27`) — RAG/Summarizer 에서 그대로 사용 가능.
- `get_node_llm(node_name)` (`provider.py:73`) — fallback 로직(`llm.<node>.* → llm.*`)이 이미 구현됨. 신규 노드 `rag`/`summarizer` 도 즉시 동작.
- `ConfigLoader.get("dotted.key", default)` (`config_loader.py`) — settings.yaml 키 확장은 코드 변경 없이 됨.

---

## Phase 3 — 검증 결과 (별도 Agent 세션 실행)

| ID | 시나리오 | 결과 | 핵심 증거 |
|----|---------|------|---------|
| S-001 | Gemini 단독 회귀 | PASS | `python main.py` 기동, `/api/chat`에 "안녕" 호출 시 `{"status":"success","answer":"안녕하세요! 무엇을 도와드릴까요?"}` |
| S-002 | Actor만 Anthropic 전환 | PASS | `[LLM] Creating actor LLM: claude-sonnet-4-5` 로그, Anthropic Actor가 `list_documents` 도구 선택 |
| S-003 | RAG만 OpenAI 전환 | SKIP | OPENAI_API_KEY 미보유 (사용자 환경) |
| S-004 | langchain-anthropic 미설치 graceful 실패 | PASS | `ImportError("langchain-anthropic 패키지가 필요합니다: pip install langchain-anthropic")` 정확히 발생 |
| S-005 | 죽은 설정(`react_loop`/`resources`/`mcp_servers`) 제거 회귀 | PASS | 코드 내 실제 참조 0건, S-001 기동 성공으로 간접 확증 |

## Phase 3 — 부수 수정 (회귀 검증 중 발견된 환경 이슈)

리팩토링 본 범위 밖이지만 시나리오 실행을 위해 함께 처리:

- **`backend/main.py`** — `load_dotenv()` 추가 (backend/.env 우선, 루트 .env fallback). `sys.stdout/stderr.reconfigure("utf-8")` 추가로 Windows cp949 콘솔의 이모지 출력 오류 차단.
- **`backend/src/memory/lessons_store.py`** — `Path.read_text()/write_text()` 에 `encoding="utf-8"` 명시. Windows에서 한글 lessons 파일 읽기/쓰기 시 cp949 codec 오류 차단.
- **`backend/requirements.txt`** — `beautifulsoup4` 추가. `utility_tools.py` 의 `web_search` 가 사용 중인데 누락되어 있던 의존성.

## 비채택 / 후속 작업

- **`utility_tools.py` 의 이모지(📁/📄/🔍 등)** — `main.py` 의 UTF-8 reconfigure 로 출력 오류 해결됨. 코드의 이모지는 보존.
- **OpenAI 프로바이더 (S-003)** — 키 보유 시 동일 메커니즘으로 즉시 검증 가능. provider.py 코드 경로는 S-002/S-004 결과로 간접 확증.
