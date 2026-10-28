
/* ==========================================
   SMART STUDY AI - MAIN JAVASCRIPT
   File: assets/js/script.js
========================================== */

document.addEventListener("DOMContentLoaded", () => {
  
  // AUTH CHECK - PROTECTED PAGES
  const protectedPages = [
    "upload.html",
    "study.html",
    "summarizer.html",
    "aistudychat.html",
    "revision.html"
  ];

  const currentPage = window.location.pathname
    .split("/")
    .pop()
    .toLowerCase();

  if (
    protectedPages.includes(currentPage) &&
    !localStorage.getItem("access_token")
  ) {
    window.location.replace("login.html");
    return;
  }

  // Protect Upload PDF links
  document.querySelectorAll('a[href="upload.html"]').forEach((link) => {
    link.addEventListener("click", (event) => {
      if (!localStorage.getItem("access_token")) {
        event.preventDefault();
        window.location.href = "login.html";
      }
    });
  });

  // ------------------------------------------
  // 1. MOBILE NAVBAR TOGGLE
  // ------------------------------------------

  const menuToggle = document.getElementById("menuToggle");
  const navMenu = document.getElementById("navMenu");

  if (menuToggle && navMenu) {
    const menuIcon = menuToggle.querySelector("i");

    function closeMenu() {
      navMenu.classList.remove("open");
      menuToggle.setAttribute("aria-expanded", "false");

      if (menuIcon) {
        menuIcon.classList.remove("fa-xmark");
        menuIcon.classList.add("fa-bars");
      }
    }

    menuToggle.setAttribute("aria-expanded", "false");

    menuToggle.addEventListener("click", () => {
      const isOpen = navMenu.classList.toggle("open");

      menuToggle.setAttribute("aria-expanded", String(isOpen));

      if (menuIcon) {
        menuIcon.classList.toggle("fa-bars", !isOpen);
        menuIcon.classList.toggle("fa-xmark", isOpen);
      }
    });

    // Close menu after clicking a navigation link
    navMenu.querySelectorAll("a").forEach((link) => {
      link.addEventListener("click", closeMenu);
    });

    // Close menu when Escape key is pressed
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        closeMenu();
      }
    });

    // Close menu when clicking outside the navbar
    document.addEventListener("click", (event) => {
      if (
        navMenu.classList.contains("open") &&
        !navMenu.contains(event.target) &&
        !menuToggle.contains(event.target)
      ) {
        closeMenu();
      }
    });
  }

  // ------------------------------------------
  // 2. SCROLL REVEAL ANIMATIONS
  // ------------------------------------------

  const revealElements = document.querySelectorAll(".reveal");
  const reduceMotion = window.matchMedia(
    "(prefers-reduced-motion: reduce)"
  ).matches;

  if (reduceMotion || !("IntersectionObserver" in window)) {
    revealElements.forEach((element) => {
      element.classList.add("visible");
    });
  } else {
    const revealObserver = new IntersectionObserver(
      (entries, observer) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("visible");
            observer.unobserve(entry.target);
          }
        });
      },
      {
        threshold: 0.12,
        rootMargin: "0px 0px -40px 0px",
      }
    );

    revealElements.forEach((element) => {
      element.classList.add("reveal-ready");
      revealObserver.observe(element);
    });
  }

  // ------------------------------------------
  // 3. SMOOTH SCROLL FOR SECTION LINKS
  // ------------------------------------------

  document.querySelectorAll('a[href^="#"]').forEach((link) => {
    link.addEventListener("click", (event) => {
      const targetId = link.getAttribute("href");

      if (!targetId || targetId === "#") return;

      const targetElement = document.querySelector(targetId);

      if (targetElement) {
        event.preventDefault();

        targetElement.scrollIntoView({
          behavior: reduceMotion ? "auto" : "smooth",
          block: "start",
        });

        // Update URL hash without jumping
        if (window.history && window.history.pushState) {
          window.history.pushState(null, "", targetId);
        }
      }
    });
  });

  // ------------------------------------------
  // 4. NAVBAR SCROLL EFFECT
  // ------------------------------------------

  const navbar = document.querySelector(".navbar");

  if (navbar) {
    const updateNavbar = () => {
      navbar.classList.toggle("scrolled", window.scrollY > 30);
    };

    updateNavbar();

    window.addEventListener("scroll", updateNavbar, {
      passive: true,
    });
  }

  // ------------------------------------------
  // 5. CURRENT YEAR IN FOOTER
  // ------------------------------------------

  const currentYear = document.getElementById("currentYear");

  if (currentYear) {
    currentYear.textContent = new Date().getFullYear();
  }

  // ------------------------------------------
  // 6. PREVENT EMPTY LINK JUMPS
  // ------------------------------------------

  document.querySelectorAll('a[href="#"]').forEach((link) => {
    link.addEventListener("click", (event) => {
      event.preventDefault();
    });
  });
  // ------------------------------------------
  // 7. LOGIN BUTTONS + AI STUDY CHAT + REVISION
  // ------------------------------------------

  const isLoggedIn = Boolean(
    localStorage.getItem("access_token")
  );

  const getStartedBtn = document.getElementById("getStartedBtn");
  const dashboardBtn = document.getElementById("dashboardBtn");

  // Update landing page authentication buttons
  if (getStartedBtn) {
    getStartedBtn.style.display = isLoggedIn ? "none" : "inline-flex";
  }

  if (dashboardBtn) {
    dashboardBtn.style.display = isLoggedIn ? "inline-flex" : "none";
  }

  // AI Study Chat feature link
  const aiStudyChatLink = document.getElementById("aiStudyChatLink");

  if (aiStudyChatLink) {
    aiStudyChatLink.href = isLoggedIn
      ? "aistudychat.html"
      : "login.html";

    const label = aiStudyChatLink.firstChild;

    if (label && label.nodeType === Node.TEXT_NODE) {
      label.textContent = isLoggedIn
        ? "Start AI Learning "
        : "Login to Start ";
    }
  }

  // Smart Revision feature link
  const smartRevisionLink = document.getElementById("smartRevisionLink");

  if (smartRevisionLink) {
    smartRevisionLink.href = isLoggedIn
      ? "revision.html"
      : "login.html";

    const label = smartRevisionLink.firstChild;

    if (label && label.nodeType === Node.TEXT_NODE) {
      label.textContent = isLoggedIn
        ? "Start Revision "
        : "Login to Start ";
    }
  }
  console.log("Smart Study AI JavaScript loaded successfully!");
});
