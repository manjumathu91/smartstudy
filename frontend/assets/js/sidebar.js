
document.addEventListener("DOMContentLoaded", async function () {
    const API_BASE_URL = "https://smartstudy-fa86.onrender.com/api";
    const mount = document.getElementById("sidebarMount");

    if (!mount) {
        console.error("Sidebar mount element #sidebarMount not found.");
        return;
    }

    // Load the shared sidebar HTML.
    try {
        const response = await fetch("/components/sidebar.html");

        if (!response.ok) {
            throw new Error(`Sidebar loading failed: ${response.status}`);
        }

        mount.innerHTML = await response.text();
    } catch (error) {
        console.error("Unable to load shared sidebar:", error);
        return;
    }

    const sidebar = document.getElementById("sidebar");
    const menuToggle = document.getElementById("menuToggle");
    const overlay = document.getElementById("sidebarOverlay");
    const sidebarUserName = document.getElementById("sidebarUserName");
    const sidebarAvatar = document.getElementById("sidebarAvatar");
    const logoutBtn = document.getElementById("logoutBtn");

    
    // Highlight the current page.
const currentPage = window.location.pathname.split("/").pop();

document.querySelectorAll("[data-page]").forEach(function (link) {
    const isCurrentPage = link.dataset.page === currentPage;

    link.classList.toggle("active", isCurrentPage);

    if (isCurrentPage) {
        link.setAttribute("aria-current", "page");
    } else {
        link.removeAttribute("aria-current");
    }
});

    // Mobile sidebar controls.
    function closeSidebar() {
        if (sidebar) sidebar.classList.remove("open");
        if (overlay) overlay.classList.remove("show");

        if (menuToggle) {
            menuToggle.setAttribute("aria-expanded", "false");
        }
    }

    if (menuToggle && sidebar && overlay) {
        menuToggle.addEventListener("click", function () {
            const isOpen = sidebar.classList.toggle("open");

            overlay.classList.toggle("show", isOpen);
            menuToggle.setAttribute("aria-expanded", String(isOpen));
        });

        overlay.addEventListener("click", closeSidebar);
    }

    
    document.querySelectorAll(".side-link, .ai-study-hub").forEach(function (link) {
    link.addEventListener("click", closeSidebar);
});

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape") closeSidebar();
    });

    // Authentication helpers.
    function redirectToLogin() {
        localStorage.removeItem("access_token");
        localStorage.removeItem("refresh_token");
        localStorage.removeItem("user_id");
        window.location.href = "login.html";
    }

    function logout() {
         const confirmed = window.confirm(
        "Are you sure you want to log out?"
    );

    if (!confirmed) {
        return;
    }

        localStorage.removeItem("access_token");
        localStorage.removeItem("refresh_token");
        localStorage.removeItem("user_id");

        window.location.href = "login.html";
    }

    if (logoutBtn) {
        logoutBtn.addEventListener("click", logout);
    }

    // Load the signed-in user's name and avatar.
    async function loadUserProfile() {
        const accessToken = localStorage.getItem("access_token");

        if (!accessToken) {
            redirectToLogin();
            return;
        }

        try {
            const response = await fetch(`${API_BASE_URL}/auth/profile/`, {
                method: "GET",
                headers: {
                    Authorization: `Bearer ${accessToken}`
                }
            });

            if (response.status === 401) {
                redirectToLogin();
                return;
            }

            if (!response.ok) {
                throw new Error("Unable to load your profile.");
            }

            const profile = await response.json();

            const fullName =
                profile.first_name && profile.last_name
                    ? `${profile.first_name} ${profile.last_name}`
                    : profile.first_name || profile.username || "Student";

            if (sidebarUserName) {
                sidebarUserName.textContent = fullName;
            }

            if (sidebarAvatar) {
                sidebarAvatar.textContent = fullName.charAt(0).toUpperCase();
            }

            // Notify page-specific scripts that the sidebar is ready.
            document.dispatchEvent(
                new CustomEvent("sidebar:loaded", {
                    detail: { profile, fullName }
                })
            );
        } catch (error) {
            console.error("Profile loading error:", error);
        }
    }

    await loadUserProfile();
});
