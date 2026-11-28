/* =====================================================================
   Оқу — живая презентация (страница /present).

   Как это работает:
   * слайды и речь отдаёт сервер (/api/present/slides) только владельцу;
   * общий номер слайда и таймер хранятся на сервере (/api/present/state);
   * каждый открытый экран (ноутбук у доски, телефон-пульт) раз в 0,7 с
     спрашивает состояние — поэтому нажатие на телефоне через долю секунды
     переключает слайд на ноутбуке;
   * при смене слайда сайт слева (iframe) сам открывает нужную страницу.
   ===================================================================== */
"use strict";

(() => {
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const POLL_MS = 700;

/* ---------- Токены — те же, что у сайта (localStorage «oqu.*») ---------- */
const store = {
    get(k) { try { return JSON.parse(localStorage.getItem("oqu." + k)); } catch { return null; } },
    set(k, v) { try { localStorage.setItem("oqu." + k, JSON.stringify(v)); } catch { /* приватный режим */ } },
};
const local = {
    get(k, d) { try { const v = localStorage.getItem("oqu.present." + k); return v === null ? d : JSON.parse(v); } catch { return d; } },
    set(k, v) { try { localStorage.setItem("oqu.present." + k, JSON.stringify(v)); } catch { /* ничего */ } },
};

async function refresh() {
    const rt = store.get("refresh");
    if (!rt) return false;
    try {
        const res = await fetch("/api/auth/refresh", { method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ refresh_token: rt }) });
        if (!res.ok) return false;
        const d = await res.json();
        store.set("access", d.access_token);
        store.set("refresh", d.refresh_token);
        return true;
    } catch { return false; }
}

async function api(path, body, retry = true) {
    const headers = {};
    const at = store.get("access");
    if (at) headers.Authorization = "Bearer " + at;
    if (body) headers["Content-Type"] = "application/json";
    const res = await fetch(path, { method: body ? "POST" : "GET", headers, body: body ? JSON.stringify(body) : undefined });
    if (res.status === 401 && retry && await refresh()) return api(path, body, false);
    if (!res.ok) { const e = new Error("HTTP " + res.status); e.status = res.status; throw e; }
    return res.json();
}

/* ---------- Состояние ---------- */
let deck = null;          // { slides, total, talk, people }
let plan = [];            // плановое время окончания каждого слайда (сек)
let state = { slide: 0, started: false, running: false, elapsed: 0, rev: -1 };
let gotAt = performance.now();
let shownSlide = -1;
let mode = "board";       // board | remote
let popup = null;         // сайт в отдельном окне (по кнопке «Окно»)

const elapsedNow = () => state.elapsed + (state.running ? (performance.now() - gotAt) / 1000 : 0);
const mmss = (sec) => {
    const s = Math.max(0, Math.floor(Math.abs(sec)));
    return String(Math.floor(s / 60)).padStart(2, "0") + ":" + String(s % 60).padStart(2, "0");
};

function applyState(s) {
    const changed = s.rev !== state.rev;
    state = s;
    gotAt = performance.now();
    if (changed) render();
    $("#start").hidden = state.started || mode === "remote";
}

async function poll() {
    try { applyState(await api("/api/present/state")); }
    catch (e) { if (e.status === 401 || e.status === 403) return showGate(e.status); }
    setTimeout(poll, POLL_MS);
}

async function send(action, slide) {
    try { applyState(await api("/api/present/control", { action, slide })); }
    catch { /* сеть моргнула — следующий опрос всё догонит */ }
}

/* ---------- Отрисовка слайда ---------- */
function slideHtml(s) {
    const parts = [`<div class="kicker">${esc(s.kicker)}</div><h1>${esc(s.title)}</h1>`];
    if (s.stats) parts.push(`<div class="stats">${s.stats.map((x) => `<div><b>${esc(x.n)}</b><span>${esc(x.l)}</span></div>`).join("")}</div>`);
    if (s.cards) parts.push(`<div class="cards">${s.cards.map((x) => `<div class="card"><h3>${esc(x.h)}</h3><p>${esc(x.t)}</p></div>`).join("")}</div>`);
    if (s.steps) parts.push(`<div class="steps">${s.steps.map((x) => `<div class="step"><h3>${esc(x.h)}</h3><p>${esc(x.t)}</p></div>`).join("")}</div>`);
    if (s.table) {
        const [head, ...rows] = s.table;
        parts.push(`<table class="tbl"><thead><tr>${head.map((h) => `<th>${esc(h)}</th>`).join("")}</tr></thead><tbody>${rows.map((r) =>
            `<tr class="${/Оқу/.test(r[0]) ? "us" : ""}">${r.map((c) => `<td>${esc(c)}</td>`).join("")}</tr>`).join("")}</tbody></table>`);
    }
    if (s.timeline) parts.push(`<ol class="timeline">${s.timeline.map((x) => `<li><b>${esc(x.h)}</b> ${esc(x.t)}</li>`).join("")}</ol>`);
    if (s.bullets) parts.push(`<ul class="bullets">${s.bullets.map((b) => `<li>${esc(b)}</li>`).join("")}</ul>`);
    if (s.ask_box) parts.push(`<div class="askbox">${s.qr ? `<img src="/static/img/qr_site.svg?v=${document.documentElement.dataset.v}" alt="QR-код сайта">` : ""}<span>${esc(s.ask_box)}</span></div>`);
    if (s.foot) parts.push(`<div class="foot">${esc(s.foot)}</div>`);
    return parts.join("");
}

function trackHtml() {
    const total = deck.total;
    const segs = deck.slides.map((s, i) => {
        const cls = i < state.slide ? "done" : i === state.slide ? "cur" : "";
        const color = deck.people[s.who].color;
        return `<i class="${cls}" style="width:${(s.time / total) * 100}%;background:${color}" title="${i + 1}. ${esc(s.title)}"></i>`;
    }).join("");
    const qa = `<i class="qa-zone" style="width:${((total - deck.talk) / total) * 100}%" title="Вопросы"></i>`;
    return segs + qa + `<span class="now"></span>`;
}

function render() {
    if (!deck) return;
    const i = Math.min(state.slide, deck.slides.length - 1);
    const s = deck.slides[i];
    const person = deck.people[s.who];
    document.documentElement.style.setProperty("--who", person.color);
    const n = `${i + 1} / ${deck.slides.length}`;
    if (mode === "board") {
        $("#who").textContent = person.name;
        $("#count").textContent = n;
        if (i !== shownSlide) {
            const box = $("#slide");
            box.innerHTML = slideHtml(s);
            box.classList.remove("enter"); void box.offsetWidth; box.classList.add("enter");
            box.scrollTop = 0;
            $("#board-notes").textContent = s.notes || "";
            openSite(s.site);
        }
        $("#track").innerHTML = trackHtml();
        $("#b-pause").textContent = state.running || !state.started ? "Пауза" : "Продолжить";
    } else {
        $("#r-who").textContent = person.name;
        $("#r-count").textContent = n;
        $("#r-title").textContent = s.title;
        const next = deck.slides[i + 1];
        $("#r-nexttitle").textContent = next ? `Дальше: ${next.title} (${deck.people[next.who].name})` : "Последний слайд, потом вопросы";
        $("#r-notes").textContent = s.notes || "";
        $("#r-ask").innerHTML = (s.ask || []).map((a) => `<li>${esc(a)}</li>`).join("");
        $("#r-askbox").hidden = !(s.ask || []).length;
        $("#r-track").innerHTML = trackHtml();
        $("#r-jump").value = String(i);
        $("#r-pause").textContent = state.running || !state.started ? "Пауза" : "Продолжить";
        if (i !== shownSlide) $(".r-body").scrollTop = 0;
    }
    shownSlide = i;
    tick();
}

/* ---------- Таймер: 10 минут, 8 доклад + 2 вопросы ---------- */
function tick() {
    if (!deck) return;
    const el = elapsedNow();
    const total = deck.total, talk = deck.talk;
    const i = Math.min(state.slide, deck.slides.length - 1);
    let cls = "ok", sub = "/ " + mmss(total), deltaText = "", deltaCls = "";
    if (!state.started) { cls = ""; deltaText = "таймер не запущен"; }
    else if (el >= total) { cls = "over"; sub = "время вышло"; }
    else if (el >= talk) { cls = "qa"; sub = "вопросы · ещё " + mmss(total - el); }
    else {
        // Отстаём ли от плана: сравниваем с плановым концом текущего слайда.
        const late = el - plan[i];
        if (late > 0) { cls = "late"; deltaText = "отстаём на " + mmss(late); deltaCls = "late"; }
        else { deltaText = "запас " + mmss(-late); deltaCls = "ahead"; }
    }
    const shown = state.started ? mmss(el) : "00:00";
    const ids = mode === "board" ? ["#timer", "#t-main", "#t-sub", "#delta", "#track"] : ["#r-timer", "#r-main", "#r-sub", "#r-delta", "#r-track"];
    const [tm, main, subEl, delta, track] = ids.map((x) => $(x));
    tm.className = "timer " + cls + (mode === "remote" ? " big" : "");
    main.textContent = shown;
    subEl.textContent = sub;
    delta.textContent = deltaText;
    delta.className = "delta " + deltaCls;
    const now = track.querySelector(".now");
    if (now) now.style.left = Math.min(100, (el / total) * 100) + "%";
}

/* ---------- Сайт слева: открыть страницу, о которой слайд ---------- */
/* «book:Название» / «read:Название» — найти книгу по названию (номера
 * книг на сервере и на ноутбуке могут отличаться). */
const resolved = {};
async function resolveTarget(target) {
    const m = /^(book|read):(.+)$/.exec(target || "");
    if (!m) return target;
    if (!resolved[target]) {
        try {
            const d = await api(`/api/books?query=${encodeURIComponent(m[2])}&page_size=5`);
            const b = d.items.find((x) => x.title === m[2]) || d.items[0];
            // На странице книги из презентации трейлер играет сразу.
            resolved[target] = b ? `#/${m[1]}/${b.id}${m[1] === "book" ? "?trailer=1" : ""}`
                : "#/catalog?query=" + encodeURIComponent(m[2]);
        } catch { return "#/catalog"; }
    }
    return resolved[target];
}

async function openSite(target) {
    target = await resolveTarget(target);
    if (!target) return;
    const frame = popup && !popup.closed ? popup : $("#site").contentWindow;
    try {
        if (target.startsWith("#") && frame.location.pathname === "/") {
            frame.location.hash = target;              // без перезагрузки сайта
        } else {
            frame.location.href = target.startsWith("#") ? "/" + target : target;
        }
    } catch {
        $("#site").src = target.startsWith("#") ? "/" + target : target;
    }
}

/* ---------- Масштаб текста слайда под ширину панели ---------- */
function fit() {
    const pane = $(".slide-pane");
    if (!pane) return;
    const w = pane.clientWidth, h = pane.clientHeight;
    const fs = Math.max(.72, Math.min(1.5, Math.min(w / 760, h / 640)));
    document.documentElement.style.setProperty("--fs", fs.toFixed(3));
}

/* ---------- Разделитель сайта и слайдов ---------- */
function initDivider() {
    const board = $("#board"), div = $("#divider");
    const saved = local.get("split", 56);
    board.style.setProperty("--split", saved + "%");
    div.addEventListener("pointerdown", (e) => {
        div.setPointerCapture(e.pointerId);
        board.classList.add("dragging");
        const move = (ev) => {
            const pct = Math.max(20, Math.min(80, (ev.clientX / window.innerWidth) * 100));
            board.style.setProperty("--split", pct + "%");
            local.set("split", Math.round(pct));
            fit();
        };
        const up = () => { board.classList.remove("dragging"); div.removeEventListener("pointermove", move); };
        div.addEventListener("pointermove", move);
        div.addEventListener("pointerup", up, { once: true });
    });
}

function toggleSite(show) {
    const board = $("#board");
    const hide = show === undefined ? !board.classList.contains("no-site") : !show;
    board.classList.toggle("no-site", hide);
    $("#b-site").classList.toggle("on", !hide);
    local.set("site", !hide);
    fit();
}

function toggleNotes() {
    const n = $("#board-notes");
    n.hidden = !n.hidden;
    $("#b-notes").classList.toggle("on", !n.hidden);
    fit();
}

/* ---------- Запуск ---------- */
function showGate(status) {
    $("#board").hidden = $("#remote").hidden = $("#start").hidden = true;
    $("#gate").hidden = false;
    $("#gate-text").textContent = status === 403
        ? "Презентация доступна только главному разработчику (владельцу). Войдите под своим аккаунтом."
        : "Сначала войдите на сайте под аккаунтом владельца, потом вернитесь на эту страницу.";
    $("#gate-login").hidden = false;
}

function bindBoard() {
    $("#b-next").onclick = () => send("next");
    $("#b-prev").onclick = () => send("prev");
    $("#b-pause").onclick = () => send(state.running ? "pause" : state.started ? "resume" : "start");
    $("#b-site").onclick = () => toggleSite();
    $("#b-notes").onclick = toggleNotes;
    $("#b-popup").onclick = () => {
        popup = window.open("/", "oqu-site");
        toggleSite(false);
        if (deck) setTimeout(() => openSite(deck.slides[state.slide].site), 800);
    };
    $("#b-full").onclick = () => (document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen()).catch(() => {});
    $("#start-go").onclick = () => send("start");
    document.addEventListener("keydown", (e) => {
        if (e.target.closest("input, select, textarea")) return;
        const k = e.key;
        // Пробел на кнопке и так её «нажмёт» — не листаем второй раз.
        if (k === " " && e.target.closest("button")) return;
        if (["ArrowRight", "PageDown", " "].includes(k)) { e.preventDefault(); send(state.started ? "next" : "start"); }
        else if (["ArrowLeft", "PageUp", "Backspace"].includes(k)) { e.preventDefault(); send("prev"); }
        else if (k === "Home") send("goto", 0);
        else if (k === "p" || k === "P" || k === "з" || k === "З") $("#b-pause").click();
        else if (k === "h" || k === "H" || k === "р" || k === "Р") toggleSite();
        else if (k === "n" || k === "N" || k === "т" || k === "Т") toggleNotes();
        else if (k === "f" || k === "F" || k === "а" || k === "А") $("#b-full").click();
    });
    initDivider();
    if (local.get("site", true) === false) toggleSite(false); else $("#b-site").classList.add("on");
    // Первую страницу сайта откроет render() — ту, что нужна текущему слайду.
    window.addEventListener("resize", fit);
    fit();
}

function bindRemote() {
    $("#r-next").onclick = () => send(state.started ? "next" : "start");
    $("#r-prev").onclick = () => send("prev");
    $("#r-start").onclick = () => { if (!state.started || confirm("Запустить таймер заново с первого слайда?")) send("start"); };
    $("#r-pause").onclick = () => send(state.running ? "pause" : state.started ? "resume" : "start");
    $("#r-jump").innerHTML = deck.slides.map((s, i) => `<option value="${i}">${i + 1}. ${esc(s.title)}</option>`).join("");
    $("#r-jump").onchange = (e) => send("goto", Number(e.target.value));
    $("#r-board").onclick = () => { location.search = "?mode=board"; };
}

async function main() {
    try {
        deck = await api("/api/present/slides");
    } catch (e) {
        return showGate(e.status === 403 ? 403 : 401);
    }
    let acc = 0;
    plan = deck.slides.map((s) => (acc += s.time));
    const forced = new URLSearchParams(location.search).get("mode");
    mode = forced === "remote" || forced === "board" ? forced
        : window.matchMedia("(max-width: 760px)").matches ? "remote" : "board";
    document.title = "Оқу · " + (mode === "remote" ? "Пульт" : "Презентация");
    $("#start-title").textContent = deck.title;
    if (mode === "board") { $("#board").hidden = false; bindBoard(); }
    else { $("#remote").hidden = false; bindRemote(); }
    setInterval(tick, 250);
    poll();
}

document.addEventListener("DOMContentLoaded", main);
})();
