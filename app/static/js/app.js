/* ==========================================================================
   VA Digital Studio — progressive enhancement
   Everything here is optional: pages stay usable without JavaScript.
   ========================================================================== */
(function () {
  "use strict";

  const csrfToken =
    document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") || "";

  /** fetch() with the CSRF header attached for unsafe methods. */
  function apiFetch(url, options = {}) {
    const method = (options.method || "GET").toUpperCase();
    const headers = new Headers(options.headers || {});
    headers.set("Accept", "application/json");
    if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
      headers.set("X-CSRF-Token", csrfToken);
    }
    if (options.body && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    return fetch(url, { ...options, headers, credentials: "same-origin" });
  }

  // --- Flash messages -----------------------------------------------------

  function dismissFlash(element) {
    element.style.transition = "opacity 160ms, transform 160ms";
    element.style.opacity = "0";
    element.style.transform = "translateY(-6px)";
    window.setTimeout(() => element.remove(), 170);
  }

  document.addEventListener("click", (event) => {
    const close = event.target.closest("[data-flash-close]");
    if (close) dismissFlash(close.closest(".flash"));
  });

  // Auto-dismiss success flashes; errors stay until the visitor closes them.
  document.querySelectorAll(".flash--success, .flash--info").forEach((flash) => {
    window.setTimeout(() => dismissFlash(flash), 6000);
  });

  // --- Scroll reveal ------------------------------------------------------

  /**
   * Fade sections in as they scroll into view.
   *
   * The `.reveal` class is applied here rather than in the template, so a
   * visitor without JavaScript (or with reduced motion, or an older browser
   * without IntersectionObserver) sees a normal, fully visible page.
   */
  const prefersReducedMotion = window.matchMedia(
    "(prefers-reduced-motion: reduce)"
  ).matches;

  if (!prefersReducedMotion && "IntersectionObserver" in window) {
    const targets = document.querySelectorAll(
      ".section-head, .card, .grid--cards > *, .features > *, .faq-item, " +
        ".stat-card, .profile-header, .cta, .hero__visual"
    );

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        });
      },
      { rootMargin: "0px 0px -8% 0px", threshold: 0.05 }
    );

    // Only animate what starts below the fold; anything already on screen
    // should simply be there, without a visible entrance.
    const fold = window.innerHeight;
    let index = 0;
    targets.forEach((element) => {
      if (element.getBoundingClientRect().top < fold * 0.9) return;
      element.classList.add("reveal");
      // A small stagger inside a row, capped so nothing feels slow.
      element.style.setProperty(
        "--reveal-delay",
        `${Math.min(index++ % 4, 3) * 60}ms`
      );
      observer.observe(element);
    });
  }

  // --- Header dropdown ----------------------------------------------------

  function closeAllDropdowns(except) {
    document.querySelectorAll("[data-user-menu-dropdown]").forEach((dropdown) => {
      if (dropdown === except) return;
      dropdown.hidden = true;
      dropdown
        .closest("[data-user-menu]")
        ?.querySelector("[data-user-menu-trigger]")
        ?.setAttribute("aria-expanded", "false");
    });
  }

  document.addEventListener("click", (event) => {
    const trigger = event.target.closest("[data-user-menu-trigger]");
    if (trigger) {
      const dropdown = trigger.closest("[data-user-menu]").querySelector(
        "[data-user-menu-dropdown]"
      );
      const willOpen = dropdown.hidden;
      closeAllDropdowns(willOpen ? dropdown : null);
      dropdown.hidden = !willOpen;
      trigger.setAttribute("aria-expanded", String(willOpen));
      return;
    }
    if (!event.target.closest("[data-user-menu-dropdown]")) closeAllDropdowns();
  });

  // --- Modal helpers ------------------------------------------------------

  const openOverlays = new Set();

  function openModal(modal) {
    if (!modal) return;
    modal.hidden = false;
    openOverlays.add(modal);
    document.body.style.overflow = "hidden";
    modal.querySelector("input, textarea, button")?.focus();
  }

  function closeModal(modal) {
    if (!modal) return;
    modal.hidden = true;
    openOverlays.delete(modal);
    if (!openOverlays.size) document.body.style.overflow = "";
  }

  function closeTopOverlay() {
    const last = Array.from(openOverlays).pop();
    if (last) closeModal(last);
  }

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      if (openOverlays.size) {
        closeTopOverlay();
      } else {
        closeDrawer();
      }
    }
  });

  // Close a modal when clicking the backdrop (but not the panel).
  document.querySelectorAll(".modal").forEach((modal) => {
    modal.addEventListener("mousedown", (event) => {
      if (event.target === modal) closeModal(modal);
    });
  });

  // --- Support modal ------------------------------------------------------

  const supportModal = document.querySelector("[data-support-modal]");

  document.addEventListener("click", (event) => {
    if (event.target.closest("[data-support-open]")) {
      event.preventDefault();
      closeDrawer();
      openModal(supportModal);
    }
    if (event.target.closest("[data-support-close]")) {
      closeModal(supportModal);
    }
  });

  // --- Balance placeholder modal -----------------------------------------

  const balanceModal = document.querySelector("[data-balance-modal]");

  document.addEventListener("click", (event) => {
    if (event.target.closest("[data-balance-topup]")) openModal(balanceModal);
    if (event.target.closest("[data-balance-close]")) closeModal(balanceModal);
  });

  // --- Mobile drawer ------------------------------------------------------

  const drawer = document.querySelector("[data-drawer]");
  const backdrop = document.querySelector("[data-drawer-backdrop]");
  const burger = document.querySelector("[data-burger]");

  function openDrawer() {
    if (!drawer) return;
    drawer.hidden = false;
    if (backdrop) backdrop.hidden = false;
    // Next frame, so the transition runs instead of jumping.
    window.requestAnimationFrame(() => {
      drawer.classList.add("is-open");
      backdrop?.classList.add("is-open");
    });
    burger?.setAttribute("aria-expanded", "true");
    document.body.style.overflow = "hidden";
    drawer.querySelector("a, button")?.focus();
  }

  function closeDrawer() {
    if (!drawer || drawer.hidden) return;
    drawer.classList.remove("is-open");
    backdrop?.classList.remove("is-open");
    burger?.setAttribute("aria-expanded", "false");
    if (!openOverlays.size) document.body.style.overflow = "";
    window.setTimeout(() => {
      if (!drawer.classList.contains("is-open")) {
        drawer.hidden = true;
        if (backdrop) backdrop.hidden = true;
      }
    }, 280);
  }

  burger?.addEventListener("click", () => {
    if (drawer?.classList.contains("is-open")) closeDrawer();
    else openDrawer();
  });

  backdrop?.addEventListener("click", closeDrawer);
  document.querySelector("[data-drawer-close]")?.addEventListener("click", closeDrawer);

  // Keep focus inside the drawer while it is open.
  drawer?.addEventListener("keydown", (event) => {
    if (event.key !== "Tab") return;
    const focusable = drawer.querySelectorAll(
      'a[href], button:not([disabled]), input, textarea, select, [tabindex]:not([tabindex="-1"])'
    );
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  });

  // --- News likes (AJAX) --------------------------------------------------

  document.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-like-button]");
    if (!button || button.classList.contains("is-busy")) return;

    const newsId = button.dataset.newsId;
    button.classList.add("is-busy");

    try {
      const response = await apiFetch(`/api/news/${newsId}/like`, { method: "POST" });

      if (response.status === 401) {
        // Not logged in — send the visitor to Google, then back here.
        const payload = await response.json().catch(() => ({}));
        window.location.href =
          payload.login_url
            ? `${payload.login_url}?next=${encodeURIComponent(window.location.pathname)}`
            : "/auth/login";
        return;
      }

      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      const data = await response.json();
      const count = button.querySelector("[data-like-count]");
      if (count) count.textContent = data.likes_count;

      button.classList.toggle("is-liked", data.liked);
      button.dataset.liked = String(data.liked);
      button.setAttribute("aria-pressed", String(data.liked));

      if (data.liked) {
        button.classList.add("just-liked");
        window.setTimeout(() => button.classList.remove("just-liked"), 360);
      }

      // Keep duplicate like buttons for the same news item in sync.
      document
        .querySelectorAll(`[data-like-button][data-news-id="${newsId}"]`)
        .forEach((other) => {
          if (other === button) return;
          other.classList.toggle("is-liked", data.liked);
          other.dataset.liked = String(data.liked);
          other.setAttribute("aria-pressed", String(data.liked));
          const otherCount = other.querySelector("[data-like-count]");
          if (otherCount) otherCount.textContent = data.likes_count;
        });
    } catch (error) {
      console.error("Не удалось поставить лайк:", error);
    } finally {
      button.classList.remove("is-busy");
    }
  });

  // --- Auto-growing chat textarea ----------------------------------------

  document.querySelectorAll("[data-chat-input]").forEach((input) => {
    input.addEventListener("input", () => {
      input.style.height = "auto";
      input.style.height = `${Math.min(input.scrollHeight, 140)}px`;
    });
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        input.closest("form")?.requestSubmit();
      }
    });
  });

  // --- Reusable chat client ----------------------------------------------

  /**
   * Connect to an order chat over WebSocket and render messages.
   * Used by both the customer page and the admin dashboard.
   */
  window.VAChat = function createChat(options) {
    const log = document.querySelector(options.logSelector);
    const form = document.querySelector(options.formSelector);
    const input = document.querySelector(options.inputSelector);
    const statusDot = document.querySelector(options.statusSelector);
    const typingLabel = document.querySelector(options.typingSelector);
    if (!log || !form) return null;

    let socket = null;
    let reconnectDelay = 1000;
    let reconnectTimer = null;
    let closedByUser = false;
    let typingTimer = null;
    let lastTypingSent = 0;

    function atBottom() {
      return log.scrollHeight - log.scrollTop - log.clientHeight < 80;
    }

    function scrollToBottom() {
      log.scrollTop = log.scrollHeight;
    }

    function setStatus(online) {
      if (!statusDot) return;
      statusDot.classList.toggle("is-online", online);
      statusDot.textContent = online ? "на связи" : "нет соединения";
    }

    function formatTime(iso) {
      const date = iso ? new Date(iso) : new Date();
      return date.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
    }

    /** Append one message. `text` is inserted as a text node, never as HTML. */
    function appendMessage(message, prepend = false) {
      if (message.id && log.querySelector(`[data-message-id="${message.id}"]`)) return;

      const wrapper = document.createElement("div");
      wrapper.className = "chat__msg";
      if (message.kind === "system") {
        wrapper.classList.add("chat__msg--system");
      } else {
        wrapper.classList.add(message.is_mine ? "chat__msg--mine" : "chat__msg--theirs");
      }
      if (message.id) wrapper.dataset.messageId = message.id;

      const bubble = document.createElement("div");
      bubble.className = "chat__bubble";
      bubble.textContent = message.text;

      const meta = document.createElement("div");
      meta.className = "chat__meta";
      const author = message.is_mine ? "Вы" : message.sender_name || "Менеджер";
      meta.textContent =
        message.kind === "system" ? formatTime(message.created_at) : `${author} · ${formatTime(message.created_at)}`;

      wrapper.append(bubble, meta);
      if (prepend) log.prepend(wrapper);
      else log.append(wrapper);
    }

    function appendHistory(messages) {
      log.textContent = "";
      if (!messages.length) {
        appendMessage(
          { kind: "system", text: "История пуста. Напишите первое сообщение." },
          false
        );
        return;
      }
      messages.forEach((message) => appendMessage(message));
      scrollToBottom();
    }

    function connect() {
      const scheme = window.location.protocol === "https:" ? "wss" : "ws";
      socket = new WebSocket(`${scheme}://${window.location.host}${options.wsPath}`);

      socket.addEventListener("open", () => {
        reconnectDelay = 1000;
        setStatus(true);
      });

      socket.addEventListener("message", (event) => {
        let payload;
        try {
          payload = JSON.parse(event.data);
        } catch {
          return;
        }

        if (payload.type === "history") {
          appendHistory(payload.messages || []);
        } else if (payload.type === "message") {
          const stick = atBottom();
          appendMessage(payload.message);
          if (stick) scrollToBottom();
        } else if (payload.type === "typing") {
          if (!typingLabel) return;
          typingLabel.textContent = payload.is_typing
            ? `${payload.sender_name || "Собеседник"} печатает…`
            : "";
        } else if (payload.type === "error") {
          if (typingLabel) typingLabel.textContent = payload.detail || "";
        }
      });

      socket.addEventListener("close", (event) => {
        setStatus(false);
        if (closedByUser) return;

        // Terminal conditions: retrying would only repeat the rejection.
        if (event.code === 4401) {
          if (typingLabel) typingLabel.textContent = "Сессия истекла — войдите заново";
          window.setTimeout(() => {
            window.location.href = `/auth/login?next=${encodeURIComponent(
              window.location.pathname
            )}`;
          }, 1200);
          return;
        }
        if (event.code === 4403 || event.code === 4404) {
          if (typingLabel) typingLabel.textContent = "Чат недоступен";
          return;
        }

        reconnectTimer = window.setTimeout(connect, reconnectDelay);
        reconnectDelay = Math.min(reconnectDelay * 1.7, 15000);
      });

      socket.addEventListener("error", () => setStatus(false));
    }

    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const text = (input?.value || "").trim();
      if (!text || !socket || socket.readyState !== WebSocket.OPEN) return;

      socket.send(JSON.stringify({ type: "message", text }));
      input.value = "";
      if (input) input.style.height = "auto";
      if (typingLabel) typingLabel.textContent = "";
      lastTypingSent = 0;
    });

    // Throttled "typing" notification: at most one every 1.5 s.
    input?.addEventListener("input", () => {
      if (!socket || socket.readyState !== WebSocket.OPEN) return;
      const now = Date.now();
      if (now - lastTypingSent < 1500) return;
      lastTypingSent = now;
      socket.send(JSON.stringify({ type: "typing", is_typing: true }));
      window.clearTimeout(typingTimer);
      typingTimer = window.setTimeout(() => {
        if (socket?.readyState === WebSocket.OPEN) {
          socket.send(JSON.stringify({ type: "typing", is_typing: false }));
        }
      }, 2200);
    });

    window.addEventListener("beforeunload", () => {
      closedByUser = true;
      window.clearTimeout(reconnectTimer);
      socket?.close();
    });

    connect();
    return { appendMessage, scrollToBottom };
  };
})();
