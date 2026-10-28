document.addEventListener("DOMContentLoaded", function () {
    "use strict";

    // =====================================================
    // 1. DOM ELEMENTS
    // =====================================================
    const API_BASE_URL = "https://smartstudy-fa86.onrender.com/api/learning/";
    const chatForm = document.getElementById("chatForm");
    const questionInput = document.getElementById("questionInput");
    const sendBtn = document.getElementById("sendBtn");
    const chatMessages = document.getElementById("chatMessages");
    const historyList = document.getElementById("historyList");
    const newChatBtn = document.getElementById("newChatBtn");
    const languageSelect = document.getElementById("languageSelect");
    const statusMessage = document.getElementById("statusMessage");
    const micBtn = document.getElementById("micBtn");
    const stopAudioBtn = document.getElementById("stopAudioBtn");
    const modeButtons = document.querySelectorAll(".mode-btn");

    if (!chatForm || !questionInput || !sendBtn || !chatMessages ||
        !historyList || !languageSelect) {
        console.error("AI Study Chat: One or more required HTML elements are missing.");
        return;
    }

    // =====================================================
    // 2. STATE
    // =====================================================
    let currentChatId = null;
    let selectedMode = "explain";
    let isSending = false;

    let recognition = null;
    let isListening = false;
    let isRecognitionStarting = false;
    let voiceChatActive = false;
    let voiceQuestionReady = false;
    let currentSpeechUtterance = null;
    let speechRunId = 0;
    let recognitionFinalTranscript = "";
    let recognitionRestartTimer = null;

    const SpeechRecognitionAPI =
        window.SpeechRecognition || window.webkitSpeechRecognition;

    // =====================================================
    // 3. GENERAL HELPERS
    // =====================================================
    const accessToken = () => localStorage.getItem("access_token");

    function showStatus(message) {
        if (statusMessage) statusMessage.textContent = message || "";
    }

    function redirectToLogin() {
        localStorage.removeItem("access_token");
        localStorage.removeItem("refresh_token");
        localStorage.removeItem("user_id");
        window.location.href = "/login.html";
    }

    function scrollToBottom() {
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function clearMessages() {
        chatMessages.replaceChildren();
    }

    function getSpeechLanguage() {
        const language = languageSelect.value || "Tamil";
        if (language === "Tamil") return "ta-IN";
        return "en-IN";
    }

    function getSpeechOutputLanguage(text) {
        const language = languageSelect.value || "Tamil";
        if (language === "Tamil") return "ta-IN";
        if (language === "English") return "en-IN";
        return /[\u0B80-\u0BFF]/.test(text) ? "ta-IN" : "en-IN";
    }

    // =====================================================
    // 4. API REQUESTS
    // =====================================================
    async function apiRequest(url, options = {}) {
        const token = accessToken();
        if (!token) {
            redirectToLogin();
            throw new Error("Please log in again.");
        }

        const response = await fetch(url, {
            ...options,
            headers: {
                "Content-Type": "application/json",
                Authorization: `Bearer ${token}`,
                ...(options.headers || {})
            }
        });

        if (response.status === 401) {
            redirectToLogin();
            throw new Error("Your session expired. Please log in again.");
        }

        let data = {};
        try {
            data = await response.json();
        } catch (_) {
            // Some successful responses may have no JSON body.
        }

        if (!response.ok) {
            throw new Error(
                data.error || data.detail || data.message ||
                `Request failed (${response.status}).`
            );
        }
        return data;
    }

    // =====================================================
    // 5. WELCOME CARD
    // =====================================================
    function addWelcomeCard() {
        clearMessages();

        const card = document.createElement("div");
        card.className = "welcome-card";
        card.id = "welcomeCard";

        const icon = document.createElement("div");
        icon.className = "welcome-icon";
        const iconElement = document.createElement("i");
        iconElement.className = "fa-solid fa-book-open-reader";
        iconElement.setAttribute("aria-hidden", "true");
        icon.appendChild(iconElement);

        const heading = document.createElement("h3");
        heading.textContent = "What would you like to learn today?";

        const paragraph = document.createElement("p");
        paragraph.textContent =
            "Ask in Tamil, English, or Tanglish. Choose a study mode and start learning at your own pace.";

        card.append(icon, heading, paragraph);
        chatMessages.appendChild(card);
    }

    // =====================================================
    // 6. SAFE MARKDOWN + VISUAL LEARNING + MERMAID
    // =====================================================
    async function renderAssistantContent(container, content) {
        const cleanedContent = String(content || "")
            .replace(/&#x20;|&#160;|&nbsp;/gi, " ")
            .replace(/\u00a0/g, " ")
            .replace(/[ \t]+$/gm, "")
            .trim();

        if (typeof marked === "undefined" || typeof DOMPurify === "undefined") {
            container.textContent = cleanedContent;
            return;
        }

        const escapeHTML = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
            "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
        }[char]));

        if (selectedMode === "visualize") {
            const sections = {
                title: "", overview: "", keyIdea: "", cards: [], facts: [], remember: ""
            };
            let currentSection = "";

            for (const line of cleanedContent.split(/\r?\n/)) {
                const value = line.trim();
                if (!value) continue;
                const heading = value.replace(/^\*\*(.*?)\*\*:?\s*$/, "$1:").trim();

                if (/^TITLE\s*:/i.test(heading)) {
                    sections.title = heading.replace(/^TITLE\s*:/i, "").trim();
                    currentSection = "title"; continue;
                }
                if (/^OVERVIEW\s*:/i.test(heading)) {
                    sections.overview = heading.replace(/^OVERVIEW\s*:/i, "").trim();
                    currentSection = "overview"; continue;
                }
                if (/^KEY IDEA\s*:/i.test(heading)) {
                    sections.keyIdea = heading.replace(/^KEY IDEA\s*:/i, "").trim();
                    currentSection = "keyIdea"; continue;
                }
                if (/^VISUAL CARDS\s*:/i.test(heading)) {
                    currentSection = "cards"; continue;
                }
                if (/^IMPORTANT FACTS\s*:/i.test(heading)) {
                    currentSection = "facts"; continue;
                }
                if (/^REMEMBER\s*:/i.test(heading)) {
                    sections.remember = heading.replace(/^REMEMBER\s*:/i, "").trim();
                    currentSection = "remember"; continue;
                }

                if (currentSection === "cards") {
                    const cardLine = value.replace(/^[-*]\s+/, "")
                        .replace(/^\*\*CARD:\*\*\s*/i, "CARD: ")
                        .replace(/^CARD:\s*/i, "");
                    const separatorIndex = cardLine.indexOf("|");
                    if (separatorIndex !== -1) {
                        const title = cardLine.slice(0, separatorIndex).replace(/\*\*/g, "").trim();
                        const description = cardLine.slice(separatorIndex + 1).replace(/\*\*/g, "").trim();
                        if (title && description) sections.cards.push({ title, description });
                    }
                    continue;
                }

                if (currentSection === "facts") {
                    const fact = value.replace(/^[-*]\s+/, "").replace(/\*\*/g, "").trim();
                    if (fact) sections.facts.push(fact);
                    continue;
                }

                if (["title", "overview", "keyIdea", "remember"].includes(currentSection)) {
                    sections[currentSection] += (sections[currentSection] ? " " : "") + value;
                }
            }

            for (const key of ["title", "overview", "keyIdea", "remember"]) {
                sections[key] = sections[key].replace(/\*\*/g, "").trim();
            }

            const uniqueBy = (items, keyFn) => {
                const seen = new Set();
                return items.filter((item) => {
                    const key = keyFn(item).toLowerCase();
                    if (seen.has(key)) return false;
                    seen.add(key);
                    return true;
                });
            };
            sections.cards = uniqueBy(sections.cards, c => `${c.title}|${c.description}`);
            sections.facts = uniqueBy(sections.facts, f => f);

            const visualText = [
                sections.title, sections.overview, sections.keyIdea,
                ...sections.cards.map(c => `${c.title} ${c.description}`)
            ].join(" ").toLowerCase();

            let visualTheme = "general";
            if (/history|historical|வரலாறு|அரசர்|பேரரசு|போர்/.test(visualText)) visualTheme = "history";
            else if (/science|scientific|அறிவியல்|photosynthesis|atom|செல்|மின்சாரம்/.test(visualText)) visualTheme = "science";
            else if (/geography|geographical|புவியியல்|நதி|மலை|காலநிலை|வரைபடம்/.test(visualText)) visualTheme = "geography";
            else if (/compare|comparison|difference|ஒப்பீடு|வேறுபாடு/.test(visualText)) visualTheme = "comparison";
            else if (/steps|process|stage|படிநிலை|செயல்முறை|நிலைகள்/.test(visualText)) visualTheme = "process";

            if (sections.cards.length) {
                const visualHTML = `
                    <section class="visual-learning theme-${visualTheme}">
                        ${sections.title ? `<header class="visual-header">
                            <span class="visual-eyebrow">SMART STUDY AI · VISUAL NOTES</span>
                            <h2 class="visual-title">${escapeHTML(sections.title)}</h2>
                        </header>` : ""}
                        ${sections.overview ? `<p class="visual-overview">${escapeHTML(sections.overview)}</p>` : ""}
                        ${sections.keyIdea ? `<div class="visual-key-idea">
                            <span class="visual-section-label">💡 KEY IDEA</span>
                            <p>${escapeHTML(sections.keyIdea)}</p></div>` : ""}
                        <div class="visual-card-grid">
                            ${sections.cards.map((card, index) => `<article class="visual-card">
                                <span class="visual-card-number">${String(index + 1).padStart(2, "0")}</span>
                                <h3>${escapeHTML(card.title)}</h3>
                                <p>${escapeHTML(card.description)}</p>
                            </article>`).join("")}
                        </div>
                        ${sections.facts.length ? `<section class="visual-facts">
                            <h3>📌 Important Facts</h3><ul>
                            ${sections.facts.map(f => `<li>${escapeHTML(f)}</li>`).join("")}
                            </ul></section>` : ""}
                        ${sections.remember ? `<aside class="visual-remember">
                            <span class="visual-section-label">🧠 REMEMBER</span>
                            <p>${escapeHTML(sections.remember)}</p></aside>` : ""}
                    </section>`;
                container.innerHTML = DOMPurify.sanitize(visualHTML);
                return;
            }
        }

        container.innerHTML = DOMPurify.sanitize(marked.parse(cleanedContent));
        const diagramNodes = container.querySelectorAll("pre > code.language-mermaid");
        diagramNodes.forEach((code) => {
            const diagram = document.createElement("div");
            diagram.className = "mermaid";
            diagram.textContent = code.textContent;
            code.parentElement.replaceWith(diagram);
        });

        if (diagramNodes.length && typeof mermaid !== "undefined") {
            try {
                await mermaid.run({ nodes: container.querySelectorAll(".mermaid") });
            } catch (error) {
                console.error("Mermaid diagram rendering failed:", error);
            }
        }
    }

    // =====================================================
    // 7. TEXT-TO-SPEECH
    // =====================================================
    function stopAudio(showMessage = false) {
        speechRunId++;
        if ("speechSynthesis" in window) window.speechSynthesis.cancel();
        currentSpeechUtterance = null;
        if (stopAudioBtn) stopAudioBtn.disabled = true;
        if (showMessage) showStatus("Audio stopped.");
    }

    function cleanTextForSpeech(text) {
        const temporaryElement = document.createElement("div");
        temporaryElement.innerHTML = String(text || "");
        return (temporaryElement.textContent || temporaryElement.innerText || "")
            .replace(/```[\s\S]*?```/g, " Code block omitted. ")
            .replace(/https?:\/\/\S+/g, " link ")
            .replace(/[#*_`>|]/g, " ")
            .replace(/\s+/g, " ")
            .trim();
    }
function getFemaleVoice(language) {
  const voices = window.speechSynthesis.getVoices();

  const lang = language === "ta" ? "ta" : "en";

  const matchingVoices = voices.filter(voice =>
    voice.lang.toLowerCase().startsWith(lang)
  );

  return (
    matchingVoices.find(voice =>
      /female|woman|zira|samantha|heera|kalpana/i.test(voice.name)
    ) ||
    matchingVoices[0] ||
    null
  );
}


    function speakAIAnswer(text, forVoiceChat = false) {
        if (!("speechSynthesis" in window) ||
            typeof SpeechSynthesisUtterance === "undefined") {
            showStatus("Text-to-speech is not supported by this browser.");
            if (forVoiceChat) restartVoiceListening();
            return;
        }

        stopAudio(false);
        const cleanText = cleanTextForSpeech(text);
        if (!cleanText) {
            if (forVoiceChat) restartVoiceListening();
            return;
        }

        const thisRunId = speechRunId;
        const utterance = new SpeechSynthesisUtterance(cleanText);
        currentSpeechUtterance = utterance;
        utterance.lang = getSpeechOutputLanguage(cleanText);

        utterance.onstart = () => {
            if (thisRunId !== speechRunId) return;
            if (stopAudioBtn) stopAudioBtn.disabled = false;
            showStatus("AI is speaking...");
        };

        utterance.onend = () => {
            if (thisRunId !== speechRunId) return;
            currentSpeechUtterance = null;
            if (stopAudioBtn) stopAudioBtn.disabled = true;
            if (forVoiceChat && voiceChatActive) {
                showStatus("AI answer finished. Listening again...");
                restartVoiceListening();
            } else {
                showStatus("Audio finished.");
            }
        };

        utterance.onerror = (event) => {
            if (thisRunId !== speechRunId) return;
            currentSpeechUtterance = null;
            if (stopAudioBtn) stopAudioBtn.disabled = true;
            if (event.error !== "canceled" && event.error !== "interrupted") {
                showStatus("Unable to play this response. Try another browser voice.");
            }
            if (forVoiceChat && voiceChatActive) restartVoiceListening();
        };

        window.speechSynthesis.speak(utterance);
    }

    if (stopAudioBtn) {
        stopAudioBtn.disabled = true;
        stopAudioBtn.addEventListener("click", () => stopAudio(true));
    }

    // =====================================================
    // 8. VOICE INPUT / CONTINUOUS VOICE CHAT
    // =====================================================
    function resetMicButton() {
        isListening = false;
        isRecognitionStarting = false;
        if (!micBtn) return;
        micBtn.classList.remove("listening");
        micBtn.innerHTML = '<i class="fa-solid fa-microphone" aria-hidden="true"></i>';
        micBtn.setAttribute("aria-label", "Start voice chat");
        micBtn.title = "Start voice chat";
    }

    function stopListening() {
        if (recognition && (isListening || isRecognitionStarting)) {
            try { recognition.stop(); } catch (_) { /* already stopped */ }
        }
        isListening = false;
        isRecognitionStarting = false;
        if (recognitionRestartTimer) {
            clearTimeout(recognitionRestartTimer);
            recognitionRestartTimer = null;
        }
        resetMicButton();
    }

    function restartVoiceListening() {
        if (!voiceChatActive || isSending || !recognition) return;
        if (recognitionRestartTimer) clearTimeout(recognitionRestartTimer);
        recognitionRestartTimer = setTimeout(() => {
            recognitionRestartTimer = null;
            if (!voiceChatActive || isSending || isListening || isRecognitionStarting) return;
            recognitionFinalTranscript = "";
            questionInput.value = "";
            try {
                recognition.lang = getSpeechLanguage();
                isRecognitionStarting = true;
                recognition.start();
            } catch (error) {
                isRecognitionStarting = false;
                console.warn("Could not restart speech recognition:", error);
                showStatus("Could not restart the microphone. Tap the mic to try again.");
            }
        }, 450);
    }

    async function submitCapturedVoiceQuestion(question) {
        if (!question || !question.trim() || isSending || !voiceChatActive) return;
        questionInput.value = question.trim();
        voiceQuestionReady = true;
        await sendQuestion(null, true);
    }

    if (micBtn) {
        if (!SpeechRecognitionAPI) {
            micBtn.disabled = true;
            micBtn.title = "Voice input is not supported by this browser";
            micBtn.setAttribute("aria-label", "Voice input unsupported");
        } else {
            recognition = new SpeechRecognitionAPI();
            recognition.continuous = false;
            recognition.interimResults = true;
            recognition.maxAlternatives = 1;

            micBtn.addEventListener("click", () => {
                if (voiceChatActive) {
                    voiceChatActive = false;
                    voiceQuestionReady = false;
                    stopListening();
                    stopAudio(false);
                    resetMicButton();
                    showStatus("Voice chat stopped.");
                    return;
                }

                if (isSending) {
                    showStatus("Please wait until the current answer finishes.");
                    return;
                }

                voiceChatActive = true;
                stopAudio(false);
                recognitionFinalTranscript = "";
                questionInput.value = "";
                try {
                    recognition.lang = getSpeechLanguage();
                    isRecognitionStarting = true;
                    recognition.start();
                } catch (error) {
                    isRecognitionStarting = false;
                    voiceChatActive = false;
                    showStatus("Unable to start microphone. Check browser permission and try again.");
                }
            });

            recognition.onstart = () => {
                isListening = true;
                isRecognitionStarting = false;
                if (micBtn) {
                    micBtn.classList.add("listening");
                    micBtn.innerHTML = '<i class="fa-solid fa-stop" aria-hidden="true"></i>';
                    micBtn.setAttribute("aria-label", "Stop voice chat");
                    micBtn.title = "Stop voice chat";
                }
                if (voiceChatActive) showStatus("Voice chat active. Speak your question.");
                else showStatus("Listening... Speak your question.");
            };

            recognition.onresult = (event) => {
                let interimTranscript = "";
                for (let i = event.resultIndex; i < event.results.length; i++) {
                    const transcript = event.results[i][0].transcript;
                    if (event.results[i].isFinal) recognitionFinalTranscript += transcript + " ";
                    else interimTranscript += transcript;
                }

                questionInput.value = (recognitionFinalTranscript + interimTranscript).trim();
                questionInput.dispatchEvent(new Event("input", { bubbles: true }));

                if (voiceChatActive && recognitionFinalTranscript.trim()) {
                    voiceQuestionReady = true;
                }
            };

            recognition.onerror = (event) => {
                isRecognitionStarting = false;
                const messages = {
                    "not-allowed": "Please allow microphone access in your browser.",
                    "service-not-allowed": "Please allow speech recognition access.",
                    "no-speech": "No speech detected. Speak again when listening resumes.",
                    "network": "Speech recognition needs a working network connection.",
                    "audio-capture": "No microphone was detected. Check your microphone."
                };
                if (event.error === "not-allowed" || event.error === "service-not-allowed") {
                    voiceChatActive = false;
                    resetMicButton();
                }
                showStatus(messages[event.error] || "Voice input failed. Please try again.");
            };

            recognition.onend = () => {
                isListening = false;
                isRecognitionStarting = false;

                const finalQuestion = recognitionFinalTranscript.trim();
                if (voiceChatActive && finalQuestion && !isSending) {
                    questionInput.value = finalQuestion;
                    recognitionFinalTranscript = "";
                    submitCapturedVoiceQuestion(finalQuestion);
                    return;
                }

                if (voiceChatActive && !isSending) {
                    resetMicButton();
                    restartVoiceListening();
                    return;
                }

                resetMicButton();
                if (!voiceChatActive && questionInput.value.trim()) {
                    showStatus("Voice captured. Review your question and press Send.");
                }
            };
        }
    }

    // =====================================================
    // 9. ADD MESSAGE + LISTEN BUTTON
    // =====================================================
    function addMessage(role, content) {
        const message = document.createElement("div");
        message.className = `message ${role}`;

        const label = document.createElement("span");
        label.className = "message-label";
        label.textContent = role === "user" ? "You" : "AI Study Tutor";

        const text = document.createElement("div");
        text.className = "message-content";
        message.append(label, text);
        chatMessages.appendChild(message);

        if (role === "assistant") {
            message.dataset.speechText = content || "";
            renderAssistantContent(text, content || "")
                .then(scrollToBottom)
                .catch((error) => {
                    console.error("Unable to render AI answer:", error);
                    text.textContent = content || "";
                    scrollToBottom();
                });

            const controls = document.createElement("div");
            controls.className = "message-audio-controls";
            const listenButton = document.createElement("button");
            listenButton.type = "button";
            listenButton.className = "message-audio-btn";
            listenButton.title = "Listen to AI answer";
            listenButton.setAttribute("aria-label", "Listen to AI answer");
            listenButton.innerHTML = '<i class="fa-solid fa-volume-high" aria-hidden="true"></i> Listen';
            listenButton.addEventListener("click", () => {
                speakAIAnswer(message.dataset.speechText || content || "", false);
            });
            controls.appendChild(listenButton);
            message.appendChild(controls);
        } else {
            text.textContent = content || "";
        }

        scrollToBottom();
        return message;
    }

    // =====================================================
    // 10. STUDY MODES
    // =====================================================
    function setMode(mode) {
        selectedMode = mode || "explain";
        modeButtons.forEach((button) => {
            const active = button.dataset.mode === selectedMode;
            button.classList.toggle("active", active);
            button.setAttribute("aria-pressed", String(active));
        });
    }

    function formatChatTitle(title) {
        return title || "New conversation";
    }

    // =====================================================
    // 11. LOAD CHAT HISTORY + DELETE MENU
    // =====================================================
    async function loadHistory() {
        historyList.replaceChildren();
        const loading = document.createElement("p");
        loading.className = "history-empty";
        loading.textContent = "Loading conversations...";
        historyList.appendChild(loading);

        try {
            const data = await apiRequest(`${API_BASE_URL}ai-study-chat/history/`);
            historyList.replaceChildren();
            const chats = Array.isArray(data.chats) ? data.chats : [];

            if (!chats.length) {
                const empty = document.createElement("p");
                empty.className = "history-empty";
                empty.textContent = "Your recent chats will appear here.";
                historyList.appendChild(empty);
                return;
            }

            chats.forEach((chat) => {
                const item = document.createElement("div");
                item.className = "history-row";

                const openButton = document.createElement("button");
                openButton.type = "button";
                openButton.className = "history-item";
                openButton.textContent = formatChatTitle(chat.title);
                openButton.dataset.chatId = chat.chat_id;
                if (String(chat.chat_id) === String(currentChatId)) openButton.classList.add("active");
                openButton.addEventListener("click", () => openChat(chat.chat_id));

                const menuWrapper = document.createElement("div");
                menuWrapper.className = "history-menu-wrapper";
                const menuButton = document.createElement("button");
                menuButton.type = "button";
                menuButton.className = "history-menu-btn";
                menuButton.innerHTML = '<i class="fa-solid fa-ellipsis" aria-hidden="true"></i>';
                menuButton.title = "Chat options";
                menuButton.setAttribute("aria-label", "Chat options");
                menuButton.setAttribute("aria-expanded", "false");

                const menu = document.createElement("div");
                menu.className = "history-menu";
                menu.hidden = true;

                const deleteButton = document.createElement("button");
                deleteButton.type = "button";
                deleteButton.className = "history-menu-delete";
                deleteButton.innerHTML = '<i class="fa-regular fa-trash-can" aria-hidden="true"></i> Delete';

                menuButton.addEventListener("click", (event) => {
                    event.stopPropagation();
                    const shouldOpen = menu.hidden;
                    document.querySelectorAll(".history-menu").forEach(m => { m.hidden = true; });
                    document.querySelectorAll(".history-menu-btn").forEach(b => b.setAttribute("aria-expanded", "false"));
                    menu.hidden = !shouldOpen;
                    menuButton.setAttribute("aria-expanded", String(shouldOpen));
                });

                deleteButton.addEventListener("click", async (event) => {
                    event.stopPropagation();
                    menu.hidden = true;
                    menuButton.setAttribute("aria-expanded", "false");
                    if (isSending) {
                        showStatus("Please wait until the current answer finishes.");
                        return;
                    }
                    if (!window.confirm(`Delete "${formatChatTitle(chat.title)}"? This cannot be undone.`)) return;

                    deleteButton.disabled = true;
                    showStatus("Deleting conversation...");
                    try {
                        await apiRequest(`${API_BASE_URL}ai-study-chat/${chat.chat_id}/`, { method: "DELETE" });
                        if (String(currentChatId) === String(chat.chat_id)) {
                            currentChatId = null;
                            questionInput.value = "";
                            languageSelect.value = "Tamil";
                            stopAudio(false);
                            setMode("explain");
                            addWelcomeCard();
                        }
                        showStatus("Conversation deleted.");
                        await loadHistory();
                    } catch (error) {
                        deleteButton.disabled = false;
                        showStatus(`Unable to delete chat: ${error.message}`);
                    }
                });

                menu.appendChild(deleteButton);
                menuWrapper.append(menuButton, menu);
                item.append(openButton, menuWrapper);
                historyList.appendChild(item);
            });
        } catch (error) {
            if (error.message.includes("log in again")) return;
            historyList.replaceChildren();
            const errorMessage = document.createElement("p");
            errorMessage.className = "history-empty";
            errorMessage.textContent = error.message;
            historyList.appendChild(errorMessage);
        }
    }

    // =====================================================
    // 12. OPEN EXISTING CHAT
    // =====================================================
    async function openChat(chatId) {
        if (isSending) {
            showStatus("Please wait until the current answer finishes.");
            return;
        }
        voiceChatActive = false;
        stopAudio(false);
        stopListening();
        showStatus("Loading conversation...");

        try {
            const data = await apiRequest(`${API_BASE_URL}ai-study-chat/${chatId}/`);
            currentChatId = data.chat_id;
            setMode(data.mode || "explain");
            if (data.language) languageSelect.value = data.language;
            clearMessages();

            const messages = Array.isArray(data.messages) ? data.messages : [];
            if (!messages.length) addWelcomeCard();
            else messages.forEach(message => addMessage(message.role, message.content));

            await loadHistory();
            showStatus("");
            questionInput.focus();
        } catch (error) {
            showStatus(`Unable to open chat: ${error.message}`);
        }
    }

    // =====================================================
    // 13. SEND QUESTION TO AI
    // =====================================================
    async function sendQuestion(event, fromVoice = false) {
        if (event && typeof event.preventDefault === "function") event.preventDefault();
        if (isSending) return;

        const question = questionInput.value.trim();
        if (!question) {
            showStatus("Please type your study question.");
            if (!fromVoice) questionInput.focus();
            return;
        }
        if (question.length > 1000) {
            showStatus("Please keep your question within 1000 characters.");
            return;
        }

        stopAudio(false);
        if (!fromVoice) {
            voiceChatActive = false;
            stopListening();
        } else {
            stopListening();
        }

        isSending = true;
        sendBtn.disabled = true;
        if (micBtn) micBtn.disabled = true;
        showStatus(fromVoice ? "I heard you. Your AI tutor is preparing an answer..." :
            "Your AI tutor is preparing an answer...");

        const welcome = document.getElementById("welcomeCard");
        if (welcome) welcome.remove();

        addMessage("user", question);
        questionInput.value = "";

        try {
            const payload = {
                question,
                chat_id: currentChatId,
                mode: selectedMode,
                language: languageSelect.value
            };
            const data = await apiRequest(`${API_BASE_URL}ai-study-chat/`, {
                method: "POST",
                body: JSON.stringify(payload)
            });

            currentChatId = data.chat_id;
            if (data.mode) setMode(data.mode);
            if (data.language) languageSelect.value = data.language;

            const answer = data.answer || "No answer was returned.";
            addMessage("assistant", answer);
            await loadHistory();

            if (fromVoice && voiceChatActive) {
                speakAIAnswer(answer, true);
            } else {
                showStatus("");
            }
        } catch (error) {
            showStatus(`Unable to get an answer: ${error.message}`);
            if (fromVoice && voiceChatActive) restartVoiceListening();
        } finally {
            isSending = false;
            sendBtn.disabled = false;
            if (micBtn && SpeechRecognitionAPI) micBtn.disabled = false;

            if (voiceChatActive && !currentSpeechUtterance) {
                restartVoiceListening();
            } else if (!voiceChatActive) {
                questionInput.focus();
            }
        }
    }

    // =====================================================
    // 14. START NEW CHAT
    // =====================================================
    function startNewChat() {
        if (isSending) return;
        voiceChatActive = false;
        stopAudio(false);
        stopListening();
        currentChatId = null;
        questionInput.value = "";
        languageSelect.value = "Tamil";
        setMode("explain");
        addWelcomeCard();
        showStatus("");
        document.querySelectorAll(".history-item").forEach(item => item.classList.remove("active"));
        questionInput.focus();
    }

    // =====================================================
    // 15. EVENT LISTENERS
    // =====================================================
    modeButtons.forEach((button) => {
        button.addEventListener("click", () => {
            if (isSending) return;
            setMode(button.dataset.mode);
            showStatus("");
        });
    });

    chatForm.addEventListener("submit", (event) => sendQuestion(event, false));

    if (newChatBtn) newChatBtn.addEventListener("click", startNewChat);

    languageSelect.addEventListener("change", () => {
        stopAudio(false);
        if (voiceChatActive && recognition && !isSending) {
            stopListening();
            restartVoiceListening();
        }
    });

    document.addEventListener("click", (event) => {
        if (!event.target.closest(".history-menu-wrapper")) {
            document.querySelectorAll(".history-menu").forEach(menu => { menu.hidden = true; });
            document.querySelectorAll(".history-menu-btn").forEach(button => button.setAttribute("aria-expanded", "false"));
        }
    });

    window.addEventListener("pagehide", () => {
        voiceChatActive = false;
        stopAudio(false);
        stopListening();
    });

    // =====================================================
    // 16. INITIALIZE
    // =====================================================
    if (!accessToken()) {
        redirectToLogin();
        return;
    }
    if (stopAudioBtn) stopAudioBtn.disabled = true;
    addWelcomeCard();
    loadHistory();
});
