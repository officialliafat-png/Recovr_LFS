const views = document.querySelectorAll("[data-view]");
const loginForm = document.querySelector("#login-form");
const itemForm = document.querySelector("#item-form");
const searchForm = document.querySelector("#search-form");
const landingItemsEl = document.querySelector("#landing-items");
const landingStatus = document.querySelector("#landing-status");
const itemsEl = document.querySelector("#items");
const myItemsEl = document.querySelector("#my-items");
const myStatusEl = document.querySelector("#my-status");
const statusEl = document.querySelector("#status");
const filters = document.querySelectorAll(".filter");
const sessionName = document.querySelector("#session-name");
const authStatus = document.querySelector("#auth-status");
const authSubmit = document.querySelector("#auth-submit");
const authCopy = document.querySelector("#auth-copy");
const authEyebrow = document.querySelector("#auth-eyebrow");
const authModeButtons = document.querySelectorAll("[data-auth-mode]");
const appPageLinks = document.querySelectorAll("[data-app-page-link]");
const appPages = document.querySelectorAll("[data-app-page]");
const signupOnlyFields = document.querySelectorAll(".signup-only");

let activeKind = "";
let activeAppAnchor = "#browse";
let activeAppPage = "board";
let authMode = "login";
let currentUser = null;
let searchParams = new URLSearchParams();
let pendingLandingSearch = "";

function setView(name) {
  views.forEach((view) => {
    view.classList.toggle("hidden", view.dataset.view !== name);
  });

  if (name === "app") {
    sessionName.textContent = currentUser
      ? `Signed in as ${currentUser.display_name}`
      : "Signed in";
    setAppPage(activeAppPage, activeAppAnchor);
  }

  if (name === "landing") {
    updateSessionLabels();
    loadLandingItems().catch((error) => {
      landingStatus.textContent = error.message;
      landingStatus.className = "form-note error";
    });
  }
}

function setAuthMode(mode) {
  authMode = mode;
  const isSignup = mode === "signup";
  authModeButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.authMode === mode);
  });
  signupOnlyFields.forEach((field) => {
    field.classList.toggle("hidden", !isSignup);
    const input = field.querySelector("input");
    if (input) input.required = isSignup;
  });

  loginForm.password.autocomplete = isSignup ? "new-password" : "current-password";
  authEyebrow.textContent = isSignup ? "New account" : "Secure access";
  authCopy.textContent = isSignup
    ? "Create an account so Recovr can attach private ownership details to your reports."
    : "Log in with your Recovr account. Your session is verified by the server.";
  authSubmit.textContent = isSignup ? "Create account" : "Log in";
  setAuthStatus("");
}

function firstName() {
  return String(currentUser?.display_name || "there").trim().split(/\s+/)[0] || "there";
}

function updateSessionLabels(scope = document) {
  scope.querySelectorAll("[data-session-label]").forEach((button) => {
    if (!currentUser) {
      button.textContent = button.dataset.guestLabel;
      return;
    }

    if (button.dataset.sessionLabel === "nav") {
      button.textContent = `Hi, ${firstName()}`;
    } else if (button.dataset.sessionLabel === "match") {
      button.textContent = "Open app to match";
    } else {
      button.textContent = "Open app";
    }
  });
}

function setAppPage(pageName, activeHref = null) {
  activeAppPage = pageName;
  activeAppAnchor = activeHref || (pageName === "mine" ? "#mine" : "#browse");
  appPages.forEach((page) => {
    page.classList.toggle("hidden", page.dataset.appPage !== pageName);
  });
  appPageLinks.forEach((link) => {
    link.classList.toggle(
      "active",
      link.dataset.appPageLink === pageName && link.getAttribute("href") === activeAppAnchor,
    );
  });

  if (pageName === "board") {
    loadItems().catch((error) => setStatus(error.message, true));
  }
  if (pageName === "mine") {
    loadMyItems().catch((error) => setMyStatus(error.message, true));
  }
}

function setAuthStatus(message, error = false) {
  authStatus.textContent = message;
  authStatus.className = error ? "form-note error" : "form-note";
}

function requireSession(destination = "app") {
  if (currentUser) {
    setView(destination);
    return true;
  }

  setView("auth");
  return false;
}

function setStatus(message, error = false) {
  statusEl.textContent = message;
  statusEl.className = error ? "error" : "";
}

function setMyStatus(message, error = false) {
  myStatusEl.textContent = message;
  myStatusEl.className = error ? "error" : "";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    credentials: "same-origin",
    ...options,
  });
  const payload = response.status === 204 ? null : await response.json();
  if (!response.ok) {
    throw new Error(payload?.detail || "Request failed");
  }
  return payload;
}

async function refreshSession() {
  try {
    const payload = await fetchJson("/api/auth/me");
    currentUser = payload.user;
    updateSessionLabels();
    return currentUser;
  } catch {
    currentUser = null;
    updateSessionLabels();
    return null;
  }
}

async function loadItems() {
  setStatus("Loading reports...");
  const params = new URLSearchParams(searchParams);
  if (activeKind) params.set("kind", activeKind);
  const query = params.toString() ? `?${params.toString()}` : "";
  const payload = await fetchJson(`/api/items${query}`);
  const items = payload.items;

  if (!items.length) {
    itemsEl.innerHTML = renderEmptyState();
    setStatus("No open reports yet.");
    return;
  }

  setStatus(`${items.length} open report${items.length === 1 ? "" : "s"}`);
  itemsEl.innerHTML = items.map(renderItem).join("");
  document.querySelectorAll("[data-match-id]").forEach((button) => {
    button.addEventListener("click", () => loadMatches(button.dataset.matchId));
  });
}

async function loadLandingItems() {
  landingStatus.textContent = "Loading recent reports...";
  landingStatus.className = "form-note";
  const payload = await fetchJson("/api/items?limit=6");
  const items = payload.items;

  if (!items.length) {
    landingStatus.textContent = "No open reports yet. Create an account to post the first one.";
    landingItemsEl.innerHTML = renderEmptyState();
    return;
  }

  landingStatus.textContent = `${items.length} recent open report${items.length === 1 ? "" : "s"}`;
  landingItemsEl.innerHTML = items.map(renderLandingItem).join("");
  wireLoginButtons(landingItemsEl);
  updateSessionLabels(landingItemsEl);
}

async function loadMyItems() {
  if (!currentUser) return;

  setMyStatus("Loading your posts...");
  const payload = await fetchJson("/api/items/mine");
  const items = payload.items;

  if (!items.length) {
    myItemsEl.innerHTML = renderManageEmptyState();
    setMyStatus("You have not posted anything yet.");
    return;
  }

  setMyStatus(`${items.length} post${items.length === 1 ? "" : "s"} on your account`);
  myItemsEl.innerHTML = items.map(renderManageItem).join("");
}

function renderEmptyState() {
  return `
    <article class="empty-state">
      <div class="sketch-scene mini">
        <span class="sketch-sun"></span>
        <span class="sketch-line a"></span>
        <span class="sketch-line b"></span>
        <span class="sketch-object"></span>
      </div>
      <h3>No entries on this page yet.</h3>
      <p class="small">Post a lost or found item and Recovr will start looking for visual matches.</p>
    </article>
  `;
}

function renderManageEmptyState() {
  return `
    <article class="empty-state">
      <h3>No posts yet.</h3>
      <p class="small">Use the Post item form above to create your first lost or found report.</p>
    </article>
  `;
}

function renderItemImage(item) {
  return item.image_url
    ? `<img src="${escapeHtml(item.image_url)}" alt="${escapeHtml(item.title)} photo" />`
    : `<div class="sketch-scene mini">
        <span class="sketch-sun"></span>
        <span class="sketch-line a"></span>
        <span class="sketch-line b"></span>
        <span class="sketch-object"></span>
      </div>`;
}

function categoryOptions(selectedCategory) {
  const categories = [
    ["electronics", "Electronics"],
    ["clothing", "Clothing"],
    ["id_cards", "ID/cards"],
    ["keys", "Keys"],
    ["bags", "Bags"],
    ["jewelry", "Jewelry"],
    ["other", "Other"],
  ];
  return categories
    .map(([value, label]) => `
      <option value="${value}" ${value === selectedCategory ? "selected" : ""}>${label}</option>
    `)
    .join("");
}

function renderLandingItem(item) {
  return `
    <article class="item-card landing-card" id="landing-item-${escapeHtml(item.id)}">
      <div class="thumb">${renderItemImage(item)}</div>
      <div class="meta">
        <span class="pill">${escapeHtml(item.kind)}</span>
        <span class="pill">${escapeHtml(item.category)}</span>
        <span class="pill">${escapeHtml(item.color)}</span>
      </div>
      <h3>${escapeHtml(item.title)}</h3>
      <p class="small">${escapeHtml(item.location)}</p>
      <p class="small"><strong>Date:</strong> ${escapeHtml(item.event_date || "not set")}</p>
      <button
        type="button"
        data-action="show-login"
        data-session-label="match"
        data-guest-label="Log in to match"
      >Log in to match</button>
    </article>
  `;
}

function renderManageItem(item) {
  return `
    <article class="manage-card" id="manage-${escapeHtml(item.id)}">
      <div>
        <div class="thumb">${renderItemImage(item)}</div>
        <div class="meta">
          <span class="pill">${escapeHtml(item.kind)}</span>
          <span class="pill">${escapeHtml(item.status)}</span>
          <span class="pill">${escapeHtml(item.category)}</span>
        </div>
      </div>
      <form class="manage-form" data-edit-id="${escapeHtml(item.id)}">
        <div class="two-column">
          <label>
            Type
            <select name="kind">
              <option value="lost" ${item.kind === "lost" ? "selected" : ""}>Lost item</option>
              <option value="found" ${item.kind === "found" ? "selected" : ""}>Found item</option>
            </select>
          </label>
          <label>
            Status
            <select name="status">
              <option value="open" ${item.status === "open" ? "selected" : ""}>Open</option>
              <option value="resolved" ${item.status === "resolved" ? "selected" : ""}>Resolved</option>
            </select>
          </label>
        </div>
        <label>
          Title
          <input name="title" value="${escapeHtml(item.title)}" required />
        </label>
        <div class="two-column">
          <label>
            Category
            <select name="category">${categoryOptions(item.category)}</select>
          </label>
          <label>
            Main color
            <input name="color" value="${escapeHtml(item.color)}" required />
          </label>
        </div>
        <label>
          Location
          <input name="location" value="${escapeHtml(item.location)}" required />
        </label>
        <div class="two-column">
          <label>
            Campus zone
            <input name="campus_zone" value="${escapeHtml(item.campus_zone || "other")}" required />
          </label>
          <label>
            Date lost/found
            <input name="event_date" type="date" value="${escapeHtml(item.event_date || "")}" required />
          </label>
        </div>
        <label>
          Details
          <textarea name="description" required>${escapeHtml(item.description)}</textarea>
        </label>
        <div class="manage-actions">
          <button type="submit">Save changes</button>
          <button type="button" data-delete-id="${escapeHtml(item.id)}" class="danger-button">Delete</button>
        </div>
      </form>
    </article>
  `;
}

function renderItem(item) {
  return `
    <article class="item-card" id="item-${escapeHtml(item.id)}">
      <div class="thumb">${renderItemImage(item)}</div>
      <div class="meta">
        <span class="pill">${escapeHtml(item.kind)}</span>
        <span class="pill">${escapeHtml(item.category)}</span>
        <span class="pill">${escapeHtml(item.color)}</span>
      </div>
      <h3>${escapeHtml(item.title)}</h3>
      <p class="small">${escapeHtml(item.description)}</p>
      <p class="small"><strong>Location:</strong> ${escapeHtml(item.location)}</p>
      <p class="small"><strong>Date:</strong> ${escapeHtml(item.event_date || "not set")}</p>
      <p class="small"><strong>Reporter:</strong> ${escapeHtml(item.owner_name || "Recovr user")}</p>
      <p class="small"><strong>Privacy:</strong> contact hidden until match confirmation</p>
      <button type="button" data-match-id="${escapeHtml(item.id)}">Find matches</button>
      <div class="match-list" data-match-results="${escapeHtml(item.id)}"></div>
    </article>
  `;
}

async function loadMatches(itemId) {
  const target = document.querySelector(`[data-match-results="${itemId}"]`);
  target.innerHTML = '<p class="small">Scoring images...</p>';

  try {
    const matches = await fetchJson(`/api/items/${itemId}/matches`);
    if (!matches.length) {
      target.innerHTML = '<p class="small">No confident image matches yet.</p>';
      return;
    }

    target.innerHTML = matches
      .map(({ item, score, explanation }) => `
        <div class="match">
          <strong>${escapeHtml(item.title)}</strong>
          <p class="small">${Math.round(score * 100)}% match - ${escapeHtml(explanation)}</p>
          <p class="small">${escapeHtml(item.location)} - contact hidden until confirmation</p>
        </div>
      `)
      .join("");
  } catch (error) {
    target.innerHTML = `<p class="small">${escapeHtml(error.message)}</p>`;
  }
}

function wireLoginButtons(scope = document) {
  scope.querySelectorAll("[data-action='show-login']").forEach((button) => {
    button.addEventListener("click", () => {
      if (currentUser) {
        setView("app");
        return;
      }
      setView("auth");
    });
  });
}

wireLoginButtons();

appPageLinks.forEach((link) => {
  link.addEventListener("click", (event) => {
    event.preventDefault();
    setAppPage(link.dataset.appPageLink, link.getAttribute("href"));
    const target = document.querySelector(link.getAttribute("href"));
    if (target && link.dataset.appPageLink === "board") {
      target.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  });
});

document.querySelectorAll("[data-action='show-landing']").forEach((button) => {
  button.addEventListener("click", () => setView("landing"));
});

authModeButtons.forEach((button) => {
  button.addEventListener("click", () => setAuthMode(button.dataset.authMode));
});

document.querySelectorAll("[data-action='logout']").forEach((button) => {
  button.addEventListener("click", async () => {
    try {
      await fetchJson("/api/auth/logout", { method: "POST" });
    } finally {
      currentUser = null;
      myItemsEl.innerHTML = "";
      updateSessionLabels();
      setView("landing");
    }
  });
});

document.querySelectorAll("[data-action='refresh-mine']").forEach((button) => {
  button.addEventListener("click", () => {
    loadMyItems().catch((error) => setMyStatus(error.message, true));
  });
});

document.querySelector("[data-action='hero-search']").addEventListener("submit", (event) => {
  event.preventDefault();
  pendingLandingSearch = new FormData(event.currentTarget).get("q") || "";
  requireSession();
});

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  setAuthStatus(authMode === "signup" ? "Creating account..." : "Checking credentials...");

  try {
    const endpoint = authMode === "signup" ? "/api/auth/signup" : "/api/auth/login";
    const payload = await fetchJson(endpoint, {
      method: "POST",
      body: new FormData(loginForm),
    });
    currentUser = payload.user;
    updateSessionLabels();

    if (pendingLandingSearch) {
      searchParams = new URLSearchParams({ q: pendingLandingSearch });
      searchForm.q.value = pendingLandingSearch;
      pendingLandingSearch = "";
    }

    loginForm.reset();
    setAuthMode("login");
    setView("app");
  } catch (error) {
    setAuthStatus(error.message, true);
  }
});

itemForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!requireSession()) return;
  setStatus("Saving report and checking for matches...");

  try {
    const payload = await fetchJson("/api/items", {
      method: "POST",
      body: new FormData(itemForm),
    });
    itemForm.reset();
    const count = payload.matches.length;
    setStatus(
      `Saved "${payload.item.title}" with ${count} immediate match${count === 1 ? "" : "es"}.`,
    );
    await loadItems();
    await loadMyItems();
  } catch (error) {
    setStatus(error.message, true);
  }
});

myItemsEl.addEventListener("submit", async (event) => {
  const form = event.target.closest("[data-edit-id]");
  if (!form) return;

  event.preventDefault();
  setMyStatus("Saving changes...");

  try {
    await fetchJson(`/api/items/${form.dataset.editId}`, {
      method: "PATCH",
      body: new FormData(form),
    });
    setMyStatus("Post updated.");
    await loadItems();
    await loadMyItems();
    await loadLandingItems();
  } catch (error) {
    setMyStatus(error.message, true);
  }
});

myItemsEl.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-delete-id]");
  if (!button) return;

  const confirmed = window.confirm("Delete this post from Recovr?");
  if (!confirmed) return;

  setMyStatus("Deleting post...");
  try {
    await fetchJson(`/api/items/${button.dataset.deleteId}`, {
      method: "DELETE",
    });
    setMyStatus("Post deleted.");
    await loadItems();
    await loadMyItems();
    await loadLandingItems();
  } catch (error) {
    setMyStatus(error.message, true);
  }
});

searchForm.addEventListener("submit", (event) => {
  event.preventDefault();
  searchParams = new URLSearchParams(new FormData(searchForm));
  for (const [key, value] of [...searchParams.entries()]) {
    if (!String(value).trim()) searchParams.delete(key);
  }
  loadItems().catch((error) => setStatus(error.message, true));
});

filters.forEach((button) => {
  button.addEventListener("click", () => {
    activeKind = button.dataset.kind;
    filters.forEach((filter) => filter.classList.remove("active"));
    button.classList.add("active");
    loadItems().catch((error) => setStatus(error.message, true));
  });
});

setAuthMode("login");
refreshSession().finally(() => setView("landing"));
