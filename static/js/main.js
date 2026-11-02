/* Small, page-aware interactions shared by the Jinja pages. */
(() => {
  document.addEventListener("error", (event) => {
    const image = event.target;
    if (!(image instanceof HTMLImageElement) || !image.matches("[data-poster-fallback]")) return;
    image.hidden = true;
    if (image.classList.contains("hero-art")) return;
    image.parentElement?.classList.add("poster-missing");
  }, true);

  const navToggle = document.querySelector(".nav-toggle");
  const siteNav = document.getElementById("site-nav");

  if (navToggle && siteNav) {
    const closeNav = () => {
      navToggle.setAttribute("aria-expanded", "false");
      navToggle.setAttribute("aria-label", "Ouvrir le menu");
      siteNav.classList.remove("is-open");
    };
    navToggle.addEventListener("click", () => {
      const isOpen = navToggle.getAttribute("aria-expanded") === "true";
      navToggle.setAttribute("aria-expanded", String(!isOpen));
      navToggle.setAttribute("aria-label", isOpen ? "Ouvrir le menu" : "Fermer le menu");
      siteNav.classList.toggle("is-open", !isOpen);
    });
    siteNav.addEventListener("click", (event) => {
      if (event.target.closest("a")) closeNav();
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") closeNav();
    });
    if (typeof window.matchMedia === "function") {
      const desktop = window.matchMedia("(min-width: 801px)");
      if (typeof desktop.addEventListener === "function") desktop.addEventListener("change", closeNav);
      else if (typeof desktop.addListener === "function") desktop.addListener(closeNav);
    }
  }

  const toastRegion = document.getElementById("toast-region");
  const showToast = (message, kind = "info") => {
    if (!toastRegion) return;
    const toast = document.createElement("div");
    toast.className = `toast toast-${kind}`;
    toast.textContent = message;
    toastRegion.replaceChildren(toast);
    window.setTimeout(() => toast.remove(), 4200);
  };

  if (new URLSearchParams(window.location.search).has("registered")) {
    showToast("Votre compte est créé. Vous pouvez maintenant vous connecter.", "success");
  }

  const confirmDialog = document.getElementById("site-confirm");
  const confirmAction = (title, message, actionLabel = "Confirmer") => new Promise((resolve) => {
    if (!confirmDialog || typeof confirmDialog.showModal !== "function") {
      resolve(window.confirm(message));
      return;
    }
    document.getElementById("site-confirm-title").textContent = title;
    document.getElementById("site-confirm-copy").textContent = message;
    const confirmButton = confirmDialog.querySelector('[value="confirm"]');
    confirmButton.textContent = actionLabel;
    confirmDialog.addEventListener("close", () => resolve(confirmDialog.returnValue === "confirm"), {once: true});
    confirmDialog.showModal();
  });

  const parseResponse = async (response) => {
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = Array.isArray(body.detail) ? body.detail.map((item) => item.msg).join("; ") : body.detail;
      throw new Error(detail || "Une erreur est survenue. Réessayez.");
    }
    return body;
  };

  document.getElementById("logout-btn")?.addEventListener("click", async (event) => {
    const button = event.currentTarget;
    button.disabled = true;
    try {
      await parseResponse(await fetch("/api/auth/logout", {method: "POST"}));
      window.location.assign("/");
    } catch {
      button.disabled = false;
      showToast("La déconnexion a échoué. Réessayez.", "error");
    }
  });

  document.querySelectorAll("[data-auth-form]").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!form.reportValidity()) return;
      const button = form.querySelector('button[type="submit"]');
      const error = form.querySelector(".form-error");
      const intent = form.dataset.authForm;
      button.disabled = true;
      button.dataset.label = button.textContent;
      button.textContent = intent === "login" ? "Connexion…" : "Création du compte…";
      error.textContent = "";
      const payload = Object.fromEntries(new FormData(form).entries());
      try {
        const user = await parseResponse(await fetch(`/api/auth/${intent}`, {
          method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload),
        }));
        const destination = intent === "login" ? (user.role === "admin" ? "/admin" : "/") : "/login?registered=1";
        window.location.assign(destination);
      } catch (requestError) {
        error.textContent = requestError instanceof TypeError
          ? "Service momentanément indisponible. Vérifiez votre connexion et réessayez."
          : requestError.message || (intent === "login" ? "Connexion impossible." : "Inscription impossible.");
        button.disabled = false;
        button.textContent = button.dataset.label;
      }
    });
  });

  const search = document.getElementById("film-search");
  const genreFilter = document.getElementById("genre-filter");
  const filmCards = [...document.querySelectorAll("#film-grid .film-card")];
  const emptySearch = document.getElementById("empty-search");
  const filterFilms = () => {
    const term = search?.value.trim().toLocaleLowerCase("fr") || "";
    const genre = genreFilter?.value || "";
    let visible = 0;
    filmCards.forEach((card) => {
      const matches = card.dataset.title.includes(term) && (!genre || card.dataset.genre === genre);
      card.hidden = !matches;
      if (matches) visible += 1;
    });
    if (emptySearch) emptySearch.hidden = visible > 0;
  };
  search?.addEventListener("input", filterFilms);
  genreFilter?.addEventListener("change", filterFilms);

  const seatMap = document.getElementById("seat-map");
  if (seatMap) {
    const rows = Number(seatMap.dataset.rows);
    const cols = Number(seatMap.dataset.cols);
    const taken = new Set(JSON.parse(seatMap.dataset.taken || "[]"));
    const selected = new Set();
    const price = Number(seatMap.dataset.price || document.getElementById("book-btn")?.dataset.price || 0);
    const selectedList = document.getElementById("selected-list");
    const total = document.getElementById("total");
    const bookButton = document.getElementById("book-btn");
    const canBook = seatMap.dataset.authenticated === "true" && Boolean(bookButton);
    const error = document.getElementById("booking-error");
    const rowLabel = (index) => {
      let label = "";
      let value = index + 1;
      while (value > 0) {
        const remainder = (value - 1) % 26;
        label = String.fromCharCode(65 + remainder) + label;
        value = Math.floor((value - 1) / 26);
      }
      return label;
    };
    const updateSummary = () => {
      selectedList.textContent = selected.size ? [...selected].sort().join(", ") : "Aucune";
      total.textContent = `${(selected.size * price).toFixed(2).replace(".", ",")} €`;
      if (bookButton) bookButton.disabled = selected.size === 0;
    };
    for (let row = 0; row < rows; row += 1) {
      const rowName = rowLabel(row);
      const rowElement = document.createElement("div");
      rowElement.className = "seat-row";
      rowElement.setAttribute("role", "group");
      rowElement.setAttribute("aria-label", `Rangée ${rowName}`);
      const label = document.createElement("span");
      label.className = "seat-row-label";
      label.setAttribute("aria-hidden", "true");
      label.textContent = rowName;
      rowElement.append(label);
      for (let column = 1; column <= cols; column += 1) {
        const seatName = `${rowName}${column}`;
        const seat = document.createElement("button");
        seat.type = "button";
        seat.className = "seat";
        seat.textContent = String(column);
        seat.setAttribute("aria-label", `Place ${seatName}, ${taken.has(seatName) ? "réservée" : "disponible"}`);
        seat.setAttribute("aria-pressed", "false");
        if (taken.has(seatName)) {
          seat.classList.add("taken");
          seat.disabled = true;
        } else if (!canBook) {
          seat.classList.add("guest-locked");
          seat.disabled = true;
          seat.setAttribute("aria-label", `Place ${seatName}, disponible, connectez-vous pour réserver`);
        } else {
          seat.addEventListener("click", () => {
            if (selected.has(seatName)) {
              selected.delete(seatName);
              seat.classList.remove("selected");
              seat.setAttribute("aria-pressed", "false");
              seat.setAttribute("aria-label", `Place ${seatName}, disponible`);
            } else {
              selected.add(seatName);
              seat.classList.add("selected");
              seat.setAttribute("aria-pressed", "true");
              seat.setAttribute("aria-label", `Place ${seatName}, sélectionnée`);
            }
            error.textContent = "";
            updateSummary();
          });
        }
        rowElement.append(seat);
      }
      seatMap.append(rowElement);
    }
    updateSummary();
    bookButton?.addEventListener("click", async () => {
      if (!selected.size) return;
      bookButton.disabled = true;
      bookButton.textContent = "Confirmation…";
      error.textContent = "";
      try {
        const result = await parseResponse(await fetch("/api/bookings", {
          method: "POST", headers: {"Content-Type": "application/json"},
          body: JSON.stringify({screening_id: Number(bookButton.dataset.screeningId), seats: [...selected]}),
        }));
        window.location.assign(`/billets/${encodeURIComponent(result.ticket_code)}`);
      } catch (requestError) {
        error.textContent = requestError.message;
        bookButton.textContent = "Confirmer les places";
        bookButton.disabled = false;
      }
    });
  }

  document.querySelectorAll("[data-cancel-reservation]").forEach((button) => {
    button.addEventListener("click", async () => {
      const reservationId = button.dataset.cancelReservation;
      const accepted = await confirmAction("Annuler cette réservation ?", "Vos places seront libérées et le billet ne sera plus valide.", "Annuler la réservation");
      if (!accepted) return;
      button.disabled = true;
      try {
        await parseResponse(await fetch(`/api/bookings/${reservationId}/cancel`, {method: "POST"}));
        showToast("Votre réservation a été annulée.", "success");
        window.location.reload();
      } catch (requestError) {
        button.disabled = false;
        const message = document.getElementById("reservation-message");
        if (message) message.textContent = requestError.message;
        else showToast(requestError.message, "error");
      }
    });
  });
})();
