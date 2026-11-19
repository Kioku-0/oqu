/* =========================================================================
   Электронная библиотека Коркыт ата — логика одностраничного интерфейса (SPA).
   Чистый JavaScript без сборщиков. Общается с REST API (см. /docs).
   ========================================================================= */
"use strict";

const API = "/api";

const state = {
    token: localStorage.getItem("token") || null,
    refresh: localStorage.getItem("refresh") || null,
    user: null,
    lang: localStorage.getItem("lang") || "ru",
    t: {},
    catalog: { query: "", author: "", year: "", genre: "", language: "",
               sort: "title", order: "asc", page: 1, mode: "grid" },
};

/* ---------- Утилиты ---------- */
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const tr = (key) => state.t[key] || key;

function toast(message, type = "info") {
    const el = document.createElement("div");
    el.className = `toast ${type}`;
    el.textContent = message;
    $("#toasts").appendChild(el);
    setTimeout(() => el.remove(), 3500);
}

/* ---------- Работа с API ---------- */
async function api(path, { method = "GET", body = null, auth = false } = {}) {
    const headers = {};
    if (body) headers["Content-Type"] = "application/json";
    if (auth && state.token) headers["Authorization"] = `Bearer ${state.token}`;
    let res = await fetch(API + path, {
        method, headers, body: body ? JSON.stringify(body) : null,
    });
    // Автоматическое обновление просроченного токена доступа.
    if (res.status === 401 && auth && state.refresh) {
        if (await refreshToken()) {
            headers["Authorization"] = `Bearer ${state.token}`;
            res = await fetch(API + path, {
                method, headers, body: body ? JSON.stringify(body) : null,
            });
        }
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || tr("error_generic"));
    return data;
}

async function refreshToken() {
    try {
        const data = await fetch(API + "/auth/refresh", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ refresh_token: state.refresh }),
        }).then((r) => r.ok ? r.json() : Promise.reject());
        setTokens(data.access_token, data.refresh_token);
        return true;
    } catch { logout(false); return false; }
}

function setTokens(access, refresh) {
    state.token = access; state.refresh = refresh;
    localStorage.setItem("token", access);
    localStorage.setItem("refresh", refresh);
}

/* ---------- Переводы (i18n) ---------- */
async function loadLang(lang) {
    state.lang = lang;
    localStorage.setItem("lang", lang);
    document.documentElement.lang = lang;
    try { state.t = await api(`/i18n/${lang}`); } catch { state.t = {}; }
    applyI18n();
    $("#lang-select").value = lang;
    if (state.user && state.token) api("/me/language",
        { method: "PUT", body: { language: lang }, auth: true }).catch(() => {});
    render();
}

function applyI18n() {
    $$("[data-i18n]").forEach((el) => { el.textContent = tr(el.dataset.i18n); });
    $$("[data-i18n-ph]").forEach((el) => { el.placeholder = tr(el.dataset.i18nPh); });
}

/* ---------- Аутентификация ---------- */
async function loadMe() {
    if (!state.token) { state.user = null; return; }
    try { state.user = await api("/auth/me", { auth: true }); }
    catch { state.user = null; }
    renderAuthArea();
}

function renderAuthArea() {
    const area = $("#auth-area");
    if (state.user) {
        const roleName = tr("role_" + state.user.role);
        area.innerHTML =
            `<span class="btn btn-ghost btn-sm">${esc(state.user.display_name)} · ${esc(roleName)}</span>
             <button class="btn btn-sm" id="logout-btn" data-i18n="nav_logout">Выйти</button>`;
        $("#logout-btn").onclick = () => logout(true);
    } else {
        area.innerHTML =
            `<button class="btn btn-primary btn-sm" id="login-open" data-i18n="nav_login">Войти</button>`;
        $("#login-open").onclick = () => openAuth("login");
    }
    applyI18n();
    updateVisibility();
}

function updateVisibility() {
    const canAdmin = state.user &&
        ["owner", "moderator", "editor"].includes(state.user.role);
    $$("[data-auth]").forEach((el) => el.classList.toggle("hidden", !state.user));
    $$('[data-perm="admin"]').forEach((el) => el.classList.toggle("hidden", !canAdmin));
}

function openAuth(tab) {
    $("#auth-modal").classList.add("open");
    switchAuthTab(tab);
}
function switchAuthTab(tab) {
    $$("[data-authtab]").forEach((b) =>
        b.classList.toggle("active", b.dataset.authtab === tab));
    $$("[data-register]").forEach((el) =>
        el.classList.toggle("hidden", tab !== "register"));
    $("#auth-form").dataset.mode = tab;
    const btn = $("#auth-submit");
    btn.textContent = tab === "login" ? tr("nav_login") : tr("nav_register");
}

async function submitAuth(e) {
    e.preventDefault();
    const form = e.target;
    const mode = form.dataset.mode || "login";
    const fd = Object.fromEntries(new FormData(form));
    try {
        if (mode === "register") {
            await api("/auth/register", { method: "POST", body: {
                username: fd.username, email: fd.email,
                password: fd.password, language: state.lang } });
            toast(tr("nav_register") + " ✓", "success");
        }
        const tokens = await api("/auth/login", { method: "POST",
            body: { username: fd.username, password: fd.password } });
        setTokens(tokens.access_token, tokens.refresh_token);
        await loadMe();
        $("#auth-modal").classList.remove("open");
        toast(tr("login_success"), "success");
        render();
    } catch (err) { toast(err.message, "error"); }
}

function logout(notify) {
    state.token = state.refresh = state.user = null;
    localStorage.removeItem("token");
    localStorage.removeItem("refresh");
    renderAuthArea();
    if (notify) toast(tr("logout_success"));
    location.hash = "#/catalog";
    render();
}

/* ---------- Маршрутизация ---------- */
function render() {
    const hash = location.hash || "#/catalog";
    const [route, param] = hash.slice(2).split("/");
    $$("#nav a").forEach((a) =>
        a.classList.toggle("active", a.getAttribute("href") === `#/${route}`));
    const views = {
        catalog: viewCatalog, book: () => viewBook(param),
        read: () => viewReader(param), shelf: viewShelf,
        stats: viewStats, admin: viewAdmin,
    };
    (views[route] || viewCatalog)();
}

/* ---------- Представление: Каталог ---------- */
async function viewCatalog() {
    const c = state.catalog;
    const app = $("#app");
    app.innerHTML = `
        <div class="toolbar">
            <input id="f-author" placeholder="${tr("filter_author")}" value="${esc(c.author)}">
            <input id="f-year" type="number" placeholder="${tr("filter_year")}" value="${esc(c.year)}" style="width:110px">
            <select id="f-sort">
                <option value="title">${tr("sort_title")}</option>
                <option value="author">${tr("sort_author")}</option>
                <option value="year">${tr("sort_year")}</option>
                <option value="created_at">${tr("sort_newest")}</option>
            </select>
            <select id="f-order">
                <option value="asc">A→Z</option><option value="desc">Z→A</option>
            </select>
            <div class="spacer"></div>
            <button class="btn btn-sm" id="mode-toggle">
                ${c.mode === "grid" ? "📚 " + tr("reader_mode_shelf") : "▦ " + tr("reader_mode_text")}
            </button>
            <button class="btn btn-primary btn-sm hidden" id="add-book-btn" data-perm2="book.add">
                + ${tr("btn_add_book")}
            </button>
        </div>
        <div id="catalog-body"><div class="empty">…</div></div>`;

    $("#f-sort").value = c.sort; $("#f-order").value = c.order;
    $("#f-author").oninput = (e) => { c.author = e.target.value; c.page = 1; debounced(); };
    $("#f-year").oninput = (e) => { c.year = e.target.value; c.page = 1; debounced(); };
    $("#f-sort").onchange = (e) => { c.sort = e.target.value; loadCatalog(); };
    $("#f-order").onchange = (e) => { c.order = e.target.value; loadCatalog(); };
    $("#mode-toggle").onclick = () => { c.mode = c.mode === "grid" ? "shelf" : "grid"; viewCatalog(); };

    if (state.user && ["owner", "editor", "author"].includes(state.user.role)) {
        const ab = $("#add-book-btn"); ab.classList.remove("hidden");
        ab.onclick = openAddBook;
    }
    loadCatalog();
}

let _debounce;
function debounced() { clearTimeout(_debounce); _debounce = setTimeout(loadCatalog, 350); }

async function loadCatalog() {
    const c = state.catalog;
    const params = new URLSearchParams({
        query: c.query, author: c.author, genre: c.genre, language: c.language,
        sort: c.sort, order: c.order, page: c.page, page_size: 12,
    });
    if (c.year) params.set("year", c.year);
    let data;
    try { data = await api(`/books?${params}`); }
    catch (e) { $("#catalog-body").innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
    const body = $("#catalog-body");
    if (!data.items.length) { body.innerHTML = `<div class="empty">${tr("empty_catalog")}</div>`; return; }
    body.innerHTML = c.mode === "grid" ? gridHtml(data.items) : shelfHtml(data.items);
    body.insertAdjacentHTML("beforeend", paginationHtml(data));
    bindCatalogEvents();
}

function coverStyle(b) {
    const c1 = b.cover_color || "#4f46e5";
    return `--c1:${c1};--c2:${c1}99;`;
}

function gridHtml(items) {
    return `<div class="grid">` + items.map((b) => `
        <div class="book-card">
            <div class="cover" style="${coverStyle(b)}">
                <span class="badge ${b.is_paid ? "badge-paid" : "badge-free"}">
                    ${b.is_paid ? tr("paid_badge") : tr("free_badge")}</span>
                <span class="cover-title">${esc(b.title)}</span>
            </div>
            <div class="card-body">
                <span class="card-author">${esc(b.author)}</span>
                <span class="card-meta">${b.year || ""} · ${esc(b.genre)} · ${b.language.toUpperCase()}</span>
                <div class="card-actions">
                    <a class="btn btn-primary btn-sm" href="#/read/${b.id}">${tr("btn_read")}</a>
                    <a class="btn btn-sm" href="#/book/${b.id}">${tr("btn_details")}</a>
                </div>
            </div>
        </div>`).join("") + `</div>`;
}

function shelfHtml(items) {
    // Книги как разноцветные корешки на деревянной полке.
    const spines = items.map((b) => {
        const h = 150 + (b.title.length % 6) * 10;
        return `<div class="spine" style="--c1:${b.cover_color};--c2:${b.cover_color}aa;--h:${h}px"
                     data-id="${b.id}" title="${esc(b.title)}">${esc(b.title)}</div>`;
    }).join("");
    return `<div class="bookshelf"><div class="shelf-row">
                <div class="shelf-books">${spines}</div>
                <div class="shelf-plank"></div>
            </div></div>`;
}

function paginationHtml(d) {
    return `<div class="pagination">
        <button class="btn btn-sm" ${d.page <= 1 ? "disabled" : ""} data-page="${d.page - 1}">← ${tr("page_prev")}</button>
        <span class="page-info">${d.page} / ${d.pages || 1}</span>
        <button class="btn btn-sm" ${d.page >= d.pages ? "disabled" : ""} data-page="${d.page + 1}">${tr("page_next")} →</button>
    </div>`;
}

function bindCatalogEvents() {
    $$("[data-page]").forEach((b) => b.onclick = () => {
        state.catalog.page = +b.dataset.page; loadCatalog();
        window.scrollTo({ top: 0, behavior: "smooth" });
    });
    $$(".spine").forEach((sp) => sp.onclick = () => {
        sp.classList.add("pulled");
        setTimeout(() => { location.hash = `#/book/${sp.dataset.id}`; }, 400);
    });
}

/* ---------- Представление: карточка книги ---------- */
async function viewBook(id) {
    const app = $("#app");
    let b, comments;
    try {
        b = await api(`/books/${id}`);
        comments = await api(`/books/${id}/comments`);
    } catch (e) { app.innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
    const canModerate = state.user &&
        ["owner", "editor", "moderator"].includes(state.user.role);
    app.innerHTML = `
        <div class="detail">
            <div class="cover" style="${coverStyle(b)}">
                <span class="cover-title">${esc(b.title)}</span>
            </div>
            <div>
                <h1>${esc(b.title)}</h1>
                <div class="meta-row">${esc(b.author)} · ${b.year || ""} ·
                    ${esc(b.genre)} · ${b.language.toUpperCase()} ·
                    <b>${b.is_paid ? tr("paid_badge") : tr("free_badge")}</b></div>
                <p style="margin-bottom:18px">${esc(b.description)}</p>
                <div style="display:flex;gap:10px;flex-wrap:wrap">
                    <a class="btn btn-primary" href="#/read/${b.id}">${tr("btn_read")}</a>
                    ${state.user ? shelfButtonsHtml(b.id) : ""}
                    ${state.user && ["owner","editor"].includes(state.user.role)
                        ? `<button class="btn btn-danger" id="del-book">${tr("btn_delete")}</button>` : ""}
                </div>
                <h3 style="margin:26px 0 12px">${tr("comments_title")} (${comments.length})</h3>
                <div id="comments">${comments.map((c) => commentHtml(c, canModerate)).join("")}</div>
                ${state.user ? `
                <div class="field" style="margin-top:14px">
                    <textarea id="comment-text" rows="2" placeholder="${tr("label_comment")}"></textarea>
                    <button class="btn btn-primary btn-sm" id="send-comment" style="align-self:flex-start">
                        ${tr("btn_send")}</button>
                </div>` : ""}
            </div>
        </div>`;

    if ($("#del-book")) $("#del-book").onclick = async () => {
        try { await api(`/books/${id}`, { method: "DELETE", auth: true });
              toast("✓"); location.hash = "#/catalog"; }
        catch (e) { toast(e.message, "error"); }
    };
    if ($("#send-comment")) $("#send-comment").onclick = async () => {
        const text = $("#comment-text").value.trim();
        if (!text) return;
        try { await api(`/books/${id}/comments`, { method: "POST",
                   body: { text }, auth: true });
              viewBook(id); }
        catch (e) { toast(e.message, "error"); }
    };
    $$("[data-shelf]").forEach((btn) => btn.onclick = async () => {
        try { await api(`/me/shelf/${id}`, { method: "PUT",
                   body: { status: btn.dataset.shelf }, auth: true });
              toast("✓ " + btn.textContent, "success"); }
        catch (e) { toast(e.message, "error"); }
    });
    $$("[data-del-comment]").forEach((btn) => btn.onclick = async () => {
        try { await api(`/comments/${btn.dataset.delComment}`,
                   { method: "DELETE", auth: true }); viewBook(id); }
        catch (e) { toast(e.message, "error"); }
    });
}

function shelfButtonsHtml(id) {
    const st = [["reading", "shelf_reading"], ["want", "shelf_want"],
                ["read", "shelf_read"], ["dropped", "shelf_dropped"]];
    return st.map(([s, k]) =>
        `<button class="btn btn-sm" data-shelf="${s}">${tr(k)}</button>`).join("");
}

function commentHtml(c, canModerate) {
    const badge = c.badge
        ? `<span class="role-badge role-${badgeClass(c.badge)}">${esc(c.badge)}</span>` : "";
    const del = (canModerate || (state.user && state.user.username === c.username))
        ? `<button class="btn btn-sm btn-ghost" data-del-comment="${c.id}">✕</button>` : "";
    return `<div class="comment">
        <div class="comment-head"><b>${esc(c.username)}</b>${badge}
            <span class="comment-time">${esc(c.created_at)}</span>${del}</div>
        <div>${esc(c.text)}</div></div>`;
}
function badgeClass(badge) {
    const map = { "Главный разработчик": "owner", "Редактор": "editor",
                  "Автор": "author", "Модератор": "moderator" };
    return map[badge] || "owner";
}

/* ---------- Представление: читалка ---------- */
async function viewReader(id) {
    const app = $("#app");
    let b;
    try { b = await api(`/books/${id}/read`, { auth: !!state.token }); }
    catch (e) { app.innerHTML = `<div class="empty">🔒 ${esc(e.message)}</div>`; return; }
    const paras = (b.content || "").split("\n\n").map((p) => `<p>${esc(p)}</p>`).join("");
    app.innerHTML = `
        <div class="reader-controls">
            <a class="btn btn-sm" href="#/book/${id}">←</a>
            <button class="btn btn-sm" id="font-dec">A−</button>
            <button class="btn btn-sm" id="font-inc">A+</button>
            <span class="page-info">${esc(b.title)} — ${esc(b.author)}</span>
        </div>
        <article class="reader" id="reader">${paras}</article>`;

    let size = 18;
    $("#font-inc").onclick = () => { size = Math.min(28, size + 2); $("#reader").style.setProperty("--reader-size", size + "px"); };
    $("#font-dec").onclick = () => { size = Math.max(14, size - 2); $("#reader").style.setProperty("--reader-size", size + "px"); };

    // Продолжить с сохранённой позиции (прокрутка).
    if (b.position) {
        setTimeout(() => window.scrollTo({ top: b.position, behavior: "smooth" }), 150);
        toast(tr("btn_continue"));
    }
    // Сохранение позиции при прокрутке (для авторизованных).
    if (state.user) {
        let saveTimer;
        window.onscroll = () => {
            clearTimeout(saveTimer);
            saveTimer = setTimeout(() => {
                api(`/me/progress/${id}`, { method: "PUT",
                    body: { position: Math.round(window.scrollY) }, auth: true })
                    .catch(() => {});
            }, 800);
        };
    }
}

/* ---------- Представление: моя полка ---------- */
async function viewShelf() {
    if (!state.user) { openAuth("login"); return; }
    const app = $("#app");
    const statuses = [["reading", "shelf_reading"], ["want", "shelf_want"],
                      ["read", "shelf_read"], ["dropped", "shelf_dropped"]];
    app.innerHTML = `<h2 class="section-title">${tr("nav_shelf")}</h2>
        <div class="tabs" id="shelf-tabs">
            ${statuses.map(([s, k], i) => `<button class="tab ${i === 0 ? "active" : ""}" data-s="${s}">${tr(k)}</button>`).join("")}
        </div><div id="shelf-body"></div>`;
    const load = async (status) => {
        let rows;
        try { rows = await api(`/me/shelf?status=${status}`, { auth: true }); }
        catch (e) { $("#shelf-body").innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
        $("#shelf-body").innerHTML = rows.length ? gridHtml(rows)
            : `<div class="empty">${tr("empty_catalog")}</div>`;
        bindCatalogEvents();
    };
    $$("#shelf-tabs .tab").forEach((t) => t.onclick = () => {
        $$("#shelf-tabs .tab").forEach((x) => x.classList.remove("active"));
        t.classList.add("active"); load(t.dataset.s);
    });
    load("reading");
}

/* ---------- Представление: статистика ---------- */
async function viewStats() {
    const app = $("#app");
    let data;
    try { data = await api("/stats/reading"); }
    catch (e) { app.innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
    const medals = ["🥇", "🥈", "🥉"];
    const rows = data.leaderboard.map((e, i) => `
        <tr><td><span class="rank-medal">${medals[i] || (i + 1)}</span></td>
            <td>${esc(e.username)}${e.badge ? ` <span class="role-badge role-owner">${esc(e.badge)}</span>` : ""}</td>
            <td>${esc(tr("role_" + e.role))}</td>
            <td><b>${esc(String(e.read_count))}</b></td></tr>`).join("");
    app.innerHTML = `<h2 class="section-title">${tr("stats_title")}</h2>
        <div class="stat-card" style="margin-bottom:20px">
            <div style="font-size:14px;color:var(--text-dim)">${tr("stats_total")}</div>
            <div style="font-size:34px;font-weight:800">${data.total_read}</div>
        </div>
        <div class="stat-card"><table class="leaderboard">
            <tr><th>#</th><th>${tr("label_username")}</th><th>Роль</th><th>${tr("shelf_read")}</th></tr>
            ${rows}</table></div>`;
}

/* ---------- Представление: админ-панель ---------- */
async function viewAdmin() {
    if (!state.user || !["owner", "moderator", "editor"].includes(state.user.role)) {
        $("#app").innerHTML = `<div class="empty">⛔ ${tr("error_generic")}</div>`; return;
    }
    const app = $("#app");
    app.innerHTML = `<h2 class="section-title">${tr("nav_admin")}</h2>
        <div class="tabs" id="admin-tabs">
            <button class="tab active" data-a="users">Пользователи</button>
            <button class="tab" data-a="log">Журнал действий</button>
            <button class="tab" data-a="unban">Заявки на разбан</button>
        </div><div id="admin-body"></div>`;
    const tabs = { users: adminUsers, log: adminLog, unban: adminUnban };
    $$("#admin-tabs .tab").forEach((t) => t.onclick = () => {
        $$("#admin-tabs .tab").forEach((x) => x.classList.remove("active"));
        t.classList.add("active"); (tabs[t.dataset.a] || adminUsers)();
    });
    adminUsers();
}

async function adminUsers() {
    let users;
    try { users = await api("/admin/users", { auth: true }); }
    catch (e) { $("#admin-body").innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
    const isOwner = state.user.role === "owner";
    $("#admin-body").innerHTML = `<table class="table">
        <tr><th>ID</th><th>Логин</th><th>Роль</th><th>Студент</th><th>Статус</th><th></th></tr>
        ${users.map((u) => `<tr>
            <td>${u.id}</td><td>${esc(u.username)}</td>
            <td>${esc(tr("role_" + u.role))}</td>
            <td>${u.is_student ? "✓" : "—"}</td>
            <td>${u.banned ? "🚫 бан" : "✅"}</td>
            <td>
                ${isOwner ? `<button class="btn btn-sm" data-role="${u.id}">Роль</button>` : ""}
                <button class="btn btn-sm" data-verify="${u.id}">Студент</button>
                ${u.banned ? `<button class="btn btn-sm" data-unban="${u.id}">Разбан</button>`
                           : `<button class="btn btn-sm btn-danger" data-ban="${u.id}">Бан</button>`}
            </td></tr>`).join("")}</table>`;

    $$("[data-ban]").forEach((b) => b.onclick = () => promptBan(b.dataset.ban));
    $$("[data-unban]").forEach((b) => b.onclick = async () => {
        try { await api(`/admin/users/${b.dataset.unban}/unban`, { method: "POST", auth: true });
              toast("✓"); adminUsers(); } catch (e) { toast(e.message, "error"); }
    });
    $$("[data-verify]").forEach((b) => b.onclick = async () => {
        try { await api(`/admin/users/${b.dataset.verify}/verify-student`, { method: "POST", auth: true });
              toast("✓"); adminUsers(); } catch (e) { toast(e.message, "error"); }
    });
    $$("[data-role]").forEach((b) => b.onclick = () => promptRole(b.dataset.role));
}

function promptBan(id) {
    openModal(`<h2>Бан пользователя #${id}</h2>
        <div class="field"><label>Причина</label><input id="ban-reason"></div>
        <div class="field"><label>Минуты (пусто = навсегда)</label><input id="ban-min" type="number"></div>
        <button class="btn btn-danger" id="ban-go" style="width:100%">Забанить</button>`);
    $("#ban-go").onclick = async () => {
        const reason = $("#ban-reason").value.trim();
        const min = $("#ban-min").value;
        try { await api(`/admin/users/${id}/ban`, { method: "POST", auth: true,
                  body: { reason, minutes: min ? +min : null } });
              closeModal(); toast("✓"); adminUsers(); }
        catch (e) { toast(e.message, "error"); }
    };
}

function promptRole(id) {
    openModal(`<h2>Роль пользователя #${id}</h2>
        <div class="field"><label>Новая роль</label>
            <select id="role-sel">
                <option value="user">Пользователь</option>
                <option value="student">Студент</option>
                <option value="author">Автор</option>
                <option value="moderator">Модератор</option>
                <option value="editor">Редактор</option>
            </select></div>
        <button class="btn btn-primary" id="role-go" style="width:100%">Назначить</button>`);
    $("#role-go").onclick = async () => {
        try { await api(`/admin/users/${id}/role`, { method: "POST", auth: true,
                  body: { role: $("#role-sel").value } });
              closeModal(); toast("✓"); adminUsers(); }
        catch (e) { toast(e.message, "error"); }
    };
}

async function adminLog() {
    let data;
    try { data = await api("/admin/log?page=1&page_size=50", { auth: true }); }
    catch (e) { $("#admin-body").innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
    $("#admin-body").innerHTML = `<table class="table">
        <tr><th>Время</th><th>Пользователь</th><th>Действие</th><th>Детали</th><th>IP</th></tr>
        ${data.items.map((l) => `<tr>
            <td>${esc(l.created_at)}</td><td>${l.user_id ?? "—"}</td>
            <td>${esc(l.action)}</td><td>${esc(l.details)}</td><td>${esc(l.ip)}</td></tr>`).join("")}
    </table>`;
}

async function adminUnban() {
    let rows;
    try { rows = await api("/admin/unban-requests", { auth: true }); }
    catch (e) { $("#admin-body").innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
    if (!rows.length) { $("#admin-body").innerHTML = `<div class="empty">—</div>`; return; }
    $("#admin-body").innerHTML = `<table class="table">
        <tr><th>ID</th><th>Пользователь</th><th>Текст</th><th></th></tr>
        ${rows.map((r) => `<tr><td>${r.id}</td><td>${esc(r.username)}</td>
            <td>${esc(r.text)}</td>
            <td><button class="btn btn-sm" data-ok="${r.id}">Одобрить</button>
                <button class="btn btn-sm btn-danger" data-no="${r.id}">Отклонить</button></td></tr>`).join("")}
    </table>`;
    const resolve = async (id, approve) => {
        try { await api(`/admin/unban-requests/${id}/resolve`, { method: "POST",
                  auth: true, body: { approve } }); adminUnban(); }
        catch (e) { toast(e.message, "error"); }
    };
    $$("[data-ok]").forEach((b) => b.onclick = () => resolve(b.dataset.ok, true));
    $$("[data-no]").forEach((b) => b.onclick = () => resolve(b.dataset.no, false));
}

function openAddBook() {
    openModal(`<h2>${tr("btn_add_book")}</h2>
        <div class="field"><label>Название</label><input id="nb-title"></div>
        <div class="field"><label>Автор</label><input id="nb-author"></div>
        <div class="field"><label>Год</label><input id="nb-year" type="number"></div>
        <div class="field"><label>Жанр</label><input id="nb-genre"></div>
        <div class="field"><label>Язык</label><select id="nb-lang">
            <option value="ru">Рус</option><option value="kk">Қаз</option><option value="en">Eng</option></select></div>
        <div class="field"><label>Описание</label><textarea id="nb-desc" rows="2"></textarea></div>
        <div class="field"><label>Текст книги</label><textarea id="nb-content" rows="4"></textarea></div>
        <div class="field"><label>Цвет обложки</label><input id="nb-color" type="color" value="#4f46e5"></div>
        <button class="btn btn-primary" id="nb-go" style="width:100%">${tr("btn_save")}</button>`);
    $("#nb-go").onclick = async () => {
        try {
            await api("/books", { method: "POST", auth: true, body: {
                title: $("#nb-title").value, author: $("#nb-author").value,
                year: $("#nb-year").value ? +$("#nb-year").value : null,
                genre: $("#nb-genre").value, language: $("#nb-lang").value,
                description: $("#nb-desc").value, content: $("#nb-content").value,
                cover_color: $("#nb-color").value } });
            closeModal(); toast("✓", "success"); loadCatalog();
        } catch (e) { toast(e.message, "error"); }
    };
}

/* ---------- Модальные окна общего назначения ---------- */
function openModal(html) {
    $("#generic-modal-content").innerHTML = html;
    $("#generic-modal").classList.add("open");
}
function closeModal() { $("#generic-modal").classList.remove("open"); }

/* ---------- Инициализация ---------- */
function init() {
    $("#lang-select").onchange = (e) => loadLang(e.target.value);
    $("#global-search").oninput = (e) => {
        state.catalog.query = e.target.value; state.catalog.page = 1;
        if ((location.hash || "#/catalog").startsWith("#/catalog")) debounced();
        else location.hash = "#/catalog";
    };
    $("#theme-toggle").onclick = () => {
        const cur = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
        document.documentElement.dataset.theme = cur;
        localStorage.setItem("theme", cur);
        $("#theme-toggle").textContent = cur === "dark" ? "☀️" : "🌙";
    };
    $$("[data-authtab]").forEach((b) => b.onclick = () => switchAuthTab(b.dataset.authtab));
    $("#auth-form").onsubmit = submitAuth;
    $$(".modal-overlay").forEach((ov) => ov.onclick = (e) => {
        if (e.target === ov) ov.classList.remove("open");
    });
    const savedTheme = localStorage.getItem("theme");
    if (savedTheme) { document.documentElement.dataset.theme = savedTheme;
        $("#theme-toggle").textContent = savedTheme === "dark" ? "☀️" : "🌙"; }
    window.addEventListener("hashchange", render);
}

(async function main() {
    init();
    await loadLang(state.lang);
    await loadMe();
    render();
})();
