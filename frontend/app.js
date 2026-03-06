/**
 * GraphAgent – Frontend Core
 * 
 * SSE 프로토콜:
 *   thinking     → 사고 과정 단계별 이벤트
 *   answer_start → 최종 답변 시작
 *   answer_chunk → 답변 텍스트 청크 (스트리밍)
 *   done         → 완료 시그널
 *   error        → 에러
 */

const API_BASE = "http://localhost:8000/api";

document.addEventListener("DOMContentLoaded", () => {
    const chatForm = document.getElementById("chat-form");
    const chatInput = document.getElementById("chat-input");
    const chatMessages = document.getElementById("chat-messages");
    const docList = document.getElementById("doc-list");
    const ingestBtn = document.getElementById("ingest-btn");
    const refreshDocsBtn = document.getElementById("refresh-docs-btn");
    const fileUpload = document.getElementById("file-upload");
    const loadingOverlay = document.getElementById("loading-overlay");

    // Markdown parser 설정
    if (typeof marked !== "undefined") {
        marked.setOptions({ breaks: true, gfm: true });
    }

    let isGenerating = false;

    // ═══════════════ Helper Functions ═══════════════

    function showLoading(show) {
        loadingOverlay.classList.toggle("hidden", !show);
    }

    function scrollToBottom() {
        requestAnimationFrame(() => {
            chatMessages.scrollTop = chatMessages.scrollHeight;
        });
    }

    /** 단순 텍스트 메시지 추가 (user / system) */
    function appendMessage(role, text) {
        const msgDiv = document.createElement("div");
        msgDiv.className = `message ${role}`;

        const avatarDiv = document.createElement("div");
        avatarDiv.className = "avatar";
        avatarDiv.innerHTML = role === "user"
            ? '<i class="fa-solid fa-user"></i>'
            : '<i class="fa-solid fa-robot"></i>';

        const bubbleDiv = document.createElement("div");
        bubbleDiv.className = "bubble";

        if (role === "system" && typeof marked !== "undefined") {
            bubbleDiv.innerHTML = marked.parse(text);
        } else {
            bubbleDiv.textContent = text;
        }

        msgDiv.appendChild(avatarDiv);
        msgDiv.appendChild(bubbleDiv);
        chatMessages.appendChild(msgDiv);
        scrollToBottom();
    }

    /** 
     * 스트리밍 응답용 메시지 컨테이너 생성
     * Returns: { thinkingProcess, thinkingSteps, thinkingToggle, answerContent, bubbleDiv, stepCount }
     */
    function createStreamingContainer() {
        const msgDiv = document.createElement("div");
        msgDiv.className = "message system";

        const avatarDiv = document.createElement("div");
        avatarDiv.className = "avatar";
        avatarDiv.innerHTML = '<i class="fa-solid fa-robot"></i>';

        const bubbleDiv = document.createElement("div");
        bubbleDiv.className = "bubble";

        // ── Thinking Process Section ──
        const thinkingProcess = document.createElement("div");
        thinkingProcess.className = "thinking-process";

        const thinkingToggle = document.createElement("div");
        thinkingToggle.className = "thinking-toggle expanded";
        thinkingToggle.innerHTML = `
            <i class="fa-solid fa-chevron-right"></i>
            <i class="fa-solid fa-brain"></i>
            <span class="toggle-text">사고 과정</span>
            <span class="step-count">0 steps</span>
        `;

        const thinkingSteps = document.createElement("div");
        thinkingSteps.className = "thinking-steps";

        // 토글 클릭 이벤트
        thinkingToggle.addEventListener("click", () => {
            thinkingToggle.classList.toggle("expanded");
            thinkingSteps.classList.toggle("collapsed");
        });

        thinkingProcess.appendChild(thinkingToggle);
        thinkingProcess.appendChild(thinkingSteps);

        // ── Answer Section ──
        const answerContent = document.createElement("div");
        answerContent.className = "answer-content";

        bubbleDiv.appendChild(thinkingProcess);
        bubbleDiv.appendChild(answerContent);
        msgDiv.appendChild(avatarDiv);
        msgDiv.appendChild(bubbleDiv);
        chatMessages.appendChild(msgDiv);
        scrollToBottom();

        return {
            thinkingProcess,
            thinkingSteps,
            thinkingToggle,
            answerContent,
            bubbleDiv,
            stepCount: 0,
        };
    }

    /** Thinking 단계 추가 — 현재 단계만 expanded, 이전 단계는 collapsed */
    function addThinkingStep(container, data) {
        container.stepCount++;

        // step count 업데이트
        const countEl = container.thinkingToggle.querySelector(".step-count");
        countEl.textContent = `${container.stepCount} steps`;

        // ── 이전 step들을 모두 collapsed로 ──
        const prevSteps = container.thinkingSteps.querySelectorAll(".thinking-step");
        prevSteps.forEach(s => {
            s.classList.remove("active");
            s.classList.add("collapsed");
            // detail 영역 숨김
            const detail = s.querySelector(".step-detail-wrap");
            if (detail) detail.style.maxHeight = "0";
        });

        // ── 새 step 생성 ──
        const stepDiv = document.createElement("div");
        stepDiv.className = "thinking-step active";

        // 헤더 (항상 보이는 요약 라인)
        const headerDiv = document.createElement("div");
        headerDiv.className = "step-header";
        headerDiv.innerHTML = `
            <span class="step-chevron"><i class="fa-solid fa-chevron-right"></i></span>
            <span class="step-icon">${data.icon || "⚙️"}</span>
            <span class="step-label">${escapeHtml(data.label || data.node)}</span>
        `;

        // 상세 내용 (접기/펼치기 대상)
        const detailWrap = document.createElement("div");
        detailWrap.className = "step-detail-wrap";

        let detailHTML = "";
        if (data.detail) {
            detailHTML += `<div class="step-detail">${escapeHtml(data.detail)}</div>`;
        }
        if (data.action) {
            detailHTML += `<div class="step-action"><i class="fa-solid fa-play"></i> ${escapeHtml(data.action)}</div>`;
        }
        if (data.action_detail) {
            detailHTML += `<div class="step-detail">${escapeHtml(data.action_detail)}</div>`;
        }
        detailWrap.innerHTML = detailHTML;

        stepDiv.appendChild(headerDiv);
        stepDiv.appendChild(detailWrap);

        // 클릭으로 개별 step 접기/펼치기
        headerDiv.addEventListener("click", () => {
            stepDiv.classList.toggle("collapsed");
            if (stepDiv.classList.contains("collapsed")) {
                detailWrap.style.maxHeight = "0";
            } else {
                detailWrap.style.maxHeight = detailWrap.scrollHeight + "px";
            }
        });

        // 현재 step은 펼침 상태
        requestAnimationFrame(() => {
            detailWrap.style.maxHeight = detailWrap.scrollHeight + "px";
        });

        container.thinkingSteps.appendChild(stepDiv);
        scrollToBottom();
    }

    function escapeHtml(text) {
        if (!text) return "";
        const div = document.createElement("div");
        div.textContent = text;
        return div.innerHTML;
    }

    /** 참고 자료 섹션 렌더링 */
    function renderSources(container, sources) {
        if (!sources || sources.length === 0) return;

        const section = document.createElement("div");
        section.className = "sources-section";

        // 토글 헤더
        const toggle = document.createElement("div");
        toggle.className = "sources-toggle";
        toggle.innerHTML = `
            <i class="fa-solid fa-chevron-right sources-chevron"></i>
            <i class="fa-solid fa-paperclip"></i>
            <span>참고 자료</span>
            <span class="sources-count">${sources.length}건</span>
        `;

        const list = document.createElement("div");
        list.className = "sources-list";

        sources.forEach(src => {
            const item = document.createElement("div");
            item.className = "source-item";

            if (src.type === "web" && src.url) {
                item.innerHTML = `
                    <span class="source-icon">🔗</span>
                    <a href="${escapeHtml(src.url)}" target="_blank" rel="noopener noreferrer" class="source-link">
                        ${escapeHtml(src.title)}
                    </a>
                `;
            } else {
                item.innerHTML = `
                    <span class="source-icon">📄</span>
                    <span class="source-title">${escapeHtml(src.title)}</span>
                `;
            }

            list.appendChild(item);
        });

        toggle.addEventListener("click", () => {
            toggle.classList.toggle("expanded");
            list.classList.toggle("expanded");
        });

        section.appendChild(toggle);
        section.appendChild(list);
        container.bubbleDiv.appendChild(section);
        scrollToBottom();
    }

    /** 문서 목록 로드 */
    async function loadDocuments() {
        try {
            const res = await fetch(`${API_BASE}/documents`);
            const data = await res.json();
            docList.innerHTML = "";

            if (data.documents && data.documents.length > 0) {
                data.documents.forEach(doc => {
                    const li = document.createElement("li");
                    const name = typeof doc === "string" ? doc : doc.filename;
                    const badge = typeof doc === "object" && doc.type ? `<span class="doc-type">${doc.type}</span>` : "";
                    li.innerHTML = `<i class="fa-regular fa-file-lines"></i> ${name} ${badge}`;
                    docList.appendChild(li);
                });
            } else {
                const li = document.createElement("li");
                li.style.color = "var(--text-muted)";
                li.textContent = "문서가 없습니다";
                docList.appendChild(li);
            }
        } catch (e) {
            console.error("Failed to load documents", e);
        }
    }

    // ═══════════════ SSE Stream Handler ═══════════════

    async function handleStreamingChat(query) {
        if (isGenerating) return;
        isGenerating = true;

        // 사용자 메시지 표시
        appendMessage("user", query);

        // "생각 중..." 로딩 표시
        const loadingDiv = document.createElement("div");
        loadingDiv.className = "message system";
        loadingDiv.id = "loading-indicator";
        loadingDiv.innerHTML = `
            <div class="avatar"><i class="fa-solid fa-robot"></i></div>
            <div class="bubble">
                <span style="color: var(--text-muted); font-size: 0.85rem;">
                    <i class="fa-solid fa-circle-notch fa-spin"></i> 생각 중...
                </span>
            </div>
        `;
        chatMessages.appendChild(loadingDiv);
        scrollToBottom();

        try {
            const response = await fetch(`${API_BASE}/chat/stream`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ query, thread_id: "demo_session_1" }),
            });

            if (!response.ok) throw new Error(`HTTP ${response.status}`);

            // 로딩 인디케이터 제거 → 스트리밍 컨테이너 생성
            const loadingEl = document.getElementById("loading-indicator");
            if (loadingEl) loadingEl.remove();

            const container = createStreamingContainer();
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = "";
            let rawAnswer = "";

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const parts = buffer.split("\n\n");
                buffer = parts.pop(); // 마지막 불완전한 부분 유지

                for (const part of parts) {
                    const line = part.trim();
                    if (!line.startsWith("data: ")) continue;

                    const dataStr = line.substring(6);
                    if (!dataStr) continue;

                    let data;
                    try {
                        data = JSON.parse(dataStr);
                    } catch (e) {
                        console.warn("JSON parse error:", e, dataStr);
                        continue;
                    }

                    // ── Event Type별 처리 ──
                    switch (data.type) {
                        case "thinking":
                            addThinkingStep(container, data);
                            break;

                        case "answer_start":
                            // 사고 과정 접기 & 답변 커서 표시
                            container.thinkingToggle.classList.remove("expanded");
                            container.thinkingSteps.classList.add("collapsed");

                            // 모든 step collapsed + active 제거
                            container.thinkingSteps.querySelectorAll(".thinking-step").forEach(s => {
                                s.classList.remove("active");
                                s.classList.add("collapsed");
                                const dw = s.querySelector(".step-detail-wrap");
                                if (dw) dw.style.maxHeight = "0";
                            });

                            container.answerContent.classList.add("streaming");
                            rawAnswer = "";
                            break;

                        case "answer_chunk":
                            if (data.content) {
                                rawAnswer += data.content;
                                // 마크다운 실시간 렌더링
                                if (typeof marked !== "undefined") {
                                    container.answerContent.innerHTML = marked.parse(rawAnswer);
                                } else {
                                    container.answerContent.textContent = rawAnswer;
                                }
                                scrollToBottom();
                            }
                            break;

                        case "done":
                            container.answerContent.classList.remove("streaming");
                            // 사고 과정 스텝 카운트 최종 업데이트
                            const finalCount = container.thinkingToggle.querySelector(".step-count");
                            finalCount.textContent = `${data.total_steps || container.stepCount} steps ✓`;
                            break;

                        case "sources":
                            renderSources(container, data.sources);
                            break;

                        case "error":
                            container.answerContent.classList.remove("streaming");
                            container.answerContent.innerHTML = `<span style="color: var(--error);">⚠️ 오류: ${escapeHtml(data.message)}</span>`;
                            break;

                        default:
                            console.log("Unknown event type:", data);
                    }
                }
            }

            // 스트림 종료 후 answer가 비어있으면 안내
            if (!rawAnswer && !container.answerContent.textContent) {
                container.answerContent.innerHTML = '<em style="color: var(--text-muted);">답변을 생성하지 못했습니다.</em>';
            }
            // 커서 제거
            container.answerContent.classList.remove("streaming");

        } catch (e) {
            const loadingEl = document.getElementById("loading-indicator");
            if (loadingEl) loadingEl.remove();
            appendMessage("system", `⚠️ 연결 오류: ${e.message}`);
            console.error(e);
        } finally {
            isGenerating = false;
        }
    }

    // ═══════════════ Event Listeners ═══════════════

    chatForm.addEventListener("submit", (e) => {
        e.preventDefault();
        const text = chatInput.value.trim();
        if (!text) return;
        chatInput.value = "";
        handleStreamingChat(text);
    });

    refreshDocsBtn.addEventListener("click", loadDocuments);

    fileUpload.addEventListener("change", async (e) => {
        const file = e.target.files[0];
        if (!file) return;

        showLoading(true);
        document.getElementById("loading-text").textContent = `${file.name} 업로드 및 인덱싱 중...`;

        const formData = new FormData();
        formData.append("file", file);

        try {
            const res = await fetch(`${API_BASE}/upload`, { method: "POST", body: formData });
            const data = await res.json();
            showLoading(false);

            if (data.status === "success") {
                appendMessage("system", `✅ 업로드 완료: ${data.message}`);
            } else {
                appendMessage("system", `❌ 업로드 실패: ${data.message}`);
            }
            loadDocuments();
        } catch (e) {
            showLoading(false);
            appendMessage("system", "⚠️ 업로드 중 연결 오류가 발생했습니다.");
        }
        fileUpload.value = "";
    });

    ingestBtn.addEventListener("click", async () => {
        showLoading(true);
        try {
            const res = await fetch(`${API_BASE}/ingest`, { method: "POST" });
            const data = await res.json();
            showLoading(false);

            if (data.status === "success") {
                appendMessage("system", `✅ 인덱싱 완료: ${data.message}`);
            } else {
                appendMessage("system", `❌ 인덱싱 실패: ${data.message}`);
            }
            loadDocuments();
        } catch (e) {
            showLoading(false);
            appendMessage("system", "⚠️ 인덱싱 중 연결 오류가 발생했습니다.");
        }
    });

    // ── 초기 로드 ──
    loadDocuments();
});
