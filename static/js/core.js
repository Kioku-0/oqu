/* =====================================================================
   Оқу — ядро интерфейса: состояние, запросы к API, переводы, маршруты,
   шапка, окна, уведомления. Страницы описаны в views.js и admin.js.
   Сайт — одностраничный (SPA): сервер отдаёт один HTML, а разделы
   переключаются по адресу после «#», без перезагрузки страницы.
   ===================================================================== */
"use strict";

const Oqu = (window.Oqu = {
    version: document.documentElement.dataset.v || "dev",
    state: { user: null, lang: "ru", theme: "light", t: {}, fallback: {} },
    routes: [],
});

/* ---------- Мелкие помощники ------------------------------------------ */
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

/** Экранирование HTML: любые данные пользователей выводятся только через него
 *  (защита от XSS — внедрения чужого кода в страницу). */
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const icon = (name, cls = "") => `<svg class="i ${cls}" aria-hidden="true"><use href="#i-${name}"/></svg>`;

const store = {
    get(key, def = null) {
        try { const v = localStorage.getItem("oqu." + key); return v === null ? def : JSON.parse(v); }
        catch { return def; }
    },
    set(key, value) {
        try {
            if (value === null || value === undefined) localStorage.removeItem("oqu." + key);
            else localStorage.setItem("oqu." + key, JSON.stringify(value));
        } catch { /* приватный режим браузера — просто не запоминаем */ }
    },
};

function debounce(fn, ms) {
    let timer;
    return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), ms); };
}

/* ---------- Переводы ---------------------------------------------------- */
const LOCALES = { ru: "ru-RU", kk: "kk-KZ", ky: "ky-KG", en: "en-GB" };

/** Перевод по ключу с подстановкой {переменных}. Если ключа нет в выбранном
 *  языке — берётся русский (основной язык проекта). */
function t(key, vars) {
    let s = Oqu.state.t[key] ?? Oqu.state.fallback[key] ?? key;
    if (vars) for (const [k, v] of Object.entries(vars)) s = s.split(`{${k}}`).join(v);
    return s;
}

/** Склонение по числу: plural(5, "books") -> ключи books.one/few/many. */
function plural(n, key) {
    const rules = new Intl.PluralRules(LOCALES[Oqu.state.lang]);
    const form = rules.select(Number(n) || 0);
    const k = `${key}.${form}`;
    return t(Oqu.state.t[k] !== undefined || Oqu.state.fallback[k] !== undefined ? k : `${key}.other`, { n });
}

async function loadDict(lang) {
    const res = await fetch(`/static/i18n/${lang}.json?v=${Oqu.version}`);
    if (!res.ok) throw new Error("i18n " + lang);
    return res.json();
}

async function setLang(lang, { save = true } = {}) {
    if (!LOCALES[lang]) lang = "ru";
    if (!Object.keys(Oqu.state.fallback).length) Oqu.state.fallback = await loadDict("ru");
    Oqu.state.t = lang === "ru" ? Oqu.state.fallback : await loadDict(lang);
    Oqu.state.lang = lang;
    document.documentElement.lang = lang;
    store.set("lang", lang);
    if (save && Oqu.state.user) api("/api/me/language", { method: "PUT", body: { language: lang } }).catch(() => {});
    applyStaticI18n();
    renderChrome();
    if (!$("#notice").hidden) showStorageNotice();   // перевести и плашку
    if (save) Oqu.router.render();
}

/** Перевести статичные элементы разметки с атрибутами data-t*. */
function applyStaticI18n(root = document) {
    $$("[data-t]", root).forEach((el) => { el.textContent = t(el.dataset.t); });
    $$("[data-t-ph]", root).forEach((el) => { el.placeholder = t(el.dataset.tPh); });
    $$("[data-t-title]", root).forEach((el) => { el.title = t(el.dataset.tTitle); el.setAttribute("aria-label", t(el.dataset.tTitle)); });
}

/* ---------- Даты, числа ------------------------------------------------- */
/** Сервер хранит время в UTC («ГГГГ-ММ-ДД ЧЧ:ММ:СС»); показываем в местном. */
function parseUtc(s) { return s ? new Date(String(s).replace(" ", "T") + "Z") : null; }
/* Некоторые браузеры (урезанные сборки Chromium/Electron) «знают» казахский
 * и кыргызский только на словах: вместо «22 қараша» выдают «2026 M11 22»,
 * вместо «кеше» — «yesterday». Проверяем один раз и тогда форматируем сами. */
function localeBroken(locale) {
    try {
        return new Intl.RelativeTimeFormat(locale, { numeric: "auto" }).format(-1, "day") === "yesterday"
            || /M\d/.test(new Intl.DateTimeFormat(locale, { dateStyle: "medium" }).format(new Date(2026, 10, 22)));
    } catch { return true; }
}
const KK_BROKEN = localeBroken("kk-KZ");
const KY_BROKEN = localeBroken("ky-KG");
/* Запасные названия месяцев и «N … бұрын / мурун» для kk и ky. */
const OWN_DATES = {
    kk: {
        months: ["қаңтар", "ақпан", "наурыз", "сәуір", "мамыр", "маусым", "шілде", "тамыз", "қыркүйек", "қазан", "қараша", "желтоқсан"],
        date: (y, d, m) => `${y} ж. ${d} ${m}`,
        words: { second: "секунд", minute: "минут", hour: "сағат", day: "күн", month: "ай", year: "жыл" },
        yesterday: "кеше", tomorrow: "ертең", now: "жаңа ғана", ago: "бұрын", later: "кейін",
    },
    ky: {
        months: ["январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"],
        date: (y, d, m) => `${y}-ж., ${d}-${m}`,
        words: { second: "секунд", minute: "мүнөт", hour: "саат", day: "күн", month: "ай", year: "жыл" },
        yesterday: "кечээ", tomorrow: "эртең", now: "азыр эле", ago: "мурун", later: "кийин",
    },
};
/** Свои правила дат, если браузер не умеет текущий язык; иначе null. */
function ownDates() {
    const lang = Oqu.state.lang;
    return (lang === "kk" && KK_BROKEN) || (lang === "ky" && KY_BROKEN) ? OWN_DATES[lang] : null;
}
function fmtDate(s, withTime = false) {
    const d = parseUtc(s);
    if (!d || isNaN(d)) return "";
    const own = ownDates();
    if (own) {
        const hm = String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0");
        return own.date(d.getFullYear(), d.getDate(), own.months[d.getMonth()]) + (withTime ? ", " + hm : "");
    }
    const opts = withTime ? { dateStyle: "medium", timeStyle: "short" } : { dateStyle: "medium" };
    return new Intl.DateTimeFormat(LOCALES[Oqu.state.lang], opts).format(d);
}
function ownRtf(own) {
    return {
        format(n, unit) {
            if (unit === "day" && n === -1) return own.yesterday;
            if (unit === "day" && n === 1) return own.tomorrow;
            if (unit === "second" && Math.abs(n) < 10) return own.now;
            const word = own.words[unit];
            return n < 0 ? `${-n} ${word} ${own.ago}` : `${n} ${word} ${own.later}`;
        },
    };
}
function fmtAgo(s) {
    const d = parseUtc(s);
    if (!d) return "";
    const sec = Math.round((d - Date.now()) / 1000);
    const own = ownDates();
    const rtf = own ? ownRtf(own)
        : new Intl.RelativeTimeFormat(LOCALES[Oqu.state.lang], { numeric: "auto" });
    const steps = [[60, "second"], [60, "minute"], [24, "hour"], [30, "day"], [12, "month"], [Infinity, "year"]];
    let value = sec;
    for (const [size, unit] of steps) {
        if (Math.abs(value) < size) return rtf.format(Math.round(value), unit);
        value /= size;
    }
    return fmtDate(s);
}
const fmtNum = (n) => new Intl.NumberFormat(LOCALES[Oqu.state.lang]).format(n);

/* ---------- Запросы к API ----------------------------------------------- */
class ApiError extends Error {
    constructor(status, data) {
        super((data && data.detail && typeof data.detail === "string") ? data.detail : "HTTP " + status);
        this.status = status;
        this.data = data || {};
        this.code = this.data.code || "";
    }
}

const tokens = {
    get access() { return store.get("access"); },
    get refresh() { return store.get("refresh"); },
    set(access, refresh) { store.set("access", access); store.set("refresh", refresh); },
    clear() { store.set("access", null); store.set("refresh", null); },
};

let refreshing = null;
async function refreshTokens() {
    if (!tokens.refresh) return false;
    refreshing ??= fetch("/api/auth/refresh", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: tokens.refresh }),
    }).then(async (res) => {
        if (!res.ok) { tokens.clear(); return false; }
        const data = await res.json();
        tokens.set(data.access_token, data.refresh_token);
        return true;
    }).catch(() => false).finally(() => { refreshing = null; });
    return refreshing;
}

/** Запрос к REST API. Сам подставляет JWT, а при истёкшем токене доступа
 *  один раз обновляет его по refresh-токену и повторяет запрос. */
async function api(path, { method = "GET", body, form, blob = false, retry = true } = {}) {
    const headers = {};
    if (tokens.access) headers.Authorization = "Bearer " + tokens.access;
    let payload;
    if (form) payload = form;
    else if (body !== undefined) { headers["Content-Type"] = "application/json"; payload = JSON.stringify(body); }
    let res;
    try {
        res = await fetch(path, { method, headers, body: payload });
    } catch {
        throw new ApiError(0, { detail: t("error.network"), code: "network" });
    }
    if (res.status === 401 && retry && tokens.refresh && !path.startsWith("/api/auth/")) {
        if (await refreshTokens()) return api(path, { method, body, form, blob, retry: false });
        Oqu.state.user = null;
        renderChrome();
    }
    if (!res.ok) {
        let data = null;
        try { data = await res.json(); } catch { /* не JSON */ }
        if (data && Array.isArray(data.detail)) data = { detail: t("error.validation"), code: "validation", fields: data.detail };
        throw new ApiError(res.status, data);
    }
    if (blob) return res.blob();
    return res.status === 204 ? null : res.json();
}

/** Понятный текст ошибки для пользователя на выбранном языке. */
function errorText(err) {
    const byCode = { network: "error.network", locked: "error.locked", forbidden: "error.forbidden",
        not_found: "error.not_found", server: "error.server" };
    if (err instanceof ApiError) {
        // Сервер отвечает по-русски; для kk/en ищем перевод этой фразы.
        const translated = Oqu.state.t["srv:" + err.message];
        if (translated) return translated;
        // «Недостаточно прав: book.add» — технический код права пользователю не нужен.
        if (err.message.startsWith("Недостаточно прав")) return t("error.forbidden");
        if (err.status === 429 && !err.code) return t("error.rate");
        if (byCode[err.code] && Oqu.state.lang !== "ru") return t(byCode[err.code]);
        return err.message || t("error.generic");
    }
    return t("error.generic");
}

/* ---------- Проверка полей форм ----------------------------------------- */
/** Показать ошибку под конкретным полем и подсветить его красным. */
function setFieldError(el, message) {
    const box = el.closest(".field, .check, .drop, .tags-input") || el;
    box.classList.add("invalid");
    el.setAttribute("aria-invalid", "true");
    let msg = box.querySelector(":scope > .field-error");
    if (!msg) {
        msg = document.createElement("small");
        msg.className = "field-error";
        msg.setAttribute("role", "alert");
        box.appendChild(msg);
    }
    msg.textContent = message;
    const clear = () => clearFieldError(el);
    el.addEventListener("input", clear, { once: true });
    el.addEventListener("change", clear, { once: true });
}
function clearFieldError(el) {
    const box = el.closest(".field, .check, .drop, .tags-input") || el;
    box.classList.remove("invalid");
    el.removeAttribute("aria-invalid");
    box.querySelector(":scope > .field-error")?.remove();
}

/** Причина ошибки поля своими словами (не текст браузера: он на языке ОС). */
function validityText(el) {
    const v = el.validity;
    const fmt = (n) => fmtNum(Number(n));
    if (v.valueMissing) return el.type === "checkbox" ? t("val.check") : t("val.required");
    if (v.rangeOverflow) return t("val.max", { n: fmt(el.max) });
    if (v.rangeUnderflow) return t("val.min", { n: fmt(el.min) });
    if (v.tooShort) return t("val.min_len", { n: el.minLength });
    if (v.tooLong) return t("val.max_len", { n: el.maxLength });
    if (v.typeMismatch) return t(el.type === "email" ? "val.email" : el.type === "url" ? "val.url" : "val.format");
    if (v.badInput || v.stepMismatch) return t("val.number");
    if (v.patternMismatch) return t("val.format");
    return t("val.format");
}

/** Проверить форму до отправки: подсветить все ошибочные поля,
 *  перевести фокус на первое. Возвращает true, если всё верно. */
function validateForm(form) {
    let first = null;
    for (const el of form.elements) {
        if (!el.name || el.disabled || !el.willValidate) continue;
        clearFieldError(el);
        if (!el.checkValidity()) {
            setFieldError(el, validityText(el));
            first ??= el;
        }
    }
    if (first) {
        first.focus({ preventScroll: true });
        first.scrollIntoView({ behavior: "smooth", block: "center" });
    }
    return !first;
}

/** Разложить ошибки сервера (FastAPI 422) по полям формы. Возвращает true,
 *  если хотя бы одну ошибку удалось показать у конкретного поля. */
function showServerFieldErrors(form, err) {
    const fields = err?.data?.fields;
    if (!form || !Array.isArray(fields)) return false;
    let shown = false;
    for (const f of fields) {
        const name = Array.isArray(f.loc) ? f.loc[f.loc.length - 1] : null;
        const el = name && form.elements[name];
        if (!el || !el.name) continue;
        const ctx = f.ctx || {};
        const byType = {
            less_than_equal: ["val.max", { n: fmtNum(ctx.le) }],
            less_than: ["val.max", { n: fmtNum(ctx.lt) }],
            greater_than_equal: ["val.min", { n: fmtNum(ctx.ge) }],
            greater_than: ["val.min", { n: fmtNum(ctx.gt) }],
            string_too_long: ["val.max_len", { n: ctx.max_length }],
            string_too_short: ["val.min_len", { n: ctx.min_length }],
            missing: ["val.required"],
            string_pattern_mismatch: ["val.format"],
            int_parsing: ["val.number"], int_from_float: ["val.number"],
            too_long: ["val.too_many", { n: ctx.max_length }],
        }[f.type];
        setFieldError(el, byType ? t(byType[0], byType[1]) : (f.msg || t("val.format")));
        shown = true;
    }
    if (shown) form.querySelector(".invalid")?.scrollIntoView({ behavior: "smooth", block: "center" });
    return shown;
}

/* ---------- Пользователь и права ---------------------------------------- */
const can = (perm) => !!(Oqu.state.user && Oqu.state.user.permissions.includes(perm));
const isStaff = () => can("user.list") || can("log.read") || can("news.manage");

async function loadMe() {
    if (!tokens.access && !tokens.refresh) { Oqu.state.user = null; return; }
    try {
        Oqu.state.user = await api("/api/me");
    } catch {
        Oqu.state.user = null;
        tokens.clear();
    }
}

function logout() {
    tokens.clear();
    Oqu.state.user = null;
    renderChrome();
    toast(t("auth.bye"));
    location.hash = "#/";
}

function avatarColor(name) {
    const palette = ["#0f6e5a", "#b0532c", "#3b5ba5", "#7d4b9a", "#a3782a", "#2f7f8f", "#9b3b54", "#4f7a2e"];
    let h = 0;
    for (const ch of String(name)) h = (h * 31 + ch.codePointAt(0)) >>> 0;
    return palette[h % palette.length];
}
function avatar(name, cls = "") {
    const letter = (String(name || "?").trim()[0] || "?").toUpperCase();
    return `<span class="avatar ${cls}" style="background:${avatarColor(name)}">${esc(letter)}</span>`;
}
const roleBadge = (role) => `<span class="badge ${esc(role)}">${esc(t("role." + role))}</span>`;

/* ---------- Шапка, меню, подвал ----------------------------------------- */
function navItems() {
    const items = [
        { href: "#/", icon: "home", key: "nav.home", match: /^#\/?$/ },
        { href: "#/catalog", icon: "grid", key: "nav.catalog", match: /^#\/catalog/ },
        { href: "#/trailers", icon: "play", key: "nav.trailers", match: /^#\/trailers/ },
        { href: "#/bookcase", icon: "case", key: "nav.bookcase", match: /^#\/bookcase/ },
        { href: "#/game", icon: "game", key: "nav.game", match: /^#\/game/ },
        { href: "#/shelf", icon: "bookmark", key: "nav.shelf", match: /^#\/shelf/, auth: true },
        { href: "#/stats", icon: "chart", key: "nav.stats", match: /^#\/stats/ },
    ];
    if (isStaff()) items.push({ href: "#/admin", icon: "shield", key: "nav.admin", match: /^#\/admin/ });
    return items.filter((i) => !i.auth || Oqu.state.user);
}

function renderChrome() {
    const hash = location.hash || "#/";
    const items = navItems();
    $("#mainnav").innerHTML = items.map((i) =>
        `<a href="${i.href}" class="${i.match.test(hash) ? "active" : ""}">${icon(i.icon)}<span>${esc(t(i.key))}</span></a>`).join("")
        + (can("book.add") ? `<a href="#/books/new" class="${/^#\/books\/new$/.test(hash) ? "active" : ""}">${icon("plus")}<span>${esc(t("nav.add_book"))}</span></a>
            <a href="#/books/new?kind=manga" class="${/^#\/books\/new\?kind=manga/.test(hash) ? "active" : ""}">${icon("image")}<span>${esc(t("nav.add_manga"))}</span></a>` : "");

    // Нижняя панель на телефоне: 5 главных разделов. Вход и профиль —
    // в шапке справа сверху (как на большинстве сайтов), здесь их нет.
    const tabs = [
        { href: "#/", icon: "home", key: "nav.home", match: /^#\/?$/ },
        { href: "#/catalog", icon: "grid", key: "nav.catalog", match: /^#\/catalog/ },
        { href: "#/trailers", icon: "play", key: "nav.trailers", match: /^#\/trailers/ },
        { href: Oqu.state.user ? "#/shelf" : "#/stats", icon: Oqu.state.user ? "bookmark" : "chart",
          key: Oqu.state.user ? "nav.shelf" : "nav.stats", match: Oqu.state.user ? /^#\/shelf/ : /^#\/stats/ },
        { href: "#/game", icon: "game", key: "nav.game", match: /^#\/game/ },
    ];
    $("#tabbar").innerHTML = tabs.map((i) =>
        `<a href="${i.href}" class="${i.match.test(hash) ? "active" : ""}">${icon(i.icon)}<span>${esc(t(i.key))}</span></a>`).join("");

    $$("#lang-list [data-lang]").forEach((b) => b.setAttribute("aria-current", String(b.dataset.lang === Oqu.state.lang)));
    $("#lang-cur").textContent = $(`#lang-list [data-lang="${Oqu.state.lang}"] span`).textContent;
    $("#theme-btn").innerHTML = icon(Oqu.state.theme === "dark" ? "sun" : "moon");

    const u = Oqu.state.user;
    $("#account").innerHTML = u
        ? `<div class="menu">
             <button class="account-btn" id="account-btn" aria-haspopup="true" aria-expanded="false">
               ${avatar(u.display_name || u.username)}<span class="name">${esc(u.display_name || u.username)}</span>
             </button>
           </div>`
        : `<button class="btn primary" id="login-btn">${esc(t("auth.login"))}</button>`;
    $("#login-btn")?.addEventListener("click", () => openAuth("login"));
    $("#account-btn")?.addEventListener("click", toggleAccountMenu);

    $("#footer").innerHTML = `<div class="footer-in">
        <div class="footer-brand"><svg aria-hidden="true"><use href="#logo"/></svg>
          <div><b>${esc(t("brand.name"))}</b>© 2026 · ${esc(t("footer.uni"))}</div></div>
        <nav>
          <a href="#/terms">${esc(t("footer.terms"))}</a>
          <a href="#/privacy">${esc(t("footer.privacy"))}</a>
          <a href="#/about">${esc(t("footer.about"))}</a>
          <a href="/docs" target="_blank" rel="noopener">API · OpenAPI</a>
        </nav></div>`;
}

function toggleAccountMenu(e) {
    e.stopPropagation();
    const btn = e.currentTarget;
    toggleLangMenu(false);
    const open = $(".menu-list");
    if (open) { open.remove(); btn.setAttribute("aria-expanded", "false"); return; }
    const u = Oqu.state.user;
    const list = document.createElement("div");
    list.className = "menu-list";
    list.innerHTML = `
        <div class="menu-head"><b>${esc(u.display_name || u.username)}</b><div class="small muted">@${esc(u.username)} · ${esc(t("role." + u.role))}</div></div>
        <a href="#/profile">${icon("user")}${esc(t("nav.profile"))}</a>
        <a href="#/shelf">${icon("bookmark")}${esc(t("nav.shelf"))}</a>
        ${can("book.add") ? `<a href="#/books/new">${icon("plus")}${esc(t("nav.add_book"))}</a>
          <a href="#/books/new?kind=manga">${icon("image")}${esc(t("nav.add_manga"))}</a>` : ""}
        ${isStaff() ? `<a href="#/admin">${icon("shield")}${esc(t("nav.admin"))}</a>` : ""}
        <a href="#/profile/settings">${icon("settings")}${esc(t("profile.settings"))}</a>
        <button type="button" id="logout-btn">${icon("logout")}${esc(t("auth.logout"))}</button>`;
    btn.parentElement.appendChild(list);
    btn.setAttribute("aria-expanded", "true");
    $("#logout-btn", list).addEventListener("click", logout);
    list.addEventListener("click", (ev) => { if (ev.target.closest("a")) list.remove(); });
}
document.addEventListener("click", () => { $(".menu-list")?.remove(); toggleLangMenu(false); });

/* ---------- Выбор языка (выпадающий список) ----------------------------- */
function toggleLangMenu(open) {
    const list = $("#lang-list"), btn = $("#lang-btn");
    if (!list) return;
    open = open ?? list.hidden;
    list.hidden = !open;
    btn.setAttribute("aria-expanded", String(open));
    if (open) ($('[aria-current="true"]', list) || $("button", list)).focus();
}

/* ---------- Тема -------------------------------------------------------- */
function setTheme(theme) {
    Oqu.state.theme = theme;
    document.documentElement.dataset.theme = theme;
    $('meta[name="theme-color"]').setAttribute("content", theme === "dark" ? "#121513" : "#0f6e5a");
    store.set("theme", theme);
    renderChrome();
}

/* ---------- Уведомления, окна ------------------------------------------- */
function toast(text, type = "info") {
    const el = document.createElement("div");
    el.className = `toast ${type}`;
    el.innerHTML = (type === "ok" ? icon("check") : "") + `<span>${esc(text)}</span>`;
    $("#toasts").appendChild(el);
    setTimeout(() => { el.style.opacity = "0"; el.style.transition = "opacity .3s"; }, 3200);
    setTimeout(() => el.remove(), 3600);
}
const toastError = (err) => toast(errorText(err), "error");

let modalReturnFocus = null;
function openModal(html, { wide = false, onClose } = {}) {
    modalReturnFocus = document.activeElement;
    const card = $("#modal-card");
    card.className = "modal-card" + (wide ? " wide" : "");
    card.innerHTML = `<button class="icon-btn modal-close" data-close aria-label="${esc(t("common.close"))}">${icon("x")}</button>` + html;
    $("#modal").hidden = false;
    $("#modal")._onClose = onClose;
    document.body.style.overflow = "hidden";
    setTimeout(() => (card.querySelector("input, textarea, select, button:not(.modal-close)") || card).focus(), 30);
    return card;
}
function closeModal() {
    const m = $("#modal");
    if (m.hidden) return;
    m.hidden = true;
    document.body.style.overflow = "";
    m._onClose?.();
    modalReturnFocus?.focus?.();
}
$("#modal").addEventListener("click", (e) => { if (e.target.closest("[data-close]")) closeModal(); });

/** Окно подтверждения вместо стандартного confirm() (его нельзя перевести и оформить). */
function confirmDialog({ title, text = "", ok = t("common.confirm"), danger = false }) {
    return new Promise((resolve) => {
        let answered = false;
        const card = openModal(`<h2>${esc(title)}</h2>${text ? `<p class="muted">${esc(text)}</p>` : ""}
            <div class="btn-row" style="justify-content:flex-end;margin-top:20px">
              <button class="btn" data-close>${esc(t("common.cancel"))}</button>
              <button class="btn ${danger ? "danger" : "primary"}" id="confirm-ok">${esc(ok)}</button>
            </div>`, { onClose: () => { if (!answered) resolve(false); } });
        $("#confirm-ok", card).addEventListener("click", () => { answered = true; closeModal(); resolve(true); });
    });
}

/** Простое окно-форма: возвращает объект полей или null при отмене. */
function formDialog({ title, fields, ok = t("common.save"), intro = "" }) {
    return new Promise((resolve) => {
        let answered = false;
        const body = fields.map((f) => {
            if (f.type === "textarea") return `<label class="field"><span>${esc(f.label)}</span><textarea class="textarea" name="${f.name}" maxlength="${f.max || 1000}" ${f.required ? "required" : ""}>${esc(f.value || "")}</textarea></label>`;
            if (f.type === "select") return `<label class="field"><span>${esc(f.label)}</span><select class="select" name="${f.name}">${f.options.map((o) => `<option value="${esc(o.value)}" ${o.value === f.value ? "selected" : ""}>${esc(o.label)}</option>`).join("")}</select></label>`;
            return `<label class="field"><span>${esc(f.label)}</span><input class="input" name="${f.name}" type="${f.type || "text"}" value="${esc(f.value || "")}" ${f.required ? "required" : ""} ${f.min !== undefined ? `min="${f.min}"` : ""} maxlength="${f.max || 200}" autocomplete="${f.autocomplete || "off"}">${f.hint ? `<small class="hint">${esc(f.hint)}</small>` : ""}</label>`;
        }).join("");
        const card = openModal(`<h2>${esc(title)}</h2>${intro}<form id="dlg-form" novalidate><div class="form-error" id="dlg-err"></div>${body}
            <div class="btn-row" style="justify-content:flex-end"><button type="button" class="btn" data-close>${esc(t("common.cancel"))}</button>
            <button class="btn primary">${esc(ok)}</button></div></form>`, { onClose: () => { if (!answered) resolve(null); } });
        $("#dlg-form", card).addEventListener("submit", (e) => {
            e.preventDefault();
            if (!validateForm(e.target)) return;
            answered = true;
            const data = Object.fromEntries(new FormData(e.target).entries());
            closeModal();
            resolve(data);
        });
    });
}

/* ---------- Вход, регистрация, заявка на разбан ------------------------- */
// Демо-аккаунты для проверки всех ролей (создаются командой python -m app.seed).
const DEMO_ACCOUNTS = [
    ["muhan", "owner", ""], ["khadizat", "editor", ""], ["moder01", "moderator", ""],
    ["author01", "author", ""], ["author02", "author", ""], ["student01", "student", ""],
    ["reader01", "user", ""], ["vladimir_p", "user", ""], ["applicant01", "user", "demo.applicant"],
    ["spammer01", "user", "demo.banned_temp"], ["banned01", "user", "demo.banned_forever"],
];
// В публичном режиме (сайт открыт в интернет) список и пароль не показываем.
const PUBLIC_MODE = document.documentElement.dataset.public === "1";
function openAuth(mode = "login", next = null) {
    const isLogin = mode === "login";
    const card = openModal(`
        <div class="auth-switch" role="tablist">
          <button type="button" data-mode="login" aria-pressed="${isLogin}">${esc(t("auth.login"))}</button>
          <button type="button" data-mode="register" aria-pressed="${!isLogin}">${esc(t("auth.register"))}</button>
        </div>
        <h2>${esc(t(isLogin ? "auth.welcome" : "auth.create"))}</h2>
        <form id="auth-form" novalidate>
          <label class="field"><span>${esc(t("auth.username"))}</span>
            <input class="input" name="username" required minlength="3" maxlength="32" autocomplete="username" autocapitalize="off" spellcheck="false"></label>
          ${isLogin ? "" : `
          <label class="field"><span>${esc(t("auth.display_name"))}</span>
            <input class="input" name="display_name" maxlength="64" autocomplete="name"></label>
          <label class="field"><span>${esc(t("auth.email"))}</span>
            <input class="input" name="email" type="email" required maxlength="254" autocomplete="email"></label>`}
          <label class="field"><span>${esc(t("auth.password"))}</span>
            <input class="input" name="password" type="password" required minlength="${isLogin ? 1 : 8}" maxlength="128" autocomplete="${isLogin ? "current-password" : "new-password"}">
            ${isLogin ? "" : `<small class="hint">${esc(t("auth.password_hint"))}</small>`}</label>
          ${isLogin || !PUBLIC_MODE ? "" : `
          <p class="hint" style="margin:0 0 12px">${esc(t("auth.demo_notice"))}</p>`}
          ${isLogin ? "" : `
          <label class="check" style="margin:4px 0 18px"><input type="checkbox" name="accept_terms" required>
            <span>${t("auth.accept", { terms: `<a href="#/terms" target="_blank">${esc(t("auth.accept_terms"))}</a>`, privacy: `<a href="#/privacy" target="_blank">${esc(t("auth.accept_privacy"))}</a>` })}</span></label>`}
          <div class="form-error above" id="auth-err" role="alert" aria-live="polite"></div>
          <button class="btn primary block lg" id="auth-submit">${esc(t(isLogin ? "auth.login" : "auth.register_btn"))}</button>
        </form>
        ${isLogin && !PUBLIC_MODE ? `<details class="demo-accounts"><summary>${esc(t("auth.demo"))} ${esc(t("auth.demo_hint"))}</summary>
          <div class="demo-grid">${DEMO_ACCOUNTS.map(([n, role, note]) => `<button type="button" data-demo="${n}">
            <b>${n}</b><span>${esc(t("role." + role))}${note ? " · " + esc(t(note)) : ""}</span></button>`).join("")}</div>
          <div>${esc(t("auth.demo_pass"))} <code>ChangeMe_2026</code></div></details>` : ""}`);

    $$("[data-mode]", card).forEach((b) => b.addEventListener("click", () => openAuth(b.dataset.mode, next)));
    $$("[data-demo]", card).forEach((b) => b.addEventListener("click", () => {
        $("[name=username]", card).value = b.dataset.demo;
        $("[name=password]", card).focus();
    }));
    const err = $("#auth-err", card);
    const btn = $("#auth-submit", card);
    // Если блокировка ещё идёт (окно закрыли и открыли снова) — продолжаем отсчёт.
    if (authLockUntil > Date.now()) startLockCountdown(err, btn);
    $("#auth-form", card).addEventListener("submit", async (e) => {
        e.preventDefault();
        const form = e.target;
        const data = Object.fromEntries(new FormData(form).entries());
        if (authLockUntil > Date.now()) return;
        err.textContent = "";
        err.classList.remove("ok");
        if (!validateForm(form)) return;
        btn.disabled = true;
        try {
            if (!isLogin) {
                await api("/api/auth/register", { method: "POST", body: {
                    username: data.username, email: data.email, password: data.password,
                    display_name: data.display_name || "", language: Oqu.state.lang, accept_terms: true } });
            }
            const tk = await api("/api/auth/login", { method: "POST", body: { username: data.username, password: data.password } });
            tokens.set(tk.access_token, tk.refresh_token);
            await loadMe();
            closeModal();
            toast(t(isLogin ? "auth.hello" : "auth.registered", { name: Oqu.state.user.display_name || Oqu.state.user.username }), "ok");
            if (Oqu.state.user.language && Oqu.state.user.language !== Oqu.state.lang && isLogin) await setLang(Oqu.state.user.language, { save: false });
            renderChrome();
            if (next) location.hash = next; else Oqu.router.render();
        } catch (ex) {
            btn.disabled = false;
            if (ex.code === "banned") return showBanned(ex.data, data.username, data.password);
            if (ex.status === 429 && ex.data.retry_after > 0) {
                authLockUntil = Date.now() + ex.data.retry_after * 1000;
                return startLockCountdown(err, btn);
            }
            if (!showServerFieldErrors(form, ex)) err.textContent = errorText(ex);
        }
    });
}

/* Обратный отсчёт после блокировки входа: кнопка неактивна, под ней —
 * «Повторить можно через 0:47». Время приходит от сервера (retry_after). */
let authLockUntil = 0;
let authLockTimer = null;
function startLockCountdown(err, btn) {
    clearInterval(authLockTimer);
    const tick = () => {
        const left = Math.ceil((authLockUntil - Date.now()) / 1000);
        if (!err.isConnected) return clearInterval(authLockTimer);
        if (left <= 0) {
            clearInterval(authLockTimer);
            btn.disabled = false;
            err.classList.add("ok");
            err.textContent = t("auth.retry_ready");
            return;
        }
        const time = Math.floor(left / 60) + ":" + String(left % 60).padStart(2, "0");
        btn.disabled = true;
        err.innerHTML = `<b>${esc(t("auth.too_many"))}</b> <span class="countdown">${esc(t("auth.retry_in", { time }))}</span>`;
    };
    tick();
    authLockTimer = setInterval(tick, 1000);
}

function showBanned(info, username, password) {
    const until = info.until ? fmtDate(info.until, true) : t("ban.forever");
    const card = openModal(`
        <h2>${esc(t("ban.title"))}</h2>
        <div class="lock-box">${icon("lock")}<div><b>${esc(t("ban.reason"))}:</b> ${esc(info.reason || "—")}<br>
          <b>${esc(t("ban.until"))}:</b> ${esc(until)}</div></div>
        <form id="unban-form"><div class="form-error" id="unban-err"></div>
          <label class="field"><span>${esc(t("ban.request_label"))}</span>
            <textarea class="textarea" name="text" required maxlength="1000" placeholder="${esc(t("ban.request_ph"))}"></textarea></label>
          <button class="btn primary block">${esc(t("ban.request_send"))}</button></form>`);
    $("#unban-form", card).addEventListener("submit", async (e) => {
        e.preventDefault();
        const text = e.target.text.value.trim();
        if (!text) return;
        try {
            await api("/api/unban-request", { method: "POST", body: { username, password, text } });
            closeModal();
            toast(t("ban.request_sent"), "ok");
        } catch (ex) { $("#unban-err", card).textContent = errorText(ex); }
    });
}

/** Требовать вход: гостю показываем окно входа и возвращаем false. */
function requireLogin(next = location.hash) {
    if (Oqu.state.user) return true;
    openAuth("login", next);
    return false;
}

/* ---------- Маршрутизатор ------------------------------------------------ */
Oqu.router = {
    add(pattern, handler, opts = {}) { Oqu.routes.push({ pattern, handler, ...opts }); },
    parse() {
        const raw = (location.hash || "#/").slice(1);
        const [path, query = ""] = raw.split("?");
        return { path: path || "/", params: new URLSearchParams(query) };
    },
    async render() {
        const { path, params } = this.parse();
        $(".menu-list")?.remove();
        // Страница может оставить «уборку» (таймеры, сохранение игры) — выполняем.
        try { Oqu.leave?.(); } finally { Oqu.leave = null; }
        renderChrome();
        const view = $("#view");
        view.classList.remove("wide");
        for (const r of Oqu.routes) {
            const m = path.match(r.pattern);
            if (!m) continue;
            if (r.auth && !Oqu.state.user) {
                setTitle(t("auth.required"));
                view.innerHTML = emptyState("lock", t("auth.required"), t("auth.required_text"),
                    `<button class="btn primary" id="need-login">${esc(t("auth.login"))}</button>`);
                $("#need-login").addEventListener("click", () => openAuth("login", location.hash));
                return;
            }
            try {
                await r.handler(view, m.slice(1), params);
            } catch (err) {
                console.error(err);
                const title = { 404: "error.not_found_title", 403: "error.forbidden_title" }[err.status] || "error.title";
                view.innerHTML = emptyState("book", t(title), errorText(err),
                    `<a class="btn" href="#/">${esc(t("nav.home"))}</a>`);
            }
            return;
        }
        view.innerHTML = emptyState("book", t("error.not_found_title"), t("error.page_missing"), `<a class="btn" href="#/">${esc(t("nav.home"))}</a>`);
    },
    /** Обновить параметры адреса (фильтры каталога) без лишней записи в истории. */
    setParams(params, replace = true) {
        const { path } = this.parse();
        const q = params.toString();
        const url = "#" + path + (q ? "?" + q : "");
        if (replace) history.replaceState(null, "", url); else location.hash = url;
    },
};

function setTitle(text) {
    const brand = t("brand.name");   // по-кыргызски «Окуу», в остальных языках «Оқу»
    document.title = text ? `${text} — ${brand}` : `${brand} — ${t("brand.tagline")}`;
}

/* ---------- Общие куски разметки ---------------------------------------- */
function emptyState(ic, title, text = "", actions = "") {
    return `<div class="empty">
        <svg class="ill" viewBox="0 0 120 90" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round">
          <!-- Полупустой шкаф (маскот сайта): пара книг, одна упала, внизу растение -->
          <rect x="14" y="6" width="92" height="78" rx="3"/><path d="M14 36h92M14 62h92M10 84h100"/>
          <rect x="24" y="14" width="8" height="22" rx="1"/><rect x="34" y="18" width="7" height="18" rx="1"/>
          <path d="M44 36l9-19 6 3-9 19"/><path d="M70 62h22v-5H70z"/>
          <path d="M28 62l2-8h10l2 8M35 54c0-6-5-9-9-10 1 5 4 8 9 10zM35 54c0-7 4-11 9-12-1 6-4 10-9 12z"/>
        </svg>
        <h3>${esc(title)}</h3>${text ? `<p>${esc(text)}</p>` : ""}${actions ? `<div class="btn-row" style="justify-content:center">${actions}</div>` : ""}</div>`;
}

/** Простой стабильный хэш строки: одна и та же книга всегда получает
 *  один и тот же «случайный» узор, высоту корешка и т. п. */
function hash(s) {
    let h = 2166136261;
    for (const ch of String(s)) h = Math.imul(h ^ ch.codePointAt(0), 16777619) >>> 0;
    return h;
}

const PATTERNS = ["plain", "stripes", "diagonal", "dots", "grid", "waves", "ornament", "frame", "band", "sun"];
const LAYOUTS = ["top", "center", "bottom"];
/** Узор обложки: выбранный редактором или «авто» — по номеру книги. */
function coverPattern(b) {
    if (b.cover_pattern && b.cover_pattern !== "auto") return b.cover_pattern;
    return PATTERNS[hash("p" + (b.id ?? b.title)) % PATTERNS.length];
}

/* Имя загруженной картинки: 32 hex-символа + расширение (так их создаёт сервер). */
const MEDIA_RE = /^[0-9a-f]{32}\.(png|jpg|webp)$/;

function cover(b, extra = "") {
    const flags = [];
    if (b.is_paid) flags.push(`<span class="badge">${icon("lock", "i-sm")}</span>`);
    if (b.has_file) flags.push(`<span class="badge">PDF</span>`);
    // Манга — не книга, а развёрнутый свиток с деревянными валиками.
    const scroll = b.kind === "manga";
    const rods = scroll ? `<span class="scroll-rod top" aria-hidden="true"></span><span class="scroll-rod bottom" aria-hidden="true"></span>` : "";
    const sc = scroll ? " is-scroll" : "";
    // Обложка-картинка (например, портрет автора): картинка во всю обложку,
    // название и автор — на полосе снизу.
    if (b.cover_image && MEDIA_RE.test(b.cover_image)) {
        return `<div class="cover has-img${sc}" style="--c:${esc(b.cover_color || "#1f5f4a")}" ${extra}>
            <img class="cover-img" src="/media/${b.cover_image}" alt="" loading="lazy" decoding="async">
            <div class="cover-flags">${flags.join("")}</div>
            <div class="cover-band"><div class="cover-title">${esc(b.title)}</div>
            <div class="cover-author">${esc(b.author)}</div></div>${rods}</div>`;
    }
    const pattern = coverPattern(b);
    const layout = scroll ? "center" : pattern === "band" ? "band" : LAYOUTS[hash("l" + (b.id ?? b.title)) % LAYOUTS.length];
    return `<div class="cover p-${pattern} l-${layout}${sc}" style="--c:${esc(b.cover_color || "#1f5f4a")}" ${extra}>
        <div class="cover-flags">${flags.join("")}</div>
        <div class="cover-title">${esc(b.title)}</div>
        <div class="cover-author">${esc(b.author)}</div>${rods}</div>`;
}

/* ---------- Текст книги с иллюстрациями и формулами ----------------------
 * Простая разметка (как в Markdown/LaTeX), блоки разделяются пустой строкой:
 *   ## Заголовок главы
 *   ![Подпись](img:<имя файла>)   — иллюстрация, загруженная в редакторе
 *   $$ E = mc^2 $$                 — формула отдельной строкой
 *   …текст \( a^2 + b^2 \) текст…  — формула внутри абзаца
 * Всё экранируется (esc), картинки берутся только с нашего сервера. */
function richText(content) {
    const blocks = (content || "").split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean);
    const inline = (s) => esc(s).replace(/\\\((.+?)\\\)/g, (_m, tex) => `<span class="r-math" data-tex="${tex}">${tex}</span>`);
    return blocks.map((p) => {
        const img = p.match(/^!\[([^\]]*)\]\(img:([^)\s]+)\)$/);
        if (img && MEDIA_RE.test(img[2])) {
            return `<figure class="r-fig"><img src="/media/${img[2]}" alt="${esc(img[1])}" loading="lazy" decoding="async">
                ${img[1] ? `<figcaption>${esc(img[1])}</figcaption>` : ""}</figure>`;
        }
        const math = p.match(/^\$\$([\s\S]+)\$\$$/);
        if (math) return `<div class="r-math r-math-block" data-tex="${esc(math[1].trim())}" data-display="1">${esc(math[1].trim())}</div>`;
        const head = p.match(/^(#{2,3})\s+(.+)$/);
        if (head) return `<h${head[1].length} class="r-head">${inline(head[2])}</h${head[1].length}>`;
        return `<p>${inline(p)}</p>`;
    }).join("");
}

/* Формулы рисует библиотека Temml (LaTeX → MathML, лежит в static/vendor).
 * Она подгружается только когда на странице действительно есть формулы. */
let temmlLoading = null;
function loadTemml() {
    if (window.temml) return Promise.resolve();
    temmlLoading ??= new Promise((resolve, reject) => {
        const v = document.documentElement.dataset.v;
        const css = document.createElement("link");
        css.rel = "stylesheet"; css.href = `/static/vendor/temml/Temml-Local.css?v=${v}`;
        document.head.appendChild(css);
        const s = document.createElement("script");
        s.src = `/static/vendor/temml/temml.min.js?v=${v}`;
        s.onload = resolve; s.onerror = reject;
        document.head.appendChild(s);
    });
    return temmlLoading;
}
async function renderMath(root) {
    const items = $$(".r-math", root);
    if (!items.length) return;
    try { await loadTemml(); } catch { return; }   // без библиотеки остаётся текст формулы
    items.forEach((el) => {
        try { window.temml.render(el.dataset.tex, el, { displayMode: !!el.dataset.display, throwOnError: false }); }
        catch { el.classList.add("r-math-error"); }
    });
}

function starsMini(b) {
    return b.rating ? `<span class="stars-mini">${icon("star")}${esc(String(b.rating).replace(".", Oqu.state.lang === "en" ? "." : ","))}</span>` : "";
}

function pager(d, onPage) {
    if (!d.pages || d.pages <= 1) return "";
    const cur = d.page, last = d.pages;
    const nums = new Set([1, last, cur - 1, cur, cur + 1].filter((n) => n >= 1 && n <= last));
    const sorted = [...nums].sort((a, b) => a - b);
    let html = `<nav class="pager" aria-label="${esc(t("pager.label"))}">
        <button data-page="${cur - 1}" ${cur <= 1 ? "disabled" : ""} aria-label="${esc(t("pager.prev"))}">${icon("left")}</button>`;
    let prev = 0;
    for (const n of sorted) {
        if (n - prev > 1) html += `<span class="gap">…</span>`;
        html += `<button data-page="${n}" ${n === cur ? 'aria-current="page"' : ""}>${n}</button>`;
        prev = n;
    }
    html += `<button data-page="${cur + 1}" ${cur >= last ? "disabled" : ""} aria-label="${esc(t("pager.next"))}">${icon("right")}</button></nav>`;
    setTimeout(() => $$(".pager button[data-page]").forEach((b) => b.addEventListener("click", () => onPage(Number(b.dataset.page)))), 0);
    return html;
}

/* ---------- Кнопка «показать пароль» ------------------------------------- */
/* Свой «глазок» у каждого поля пароля. Встроенный глазок Edge прячет пароль
 * и сам исчезает, стоит уйти с поля или переключить окно (так задумано в
 * браузере), поэтому он отключён в CSS (::-ms-reveal), а наш остаётся. */
function addPasswordToggle(input) {
    if (input.dataset.eye) return;
    input.dataset.eye = "1";
    const wrap = document.createElement("span");
    wrap.className = "pass-wrap";
    input.replaceWith(wrap);
    wrap.appendChild(input);
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "pass-eye";
    const sync = () => {
        const shown = input.type === "text";
        btn.innerHTML = icon(shown ? "eye-off" : "eye");
        btn.setAttribute("aria-pressed", String(shown));
        btn.setAttribute("aria-label", t(shown ? "auth.hide_password" : "auth.show_password"));
        btn.title = btn.getAttribute("aria-label");
    };
    btn.addEventListener("click", (e) => {
        e.preventDefault();
        input.type = input.type === "password" ? "text" : "password";
        sync();
        input.focus();
    });
    // После очистки формы (например, пароль успешно сменён) — снова скрыть.
    input.form?.addEventListener("reset", () => { input.type = "password"; sync(); });
    sync();
    wrap.appendChild(btn);
}
function watchPasswordFields() {
    const scan = (root) => root.querySelectorAll?.('input[type="password"]').forEach(addPasswordToggle);
    scan(document);
    new MutationObserver((list) => list.forEach((m) => m.addedNodes.forEach((n) => {
        if (n.nodeType !== 1) return;
        if (n.matches('input[type="password"]')) addPasswordToggle(n); else scan(n);
    }))).observe(document.body, { childList: true, subtree: true });
}

/* ---------- Запуск ------------------------------------------------------- */
function showStorageNotice() {
    if (store.get("notice")) return;
    const box = $("#notice");
    box.innerHTML = `<p>${esc(t("notice.text"))} <a href="#/privacy">${esc(t("notice.more"))}</a></p>
        <button class="btn sm primary" id="notice-ok">${esc(t("notice.ok"))}</button>`;
    box.hidden = false;
    $("#notice-ok").addEventListener("click", () => { store.set("notice", 1); box.hidden = true; });
}

async function boot() {
    const prefersDark = window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches;
    setTheme(store.get("theme", prefersDark ? "dark" : "light"));
    watchPasswordFields();
    const browserLang = (navigator.language || "ru").slice(0, 2);
    const lang = store.get("lang", ["kk", "ky", "en"].includes(browserLang) ? browserLang : "ru");
    await Promise.all([setLang(lang, { save: false }), loadMe()]);
    if (Oqu.state.user && Oqu.state.user.language !== Oqu.state.lang && !store.get("lang")) {
        await setLang(Oqu.state.user.language, { save: false });
    }

    $("#lang-btn").addEventListener("click", (e) => { e.stopPropagation(); $(".menu-list")?.remove(); toggleLangMenu(); });
    $$("#lang-list [data-lang]").forEach((b) => b.addEventListener("click", () => {
        toggleLangMenu(false);
        $("#lang-btn").focus();
        if (b.dataset.lang !== Oqu.state.lang) setLang(b.dataset.lang);
    }));
    // Стрелки вверх/вниз двигают выбор внутри открытого списка.
    $("#lang-list").addEventListener("keydown", (e) => {
        if (!["ArrowDown", "ArrowUp"].includes(e.key)) return;
        e.preventDefault();
        const items = $$("#lang-list button"), i = items.indexOf(document.activeElement);
        items[(i + (e.key === "ArrowDown" ? 1 : items.length - 1)) % items.length].focus();
    });
    $("#theme-btn").addEventListener("click", () => setTheme(Oqu.state.theme === "dark" ? "light" : "dark"));
    $("#search-form").addEventListener("submit", (e) => {
        e.preventDefault();
        const q = $("#search-input").value.trim();
        location.hash = "#/catalog" + (q ? "?query=" + encodeURIComponent(q) : "");
    });
    // Горячие клавиши: «/» — к поиску (как на GitHub и YouTube), Esc — закрыть окно.
    document.addEventListener("keydown", (e) => {
        const typing = /INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName) || document.activeElement?.isContentEditable;
        if (e.key === "/" && !typing) { e.preventDefault(); $("#search-input").focus(); }
        if (e.key === "Escape") { closeModal(); $(".menu-list")?.remove(); toggleLangMenu(false); }
    });
    window.addEventListener("hashchange", () => { Oqu.router.render(); window.scrollTo(0, 0); });
    await Oqu.router.render();
    showStorageNotice();

    // Пасхалка для тех, кто открыл консоль разработчика.
    console.log("%cОқу%c  REST API · FastAPI · JWT\nСделано Мұханом и Хадизат. Документация API: /docs",
        "font:700 28px Cambria,serif;color:#0f6e5a", "font:13px monospace;color:#6d685d");
}

Object.assign(Oqu, { $, $$, esc, icon, t, plural, api, ApiError, errorText, can, isStaff, store, tokens, toast,
    toastError, openModal, closeModal, confirmDialog, formDialog, openAuth, requireLogin, setTitle, emptyState,
    cover, starsMini, pager, fmtDate, fmtAgo, fmtNum, avatar, roleBadge, loadMe, renderChrome, debounce, setLang,
    setTheme, applyStaticI18n, validateForm, showServerFieldErrors, setFieldError, clearFieldError,
    coverPattern, hash, parseUtc });

document.addEventListener("DOMContentLoaded", boot);
