/* =====================================================================
   Оқу — «живые» книги:
   * трейлер книги: книга стоит вертикально, обложка распахивается,
     страницы перелистываются, на каждой — анимированная сцена и
     интригующая подпись (пишет автор или генерирует ИИ);
   * лента трейлеров #/trailers — «книжный TikTok»: листаешь вниз,
     трейлеры играют сами, «Читать» — в один тап;
   * читалка манги с переводом поверх картинки на ru/kk/ky/en
     (готовый перевод или ИИ-перевод страницы с любого языка);
   * анимация открытия книги перед чтением;
   * блоки редактора: тип издания, трейлер, страницы манги.
   ===================================================================== */
"use strict";

(() => {
const { $, $$, esc, icon, t, api, can, store, toast, toastError, openModal, closeModal, confirmDialog,
    setTitle, emptyState, cover, fmtNum } = Oqu;
const route = (p, h, o) => Oqu.router.add(p, h, o);
const reduceMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/* ======================================================================
   Сцены трейлера: маленькие анимированные иллюстрации (SVG + CSS).
   Каталог тот же, что на сервере (service.TRAILER_SCENES).
   ====================================================================== */
const SKY = {
    day: ["#9fd3e6", "#e9f4ea"], dusk: ["#f1a66a", "#f7dcb4"], night: ["#16213e", "#3b3f6b"],
    sea: ["#8cc3d8", "#d9eef2"], storm: ["#3a4150", "#6c7383"], wonder: ["#c9b6e8", "#f5e6f0"],
};
const sky = (id, k) => `<defs><linearGradient id="sk-${id}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${SKY[k][0]}"/><stop offset="1" stop-color="${SKY[k][1]}"/></linearGradient></defs>
    <rect width="320" height="200" fill="url(#sk-${id})"/>`;
const stars = (n = 18) => Array.from({ length: n }, (_, i) =>
    `<circle class="tr-twinkle" style="animation-delay:${(i * 0.37) % 3}s" cx="${(i * 71) % 320}" cy="${(i * 37) % 90 + 6}" r="${i % 3 ? 1.2 : 1.8}" fill="#fff"/>`).join("");

const SCENES = {
    rider: (id) => `${sky(id, "dusk")}<circle cx="250" cy="70" r="26" fill="#ffe2a8"/>
        <g class="tr-drift"><path d="M-40 150 Q 40 120 120 150 T 280 150 T 440 150 V200 H-40z" fill="#c9a46a"/></g>
        <path d="M0 165 Q 80 150 160 165 T 320 165 V200 H0z" fill="#a37b44"/>
        <g class="tr-dust">${[0, 1, 2, 3].map((i) => `<circle cx="${70 - i * 14}" cy="${150 + (i % 2) * 4}" r="${5 - i}" fill="#e8d2a6" opacity=".8"/>`).join("")}</g>
        <g class="tr-gallop" transform="translate(150 118)">
          <path d="M-46 -2 Q -20 -22 24 -20 L40 -40 L52 -42 L58 -32 L48 -28 L40 -12 L30 4 L-40 6z" fill="#3b2a1d"/>
          <path class="tr-leg-a" d="M-34 4 L-46 30 M-22 4 L-12 30 M20 2 L34 28 M28 2 L16 30" stroke="#3b2a1d" stroke-width="5" stroke-linecap="round"/>
          <path d="M-46 -2 L-66 -10 L-60 6z" fill="#3b2a1d"/>
          <path d="M-6 -20 L-12 -46 L4 -52 L10 -22z" fill="#7a2e2e"/><circle cx="-2" cy="-58" r="7" fill="#e7c9a2"/>
          <path d="M-10 -60 L-2 -74 L8 -60z" fill="#1f5f4a"/><path class="tr-cape" d="M-10 -44 L-36 -36 L-30 -26 L-8 -34z" fill="#c8902e"/>
        </g>`,
    ship: (id) => `${sky(id, "sea")}<g class="tr-drift"><ellipse cx="60" cy="40" rx="30" ry="9" fill="#fff" opacity=".8"/><ellipse cx="230" cy="30" rx="38" ry="10" fill="#fff" opacity=".7"/></g>
        <g class="tr-bob" transform="translate(160 120)">
          <path d="M-60 0 L60 0 L46 22 L-46 22z" fill="#5c3a21"/><rect x="-3" y="-70" width="5" height="70" fill="#3b2a1d"/>
          <path d="M3 -66 Q 40 -40 3 -6z" fill="#f4efe2"/><path d="M-4 -60 Q -36 -36 -4 -10z" fill="#ece5d3"/><path d="M2 -70 l16 5 -16 5z" fill="#b42318"/>
        </g>
        <g class="tr-wave"><path d="M-320 150 q 20 -10 40 0 t 40 0 t 40 0 t 40 0 t 40 0 t 40 0 t 40 0 t 40 0 t 40 0 t 40 0 t 40 0 t 40 0 t 40 0 t 40 0 t 40 0 t 40 0 V200 H-320z" fill="#2f7f8f"/></g>
        <g class="tr-wave slow"><path d="M-320 165 q 20 -8 40 0 t 40 0 t 40 0 t 40 0 t 40 0 t 40 0 t 40 0 t 40 0 t 40 0 t 40 0 t 40 0 t 40 0 t 40 0 t 40 0 t 40 0 t 40 0 V200 H-320z" fill="#1b5a68"/></g>`,
    city: (id) => `${sky(id, "night")}${stars(12)}<circle cx="268" cy="34" r="14" fill="#f5efd6"/>
        ${[[10, 70, 40], [54, 50, 60], [118, 80, 50], [172, 40, 70], [246, 64, 60]].map(([x, h, w], i) =>
            `<rect x="${x}" y="${200 - h - 40}" width="${w}" height="${h + 40}" fill="${i % 2 ? "#232a45" : "#1b2138"}"/>` +
            Array.from({ length: 6 }, (_, k) => `<rect class="tr-window" style="animation-delay:${(i * 0.7 + k * 0.45) % 4}s" x="${x + 6 + (k % 3) * (w / 3.4)}" y="${200 - h - 30 + Math.floor(k / 3) * 22}" width="7" height="10" fill="#ffd77a"/>`).join("")).join("")}
        <rect x="0" y="186" width="320" height="14" fill="#11162a"/><g class="tr-walk"><circle cx="0" cy="168" r="4" fill="#0b0e1c"/><rect x="-3" y="172" width="6" height="14" fill="#0b0e1c"/></g>`,
    castle: (id) => `${sky(id, "dusk")}<g class="tr-drift"><ellipse cx="80" cy="46" rx="34" ry="8" fill="#fff" opacity=".6"/></g>
        <path d="M0 170 Q 160 110 320 170 V200 H0z" fill="#6b8f5a"/>
        <g transform="translate(160 86)" fill="#8a8f99"><rect x="-50" y="10" width="100" height="56"/><rect x="-62" y="-6" width="22" height="72"/><rect x="40" y="-6" width="22" height="72"/>
          <rect x="-12" y="-30" width="24" height="96"/>${[-62, -55, -48, 40, 47, 54].map((x) => `<rect x="${x}" y="-12" width="5" height="7"/>`).join("")}
          <path d="M-12 -30 L0 -46 L12 -30z" fill="#7a2e2e"/><path d="M-14 66 V40 a14 14 0 0 1 28 0 V66z" fill="#3b2a1d"/>
          <path class="tr-flag" d="M0 -46 V-62 l18 4 -18 5" fill="#c8902e" stroke="#3b2a1d"/></g>`,
    forest: (id) => `${sky(id, "night")}${stars(8)}
        ${[20, 70, 130, 200, 260, 300].map((x, i) => `<path d="M${x} 200 L${x - 26} 200 L${x} ${90 + (i % 3) * 18} L${x + 26} 200z" fill="${i % 2 ? "#13301f" : "#1c3f2a"}"/>`).join("")}
        ${Array.from({ length: 14 }, (_, i) => `<circle class="tr-firefly" style="animation-delay:${(i * 0.53) % 4}s;--dx:${(i % 5) * 6 - 12}px" cx="${(i * 47) % 300 + 10}" cy="${120 + (i * 29) % 70}" r="2" fill="#f4f19a"/>`).join("")}`,
    yurt: (id) => `${sky(id, "day")}<circle cx="60" cy="44" r="20" fill="#fff3c4"/>
        <path d="M0 160 Q 160 136 320 160 V200 H0z" fill="#c9b27a"/><path d="M0 178 Q 160 160 320 178 V200 H0z" fill="#b39a5f"/>
        <g transform="translate(170 150)"><path d="M-46 0 V-24 Q 0 -60 46 -24 V0z" fill="#f4efe2" stroke="#8a5a35" stroke-width="2"/>
          <path d="M-46 -24 Q 0 -60 46 -24" fill="none" stroke="#b42318" stroke-width="5"/><rect x="-9" y="-22" width="18" height="22" fill="#b0532c"/>
          <path d="M-36 -8 h72" stroke="#c8902e" stroke-width="3" stroke-dasharray="6 4"/></g>
        <g class="tr-soar"><path d="M0 0 q 14 -10 26 0 q 12 -10 26 0 q -12 -4 -26 4 q -14 -8 -26 -4z" fill="#3b2a1d"/></g>`,
    train: (id) => `${sky(id, "dusk")}<path d="M0 150 Q 120 120 320 150 V200 H0z" fill="#7d8f6a"/>
        <rect x="0" y="172" width="320" height="4" fill="#3b2a1d"/>${Array.from({ length: 16 }, (_, i) => `<rect x="${i * 21}" y="176" width="10" height="4" fill="#5c3a21"/>`).join("")}
        <g class="tr-rumble" transform="translate(120 128)"><rect x="0" y="0" width="90" height="36" rx="4" fill="#1f5f4a"/><rect x="62" y="-20" width="28" height="22" fill="#174a3a"/>
          <rect x="10" y="-14" width="14" height="16" fill="#174a3a"/><rect x="66" y="-14" width="10" height="9" fill="#ffd77a"/><path d="M90 26 l14 10 h-14z" fill="#b42318"/>
          ${[16, 44, 74].map((x) => `<g class="tr-wheel" style="transform-origin:${x}px 40px"><circle cx="${x}" cy="40" r="8" fill="#222"/><path d="M${x - 7} 40 h14" stroke="#888" stroke-width="2"/></g>`).join("")}
          <rect x="-70" y="6" width="64" height="30" rx="3" fill="#7a2e2e"/>${[-62, -44, -26].map((x) => `<rect x="${x}" y="12" width="12" height="10" fill="#ffd77a"/>`).join("")}</g>
        <g class="tr-steam">${[0, 1, 2].map((i) => `<circle style="animation-delay:${i * 0.6}s" cx="137" cy="100" r="${8 + i * 3}" fill="#fff" opacity=".85"/>`).join("")}</g>`,
    letter: (id) => `<rect width="320" height="200" fill="#3a2a1e"/><rect x="0" y="130" width="320" height="70" fill="#6b4a2e"/>
        <g class="tr-glow"><circle cx="230" cy="70" r="70" fill="#ffd77a" opacity=".18"/></g>
        <g transform="translate(110 128) rotate(-6)"><rect x="-60" y="-34" width="120" height="70" fill="#f4efe2"/>
          ${[0, 1, 2, 3].map((k) => `<path class="tr-write" style="animation-delay:${k * 0.8}s" d="M-48 ${-20 + k * 13} h${90 - k * 12}" stroke="#1b221f" stroke-width="2"/>`).join("")}
          <circle cx="40" cy="26" r="8" fill="#b42318"/></g>
        <g transform="translate(230 120)"><rect x="-8" y="-30" width="16" height="40" fill="#f4efe2"/><path class="tr-flame" d="M0 -48 q 9 10 0 18 q -9 -8 0 -18z" fill="#ffb347"/></g>
        <path class="tr-quill" d="M150 96 L 196 40 L 200 44 Z" fill="#e7e2d4" stroke="#8a8f99"/>`,
    duel: (id) => `${sky(id, "storm")}<path d="M0 160 H320 V200 H0z" fill="#3d3d3d"/>
        <g class="tr-lunge-l" transform="translate(96 120)"><circle cx="0" cy="-34" r="9" fill="#111"/><path d="M-8 -24 h16 l4 30 h-24z" fill="#111"/><path d="M-6 6 l-6 34 M6 6 l6 34" stroke="#111" stroke-width="6"/><path d="M8 -16 L 56 -30" stroke="#ddd" stroke-width="3"/></g>
        <g class="tr-lunge-r" transform="translate(224 120)"><circle cx="0" cy="-34" r="9" fill="#111"/><path d="M-8 -24 h16 l4 30 h-24z" fill="#111"/><path d="M-6 6 l-6 34 M6 6 l6 34" stroke="#111" stroke-width="6"/><path d="M-8 -16 L -56 -30" stroke="#ddd" stroke-width="3"/></g>
        <circle class="tr-spark" cx="160" cy="88" r="10" fill="#ffe27a"/>`,
    ball: (id) => `<rect width="320" height="200" fill="#5a1f2f"/>${[40, 120, 200, 280].map((x) => `<path d="M${x} 0 v40" stroke="#c8902e"/><circle class="tr-twinkle" cx="${x}" cy="46" r="8" fill="#ffe7a3"/>`).join("")}
        <rect y="150" width="320" height="50" fill="#3a1520"/>
        ${[[90, "#f4efe2"], [220, "#c9b6e8"]].map(([x, dress], i) => `<g class="tr-waltz" style="animation-delay:${i * 0.8}s;transform-origin:${x}px 150px">
          <circle cx="${x - 8}" cy="88" r="7" fill="#e7c9a2"/><path d="M${x - 15} 96 h14 l14 54 h-42z" fill="${dress}"/>
          <circle cx="${x + 10}" cy="84" r="7" fill="#e7c9a2"/><rect x="${x + 4}" y="92" width="12" height="58" fill="#111"/></g>`).join("")}`,
    robot: (id) => `<rect width="320" height="200" fill="#e2efe9"/>${Array.from({ length: 8 }, (_, i) => `<rect x="${12 + i * 38}" y="${20 + (i % 3) * 8}" width="${14 + (i % 4) * 5}" height="${60 - (i % 3) * 8}" fill="${["#1f5f4a", "#0f4c81", "#7a2e2e", "#c8902e"][i % 4]}"/>`).join("")}
        <rect x="0" y="84" width="320" height="6" fill="#8a5a35"/><rect y="170" width="320" height="30" fill="#c9d8cf"/>
        <g class="tr-bob" transform="translate(160 130)"><rect x="-26" y="-30" width="52" height="46" rx="8" fill="#9aa4b2"/><rect x="-18" y="-60" width="36" height="28" rx="6" fill="#b9c2cf"/>
          <circle class="tr-blink" cx="-8" cy="-46" r="4" fill="#0f6e5a"/><circle class="tr-blink" cx="8" cy="-46" r="4" fill="#0f6e5a"/><path d="M0 -60 v-10" stroke="#555" stroke-width="2"/><circle class="tr-twinkle" cx="0" cy="-72" r="3" fill="#b42318"/>
          <g class="tr-arm"><rect x="24" y="-26" width="34" height="8" rx="4" fill="#9aa4b2"/><rect x="54" y="-40" width="10" height="26" fill="#7a2e2e"/></g>
          <rect x="-20" y="16" width="12" height="22" fill="#7d8796"/><rect x="8" y="16" width="12" height="22" fill="#7d8796"/></g>`,
    rabbit: (id) => `${sky(id, "wonder")}<circle cx="70" cy="60" r="30" fill="#fff" opacity=".5"/>
        ${[30, 280, 250].map((x, i) => `<g class="tr-float" style="animation-delay:${i}s"><rect x="${x}" y="${40 + i * 30}" width="18" height="22" rx="3" fill="${["#b42318", "#0f4c81", "#c8902e"][i]}" transform="rotate(${i * 20 - 15} ${x} ${50 + i * 30})"/></g>`).join("")}
        <path d="M0 170 Q 160 150 320 170 V200 H0z" fill="#8fc48a"/>
        <g class="tr-hop" transform="translate(150 140)"><ellipse cx="0" cy="0" rx="20" ry="24" fill="#fff" stroke="#bbb"/><circle cx="0" cy="-30" r="14" fill="#fff" stroke="#bbb"/>
          <path d="M-6 -40 q -6 -30 2 -34 q 6 6 4 34z M6 -40 q 4 -30 12 -32 q 4 8 -6 34z" fill="#fff" stroke="#bbb"/><circle cx="-5" cy="-32" r="2" fill="#b42318"/>
          <path d="M-16 -8 h32 v16 h-32z" fill="#b42318"/><circle class="tr-tick" cx="24" cy="-2" r="9" fill="#ffe27a" stroke="#8a5a35" stroke-width="2"/><path class="tr-hand" d="M24 -2 v-6" stroke="#3b2a1d" stroke-width="2" style="transform-origin:24px -2px"/></g>`,
    storm: (id) => `${sky(id, "storm")}<g class="tr-drift"><ellipse cx="90" cy="40" rx="70" ry="22" fill="#2a2f3a"/><ellipse cx="230" cy="36" rx="80" ry="24" fill="#23272f"/></g>
        <path class="tr-bolt" d="M180 50 l-20 46 h16 l-14 44 l34 -56 h-18 l14 -34z" fill="#ffe27a"/>
        <g class="tr-rain">${Array.from({ length: 30 }, (_, i) => `<path d="M${(i * 23) % 330} ${(i * 31) % 200} l-6 14" stroke="#aeb7c8" stroke-width="1.5"/>`).join("")}</g>
        <path d="M0 175 H320 V200 H0z" fill="#22262e"/><rect class="tr-flash" width="320" height="200" fill="#fff"/>`,
    road: (id) => `${sky(id, "dusk")}<circle cx="160" cy="112" r="34" fill="#ffd98a"/>
        <path d="M0 120 H320 V200 H0z" fill="#8a7a55"/><path d="M150 120 L170 120 L250 200 L70 200z" fill="#c9b27a"/>
        <g class="tr-walk-up" transform="translate(160 176)"><circle cx="0" cy="-30" r="6" fill="#2b2118"/><path d="M-6 -24 h12 l3 22 h-18z" fill="#2b2118"/><path d="M8 -20 l10 -20" stroke="#2b2118" stroke-width="2"/></g>`,
    books: (id) => `<rect width="320" height="200" fill="#f2f5f1"/><g class="tr-glow"><circle cx="200" cy="60" r="70" fill="#ffd77a" opacity=".25"/></g>
        <path d="M200 30 v30 M178 66 h44 l-10 -16 h-24z" stroke="#3b3d3c" stroke-width="3" fill="#c8902e"/>
        <rect y="168" width="320" height="32" fill="#8a5a35"/>
        ${[["#1f5f4a", 20], ["#0f4c81", 16], ["#7a2e2e", 18], ["#c8902e", 14]].map(([c, h], i) => `<rect x="${80 - i * 4}" y="${168 - 18 * (i + 1)}" width="${120 + i * 6}" height="${h}" rx="2" fill="${c}"/>`).join("")}
        <g class="tr-float"><path d="M232 130 q 20 -10 40 0 v24 q -20 -10 -40 0z M272 130 q 20 -10 40 0 v24 q -20 -10 -40 0z" fill="#fff" stroke="#8a8f99"/></g>`,
    space: (id) => `<rect width="320" height="200" fill="#0b1026"/>${stars(30)}
        <g class="tr-spin-slow" style="transform-origin:220px 100px"><circle cx="220" cy="100" r="40" fill="#3fb68f"/><ellipse cx="220" cy="100" rx="66" ry="14" fill="none" stroke="#c8902e" stroke-width="4"/></g>
        <path class="tr-comet" d="M0 0 l-40 -10" stroke="#fff" stroke-width="2" stroke-linecap="round"/>
        <g class="tr-float"><circle cx="70" cy="140" r="12" fill="#f4efe2"/><path d="M62 152 h16 v22 h-16z" fill="#f4efe2"/></g>`,
};
let sceneSeq = 0;
function sceneSvg(name) {
    const draw = SCENES[name] || SCENES.books;
    const id = "s" + (++sceneSeq);
    return `<svg class="tr-scene sc-${esc(name)}" viewBox="0 0 320 200" preserveAspectRatio="xMidYMid slice" aria-hidden="true">${draw(id)}</svg>`;
}

/* ======================================================================
   Плеер трейлера: вертикальная книга, обложка распахивается,
   страницы перелистываются. Используется в окне, в ленте и в редакторе.
   ====================================================================== */
const PAGE_MS = 4300;

function pageHtml(scene, i, n) {
    return `<div class="tr-page">${sceneSvg(scene.scene)}
        <p class="tr-caption">${esc(scene.text)}</p><span class="tr-num">${i + 1} / ${n}</span></div>`;
}
function endHtml(b) {
    return `<div class="tr-page tr-end"><div class="tr-end-cover">${cover(b)}</div>
        <a class="btn primary" href="#/${b.kind === "manga" || b.has_text || !b.has_file ? "read" : "book"}/${b.id}" data-tr-read>${icon("book")}${esc(t(b.kind === "manga" ? "media.read_manga" : "media.read_now"))}</a></div>`;
}

class TrailerPlayer {
    constructor(host, book, scenes, { loop = false, onEnd = null } = {}) {
        this.host = host; this.b = book; this.scenes = scenes; this.loop = loop; this.onEnd = onEnd;
        this.i = -1; this.timer = null; this.playing = false;
        host.innerHTML = `<div class="tr-stage">
            <div class="tr-book closed"><div class="tr-under"></div><div class="tr-cover-leaf">${cover(book)}</div></div>
            <div class="tr-dots">${scenes.map(() => "<i></i>").join("")}<i></i></div></div>`;
        this.book = $(".tr-book", host);
        this.under = $(".tr-under", host);
        this.dots = $$(".tr-dots i", host);
        this.book.addEventListener("click", (e) => { if (!e.target.closest("[data-tr-read]")) this.next(); });
    }
    play() {
        if (this.playing) return;
        this.playing = true;
        if (this.i < 0) {
            this.under.innerHTML = pageHtml(this.scenes[0], 0, this.scenes.length);
            setTimeout(() => { this.book.classList.remove("closed"); this.book.classList.add("open"); this.i = 0; this.mark(); this.schedule(); },
                reduceMotion() ? 0 : 500);
        } else this.schedule();
    }
    pause() { this.playing = false; clearTimeout(this.timer); }
    schedule() { clearTimeout(this.timer); if (this.playing) this.timer = setTimeout(() => this.next(true), PAGE_MS); }
    mark() { this.dots.forEach((d, k) => d.classList.toggle("on", k === this.i)); }
    next(auto = false) {
        if (this.i < 0) { this.play(); return; }
        const n = this.scenes.length;
        if (this.i >= n) {                      // последняя страница «Читать»
            if (!this.loop) { this.pause(); this.onEnd?.(); return; }
            this.i = -1; this.book.classList.add("closed"); this.book.classList.remove("open");
            this.playing = false; setTimeout(() => this.play(), 600); return;
        }
        const old = this.under.innerHTML;
        this.i += 1;
        this.under.innerHTML = this.i < n ? pageHtml(this.scenes[this.i], this.i, n) : endHtml(this.b);
        if (!reduceMotion()) {
            const leaf = document.createElement("div");
            leaf.className = "tr-leaf";
            leaf.innerHTML = old;
            this.book.appendChild(leaf);
            leaf.addEventListener("animationend", () => leaf.remove(), { once: true });
            setTimeout(() => leaf.remove(), 1200);
        }
        this.mark();
        if (this.i >= n && !this.loop) { this.pause(); return; }
        if (auto || this.playing) this.schedule();
    }
    destroy() { this.pause(); }
}

/** Трейлер в окне поверх страницы (кнопка «Трейлер», первое открытие книги). */
async function openTrailer(b, scenes) {
    if (!scenes) {
        try { scenes = (await api(`/api/books/${b.id}/trailer`)).scenes; }
        catch (e) { toastError(e); return; }
    }
    const card = openModal(`<div class="tr-modal"><div class="tr-modal-head"><b>${esc(b.title)}</b><span class="muted small">${esc(b.author)}</span></div>
        <div id="tr-host"></div><div class="btn-row" style="justify-content:center">
        <button class="btn sm ghost" data-close>${esc(t("media.skip"))}</button></div></div>`, { wide: true, onClose: () => player.destroy() });
    card.classList.add("tr-modal-card");
    const player = new TrailerPlayer($("#tr-host", card), b, scenes);
    player.play();
    $("[data-tr-read]", card)?.addEventListener("click", closeModal);
    card.addEventListener("click", (e) => { if (e.target.closest("[data-tr-read]")) closeModal(); });
}

// Ушли на другую страницу (в том числе по команде пульта презентации) —
// закрыть окно трейлера.
window.addEventListener("hashchange", () => { if ($("#modal-card.tr-modal-card") && !$("#modal").hidden) closeModal(); });

/** На странице книги: кнопка «Трейлер» и автопоказ при первом открытии. */
function bookPageHooks(b, force = false) {
    if (!b.has_trailer) return "";
    setTimeout(() => {
        $("#tr-open")?.addEventListener("click", () => openTrailer(b));
        const key = "trailer.seen." + b.id;
        if (force || (!store.get(key) && !reduceMotion())) { store.set(key, 1); openTrailer(b); }
    }, 0);
    return `<button class="btn lg block tr-btn" id="tr-open">${icon("play")}${esc(t("media.trailer"))}</button>`;
}

/* ======================================================================
   Лента трейлеров — «книжный TikTok»
   ====================================================================== */
route(/^\/trailers$/, async (view) => {
    setTitle(t("media.feed"));
    view.classList.add("wide");
    view.innerHTML = `<div class="feed-head"><div><h1>${esc(t("media.feed"))}</h1><p class="muted">${esc(t("media.feed_lead"))}</p></div></div>
        <div class="feed" id="feed"></div><div id="feed-more"></div>`;
    const feed = $("#feed");
    const players = new Map();
    let page = 1, pages = 1, loading = false;
    const io = new IntersectionObserver((entries) => {
        for (const e of entries) {
            const p = players.get(e.target);
            if (!p) continue;
            if (e.isIntersecting && e.intersectionRatio > 0.6) p.play(); else p.pause();
        }
    }, { threshold: [0, 0.6, 1] });
    async function load() {
        if (loading || page > pages) return;
        loading = true;
        const d = await api(`/api/trailers?page=${page}&page_size=6`);
        pages = d.pages; page += 1;
        if (!d.items.length && page === 2) feed.innerHTML = emptyState("play", t("media.feed_empty"));
        for (const b of d.items) {
            const el = document.createElement("article");
            el.className = "feed-item";
            el.innerHTML = `<div class="feed-player"></div>
              <div class="feed-info"><span class="badge">${esc(t(b.kind === "manga" ? "media.kind_manga" : "media.kind_book"))}</span>
                <h2><a href="#/book/${b.id}">${esc(b.title)}</a></h2><div class="muted">${esc(b.author)}</div>
                <p class="small muted">${esc(b.description).slice(0, 180)}</p>
                <div class="btn-row"><a class="btn primary" href="#/${b.kind === "manga" || b.has_text || !b.has_file ? "read" : "book"}/${b.id}">${icon("book")}${esc(t(b.kind === "manga" ? "media.read_manga" : "media.read_now"))}</a>
                <a class="btn" href="#/book/${b.id}">${esc(t("book.details"))}</a></div>
                <div class="small muted">${icon("star", "i-sm")} ${b.rating ?? "—"} · ${esc(t("book.reads"))}: ${fmtNum(b.reads)}</div></div>`;
            feed.appendChild(el);
            const p = new TrailerPlayer($(".feed-player", el), b, b.trailer.scenes, { loop: true });
            players.set(el, p);
            io.observe(el);
        }
        loading = false;
    }
    await load();
    // Подгрузка следующих трейлеров, когда долистали до конца.
    const more = new IntersectionObserver((e) => { if (e[0].isIntersecting) load().catch(() => {}); });
    more.observe($("#feed-more"));
    const stop = () => { players.forEach((p) => p.destroy()); io.disconnect(); more.disconnect(); window.removeEventListener("hashchange", stop); };
    window.addEventListener("hashchange", stop);
});

/* ======================================================================
   Анимация открытия книги перед чтением
   ====================================================================== */
function openingAnimation(b) {
    if (reduceMotion() || store.get("opening.off")) return;
    const el = document.createElement("div");
    el.className = "book-opening";
    el.innerHTML = `<div class="bo-book"><div class="bo-pages"><span></span><span></span><span></span></div><div class="bo-cover">${cover(b)}</div></div>`;
    document.body.appendChild(el);
    el.addEventListener("click", () => el.remove());
    setTimeout(() => el.classList.add("done"), 1250);
    setTimeout(() => el.remove(), 1700);
}

/* ======================================================================
   Читалка манги: страницы-картинки и перевод поверх них
   ====================================================================== */
const TR_LANGS = ["ru", "kk", "ky", "en"];

async function mangaReader(view, b, params) {
    setTitle(b.title);
    let pages;
    try { pages = await api(`/api/books/${b.id}/pages`); }
    catch (err) {
        if (err.status !== 403) throw err;
        view.innerHTML = emptyState("lock", t("book.paid_title"), Oqu.errorText(err), `<a class="btn primary" href="#/book/${b.id}">${esc(t("book.details"))}</a>`);
        return;
    }
    const u = Oqu.state.user;
    const aiOn = await api("/api/ai/status").then((s) => s.enabled).catch(() => false);
    let lang = store.get("manga.lang", TR_LANGS.includes(Oqu.state.lang) ? Oqu.state.lang : "ru");
    view.classList.add("wide");
    document.body.classList.add("reading");
    view.innerHTML = `<div class="manga">
      <div class="reader-bar manga-bar">
        <a class="icon-btn" href="#/book/${b.id}" aria-label="${esc(t("common.back"))}">${icon("left")}</a>
        <div class="title">${esc(b.title)} <span class="muted small" id="mg-pos"></span></div>
        <label class="mg-lang">${icon("translate")}<select class="select" id="mg-lang" aria-label="${esc(t("media.translation"))}">
          <option value="orig">${esc(t("media.original"))}</option>${TR_LANGS.map((l) => `<option value="${l}" ${l === lang ? "selected" : ""}>${esc(t("lang." + l))}</option>`).join("")}</select></label>
        <button class="btn sm" id="mg-ai" hidden>${icon("spark")}<span>${esc(t("media.ai_translate"))}</span></button>
        <div class="reader-progress" id="mg-progress"></div>
      </div>
      <div class="mg-note small muted" id="mg-note"></div>
      <div class="mg-pages" id="mg-pages">${pages.length ? pages.map((p) => `<figure class="mg-page" data-pid="${p.id}" data-idx="${p.idx}" style="aspect-ratio:${p.width}/${p.height}">
          <img src="${esc(p.url)}" alt="${esc(t("reader.page_n", { n: p.idx }))}" loading="lazy" width="${p.width}" height="${p.height}">
          <div class="mg-layer"></div></figure>`).join("") : emptyState("image", t("media.no_pages"))}</div>
      <div class="mg-end">${esc(t("media.manga_end"))} <a href="#/book/${b.id}">${esc(t("book.details"))}</a></div></div>`;
    if (!pages.length) return;
    let translations = {};

    const fitAll = () => $$(".mg-box").forEach(fitBox);
    async function loadLang() {
        const sel = $("#mg-lang").value;
        if (sel === "orig") { translations = {}; render(); return; }
        lang = sel; store.set("manga.lang", lang);
        translations = await api(`/api/books/${b.id}/translations?lang=${lang}`).catch(() => ({}));
        render();
    }
    function render() {
        const sel = $("#mg-lang").value;
        let missing = 0;
        $$(".mg-page").forEach((fig) => {
            const boxes = sel === "orig" ? null : translations[fig.dataset.pid];
            if (sel !== "orig" && !boxes) missing += 1;
            $(".mg-layer", fig).innerHTML = (boxes || []).map((x) =>
                `<div class="mg-box ${x.shape === "oval" ? "oval" : "rect"}" style="left:${x.x}%;top:${x.y}%;width:${x.w}%;height:${x.h}%" title="${esc(x.src)}"><span>${esc(x.text)}</span></div>`).join("");
        });
        requestAnimationFrame(fitAll);
        const btn = $("#mg-ai");
        btn.hidden = !(sel !== "orig" && missing);
        $("#mg-note").textContent = sel === "orig" ? t("media.orig_hint")
            : missing ? (aiOn ? t("media.missing_ai", { n: missing }) : t("media.missing_noai", { n: missing })) : t("media.tr_ready");
        btn.disabled = !aiOn || !u;
    }
    $("#mg-lang").value = store.get("manga.view", "tr") === "orig" ? "orig" : lang;
    $("#mg-lang").addEventListener("change", () => { store.set("manga.view", $("#mg-lang").value === "orig" ? "orig" : "tr"); loadLang(); });
    $("#mg-ai").addEventListener("click", async () => {
        if (!Oqu.requireLogin()) return;
        const btn = $("#mg-ai");
        btn.disabled = true;
        const todo = $$(".mg-page").filter((f) => !translations[f.dataset.pid]);
        let k = 0;
        for (const fig of todo) {
            k += 1;
            $("span", btn).textContent = t("media.translating", { k, n: todo.length });
            fig.classList.add("mg-busy");
            try {
                translations[fig.dataset.pid] = await api(`/api/manga/pages/${fig.dataset.pid}/translate`, { method: "POST", body: { lang } });
                render();
            } catch (e) { toastError(e); fig.classList.remove("mg-busy"); break; }
            fig.classList.remove("mg-busy");
        }
        $("span", btn).textContent = t("media.ai_translate");
        render();
    });
    // Длинное нажатие на рамку — показать оригинальную реплику.
    $("#mg-pages").addEventListener("click", (e) => {
        const box = e.target.closest(".mg-box");
        if (box) box.classList.toggle("peek");
    });
    window.addEventListener("resize", fitAll);
    await loadLang();

    // Прогресс: какая страница на экране; место сохраняется.
    const total = pages.length;
    let current = 1;
    const saveProgress = Oqu.debounce(() => {
        store.set("progress." + b.id + ".manga", current);
        if (u) api(`/api/me/progress/${b.id}`, { method: "PUT", body: { position: current } }).catch(() => {});
    }, 1200);
    const io = new IntersectionObserver((entries) => {
        for (const e of entries) if (e.isIntersecting) {
            current = Number(e.target.dataset.idx);
            $("#mg-pos").textContent = t("media.page_of", { k: current, n: total });
            $("#mg-progress").style.setProperty("--p", (current / total) * 100 + "%");
            saveProgress();
        }
    }, { rootMargin: "-45% 0px -45% 0px" });
    $$(".mg-page").forEach((f) => io.observe(f));
    const start = Number(params.get("page")) || b.position || store.get("progress." + b.id + ".manga", 1);
    if (start > 1) setTimeout(() => $(`.mg-page[data-idx="${start}"]`)?.scrollIntoView(), 60);
    const stop = () => { io.disconnect(); window.removeEventListener("resize", fitAll); window.removeEventListener("hashchange", stop); };
    window.addEventListener("hashchange", stop);
}

/** Уменьшать шрифт реплики, пока текст не поместится в рамку облачка. */
function fitBox(box) {
    const span = box.firstElementChild;
    // Прямоугольные подписи (рамки-плашки) заполняем целиком, овалы — на 80%.
    const oval = box.classList.contains("oval");
    const h = box.clientHeight * (oval ? 0.84 : 0.96), w = box.clientWidth * (oval ? 0.8 : 0.94);
    let size = Math.max(9, Math.min(26, h / 2.2, w / 2.6));
    span.style.fontSize = size + "px";
    while (size > 7 && (span.scrollHeight > h || span.scrollWidth > w)) {
        size -= 0.5;
        span.style.fontSize = size + "px";
    }
}

/* ======================================================================
   Редактор книги: тип издания, трейлер (вручную или ИИ), страницы манги
   ====================================================================== */
const SCENE_IDS = Object.keys(SCENES);

function editorHtml(book) {
    if (!book) return `<div class="card section"><h2>${icon("play")} ${esc(t("media.editor_title"))}</h2><p class="muted small">${esc(t("media.after_save"))}</p></div>`;
    return `${book.kind === "manga" ? `<div class="card section" id="ed-manga"><h2>${icon("image")} ${esc(t("media.pages_title"))}</h2>
        <p class="muted small">${esc(t("media.pages_hint"))}</p>
        <div class="mg-thumbs" id="mg-thumbs"></div>
        <label class="drop">${icon("upload")}<div id="mg-up-name">${esc(t("media.pages_load"))}</div><input type="file" id="mg-files" accept="image/png,image/jpeg,image/webp" multiple></label></div>` : ""}
      <div class="card section" id="ed-trailer"><h2>${icon("play")} ${esc(t("media.editor_title"))}</h2>
        <p class="muted small">${esc(t("media.editor_hint"))}</p>
        <div id="tr-rows"></div>
        <div class="btn-row" style="margin-top:10px">
          <button type="button" class="btn sm" id="tr-add">${icon("plus")}${esc(t("media.scene_add"))}</button>
          <button type="button" class="btn sm" id="tr-ai">${icon("spark")}${esc(t("media.ai_generate"))}</button>
          <button type="button" class="btn sm" id="tr-preview">${icon("play")}${esc(t("media.preview"))}</button>
          <button type="button" class="btn sm primary" id="tr-save">${esc(t("media.trailer_save"))}</button>
          <button type="button" class="btn sm ghost" id="tr-del" ${book.has_trailer ? "" : "hidden"}>${icon("trash")}${esc(t("common.delete"))}</button>
        </div><small class="hint" id="tr-ai-note"></small></div>`;
}

async function bindEditor(book) {
    if (!book) return;
    let scenes = [];
    if (book.has_trailer) scenes = (await api(`/api/books/${book.id}/trailer`).catch(() => ({ scenes: [] }))).scenes;
    if (!scenes.length) scenes = [{ scene: "books", text: "" }, { scene: "road", text: "" }, { scene: "space", text: "" }];
    const rows = $("#tr-rows");
    const draw = () => {
        rows.innerHTML = scenes.map((s, i) => `<div class="tr-row" data-i="${i}">
            <div class="tr-thumb">${sceneSvg(s.scene)}</div>
            <div class="tr-row-fields"><select class="select" data-k="scene">${SCENE_IDS.map((id) => `<option value="${id}" ${id === s.scene ? "selected" : ""}>${esc(t("scene." + id))}</option>`).join("")}</select>
            <textarea class="textarea" data-k="text" maxlength="160" rows="2" placeholder="${esc(t("media.scene_ph"))}">${esc(s.text)}</textarea></div>
            <button type="button" class="icon-btn" data-rm aria-label="${esc(t("common.delete"))}">${icon("x")}</button></div>`).join("");
        $$(".tr-row", rows).forEach((row) => {
            const i = Number(row.dataset.i);
            $("[data-k=scene]", row).addEventListener("change", (e) => { scenes[i].scene = e.target.value; draw(); });
            $("[data-k=text]", row).addEventListener("input", (e) => { scenes[i].text = e.target.value; });
            $("[data-rm]", row).addEventListener("click", () => { if (scenes.length > 3) { scenes.splice(i, 1); draw(); } });
        });
        $("#tr-add").disabled = scenes.length >= 8;
    };
    draw();
    $("#tr-add").addEventListener("click", () => { scenes.push({ scene: "books", text: "" }); draw(); });
    $("#tr-preview").addEventListener("click", () => {
        const ready = scenes.filter((s) => s.text.trim());
        if (ready.length < 3) return toast(t("media.need3"), "error");
        openTrailer(book, ready);
    });
    $("#tr-save").addEventListener("click", async () => {
        try {
            await api(`/api/books/${book.id}/trailer`, { method: "PUT", body: { scenes: scenes.filter((s) => s.text.trim()) } });
            $("#tr-del").hidden = false;
            toast(t("media.trailer_saved"), "ok");
        } catch (e) { toastError(e); }
    });
    $("#tr-del").addEventListener("click", async () => {
        if (!await confirmDialog({ title: t("media.trailer_del_q"), ok: t("common.delete"), danger: true })) return;
        try { await api(`/api/books/${book.id}/trailer`, { method: "DELETE" }); $("#tr-del").hidden = true; toast(t("common.saved"), "ok"); }
        catch (e) { toastError(e); }
    });
    const aiOn = await api("/api/ai/status").then((s) => s.enabled).catch(() => false);
    $("#tr-ai").disabled = !aiOn;
    $("#tr-ai-note").textContent = aiOn ? t("media.ai_note") : t("media.ai_off");
    $("#tr-ai").addEventListener("click", async () => {
        const btn = $("#tr-ai");
        btn.disabled = true; btn.classList.add("loading");
        try {
            scenes = (await api(`/api/books/${book.id}/trailer/generate`, { method: "POST" })).scenes;
            draw(); $("#tr-del").hidden = false;
            toast(t("media.ai_done"), "ok");
            openTrailer(book, scenes);
        } catch (e) { toastError(e); }
        btn.disabled = false; btn.classList.remove("loading");
    });

    if (book.kind !== "manga") return;
    const thumbs = async () => {
        const pages = await api(`/api/books/${book.id}/pages`).catch(() => []);
        $("#mg-thumbs").innerHTML = pages.length ? pages.map((p) => `<div class="mg-thumb"><img src="${esc(p.url)}" alt="" loading="lazy">
            <span>${p.idx}${p.langs.length ? " · " + p.langs.join(", ") : ""}</span><button type="button" class="icon-btn" data-pdel="${p.id}" aria-label="${esc(t("common.delete"))}">${icon("trash", "i-sm")}</button></div>`).join("")
            : `<p class="muted small">${esc(t("media.no_pages"))}</p>`;
        $$("[data-pdel]").forEach((x) => x.addEventListener("click", async () => {
            if (!await confirmDialog({ title: t("media.page_del_q"), ok: t("common.delete"), danger: true })) return;
            try { await api(`/api/manga/pages/${x.dataset.pdel}`, { method: "DELETE" }); thumbs(); }
            catch (e) { toastError(e); }
        }));
    };
    thumbs();
    $("#mg-files").addEventListener("change", async (e) => {
        // Файлы загружаются по порядку имён: 001.png, 002.png, …
        const files = [...e.target.files].sort((a, c) => a.name.localeCompare(c.name, undefined, { numeric: true }));
        e.target.value = "";
        let k = 0;
        for (const f of files) {
            k += 1;
            $("#mg-up-name").textContent = t("media.uploading", { k, n: files.length });
            if (f.size > 8 * 1024 * 1024) { toast(t("media.page_big", { name: f.name }), "error"); continue; }
            const fd = new FormData(); fd.append("file", f);
            try { await api(`/api/books/${book.id}/pages`, { method: "POST", form: fd }); }
            catch (err) { toastError(err); break; }
        }
        $("#mg-up-name").textContent = t("media.pages_load");
        toast(t("media.pages_done"), "ok");
        thumbs();
    });
}

Oqu.media = { TrailerPlayer, openTrailer, bookPageHooks, openingAnimation, mangaReader, editorHtml, bindEditor, sceneSvg, SCENES };
})();
