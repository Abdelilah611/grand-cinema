/* Admin dashboard behaviors are scoped to this page and this module. */
(() => {
  const errorEl = document.getElementById("admin-error");
  const filmForm = document.getElementById("film-form");
  const filmStatus = document.getElementById("film-status");
  const filmList = document.getElementById("films-list");
  const dialog = document.getElementById("confirm-dialog");
  let films = [];
  let previewUrl = "";

  const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[char]);
  const posterUrl = (poster) => poster?.startsWith("uploads/") ? `/static/${poster}` : `/static/posters/${poster || "film1.svg"}`;
  const showError = (message = "") => { errorEl.textContent = message; };
  const money = (value) => `${Number(value).toFixed(2).replace(".", ",")} €`;

  async function api(path, options = {}) {
    const headers = {...options.headers};
    if (options.body && !(options.body instanceof FormData)) headers["Content-Type"] = "application/json";
    const response = await fetch(path, {...options, headers});
    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = Array.isArray(result.detail) ? result.detail.map((item) => item.msg).join("; ") : result.detail;
      throw new Error(detail || `Erreur ${response.status}`);
    }
    return result;
  }

  function confirmAction(title, message, actionLabel = "Supprimer") {
    return new Promise((resolve) => {
      if (!dialog || typeof dialog.showModal !== "function") {
        resolve(window.confirm(message));
        return;
      }
      document.getElementById("confirm-title").textContent = title;
      document.getElementById("confirm-copy").textContent = message;
      dialog.querySelector('[value="confirm"]').textContent = actionLabel;
      dialog.addEventListener("close", () => resolve(dialog.returnValue === "confirm"), {once: true});
      dialog.showModal();
    });
  }

  async function loadStats() {
    const stats = await api("/api/admin/stats");
    document.getElementById("stat-boxes").innerHTML = [
      ["Réservations confirmées", stats.total_reservations], ["Réservations annulées", stats.cancelled_reservations],
      ["Billets valides ou utilisés", stats.tickets_sold], ["Places vendues", stats.total_seats],
      ["Revenus", money(stats.total_revenue)], ["Remplissage global", `${stats.global_fill_rate} %`],
    ].map(([label, value]) => `<div class="stat-box"><strong>${escapeHtml(value)}</strong>${escapeHtml(label)}</div>`).join("");
    document.getElementById("stats-films").innerHTML = stats.per_film.map((film) =>
      `<tr><td>${escapeHtml(film.title)}</td><td>${film.reservations}</td><td>${film.seats}</td><td>${money(film.revenue)}</td><td>${film.fill_rate} %</td></tr>`).join("");
    document.getElementById("stats-rooms").innerHTML = stats.per_room.map((room) =>
      `<tr><td>${escapeHtml(room.name)}</td><td>${room.seats}</td><td>${room.fill_rate} %</td></tr>`).join("");
    document.getElementById("stats-screenings").innerHTML = stats.per_screening.map((screening) =>
      `<tr><td>${escapeHtml(screening.film_title)}</td><td>${escapeHtml(screening.room_name)}</td><td>${new Date(screening.start_time).toLocaleString("fr-FR")}</td><td>${screening.reserved} / ${screening.capacity}</td><td>${screening.fill_rate} %</td><td>${money(screening.revenue)}</td></tr>`).join("");
  }

  function renderFilms() {
    const term = document.getElementById("admin-film-search").value.trim().toLocaleLowerCase("fr");
    const state = document.getElementById("admin-film-status").value;
    const sort = document.getElementById("admin-film-sort")?.value || "title";
    const filtered = films.filter((film) => {
      const matchesTerm = `${film.title} ${film.genre} ${film.director}`.toLocaleLowerCase("fr").includes(term);
      return matchesTerm && (!state || (state === "published") === film.is_published);
    }).sort((a, b) => sort === "newest" ? b.id - a.id : a.title.localeCompare(b.title, "fr"));
    document.getElementById("film-count").textContent = `(${filtered.length})`;
    filmList.innerHTML = filtered.map((film) =>
      `<tr><td><img class="film-thumb" data-poster-fallback src="${escapeHtml(posterUrl(film.poster))}" alt=""></td><td><strong>${escapeHtml(film.title)}</strong></td><td>${escapeHtml(film.genre || "—")}</td><td>${film.duration_min} min</td><td>${escapeHtml(film.release_date || film.release_year || "—")}</td><td><span class="film-badge ${film.is_published ? "published" : "draft"}">${film.is_published ? "Publié" : "Brouillon"}</span></td><td class="film-actions"><button class="btn btn-small" data-edit="${film.id}" type="button">Modifier</button><button class="btn btn-small btn-quiet" data-publish="${film.id}" type="button">${film.is_published ? "Dépublier" : "Publier"}</button><button class="btn btn-small btn-danger" data-delete-film="${film.id}" type="button">Supprimer</button></td></tr>`).join("") || '<tr><td colspan="7">Aucun film ne correspond à ces filtres.</td></tr>';
  }

  async function loadFilms() {
    films = await api("/api/admin/films");
    renderFilms();
    document.getElementById("screening-film").innerHTML = films.map((film) =>
      `<option value="${film.id}">${escapeHtml(film.title)}</option>`).join("");
  }

  async function loadRooms() {
    const rooms = await api("/api/admin/rooms");
    document.getElementById("rooms-list").innerHTML = rooms.map((room) =>
      `<tr><td>${escapeHtml(room.name)}</td><td>${escapeHtml(room.room_type)}</td><td>${room.capacity}</td><td>${room.rows} × ${room.cols}</td><td><button class="btn btn-small btn-danger" data-delete-room="${room.id}" type="button">Supprimer</button></td></tr>`).join("");
    document.getElementById("screening-room").innerHTML = rooms.map((room) =>
      `<option value="${room.id}">${escapeHtml(room.name)}</option>`).join("");
  }
  async function loadScreenings() {
    const screenings = await api("/api/admin/screenings");
    document.getElementById("screenings-list").innerHTML = screenings.map((screening) =>
      `<tr><td>${escapeHtml(screening.film_title)}</td><td>${escapeHtml(screening.room_name)}</td><td>${new Date(screening.start_time).toLocaleString("fr-FR")}</td><td>${money(screening.price)}</td><td><button class="btn btn-small btn-danger" data-delete-screening="${screening.id}" type="button">Supprimer</button></td></tr>`).join("");
  }
  async function loadBookings() {
    const bookings = await api("/api/admin/bookings");
    document.getElementById("bookings-list").innerHTML = bookings.map((booking) =>
      `<tr><td>${escapeHtml(booking.user_email)}</td><td>${escapeHtml(booking.film_title)}</td><td>${escapeHtml(booking.room_name)}</td><td>${new Date(booking.start_time).toLocaleString("fr-FR")}</td><td>${escapeHtml(booking.seats.join(", "))}</td><td>${money(booking.total)}</td><td>${escapeHtml(booking.status)}</td><td>${booking.status === "confirmed" ? `<button class="btn btn-small btn-danger" data-cancel-booking="${booking.id}" type="button">Annuler</button>` : "—"}</td></tr>`).join("");
  }

  async function deleteItem(path, title, message, reload) {
    if (!await confirmAction(title, message)) return;
    try { await api(path, {method: "DELETE"}); showError(); await reload(); }
    catch (error) { showError(error.message); }
  }
  async function cancelBooking(id) {
    if (!await confirmAction("Annuler cette réservation ?", "Le billet correspondant ne sera plus valide.", "Annuler la réservation")) return;
    try { await api(`/api/admin/bookings/${id}/cancel`, {method: "POST"}); showError(); await loadBookings(); }
    catch (error) { showError(error.message); }
  }

  function setPosterPreview(url) {
    const image = document.getElementById("poster-preview");
    const placeholder = document.getElementById("poster-placeholder");
    image.hidden = !url;
    placeholder.hidden = Boolean(url);
    if (url) image.src = url;
    else image.removeAttribute("src");
  }
  function resetFilmForm() {
    filmForm.reset();
    filmForm.elements.film_id.value = "";
    document.getElementById("film-form-title").textContent = "Ajouter un film";
    document.getElementById("film-submit").textContent = "Enregistrer le brouillon";
    document.getElementById("film-cancel").hidden = true;
    filmStatus.textContent = "";
    setPosterPreview("");
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = "";
  }
  function editFilm(id) {
    const film = films.find((item) => item.id === id);
    if (!film) return;
    const values = {
      film_id: film.id, title: film.title, genre: film.genre, duration_min: film.duration_min,
      director: film.director, cast_names: film.cast, release_date: film.release_date || "",
      release_year: film.release_year, age_rating: film.age_rating, language: film.language,
      trailer_url: film.trailer_url, synopsis: film.synopsis,
      is_published: String(film.is_published), poster: film.poster,
    };
    Object.entries(values).forEach(([name, value]) => { filmForm.elements[name].value = value ?? ""; });
    document.getElementById("film-form-title").textContent = `Modifier : ${film.title}`;
    document.getElementById("film-submit").textContent = "Enregistrer les modifications";
    document.getElementById("film-cancel").hidden = false;
    setPosterPreview(posterUrl(film.poster));
    filmForm.scrollIntoView({behavior: "smooth", block: "start"});
    filmForm.elements.title.focus({preventScroll: true});
  }

  filmList.addEventListener("click", async (event) => {
    const edit = event.target.closest("[data-edit]");
    const publish = event.target.closest("[data-publish]");
    const remove = event.target.closest("[data-delete-film]");
    if (edit) editFilm(Number(edit.dataset.edit));
    if (publish) {
      const film = films.find((item) => item.id === Number(publish.dataset.publish));
      if (!film) return;
      publish.disabled = true;
      try {
        await api(`/api/admin/films/${film.id}/${film.is_published ? "unpublish" : "publish"}`, {method: "POST"});
        filmStatus.textContent = film.is_published ? "Film dépublié." : "Film publié sur le site.";
        showError();
        await loadFilms();
      } catch (error) { showError(error.message); publish.disabled = false; }
    }
    if (remove) {
      const film = films.find((item) => item.id === Number(remove.dataset.deleteFilm));
      await deleteItem(`/api/admin/films/${remove.dataset.deleteFilm}`, `Supprimer « ${film?.title || "ce film"} » ?`, "Cette action est définitive. Les films avec des séances ne peuvent pas être supprimés.", async () => {
        resetFilmForm(); await loadFilms();
      });
    }
  });

  document.getElementById("admin-film-search").addEventListener("input", renderFilms);
  document.getElementById("admin-film-status").addEventListener("change", renderFilms);
  document.getElementById("admin-film-sort")?.addEventListener("change", renderFilms);
  document.querySelector(".admin-page").addEventListener("click", async (event) => {
    const room = event.target.closest("[data-delete-room]");
    const screening = event.target.closest("[data-delete-screening]");
    const booking = event.target.closest("[data-cancel-booking]");
    if (room) await deleteItem(`/api/admin/rooms/${room.dataset.deleteRoom}`, "Supprimer cette salle ?", "Vérifiez qu’aucune séance active ne dépend de cette salle.", loadRooms);
    if (screening) await deleteItem(`/api/admin/screenings/${screening.dataset.deleteScreening}`, "Supprimer cette séance ?", "Les réservations associées pourraient être affectées.", loadScreenings);
    if (booking) await cancelBooking(booking.dataset.cancelBooking);
  });

  document.getElementById("poster-file").addEventListener("change", (event) => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    const file = event.target.files[0];
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) {
      filmStatus.textContent = "L’affiche ne doit pas dépasser 5 Mo.";
      event.target.value = "";
      return;
    }
    previewUrl = URL.createObjectURL(file);
    setPosterPreview(previewUrl);
    filmStatus.textContent = "";
  });
  filmForm.elements.is_published.addEventListener("change", (event) => {
    if (!filmForm.elements.film_id.value) document.getElementById("film-submit").textContent = event.target.value === "true" ? "Enregistrer et publier" : "Enregistrer le brouillon";
  });
  filmForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!filmForm.reportValidity()) return;
    const button = document.getElementById("film-submit");
    const id = filmForm.elements.film_id.value;
    const formData = new FormData(filmForm);
    formData.set("duration_min", String(Number(formData.get("duration_min"))));
    formData.set("release_year", String(Number(formData.get("release_year") || 0)));
    button.disabled = true;
    button.textContent = "Enregistrement…";
    filmStatus.textContent = "";
    try {
      await api(id ? `/api/admin/films/${id}` : "/api/admin/films", {method: id ? "PUT" : "POST", body: formData});
      resetFilmForm();
      filmStatus.textContent = "Film enregistré avec succès.";
      showError();
      await loadFilms();
    } catch (error) { filmStatus.textContent = error.message; }
    finally {
      button.disabled = false;
      if (!filmForm.elements.film_id.value) button.textContent = filmForm.elements.is_published.value === "true" ? "Enregistrer et publier" : "Enregistrer le brouillon";
    }
  });
  document.getElementById("new-film").addEventListener("click", () => { resetFilmForm(); filmForm.scrollIntoView({behavior: "smooth"}); filmForm.elements.title.focus({preventScroll: true}); });
  document.getElementById("film-cancel").addEventListener("click", resetFilmForm);

  function bindForm(formId, path, reload) {
    document.getElementById(formId).addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!event.currentTarget.reportValidity()) return;
      const form = event.currentTarget;
      const button = form.querySelector('[type="submit"]');
      const data = Object.fromEntries(new FormData(form).entries());
      for (const key of ["rows", "cols", "film_id", "room_id"]) if (data[key]) data[key] = Number(data[key]);
      if (data.price) data.price = Number(data.price);
      if (data.rows && data.cols) data.capacity = data.rows * data.cols;
      button.disabled = true;
      try { await api(path, {method: "POST", body: JSON.stringify(data)}); showError(); form.reset(); await reload(); }
      catch (error) { showError(error.message); }
      finally { button.disabled = false; }
    });
  }

  const loaders = {
    stats: loadStats,
    films: loadFilms,
    rooms: loadRooms,
    screenings: async () => { await loadFilms(); await loadRooms(); await loadScreenings(); },
    bookings: loadBookings,
  };
  document.querySelectorAll(".admin-tabs [data-tab]").forEach((tabButton) => {
    tabButton.addEventListener("click", async () => {
      document.querySelectorAll(".admin-tabs [data-tab]").forEach((button) => {
        button.classList.toggle("active", button === tabButton);
        button.setAttribute("aria-selected", String(button === tabButton));
      });
      document.querySelectorAll(".admin-panel").forEach((panel) => { panel.hidden = panel.id !== tabButton.getAttribute("aria-controls"); });
      try { await loaders[tabButton.dataset.tab](); showError(); }
      catch (error) { showError(error.message); }
    });
    tabButton.addEventListener("keydown", (event) => {
      const tabs = [...document.querySelectorAll(".admin-tabs [data-tab]")];
      const current = tabs.indexOf(tabButton);
      let next = null;
      if (event.key === "ArrowRight") next = (current + 1) % tabs.length;
      if (event.key === "ArrowLeft") next = (current - 1 + tabs.length) % tabs.length;
      if (event.key === "Home") next = 0;
      if (event.key === "End") next = tabs.length - 1;
      if (next !== null) {
        event.preventDefault();
        tabs[next].focus();
        tabs[next].click();
      }
    });
  });
  bindForm("room-form", "/api/admin/rooms", loadRooms);
  bindForm("screening-form", "/api/admin/screenings", loadScreenings);
  loadStats().catch((error) => showError(error.message));
})();
