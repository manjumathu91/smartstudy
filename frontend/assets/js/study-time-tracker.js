(() => {
    "use strict";

    const API_BASE = "http://127.0.0.1:8000/api";
    const token = localStorage.getItem("access_token");
    const userId = localStorage.getItem("user_id");

    // Do not track logged-out users.
    if (!token || !userId) return;

    const path = window.location.pathname.toLowerCase();

    let pageType = "notes";

    if (path.includes("quiz")) {
        pageType = "quiz";
    } else if (path.includes("revision")) {
        pageType = "revision";
    } else if (path.includes("flashcard")) {
        pageType = "flashcards";
    }

    // Keep the same session across page navigation and refresh
    // in this browser tab, but use a separate key per user.
    const storagePrefix = `smartStudyTime_${userId}_`;
    const sessionKey = storagePrefix + "sessionId";
    const elapsedKey = storagePrefix + "elapsedSeconds";

    let sessionId = sessionStorage.getItem(sessionKey);

    if (!sessionId) {
        sessionId = (
            typeof crypto.randomUUID === "function"
                ? crypto.randomUUID()
                : `${Date.now()}-${Math.random().toString(36).slice(2)}`
        );

        sessionStorage.setItem(sessionKey, sessionId);
    }

    let elapsedSeconds = Number(
        sessionStorage.getItem(elapsedKey) || 0
    );

    if (!Number.isSafeInteger(elapsedSeconds) || elapsedSeconds < 0) {
        elapsedSeconds = 0;
    }

    let lastSentSeconds = -1;
    let sending = false;
    let pendingSend = false;

    async function saveStudyTime(useKeepalive = false) {
        if (document.visibilityState !== "visible" && !useKeepalive) {
            return;
        }

        if (sending) {
            pendingSend = true;
            return;
        }

        // No need to send the same total repeatedly.
        if (elapsedSeconds === lastSentSeconds && !useKeepalive) {
            return;
        }

        sending = true;
        const snapshot = elapsedSeconds;

        try {
            const response = await fetch(`${API_BASE}/learning/study-time/`, {
                method: "POST",
                headers: {
                    "Authorization": `Bearer ${token}`,
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    session_id: sessionId,
                    elapsed_seconds: snapshot,
                    page_type: pageType
                }),
                keepalive: useKeepalive
            });

            if (response.status === 401) {
                // Don't redirect automatically from the tracker.
                // The existing page authentication logic can handle login.
                return;
            }

            if (!response.ok) {
                throw new Error(`Study time save failed: ${response.status}`);
            }

            lastSentSeconds = Math.max(lastSentSeconds, snapshot);
        } catch (error) {
            // The next heartbeat retries with the latest cumulative total.
            console.error("Study time tracking error:", error);
        } finally {
            sending = false;

            if (pendingSend) {
                pendingSend = false;

                if (elapsedSeconds > lastSentSeconds) {
                    saveStudyTime();
                }
            }
        }
    }

    function storeElapsedTime() {
        sessionStorage.setItem(elapsedKey, String(elapsedSeconds));
    }

    // Count only while the study page is visible.
    setInterval(() => {
        if (document.visibilityState !== "visible") return;

        elapsedSeconds += 1;
        storeElapsedTime();
    }, 1000);

    // Send cumulative time every 15 seconds.
    setInterval(() => {
        if (document.visibilityState === "visible") {
            saveStudyTime();
        }
    }, 15000);

    document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "visible") {
            saveStudyTime();
        } else {
            saveStudyTime(true);
        }
    });

    // Try to save the latest total when leaving the page.
    window.addEventListener("pagehide", () => {
        storeElapsedTime();
        saveStudyTime(true);
    });

    // Save a starting record so a short study session is initialized.
    saveStudyTime();
})();