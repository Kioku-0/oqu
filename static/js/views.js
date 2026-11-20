/* =====================================================================
   Оқу — страницы: главная, каталог, шкаф, книга, читалка, полка,
   профиль, статистика, редактор книги, юридические страницы.
   ===================================================================== */
"use strict";

(() => {
const { $, $$, esc, icon, t, plural, api, can, store, toast, toastError, openModal, closeModal,
    confirmDialog, formDialog, requireLogin, setTitle, emptyState, cover, starsMini, pager, fmtDate,
    fmtAgo, fmtNum, avatar, roleBadge, debounce } = Oqu;
const route = (p, h, o) => Oqu.router.add(p, h, o);

const SHELVES = ["reading", "want", "read", "dropped"];
const LANG_NAMES = { ru: "lang.ru", kk: "lang.kk", en: "lang.en" };
const COVER_PATTERNS = ["auto", "plain", "stripes", "diagonal", "dots", "grid", "waves", "ornament", "frame", "band", "sun"];
const COLORS = ["#1f5f4a", "#0f4c81", "#7a2e2e", "#b0532c", "#6b3fa0", "#2f7f8f", "#a3782a", "#3d3d3d", "#9b3b54", "#4f7a2e"];

/* ---------- Общие элементы ---------------------------------------------- */
function tile(b, extra = "") {
    return `<a class="book-tile" href="#/book/${b.id}">${cover(b)}
        <div><div class="t">${esc(b.title)}</div><div class="a">${esc(b.author)}</div>
        <div class="meta-line">${starsMini(b)}${b.year ? `<span>${b.year}</span>` : ""}${extra}</div></div></a>`;
}
function skeletonGrid(n = 10) {
    return `<div class="books-grid">${Array.from({ length: n }, () =>
        `<div><div class="skeleton sk-cover"></div><div class="skeleton sk-line"></div><div class="skeleton sk-line" style="width:60%"></div></div>`).join("")}</div>`;
}
/** Прогресс: у текстовых книг — промилле (0–1000), у PDF без текста — номер страницы. */
function progressLabel(b) {
    if (!b.position) return t("book.not_started");
    return b.has_text ? `${Math.round(b.position / 10)}%` : t("reader.page_n", { n: b.position });
}
function progressBar(b) {
    const pct = b.has_text ? Math.min(100, Math.round((b.position || 0) / 10)) : 0;
    return `<div class="progress" title="${esc(progressLabel(b))}"><i style="width:${pct}%"></i></div>`;
}
const genreName = (g) => (g ? (Oqu.state.t["genre." + g] || g) : "—");

/* ======================================================================
   Главная
   ====================================================================== */
route(/^\/$/, async (view) => {
    setTitle("");
    view.innerHTML = `<section class="hero">
        <div>
          <h1>${esc(t("home.title"))}</h1>
          <p class="lead">${esc(t("home.lead"))}</p>
          <div class="btn-row"><a class="btn primary lg" href="#/catalog">${icon("grid")}${esc(t("home.to_catalog"))}</a>
          <a class="btn lg" href="#/bookcase">${icon("case")}${esc(t("home.to_case"))}</a></div>
        </div>
        <div class="hero-stack" id="hero-stack"></div>
      </section>
      <div id="home-continue"></div>
      <section class="section"><div class="stat-row" id="home-stats">${'<div class="stat skeleton" style="height:84px"></div>'.repeat(4)}</div></section>
      <section class="section"><div class="section-head"><h2>${esc(t("home.genres"))}</h2></div><div class="chips" id="home-genres"></div></section>
      <section class="section"><div class="section-head"><h2>${esc(t("home.new"))}</h2><a href="#/catalog?sort=-created_at">${esc(t("common.all"))} →</a></div><div class="strip" id="home-new"></div></section>
      <section class="section"><div class="section-head"><h2>${esc(t("home.popular"))}</h2><a href="#/catalog?sort=-popular">${esc(t("common.all"))} →</a></div><div class="strip" id="home-pop"></div></section>
      <section class="section"><div class="section-head"><h2>${esc(t("home.rated"))}</h2><a href="#/catalog?sort=-rating">${esc(t("common.all"))} →</a></div><div class="strip" id="home-rated"></div></section>`;

    const strip = (sel, items) => { $(sel).innerHTML = items.length ? items.map((b) => tile(b)).join("") : `<p class="muted">${esc(t("catalog.empty"))}</p>`; };
    const jobs = [
        api("/api/books?sort=created_at&order=desc&page_size=12").then((d) => {
            strip("#home-new", d.items);
            $("#hero-stack").innerHTML = d.items.slice(0, 3).map((b) =>
                `<a href="#/book/${b.id}" aria-label="${esc(b.title)}">${cover(b)}</a>`).join("");
        }),
        api("/api/books?sort=popular&order=desc&page_size=12").then((d) => strip("#home-pop", d.items)),
        api("/api/books?sort=rating&order=desc&page_size=12").then((d) => strip("#home-rated", d.items)),
        api("/api/stats").then((s) => {
            $("#home-stats").innerHTML = [
                [s.total_books, "home.stat_books"], [s.total_users, "home.stat_users"],
                [s.total_read, "home.stat_read"], [s.reading_now, "home.stat_reading"]]
                .map(([n, k]) => `<div class="stat"><b>${fmtNum(n)}</b><span>${esc(t(k))}</span></div>`).join("");
            $("#home-genres").innerHTML = s.genres.map((g) =>
                `<a class="chip" href="#/catalog?genre=${encodeURIComponent(g.name)}">${esc(genreName(g.name))} <span class="n">${g.count}</span></a>`).join("");
        }),
    ];
    if (Oqu.state.user) {
        jobs.push(api("/api/me/summary").then((s) => {
            if (!s.continue.length) return;
            $("#home-continue").innerHTML = `<section class="section"><div class="section-head"><h2>${esc(t("home.continue"))}</h2>
                <a href="#/shelf">${esc(t("nav.shelf"))} →</a></div><div class="continue-grid">${s.continue.slice(0, 4).map(continueCard).join("")}</div></section>`;
        }));
    }
    await Promise.allSettled(jobs);
});

function continueCard(b) {
    return `<a class="continue-card" href="#/read/${b.id}">${cover(b)}
        <div style="min-width:0"><div class="t" style="font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(b.title)}</div>
        <div class="small muted" style="margin-bottom:8px">${esc(b.author)} · ${esc(fmtAgo(b.read_at))}</div>
        ${progressBar(b)}<div class="small muted" style="margin-top:4px">${esc(progressLabel(b))}</div></div></a>`;
}

route(/^\/login$/, async (view) => {
    location.replace("#/");
    if (!Oqu.state.user) setTimeout(() => Oqu.openAuth("login"), 50);
});

/* ======================================================================
   Каталог: поиск, фильтры, сортировка, 3 режима вида, пагинация
   ====================================================================== */
const SORTS = [["title", "sort.title"], ["author", "sort.author"], ["-created_at", "sort.new"],
    ["-popular", "sort.popular"], ["-rating", "sort.rating"], ["-year", "sort.year_desc"], ["year", "sort.year_asc"]];

route(/^\/catalog$/, async (view, _m, params) => {
    setTitle(t("nav.catalog"));
    const viewMode = store.get("view", "grid");
    $("#search-input").value = params.get("query") || "";
    view.innerHTML = `<div class="page-head"><h1>${esc(t("nav.catalog"))}</h1></div>
      <div class="catalog">
        <aside class="filters" id="filters"></aside>
        <div>
          <div class="toolbar">
            <div class="left">
              <button class="btn sm filters-toggle" id="filters-toggle">${icon("filter")}${esc(t("catalog.filters"))}</button>
              <span class="muted" id="cat-total"></span>
            </div>
            <div class="left">
              <select class="select" id="cat-sort" style="width:auto" aria-label="${esc(t("catalog.sort"))}">
                ${SORTS.map(([v, k]) => `<option value="${v}">${esc(t(k))}</option>`).join("")}</select>
              <div class="seg" role="group" aria-label="${esc(t("catalog.view"))}">
                ${[["grid", "grid"], ["list", "list"], ["table", "table"]].map(([m, ic]) =>
                    `<button data-view="${m}" aria-pressed="${viewMode === m}" title="${esc(t("view." + m))}">${icon(ic)}</button>`).join("")}
              </div>
            </div>
          </div>
          <div id="active-filters" class="chips" style="margin-bottom:14px"></div>
          <div id="cat-results">${skeletonGrid()}</div>
          <div id="cat-pager"></div>
        </div>
      </div>`;

    // Сортировка хранится в адресе в виде «-поле» (минус — по убыванию).
    const sortValue = params.get("sort") || "title";
    $("#cat-sort").value = SORTS.some(([v]) => v === sortValue) ? sortValue : "title";
    $("#cat-sort").addEventListener("change", (e) => update({ sort: e.target.value, page: null }));
    $$("[data-view]").forEach((b) => b.addEventListener("click", () => {
        store.set("view", b.dataset.view);
        $$("[data-view]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
        load();
    }));
    $("#filters-toggle").addEventListener("click", () => $("#filters").classList.toggle("open"));

    function update(changes) {
        const p = Oqu.router.parse().params;
        for (const [k, v] of Object.entries(changes)) { if (v === null || v === "") p.delete(k); else p.set(k, v); }
        Oqu.router.setParams(p);
        renderFilters();
        load();
    }

    const [genres, tags] = await Promise.all([api("/api/genres").catch(() => []), api("/api/tags").catch(() => [])]);

    function renderFilters() {
        const p = Oqu.router.parse().params;
        const opt = (key, value, label, n) => `<button data-f="${key}" data-v="${esc(value)}" aria-pressed="${(p.get(key) || "") === value}">
            <span>${esc(label)}</span>${n !== undefined ? `<span class="muted">${n}</span>` : ""}</button>`;
        $("#filters").innerHTML = `
          <div><h3>${esc(t("filter.genre"))}</h3><div class="filter-list">${opt("genre", "", t("common.all"))}${genres.map((g) => opt("genre", g.name, genreName(g.name), g.count)).join("")}</div></div>
          <div><h3>${esc(t("filter.language"))}</h3><div class="filter-list">${opt("language", "", t("common.all"))}${["ru", "kk", "en"].map((l) => opt("language", l, t(LANG_NAMES[l]))).join("")}</div></div>
          <div><h3>${esc(t("filter.access"))}</h3><div class="filter-list">${opt("access", "", t("common.all"))}${opt("access", "free", t("filter.free"))}${opt("access", "paid", t("filter.paid"))}</div></div>
          <div><h3>${esc(t("filter.years"))}</h3><div class="row" style="grid-template-columns:1fr 1fr">
            <input class="input" type="number" min="0" max="2100" id="f-yf" placeholder="${esc(t("filter.from"))}" value="${esc(p.get("year_from") || "")}">
            <input class="input" type="number" min="0" max="2100" id="f-yt" placeholder="${esc(t("filter.to"))}" value="${esc(p.get("year_to") || "")}"></div></div>
          <div><h3>${esc(t("filter.author"))}</h3><input class="input" id="f-author" maxlength="100" value="${esc(p.get("author") || "")}" placeholder="${esc(t("filter.author_ph"))}"></div>
          ${tags.length ? `<div><h3>${esc(t("filter.tags"))}</h3><div class="chips">${tags.map((tg) =>
            `<button class="chip" data-tag="${esc(tg.name)}" aria-pressed="${p.get("tag") === tg.name}">#${esc(tg.name)}</button>`).join("")}</div></div>` : ""}
          <button class="btn ghost sm" id="f-reset">${icon("x")}${esc(t("filter.reset"))}</button>`;
        $$("#filters [data-f]").forEach((b) => b.addEventListener("click", () => update({ [b.dataset.f]: b.dataset.v, page: null })));
        $$("#filters [data-tag]").forEach((b) => b.addEventListener("click", () =>
            update({ tag: p.get("tag") === b.dataset.tag ? null : b.dataset.tag, page: null })));
        const years = debounce(() => update({ year_from: $("#f-yf").value, year_to: $("#f-yt").value, page: null }), 600);
        $("#f-yf").addEventListener("input", years);
        $("#f-yt").addEventListener("input", years);
        $("#f-author").addEventListener("input", debounce((e) => update({ author: e.target.value.trim(), page: null }), 500));
        $("#f-reset").addEventListener("click", () => { Oqu.router.setParams(new URLSearchParams()); $("#search-input").value = ""; renderFilters(); load(); });

        // Активные фильтры — «чипсы» с крестиком над результатами.
        const active = [];
        if (p.get("query")) active.push(["query", `«${p.get("query")}»`]);
        if (p.get("genre")) active.push(["genre", genreName(p.get("genre"))]);
        if (p.get("language")) active.push(["language", t(LANG_NAMES[p.get("language")])]);
        if (p.get("access")) active.push(["access", t("filter." + p.get("access"))]);
        if (p.get("tag")) active.push(["tag", "#" + p.get("tag")]);
        if (p.get("author")) active.push(["author", p.get("author")]);
        if (p.get("year_from") || p.get("year_to")) active.push(["years", `${p.get("year_from") || "…"}–${p.get("year_to") || "…"}`]);
        $("#active-filters").innerHTML = active.map(([k, label]) =>
            `<button class="chip active" data-clear="${k}">${esc(label)} ${icon("x", "i-sm")}</button>`).join("");
        $$("[data-clear]").forEach((b) => b.addEventListener("click", () => {
            if (b.dataset.clear === "query") $("#search-input").value = "";
            update(b.dataset.clear === "years" ? { year_from: null, year_to: null, page: null } : { [b.dataset.clear]: null, page: null });
        }));
    }

    async function load() {
        const p = Oqu.router.parse().params;
        const q = new URLSearchParams();
        for (const k of ["query", "genre", "language", "access", "tag", "author", "year_from", "year_to"]) if (p.get(k)) q.set(k, p.get(k));
        const s = p.get("sort") || "title";
        q.set("sort", s.replace("-", ""));
        q.set("order", s.startsWith("-") ? "desc" : "asc");
        q.set("page", p.get("page") || "1");
        q.set("page_size", "24");
        const res = $("#cat-results");
        res.style.opacity = ".5";
        try {
            const d = await api("/api/books?" + q);
            res.style.opacity = "";
            $("#cat-total").textContent = plural(d.total, "catalog.found");
            const mode = store.get("view", "grid");
            if (!d.items.length) {
                res.innerHTML = emptyState("book", t("catalog.empty"), t("catalog.empty_hint"));
            } else if (mode === "list") {
                res.innerHTML = `<div class="books-list">${d.items.map((b) => `<a class="book-row" href="#/book/${b.id}">${cover(b)}
                    <div style="min-width:0"><b>${esc(b.title)}</b><div class="muted">${esc(b.author)}${b.year ? " · " + b.year : ""}</div>
                    <div class="d">${esc(b.description)}</div></div>
                    <div class="meta-line" style="flex-direction:column;align-items:flex-end">${starsMini(b)}
                    <span class="badge ${b.is_paid ? "paid" : "free"}">${esc(t(b.is_paid ? "book.paid" : "book.free"))}</span>
                    <span>${esc(genreName(b.genre))}</span></div></a>`).join("")}</div>`;
            } else if (mode === "table") {
                res.innerHTML = `<div class="table-wrap"><table class="data"><thead><tr>
                    <th>${esc(t("book.title"))}</th><th>${esc(t("book.author"))}</th><th>${esc(t("book.year"))}</th>
                    <th>${esc(t("book.genre"))}</th><th>${esc(t("book.language"))}</th><th>${esc(t("book.rating"))}</th><th>${esc(t("book.access"))}</th></tr></thead>
                    <tbody>${d.items.map((b) => `<tr><td><span class="swatch" style="background:${esc(b.cover_color)}"></span><a href="#/book/${b.id}">${esc(b.title)}</a></td>
                    <td>${esc(b.author)}</td><td>${b.year ?? "—"}</td><td>${esc(genreName(b.genre))}</td><td>${esc(b.language.toUpperCase())}</td>
                    <td>${b.rating ? starsMini(b) : "—"}</td><td><span class="badge ${b.is_paid ? "paid" : "free"}">${esc(t(b.is_paid ? "book.paid" : "book.free"))}</span></td></tr>`).join("")}</tbody></table></div>`;
            } else {
                res.innerHTML = `<div class="books-grid">${d.items.map((b) => tile(b)).join("")}</div>`;
            }
            $("#cat-pager").innerHTML = pager(d, (n) => { update({ page: n > 1 ? n : null }); window.scrollTo({ top: 0, behavior: "smooth" }); });
        } catch (err) {
            res.style.opacity = "";
            res.innerHTML = emptyState("book", t("error.title"), Oqu.errorText(err));
        }
    }

    renderFilters();
    await load();
});

/* ======================================================================
   Шкаф: случайные книги выбранного жанра на деревянных полках
   ====================================================================== */
const hash = Oqu.hash;
const SHELF_COUNT = 4;
const ANIMS = ["pull", "tilt", "slide", "spin", "rise"];

/* Декор шкафа — маленькие SVG-рисунки (иллюстрация, не интерфейс). */
const DECOR = {
    plant: [44, 74, `<path d="M10 52h24l-3 20H13z" fill="#b5653a"/><rect x="8" y="48" width="28" height="6" rx="2" fill="#c97a4b"/>
        <path d="M22 48C22 33 13 25 4 22c4 11 9 20 18 26zM22 48c0-17 7-28 18-32-2 13-7 24-18 32zM22 48c-2-16 0-30 0-44 6 11 7 29 0 44z" fill="#4f8a4b"/>
        <path d="M22 48c-1-9-5-15-10-18M22 48c1-10 5-17 10-21" stroke="#3b6b38" stroke-width="1.2" fill="none"/>`],
    globe: [46, 76, `<path d="M8 30a17 17 0 0 0 30 10" stroke="#8a6a3a" stroke-width="2.5" fill="none"/>
        <circle cx="23" cy="28" r="16" fill="#3b7ea1"/><path d="M14 18c4 2 6 6 4 9s1 6 4 6 2 5-1 7M28 14c-2 4 2 6 5 6s4 5 1 8" stroke="#6fae5c" stroke-width="4" fill="none" stroke-linecap="round"/>
        <rect x="21" y="52" width="4" height="12" fill="#8a6a3a"/><rect x="11" y="64" width="24" height="6" rx="2" fill="#6b4c2a"/>`],
    hourglass: [26, 52, `<rect x="2" y="2" width="22" height="4" rx="1.5" fill="#6b4c2a"/><rect x="2" y="46" width="22" height="4" rx="1.5" fill="#6b4c2a"/>
        <path d="M5 6h16c0 10-7 12-7 20s7 10 7 20H5c0-10 7-12 7-20S5 16 5 6z" fill="rgba(220,235,245,.55)" stroke="#c9d6dc"/>
        <path d="M8 40h10l-5-8z" fill="#e2b866"/><path d="M8 12h10c-1 4-4 6-5 8-1-2-4-4-5-8z" fill="#e2b866"/>`],
    candle: [24, 66, `<path d="M12 4c3 4 3 7 0 9-3-2-3-5 0-9z" fill="#ffcf5a"/><path d="M12 7c1.5 2 1.5 4 0 5-1.5-1-1.5-3 0-5z" fill="#fff4c2"/>
        <rect x="8" y="14" width="8" height="34" rx="2" fill="#f4ecd8"/><rect x="2" y="48" width="20" height="4" rx="2" fill="#a8873f"/>
        <rect x="9" y="52" width="6" height="8" fill="#a8873f"/><rect x="3" y="60" width="18" height="5" rx="2" fill="#8a6d2f"/>`],
    bookend: [18, 60, `<path d="M2 58V6h6v46h8v6z" fill="#3b3b3b"/><path d="M2 6h6v4H2z" fill="#575757"/>`],
    frame: [52, 62, `<rect x="2" y="2" width="48" height="56" rx="2" fill="#7a5532"/><rect x="7" y="7" width="38" height="46" fill="#e9dfc7"/>
        <path d="M7 44l11-14 8 9 6-6 13 15H7z" fill="#5e8f6a"/><circle cx="34" cy="17" r="4" fill="#e7b75a"/><path d="M40 58l6 4" stroke="#5a3d22" stroke-width="3"/>`],
    clock: [42, 52, `<rect x="4" y="44" width="34" height="6" rx="2" fill="#6b4c2a"/><circle cx="21" cy="24" r="19" fill="#8a6a3a"/>
        <circle cx="21" cy="24" r="15" fill="#f6f0e2"/><path d="M21 13v11l7 5" stroke="#2b2b2b" stroke-width="2" stroke-linecap="round" fill="none"/>`],
    vase: [34, 80, `<path d="M17 36c-2-12-8-20-13-24M17 36c0-14 2-24 1-32M17 36c3-12 8-18 14-20" stroke="#4f8a4b" stroke-width="1.6" fill="none"/>
        <circle cx="4" cy="12" r="4" fill="#e07a5f"/><circle cx="18" cy="5" r="4" fill="#f2cc8f"/><circle cx="31" cy="16" r="4" fill="#e07a5f"/>
        <path d="M10 38h14c1 6-3 8-3 14 0 8 6 12 6 20-2 4-18 4-20 0 0-8 6-12 6-20 0-6-4-8-3-14z" fill="#3d6f8f"/>`],
    box: [54, 34, `<rect x="2" y="8" width="50" height="24" rx="2" fill="#8a5a35"/><rect x="0" y="4" width="54" height="8" rx="2" fill="#a06b42"/>
        <rect x="23" y="12" width="8" height="6" rx="1" fill="#d9b25c"/>`],
};
const SPINE_COLORS = ["#7a2e2e", "#1f5f4a", "#0f4c81", "#a3782a", "#3d3d3d", "#6b3fa0", "#2f7f8f", "#9b3b54", "#4f7a2e", "#b0532c"];

function decorHtml(name, scale) {
    const [w, h, body] = DECOR[name];
    return { w: Math.round(w * scale), html: `<svg class="decor" aria-hidden="true" width="${Math.round(w * scale)}" height="${Math.round(h * scale)}" viewBox="0 0 ${w} ${h}">${body}</svg>` };
}
function stackHtml(scale) {
    const count = 2 + Math.floor(Math.random() * 3);
    const base = Math.round((62 + Math.random() * 26) * scale);
    let html = "";
    for (let i = 0; i < count; i++) {
        const w = base - Math.round(Math.random() * 14 * scale);
        html += `<i style="width:${w}px;background:${SPINE_COLORS[Math.floor(Math.random() * SPINE_COLORS.length)]}"></i>`;
    }
    return { w: base, html: `<span class="stack" aria-hidden="true">${html}</span>` };
}
/** Случайный предмет декора, который влезает в оставшееся место. */
function randomDecor(space, scale) {
    const options = Object.keys(DECOR).filter((k) => DECOR[k][0] * scale <= space);
    if (space >= 70 * scale && Math.random() < .35) return stackHtml(scale);
    if (!options.length) return null;
    return decorHtml(options[Math.floor(Math.random() * options.length)], scale);
}

route(/^\/bookcase$/, async (view, _m, params) => {
    setTitle(t("nav.bookcase"));
    const genres = await api("/api/genres").catch(() => []);
    let genre = params.get("genre") || "";
    let anim = store.get("case.anim", "random");
    view.innerHTML = `<div class="page-head"><div><h1>${esc(t("case.title"))}</h1><p class="muted" style="margin:0">${esc(t("case.lead"))}</p></div></div>
      <div class="case-tools">
        <div class="chips" id="case-genres"></div>
        <button class="btn" id="case-shuffle">${icon("shuffle")}${esc(t("case.shuffle"))}</button>
      </div>
      <div class="case-tools"><div class="group"><span class="small muted">${esc(t("case.anim"))}:</span>
        <div class="seg" id="case-anims">${["random", ...ANIMS].map((a) =>
            `<button data-anim="${a}" aria-pressed="${anim === a}">${esc(t("case.anim_" + a))}</button>`).join("")}</div></div></div>
      <div class="bookcase" id="bookcase"></div>`;
    $$("[data-anim]").forEach((b) => b.addEventListener("click", () => {
        anim = b.dataset.anim;
        store.set("case.anim", anim);
        $$("[data-anim]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    }));

    const renderGenres = () => {
        $("#case-genres").innerHTML = [["", t("common.all")], ...genres.map((g) => [g.name, genreName(g.name)])].map(([v, l]) =>
            `<button class="chip" data-g="${esc(v)}" aria-pressed="${genre === v}">${esc(l)}</button>`).join("");
        $$("[data-g]").forEach((b) => b.addEventListener("click", () => {
            genre = b.dataset.g;
            const p = new URLSearchParams(); if (genre) p.set("genre", genre);
            Oqu.router.setParams(p);
            renderGenres(); fill();
        }));
    };

    /** Расставить книги по 4 полкам: при «Все» — группами по жанрам (жанр
     *  пишется на табличке доски), при выбранном жанре — поровну. Пустое
     *  место заполняется декором, чтобы шкаф выглядел полным. */
    async function fill() {
        const caseEl = $("#bookcase");
        const books = await api(`/api/books/random?limit=60${genre ? "&genre=" + encodeURIComponent(genre) : ""}`);
        caseEl.innerHTML = `<div class="case-body"><div class="shelf"><div class="shelf-row"></div></div></div>`;
        // Место на полке, px (если окно свёрнуто и ширина 0 — берём разумный минимум).
        const width = Math.max(260, $(".shelf-row", caseEl).clientWidth - 12);
        const shelfH = parseFloat(getComputedStyle(caseEl).getPropertyValue("--shelf-h")) || 200;
        const scale = shelfH / 200;
        const gap = 3;
        const spineW = (b) => Math.round(Math.min(52, 30 + b.title.length / 2.2) * scale);
        const usable = width * .82;                                   // ~18% оставляем под декор

        const shelves = Array.from({ length: SHELF_COUNT }, () => ({ books: [], used: 0, genres: [] }));
        const put = (shelf, b) => { shelf.books.push(b); shelf.used += spineW(b) + gap; };
        if (genre) {
            const total = books.reduce((s, b) => s + spineW(b) + gap, 0);
            const rows = Math.min(SHELF_COUNT, Math.max(1, Math.ceil(total / usable)));
            books.forEach((b, i) => put(shelves[Math.floor(i * rows / books.length)], b));
            shelves.forEach((s) => { s.genres = [genre]; });
        } else {
            const buckets = {};
            books.forEach((b) => { (buckets[b.genre || ""] ??= []).push(b); });
            const ordered = Object.entries(buckets).sort((a, b) => b[1].length - a[1].length);
            for (const [g, list] of ordered) {
                const need = list.reduce((s, b) => s + spineW(b) + gap, 0);
                const fit = shelves.filter((s) => s.used + need <= usable).sort((a, b) => a.used - b.used)[0]
                    || shelves.slice().sort((a, b) => a.used - b.used)[0];
                fit.genres.push(g);
                list.forEach((b) => put(fit, b));
            }
        }

        const shelfHtml = (s, index) => {
            // Лишние книги, которые не влезли, не показываем (их видно после «Перемешать»).
            const items = [];
            let used = 0;
            for (const b of s.books) {
                const h = hash(b.title + b.id);
                const tilt = h % 7 === 0 ? " tilt" : "";
                const need = spineW(b) + gap + (tilt ? 12 : 0);   // у наклонной — отступы
                if (used + need > width - 30) break;
                used += need;
                const height = Math.round((140 + (h % 45)) * scale);
                items.push(`<button class="spine s-${1 + (h % 6)}${tilt}" data-id="${b.id}" style="--c:${esc(b.cover_color)};--h:${height}px;--w:${spineW(b)}px"
                    title="${esc(b.title)} — ${esc(b.author)}"><span>${esc(b.title)}</span></button>`);
            }
            let free = width - used - 10;                         // запас на тени
            const left = [], right = [];
            // Слева — подставка или растение, справа — декор до конца полки.
            if (items.length && free > 60 * scale && Math.random() < .6) {
                const d = Math.random() < .5 ? decorHtml("bookend", scale) : randomDecor(Math.min(free / 2, 60 * scale), scale);
                if (d) { left.push(d.html); free -= d.w + gap; }
            }
            // Остаток полки: в основном книги без названий «для вида» (на них
            // нельзя нажать) и максимум 2 предмета декора — как в настоящем шкафу.
            let guard = 0, decorLeft = 2;
            while (free > 20 * scale && guard++ < 80) {
                if (decorLeft > 0 && free > 50 * scale && Math.random() < .22) {
                    const d = randomDecor(Math.min(free - gap, 90 * scale), scale);
                    if (d) { right.push(d.html); free -= d.w + gap; decorLeft--; continue; }
                }
                const w = Math.round((20 + Math.random() * 18) * scale);
                if (w + gap > free) break;
                const hh = Math.round((128 + Math.random() * 56) * scale);
                const color = SPINE_COLORS[Math.floor(Math.random() * SPINE_COLORS.length)];
                right.push(`<span class="spine blank s-${1 + Math.floor(Math.random() * 6)}" aria-hidden="true" style="--c:${color};--h:${hh}px;--w:${w}px"></span>`);
                free -= w + gap;
            }
            const names = s.genres.filter(Boolean).map(genreName);
            const label = names.length > 3 ? `${names.slice(0, 3).join(" · ")} +${names.length - 3}`
                : names.join(" · ") || (s.books.length ? t("case.misc") : t("case.soon"));
            return `<div class="shelf"><div class="shelf-row" style="gap:${gap}px">${left.join("")}${items.join("")}${right.join("")}</div>
                <div class="plank"><span class="plate">${esc(label)}</span></div></div>`;
        };

        caseEl.innerHTML = `<div class="case-crown" aria-hidden="true">${decorHtml("globe", 1).html}${stackHtml(1).html}${decorHtml("plant", 1).html}</div>
            <div class="case-cornice"></div>
            <div class="case-body">${shelves.map(shelfHtml).join("")}</div>
            <div class="case-base"></div>`;
        if (!books.length) $(".shelf-row", caseEl).insertAdjacentHTML("afterbegin", `<span class="shelf-empty">${esc(t("case.empty"))}</span>`);
        const byId = Object.fromEntries(books.map((b) => [b.id, b]));
        $$(".spine", caseEl).forEach((sp) => sp.addEventListener("click", () =>
            pullBook(sp, byId[sp.dataset.id], anim === "random" ? ANIMS[Math.floor(Math.random() * ANIMS.length)] : anim)));
    }

    renderGenres();
    $("#case-shuffle").addEventListener("click", fill);
    await fill();
});

/* Пять анимаций: как корешок уходит с полки и как книга появляется.
   [класс корешка, начальное положение летящей книги, задержка, доп. класс] */
const ANIM_SPEC = {
    pull: ["pulled", "rotateY(70deg)", 320, ""],                       // выдвинуть
    tilt: ["a-tilt", "rotate(-16deg)", 300, ""],                       // наклонить
    slide: ["a-slide", "perspective(900px) rotateY(-95deg)", 300, "f-door"], // распахнуть
    spin: ["a-spin", "rotateY(540deg) scale(.6)", 420, ""],            // закружить
    rise: ["a-rise", "scale(.25)", 380, ""],                           // взлететь
};

/** Анимация: корешок уходит с полки, книга «вылетает» к центру и раскрывается. */
function pullBook(spine, b, anim = "pull") {
    const [cls, start, delay, flyCls] = ANIM_SPEC[anim] || ANIM_SPEC.pull;
    if (Object.values(ANIM_SPEC).some(([c]) => spine.classList.contains(c))) return;
    spine.classList.add(cls);
    const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
    setTimeout(() => {
        const r = spine.getBoundingClientRect();
        const fly = document.createElement("div");
        fly.className = "flying-book " + flyCls;
        fly.innerHTML = cover(b);
        Object.assign(fly.style, { left: r.left + "px", top: r.top + "px", width: Math.max(r.width, 30) + "px", height: r.height + "px",
            opacity: anim === "rise" ? "0" : "1", transform: start });
        fly.firstElementChild.style.height = "100%";
        document.body.appendChild(fly);
        const w = Math.min(220, innerWidth * .45), h = w * 1.5;
        requestAnimationFrame(() => requestAnimationFrame(() => Object.assign(fly.style, {
            left: (innerWidth - w) / 2 + "px", top: (innerHeight - h) / 2 - 40 + "px", width: w + "px", height: h + "px",
            transform: "none", opacity: "1" })));
        setTimeout(() => {
            fly.remove();
            const card = openModal(`<div class="case-preview">${cover(b)}
                <div><h2 style="padding-right:30px">${esc(b.title)}</h2><p class="muted">${esc(b.author)}${b.year ? " · " + b.year : ""}</p>
                <div class="meta-line" style="margin-bottom:10px">${starsMini(b)}<span class="badge ${b.is_paid ? "paid" : "free"}">${esc(t(b.is_paid ? "book.paid" : "book.free"))}</span>
                ${b.genre ? `<span>${esc(genreName(b.genre))}</span>` : ""}</div>
                <p class="small" style="display:-webkit-box;-webkit-line-clamp:5;-webkit-box-orient:vertical;overflow:hidden">${esc(b.description)}</p>
                <div class="btn-row"><a class="btn primary" href="#/read/${b.id}">${icon("book")}${esc(t("book.read"))}</a>
                <a class="btn" href="#/book/${b.id}">${esc(t("book.details"))}</a></div></div></div>`,
            { wide: true, onClose: () => spine.classList.remove(cls) });
            $$("a", card).forEach((a) => a.addEventListener("click", () => closeModal()));
        }, reduce ? 0 : 560);
    }, reduce ? 0 : delay);
}

/* ======================================================================
   Карточка книги
   ====================================================================== */
route(/^\/book\/(\d+)$/, async (view, [id]) => {
    view.innerHTML = `<div class="book-page"><div><div class="skeleton sk-cover"></div></div><div><div class="skeleton" style="height:40px;width:60%"></div>
        <div class="skeleton sk-line" style="width:30%"></div><div class="skeleton" style="height:120px;margin-top:24px"></div></div></div>`;
    const b = await api(`/api/books/${id}`);
    setTitle(b.title);
    const u = Oqu.state.user;
    const readBtns = [];
    if (b.can_read) {
        const label = b.position ? t("book.continue_at", { p: progressLabel(b) }) : t("book.read");
        if (b.has_text || !b.has_file) readBtns.push(`<a class="btn primary lg block" href="#/read/${b.id}">${icon("book")}${esc(label)}</a>`);
        if (b.has_file) readBtns.push(`<a class="btn ${b.has_text ? "" : "primary"} lg block" href="#/read/${b.id}?mode=pdf">${icon("pdf")}${esc(t("book.read_scan"))}</a>`);
    }
    view.innerHTML = `<div class="book-page">
      <aside class="book-aside">${cover(b)}
        <div style="display:flex;flex-direction:column;gap:10px">${readBtns.join("")}
          ${b.external_url ? `<a class="btn block" href="${esc(b.external_url)}" target="_blank" rel="noopener noreferrer">${icon("link")}${esc(t("book.external"))}</a>` : ""}
        </div>
      </aside>
      <div class="book-main">
        <div class="meta-line" style="margin-bottom:8px">
          <span class="badge ${b.is_paid ? "paid" : "free"}">${esc(t(b.is_paid ? "book.paid" : "book.free"))}</span>
          ${b.genre ? `<a class="badge" href="#/catalog?genre=${encodeURIComponent(b.genre)}">${esc(genreName(b.genre))}</a>` : ""}
        </div>
        <h1>${esc(b.title)}</h1>
        <div class="book-author"><a href="#/catalog?author=${encodeURIComponent(b.author)}">${esc(b.author)}</a></div>
        <div class="btn-row" id="rating-row"></div>
        ${b.is_paid && !b.can_read ? lockBox(b) : ""}
        <div id="shelf-ctl" style="margin:18px 0"></div>
        <div class="facts">
          <div class="fact"><small>${esc(t("book.year"))}</small><b>${b.year ?? "—"}</b></div>
          <div class="fact"><small>${esc(t("book.language"))}</small><b>${esc(t(LANG_NAMES[b.language]))}</b></div>
          <div class="fact"><small>${esc(t("book.format"))}</small><b>${[b.has_text ? t("book.fmt_text") : "", b.has_file ? "PDF" : ""].filter(Boolean).join(" + ") || "—"}</b></div>
          <div class="fact"><small>${esc(t("book.reads"))}</small><b>${fmtNum(b.reads)}</b></div>
        </div>
        ${b.description ? `<h2>${esc(t("book.about"))}</h2><p class="description">${esc(b.description)}</p>` : ""}
        ${b.tags.length ? `<div class="chips" style="margin:14px 0">${b.tags.map((x) => `<a class="tag" href="#/catalog?tag=${encodeURIComponent(x)}">#${esc(x)}</a>`).join("")}</div>` : ""}
        ${b.can_edit || b.can_delete ? `<div class="btn-row" style="margin:18px 0">
          ${b.can_edit ? `<a class="btn sm" href="#/books/${b.id}/edit">${icon("edit")}${esc(t("common.edit"))}</a>` : ""}
          ${b.can_delete ? `<button class="btn sm danger" id="del-book">${icon("trash")}${esc(t("common.delete"))}</button>` : ""}</div>` : ""}
        <section class="section" id="comments-sec"></section>
      </div></div>`;

    // Оценка звёздами
    const renderRating = (mine) => {
        $("#rating-row").innerHTML = `${b.rating ? `<span class="stars-mini" style="font-size:16px">${icon("star")} ${esc(String(b.rating))}</span>
            <span class="muted small">${esc(plural(b.rating_count, "book.ratings"))}</span>` : `<span class="muted small">${esc(t("book.no_ratings"))}</span>`}
          ${u ? `<span class="rating-input" role="radiogroup" aria-label="${esc(t("book.rate"))}">${[1, 2, 3, 4, 5].map((n) =>
            `<button data-rate="${n}" class="${mine && n <= mine ? "on" : ""}" aria-label="${n}">${icon("star")}</button>`).join("")}</span>` : ""}`;
        $$("[data-rate]").forEach((btn) => btn.addEventListener("click", async () => {
            try {
                await api(`/api/books/${b.id}/rating`, { method: "PUT", body: { value: Number(btn.dataset.rate) } });
                const fresh = await api(`/api/books/${b.id}`);
                b.rating = fresh.rating; b.rating_count = fresh.rating_count;
                renderRating(Number(btn.dataset.rate));
                toast(t("book.rated"), "ok");
            } catch (e) { toastError(e); }
        }));
    };
    renderRating(b.my_rating);

    // Полка: статусы как в MangaLib
    const renderShelf = (status) => {
        $("#shelf-ctl").innerHTML = `<div class="seg" role="group" aria-label="${esc(t("nav.shelf"))}">${SHELVES.map((s) =>
            `<button data-shelf="${s}" aria-pressed="${status === s}">${esc(t("shelf." + s))}</button>`).join("")}</div>`;
        $$("[data-shelf]").forEach((btn) => btn.addEventListener("click", async () => {
            if (!requireLogin()) return;
            const next = status === btn.dataset.shelf ? null : btn.dataset.shelf;
            try {
                await api(`/api/me/shelf/${b.id}`, { method: "PUT", body: { status: next } });
                renderShelf(next);
                toast(next ? t("shelf.added", { s: t("shelf." + next) }) : t("shelf.removed"), "ok");
            } catch (e) { toastError(e); }
        }));
    };
    renderShelf(b.shelf_status);

    $("#buy-btn")?.addEventListener("click", async () => {
        if (!requireLogin()) return;
        const ok = await confirmDialog({ title: t("buy.title", { title: b.title }), text: t("buy.text", { price: fmtNum(b.price) }), ok: t("buy.ok", { price: fmtNum(b.price) }) });
        if (!ok) return;
        try { await api(`/api/books/${b.id}/buy`, { method: "POST" }); toast(t("buy.done"), "ok"); Oqu.router.render(); }
        catch (e) { toastError(e); }
    });
    $("#del-book")?.addEventListener("click", async () => {
        if (!await confirmDialog({ title: t("book.delete_q"), text: t("book.delete_text", { title: b.title }), ok: t("common.delete"), danger: true })) return;
        try { await api(`/api/books/${b.id}`, { method: "DELETE" }); toast(t("book.deleted"), "ok"); location.hash = "#/catalog"; }
        catch (e) { toastError(e); }
    });

    renderComments(b.id, 1);
});

function lockBox(b) {
    const u = Oqu.state.user;
    const studentHint = u && !u.is_student && can("student.apply")
        ? `<a href="#/profile/student">${esc(t("book.student_link"))}</a>` : "";
    return `<div class="lock-box">${icon("lock")}<div>
        <b>${esc(t("book.paid_title"))}</b><br>${esc(t("book.paid_text", { date: fmtDate(b.paid_until) }))} ${studentHint}
        <div class="btn-row" style="margin-top:10px"><button class="btn primary sm" id="buy-btn">${icon("cart")}${esc(t("buy.ok", { price: fmtNum(b.price) }))}</button></div>
      </div></div>`;
}

async function renderComments(bookId, page) {
    const sec = $("#comments-sec");
    if (!sec) return;
    const d = await api(`/api/books/${bookId}/comments?page=${page}&page_size=10`);
    const u = Oqu.state.user;
    sec.innerHTML = `<div class="section-head"><h2>${esc(t("comments.title"))} <span class="muted" style="font-size:16px">${d.total}</span></h2></div>
      ${u && can("comment.write") ? `<form class="comment-form" id="comment-form">${avatar(u.display_name || u.username)}
        <div><textarea class="textarea" name="text" maxlength="2000" required placeholder="${esc(t("comments.placeholder"))}" style="min-height:80px"></textarea>
        <div class="btn-row" style="justify-content:space-between;margin-top:8px"><span class="small muted">${esc(t("comments.rules"))}</span>
        <button class="btn primary sm">${esc(t("comments.send"))}</button></div></div></form>`
        : `<p class="muted">${esc(t("comments.guest"))} <a href="#" id="c-login">${esc(t("auth.login"))}</a></p>`}
      <div class="comments">${d.items.length ? d.items.map((c) => commentHtml(c)).join("") : `<p class="muted">${esc(t("comments.empty"))}</p>`}</div>
      ${pager(d, (n) => renderComments(bookId, n))}`;
    $("#c-login")?.addEventListener("click", (e) => { e.preventDefault(); Oqu.openAuth("login", location.hash); });
    $("#comment-form")?.addEventListener("submit", async (e) => {
        e.preventDefault();
        const text = e.target.text.value.trim();
        if (!text) return;
        try { await api(`/api/books/${bookId}/comments`, { method: "POST", body: { text } }); toast(t("comments.added"), "ok"); renderComments(bookId, 1); }
        catch (err) { toastError(err); }
    });
    $$("[data-cedit]", sec).forEach((btn) => btn.addEventListener("click", async () => {
        const c = d.items.find((x) => x.id === Number(btn.dataset.cedit));
        const res = await formDialog({ title: t("comments.edit"), fields: [{ name: "text", type: "textarea", label: t("comments.text"), value: c.text, max: 2000, required: true }] });
        if (!res) return;
        try { await api(`/api/comments/${c.id}`, { method: "PATCH", body: { text: res.text } }); toast(t("comments.saved"), "ok"); renderComments(bookId, page); }
        catch (err) { toastError(err); }
    }));
    $$("[data-cdel]", sec).forEach((btn) => btn.addEventListener("click", async () => {
        if (!await confirmDialog({ title: t("comments.delete_q"), ok: t("common.delete"), danger: true })) return;
        try { await api(`/api/comments/${btn.dataset.cdel}`, { method: "DELETE" }); toast(t("comments.deleted"), "ok"); renderComments(bookId, page); }
        catch (err) { toastError(err); }
    }));
}

function commentHtml(c) {
    const u = Oqu.state.user;
    const own = u && u.id === c.user_id;
    const canDel = (own && can("comment.delete_own")) || can("comment.delete_any");
    const badge = c.badge ? `<span class="badge ${esc(c.badge)}">${esc(t("badge." + c.badge))}</span>` : "";
    return `<div class="comment">${avatar(c.display_name || c.username)}
      <div class="comment-body"><div class="comment-head"><b>${esc(c.display_name || c.username)}</b>${badge}
        <span class="small muted" title="${esc(fmtDate(c.created_at, true))}">${esc(fmtAgo(c.created_at))}${c.edited_at ? " · " + esc(t("comments.edited")) : ""}</span></div>
        <div class="comment-text">${esc(c.text)}</div>
        ${own || canDel ? `<div class="comment-actions">
          ${own ? `<button class="btn ghost sm" data-cedit="${c.id}">${icon("edit", "i-sm")}${esc(t("common.edit"))}</button>` : ""}
          ${canDel ? `<button class="btn ghost sm" data-cdel="${c.id}">${icon("trash", "i-sm")}${esc(t("common.delete"))}</button>` : ""}</div>` : ""}
      </div></div>`;
}

/* ======================================================================
   Читалка: текст или PDF-скан, настройки, автосохранение места, закладки
   ====================================================================== */
let readerCleanup = null;
window.addEventListener("hashchange", () => {
    readerCleanup?.(); readerCleanup = null;
    document.body.classList.toggle("reading", location.hash.startsWith("#/read/"));
});

route(/^\/read\/(\d+)$/, async (view, [id], params) => {
    let b;
    try {
        b = await api(`/api/books/${id}/read`);
    } catch (err) {
        if (err.status !== 403) throw err;
        // Платная книга без доступа: объясняем и ведём на её страницу.
        setTitle(t("book.paid_title"));
        view.innerHTML = emptyState("lock", t("book.paid_title"), Oqu.errorText(err),
            `<a class="btn primary" href="#/book/${id}">${esc(t("book.details"))}</a>`
            + (Oqu.state.user ? "" : `<button class="btn" id="r-login">${esc(t("auth.login"))}</button>`));
        $("#r-login")?.addEventListener("click", () => Oqu.openAuth("login", location.hash));
        return;
    }
    setTitle(b.title);
    const mode = params.get("mode") === "pdf" || (!b.content && b.has_file) ? "pdf" : "text";
    const prefs = store.get("reader", { fs: 19, theme: "", width: 680 });
    const u = Oqu.state.user;
    view.classList.add("wide");
    document.body.classList.add("reading");
    view.innerHTML = `<div class="reader" id="reader" data-rtheme="${esc(prefs.theme)}" style="--rfs:${prefs.fs}px;--rw:${prefs.width}px">
      <div class="reader-bar">
        <a class="icon-btn" href="#/book/${b.id}" title="${esc(t("common.back"))}" aria-label="${esc(t("common.back"))}">${icon("left")}</a>
        <div class="title">${esc(b.title)} <span class="muted small" id="r-pct"></span></div>
        ${b.has_file && b.content ? `<div class="seg"><button data-mode="text" aria-pressed="${mode === "text"}">${icon("text")}</button>
          <button data-mode="pdf" aria-pressed="${mode === "pdf"}">PDF</button></div>` : ""}
        <button class="icon-btn" id="r-marks" title="${esc(t("reader.bookmarks"))}" aria-label="${esc(t("reader.bookmarks"))}">${icon("bookmark")}</button>
        ${mode === "text" ? `<button class="icon-btn" id="r-settings" title="${esc(t("reader.settings"))}" aria-label="${esc(t("reader.settings"))}">${icon("settings")}</button>` : ""}
        <div class="reader-progress" id="r-progress"></div>
      </div>
      <div id="r-body"></div><div id="r-panel"></div></div>`;
    $$("[data-mode]").forEach((btn) => btn.addEventListener("click", () => {
        location.hash = `#/read/${b.id}` + (btn.dataset.mode === "pdf" ? "?mode=pdf" : "");
    }));

    const body = $("#r-body");
    const localKey = "progress." + b.id;
    let currentPos = () => 0;
    let goTo = () => {};

    if (mode === "pdf") {
        body.innerHTML = `<div class="empty">${esc(t("reader.loading_pdf"))}</div>`;
        const blob = await api(`/api/books/${b.id}/file`, { blob: true });
        const url = URL.createObjectURL(blob);
        let page = (!b.content && b.position) || store.get(localKey + ".pdf", 1) || 1;
        const show = (p) => { body.innerHTML = `<iframe class="reader-pdf" title="${esc(b.title)}" src="${url}#page=${p}"></iframe>`; };
        show(page);
        currentPos = () => page;
        goTo = (p) => { page = p; show(p); };
        $("#r-pct").textContent = t("reader.page_n", { n: page });
        readerCleanup = () => URL.revokeObjectURL(url);
        // PDF-просмотрщик браузера не сообщает текущую страницу,
        // поэтому место отмечается вручную: «Я на странице N».
        $(".reader-bar .title").insertAdjacentHTML("afterend", `<button class="btn sm" id="r-setpage">${esc(t("reader.i_am_on"))}</button>`);
        $("#r-setpage").addEventListener("click", async () => {
            const res = await formDialog({ title: t("reader.i_am_on"), fields: [{ name: "page", type: "number", min: 1, label: t("reader.page"), value: String(page), required: true }] });
            if (!res) return;
            page = Math.max(1, parseInt(res.page, 10) || 1);
            store.set(localKey + ".pdf", page);
            $("#r-pct").textContent = t("reader.page_n", { n: page });
            if (u && !b.content) api(`/api/me/progress/${b.id}`, { method: "PUT", body: { position: page } }).catch(() => {});
            toast(t("reader.saved"), "ok");
        });
    } else {
        const paras = (b.content || "").split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean);
        body.innerHTML = `<article class="reader-text" id="r-text"><h1>${esc(b.title)}</h1><div class="by">${esc(b.author)}</div>
            ${paras.length ? paras.map((p) => `<p>${esc(p)}</p>`).join("") : `<p class="muted">${esc(t("reader.no_text"))}</p>`}
            <p class="muted" style="text-align:center;text-indent:0;margin-top:3em">❦</p></article>`;
        const maxScroll = () => Math.max(1, document.documentElement.scrollHeight - innerHeight);
        currentPos = () => Math.round(Math.min(1, scrollY / maxScroll()) * 1000);
        goTo = (pos) => window.scrollTo({ top: (pos / 1000) * maxScroll(), behavior: "smooth" });
        const updateBar = () => {
            const p = currentPos();
            $("#r-progress").style.width = p / 10 + "%";
            $("#r-pct").textContent = `· ${Math.round(p / 10)}%`;
        };
        const save = debounce(() => {
            const p = currentPos();
            store.set(localKey, p);
            if (u) api(`/api/me/progress/${b.id}`, { method: "PUT", body: { position: p } }).catch(() => {});
        }, 1200);
        const onScroll = () => { updateBar(); save(); };
        window.addEventListener("scroll", onScroll, { passive: true });
        const onKey = (e) => {
            if (/INPUT|TEXTAREA/.test(document.activeElement?.tagName)) return;
            if (e.key === "ArrowRight" || e.key === "PageDown") { e.preventDefault(); scrollBy({ top: innerHeight * .85, behavior: "smooth" }); }
            if (e.key === "ArrowLeft" || e.key === "PageUp") { e.preventDefault(); scrollBy({ top: -innerHeight * .85, behavior: "smooth" }); }
        };
        document.addEventListener("keydown", onKey);
        readerCleanup = () => { window.removeEventListener("scroll", onScroll); document.removeEventListener("keydown", onKey); $(".resume-pill")?.remove(); };

        // Продолжить с места остановки (сервер для вошедших, браузер — для гостей).
        const saved = b.position || store.get(localKey, 0);
        requestAnimationFrame(() => {
            if (saved > 15) {
                window.scrollTo({ top: (saved / 1000) * maxScroll() });
                const pill = document.createElement("div");
                pill.className = "resume-pill";
                pill.innerHTML = `<span>${esc(t("reader.resumed", { p: Math.round(saved / 10) }))}</span><button class="btn sm">${esc(t("reader.from_start"))}</button>`;
                document.body.appendChild(pill);
                $("button", pill).addEventListener("click", () => { window.scrollTo({ top: 0, behavior: "smooth" }); pill.remove(); });
                setTimeout(() => pill.remove(), 6000);
            }
            updateBar();
        });

        $("#r-settings").addEventListener("click", () => togglePanel("settings"));
    }

    function applyPrefs() {
        const r = $("#reader");
        r.style.setProperty("--rfs", prefs.fs + "px");
        r.style.setProperty("--rw", prefs.width + "px");
        r.dataset.rtheme = prefs.theme;
        store.set("reader", prefs);
    }

    async function togglePanel(kind) {
        const panel = $("#r-panel");
        if (panel.dataset.kind === kind) { panel.innerHTML = ""; panel.dataset.kind = ""; return; }
        panel.dataset.kind = kind;
        if (kind === "settings") {
            panel.innerHTML = `<div class="reader-panel"><h3>${esc(t("reader.settings"))}</h3>
              <div class="field"><span>${esc(t("reader.font"))}</span><div class="btn-row">
                <button class="btn sm" data-fs="-1">${icon("minus")}</button><b id="fs-val">${prefs.fs}</b><button class="btn sm" data-fs="1">${icon("plus")}</button></div></div>
              <div class="field"><span>${esc(t("reader.theme"))}</span><div class="seg">
                ${[["", "reader.t_paper"], ["sepia", "reader.t_sepia"], ["night", "reader.t_night"]].map(([v, k]) =>
                    `<button data-rt="${v}" aria-pressed="${prefs.theme === v}">${esc(t(k))}</button>`).join("")}</div></div>
              <div class="field"><span>${esc(t("reader.width"))}</span><div class="seg">
                ${[[600, "reader.w_narrow"], [680, "reader.w_normal"], [820, "reader.w_wide"]].map(([v, k]) =>
                    `<button data-rw="${v}" aria-pressed="${prefs.width === v}">${esc(t(k))}</button>`).join("")}</div></div>
              <p class="small muted" style="margin:0">${esc(t("reader.keys"))}</p></div>`;
            $$("[data-fs]", panel).forEach((x) => x.addEventListener("click", () => {
                prefs.fs = Math.min(30, Math.max(14, prefs.fs + Number(x.dataset.fs))); $("#fs-val").textContent = prefs.fs; applyPrefs();
            }));
            $$("[data-rt]", panel).forEach((x) => x.addEventListener("click", () => {
                prefs.theme = x.dataset.rt; $$("[data-rt]", panel).forEach((y) => y.setAttribute("aria-pressed", String(y === x))); applyPrefs();
            }));
            $$("[data-rw]", panel).forEach((x) => x.addEventListener("click", () => {
                prefs.width = Number(x.dataset.rw); $$("[data-rw]", panel).forEach((y) => y.setAttribute("aria-pressed", String(y === x))); applyPrefs();
            }));
            return;
        }
        if (!u) { panel.innerHTML = ""; panel.dataset.kind = ""; requireLogin(); return; }
        const marks = await api(`/api/me/bookmarks?book_id=${b.id}`);
        const label = (m) => mode === "pdf" ? t("reader.page_n", { n: m.position }) : `${Math.round(m.position / 10)}%`;
        panel.innerHTML = `<div class="reader-panel"><h3>${esc(t("reader.bookmarks"))}</h3>
          <form id="mark-form"><input class="input" name="note" maxlength="500" placeholder="${esc(t("reader.note_ph"))}">
          <button class="btn primary sm block" style="margin-top:8px">${icon("plus")}${esc(t("reader.add_mark", { p: mode === "pdf" ? t("reader.page_n", { n: currentPos() }) : Math.round(currentPos() / 10) + "%" }))}</button></form>
          <div class="mark-list">${marks.length ? marks.map((m) => `<div class="mark-item"><button class="go" data-go="${m.position}">
            <b>${esc(label(m))}</b> <span class="small muted">${esc(fmtAgo(m.created_at))}</span><div class="small">${esc(m.note || "—")}</div></button>
            <button class="icon-btn" data-mdel="${m.id}" aria-label="${esc(t("common.delete"))}">${icon("trash", "i-sm")}</button></div>`).join("")
            : `<p class="small muted">${esc(t("reader.no_marks"))}</p>`}</div></div>`;
        $("#mark-form", panel).addEventListener("submit", async (e) => {
            e.preventDefault();
            try {
                await api(`/api/me/bookmarks/${b.id}`, { method: "POST", body: { position: currentPos(), note: e.target.note.value.trim() } });
                toast(t("reader.mark_added"), "ok"); panel.dataset.kind = ""; togglePanel("marks");
            } catch (err) { toastError(err); }
        });
        $$("[data-go]", panel).forEach((x) => x.addEventListener("click", () => goTo(Number(x.dataset.go))));
        $$("[data-mdel]", panel).forEach((x) => x.addEventListener("click", async () => {
            try { await api(`/api/me/bookmarks/${x.dataset.mdel}`, { method: "DELETE" }); panel.dataset.kind = ""; togglePanel("marks"); }
            catch (err) { toastError(err); }
        }));
    }
    $("#r-marks").addEventListener("click", () => togglePanel("marks"));
});

/* ======================================================================
   Моя полка
   ====================================================================== */
route(/^\/shelf$/, async (view, _m, params) => {
    setTitle(t("nav.shelf"));
    const status = SHELVES.includes(params.get("s")) ? params.get("s") : "reading";
    const summary = await api("/api/me/summary");
    const counts = summary.shelf_counts;
    view.innerHTML = `<div class="page-head"><h1>${esc(t("nav.shelf"))}</h1></div>
      <div class="tabs" role="tablist">${SHELVES.map((s) => `<button role="tab" data-s="${s}" aria-selected="${s === status}">
        ${esc(t("shelf." + s))}<span class="count">${counts[s]}</span></button>`).join("")}</div><div id="shelf-list">${skeletonGrid(6)}</div>`;
    $$("[data-s]").forEach((b) => b.addEventListener("click", () => { location.hash = "#/shelf?s=" + b.dataset.s; }));
    const items = await api("/api/me/shelf?status=" + status);
    $("#shelf-list").innerHTML = items.length
        ? `<div class="books-grid">${items.map((b) => `<div>${tile(b)}${status === "reading" ? `<div style="margin-top:6px">${progressBar(b)}
            <div class="small muted" style="margin-top:3px">${esc(progressLabel(b))}</div></div>` : ""}</div>`).join("")}</div>`
        : emptyState("bookmark", t("shelf.empty_" + status), t("shelf.empty_hint"), `<a class="btn primary" href="#/catalog">${esc(t("home.to_catalog"))}</a>`);
}, { auth: true });

/* ======================================================================
   Профиль: обзор, статус студента, настройки, удаление аккаунта
   ====================================================================== */
route(/^\/profile(?:\/(\w+))?$/, async (view, [tab = "overview"]) => {
    setTitle(t("nav.profile"));
    const s = await api("/api/me/summary");
    const u = s.user;
    Oqu.state.user = u;
    const tabs = [["overview", "profile.overview"], ["student", "profile.student"], ["settings", "profile.settings"]];
    view.innerHTML = `<div class="profile-head">${avatar(u.display_name || u.username, "lg")}
        <div><h1>${esc(u.display_name || u.username)}</h1>
        <div class="meta-line">@${esc(u.username)} ${roleBadge(u.role)} ${u.is_student ? `<span class="badge free">${icon("cap", "i-sm")} ${esc(t("profile.verified"))}</span>` : ""}
        <span>${esc(t("profile.since", { date: fmtDate(u.created_at) }))}</span></div></div></div>
      <div class="tabs" role="tablist">${tabs.map(([k, l]) => `<button role="tab" data-tab="${k}" aria-selected="${k === tab}">${esc(t(l))}</button>`).join("")}</div>
      <div id="profile-body"></div>`;
    $$("[data-tab]").forEach((b) => b.addEventListener("click", () => { location.hash = "#/profile" + (b.dataset.tab === "overview" ? "" : "/" + b.dataset.tab); }));
    const body = $("#profile-body");

    if (tab === "student") return studentTab(body, u, s.student_request);
    if (tab === "settings") return settingsTab(body, u);

    body.innerHTML = `<div class="stat-row">${SHELVES.map((k) => `<a class="stat" href="#/shelf?s=${k}" style="color:inherit;text-decoration:none">
        <b>${s.shelf_counts[k]}</b><span>${esc(t("shelf." + k))}</span></a>`).join("")}</div>
      <section class="section"><div class="section-head"><h2>${esc(t("home.continue"))}</h2></div>
        ${s.continue.length ? `<div class="continue-grid">${s.continue.map(continueCard).join("")}</div>` : `<p class="muted">${esc(t("profile.no_continue"))}</p>`}</section>
      <section class="section"><div class="section-head"><h2>${esc(t("reader.bookmarks"))}</h2></div>
        ${s.bookmarks.length ? `<div class="mark-list">${s.bookmarks.map((m) => `<a class="mark-item" href="#/read/${m.book_id}" style="color:inherit;text-decoration:none">
          ${icon("bookmark")}<div><b>${esc(m.title)}</b> <span class="small muted">${esc(fmtAgo(m.created_at))}</span><div class="small">${esc(m.note || "—")}</div></div></a>`).join("")}</div>`
        : `<p class="muted">${esc(t("reader.no_marks"))}</p>`}</section>`;
}, { auth: true });

function studentTab(body, u, reqStatus) {
    if (u.is_student) {
        body.innerHTML = `<div class="card"><h2>${icon("cap")} ${esc(t("student.ok_title"))}</h2><p>${esc(t("student.ok_text"))}</p></div>`;
        return;
    }
    if (!can("student.apply")) {
        body.innerHTML = `<div class="card"><p class="muted">${esc(t("student.not_needed"))}</p></div>`;
        return;
    }
    if (reqStatus === "pending") {
        body.innerHTML = `<div class="card"><h2>${icon("clock")} ${esc(t("student.pending_title"))}</h2><p>${esc(t("student.pending_text"))}</p></div>`;
        return;
    }
    body.innerHTML = `<div class="card" style="max-width:640px"><h2>${esc(t("student.title"))}</h2><p class="muted">${esc(t("student.lead"))}</p>
      ${reqStatus === "rejected" ? `<div class="form-error">${esc(t("student.rejected"))}</div>` : ""}
      <form id="student-form"><label class="drop" id="drop">${icon("upload")}<div id="drop-text">${esc(t("student.drop"))}</div>
        <input type="file" name="file" accept="image/jpeg,image/png,image/webp" required></label>
        <p class="small muted" style="margin-top:10px">${esc(t("student.privacy"))}</p>
        <button class="btn primary">${esc(t("student.send"))}</button></form></div>`;
    const input = $("[name=file]", body);
    input.addEventListener("change", () => { $("#drop-text").textContent = input.files[0]?.name || t("student.drop"); });
    $("#student-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        const file = input.files[0];
        if (!file) return toast(t("student.drop"), "error");
        if (file.size > 5 * 1024 * 1024) return toast(t("student.too_big"), "error");
        const form = new FormData(); form.append("file", file);
        try { await api("/api/me/student-request", { method: "POST", form }); toast(t("student.sent"), "ok"); Oqu.router.render(); }
        catch (err) { toastError(err); }
    });
}

function settingsTab(body, u) {
    body.innerHTML = `<div class="grid-2">
      <form class="card" id="name-form"><h2>${esc(t("settings.profile"))}</h2>
        <label class="field"><span>${esc(t("auth.display_name"))}</span><input class="input" name="display_name" maxlength="64" required value="${esc(u.display_name)}"></label>
        <label class="field"><span>${esc(t("auth.email"))}</span><input class="input" value="${esc(u.email)}" disabled></label>
        <button class="btn primary">${esc(t("common.save"))}</button></form>
      <form class="card" id="pass-form"><h2>${esc(t("settings.password"))}</h2>
        <label class="field"><span>${esc(t("settings.old_password"))}</span><input class="input" type="password" name="old_password" required autocomplete="current-password" maxlength="128"></label>
        <label class="field"><span>${esc(t("settings.new_password"))}</span><input class="input" type="password" name="new_password" required minlength="8" autocomplete="new-password" maxlength="128">
          <small class="hint">${esc(t("auth.password_hint"))}</small></label>
        <button class="btn primary">${esc(t("settings.change"))}</button></form>
      <div class="card"><h2>${esc(t("settings.interface"))}</h2>
        <div class="field"><span>${esc(t("settings.language"))}</span><div class="seg">${["kk", "ru", "en"].map((l) =>
            `<button data-l="${l}" aria-pressed="${Oqu.state.lang === l}">${esc(t(LANG_NAMES[l]))}</button>`).join("")}</div></div>
        <div class="field"><span>${esc(t("settings.theme"))}</span><div class="seg">${["light", "dark"].map((th) =>
            `<button data-th="${th}" aria-pressed="${Oqu.state.theme === th}">${esc(t("theme." + th))}</button>`).join("")}</div></div></div>
      <div class="card danger-zone"><h2>${esc(t("settings.delete_title"))}</h2><p class="muted">${esc(t(u.role === "owner" ? "settings.delete_owner" : "settings.delete_text"))}</p>
        <button class="btn danger" id="del-acc" ${u.role === "owner" ? "disabled" : ""}>${icon("trash")}${esc(t("settings.delete_btn"))}</button></div>
    </div>`;
    $("#name-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        if (!e.target.display_name.value.trim()) e.target.display_name.value = "";
        if (!Oqu.validateForm(e.target)) return;
        try { Oqu.state.user = await api("/api/me", { method: "PATCH", body: { display_name: e.target.display_name.value.trim() } }); toast(t("common.saved"), "ok"); Oqu.router.render(); }
        catch (err) { toastError(err); }
    });
    $("#pass-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        if (!Oqu.validateForm(e.target)) return;
        try {
            await api("/api/me/password", { method: "POST", body: { old_password: e.target.old_password.value, new_password: e.target.new_password.value } });
            e.target.reset(); toast(t("settings.password_changed"), "ok");
        } catch (err) {
            if (err.status === 401) Oqu.setFieldError(e.target.old_password, Oqu.errorText(err));
            else if (!Oqu.showServerFieldErrors(e.target, err)) toastError(err);
        }
    });
    $$("[data-l]", body).forEach((b) => b.addEventListener("click", () => Oqu.setLang(b.dataset.l)));
    $$("[data-th]", body).forEach((b) => b.addEventListener("click", () => { Oqu.setTheme(b.dataset.th); Oqu.router.render(); }));
    $("#del-acc").addEventListener("click", async () => {
        const res = await formDialog({ title: t("settings.delete_title"), intro: `<p class="form-error">${esc(t("settings.delete_warn"))}</p>`,
            fields: [{ name: "password", type: "password", label: t("auth.password"), required: true, autocomplete: "current-password" }], ok: t("settings.delete_btn") });
        if (!res) return;
        try {
            await api("/api/me", { method: "DELETE", body: { password: res.password } });
            Oqu.tokens.clear(); Oqu.state.user = null; toast(t("settings.deleted"), "ok"); location.hash = "#/";
        } catch (err) { toastError(err); }
    });
}

/* ======================================================================
   Статистика
   ====================================================================== */
route(/^\/stats$/, async (view) => {
    setTitle(t("nav.stats"));
    const s = await api("/api/stats");
    const maxGenre = Math.max(1, ...s.genres.map((g) => g.count));
    view.innerHTML = `<div class="page-head"><div><h1>${esc(t("stats.title"))}</h1><p class="muted" style="margin:0">${esc(t("stats.lead"))}</p></div></div>
      <div class="stat-row">${[[s.total_read, "home.stat_read"], [s.reading_now, "home.stat_reading"], [s.total_books, "home.stat_books"],
        [s.total_users, "home.stat_users"], [s.total_comments, "stats.comments"]].map(([n, k]) => `<div class="stat"><b>${fmtNum(n)}</b><span>${esc(t(k))}</span></div>`).join("")}</div>
      <div class="grid-2 section">
        <div class="card"><h2>${esc(t("stats.leaders"))}</h2>${s.leaderboard.map((e) => `<div class="leader ${e.place === 0 ? "zero" : e.place === 1 ? "first" : ""}">
          <span class="place" title="${esc(e.place === 0 ? t("stats.zero_place") : "")}">${e.place === 0 ? `${icon("crown")}<small>0</small>` : e.place === 1 ? `${icon("crown")}<small>1</small>` : e.place}</span>${avatar(e.display_name || e.username)}
          <div style="min-width:0"><b>${esc(e.display_name || e.username)}</b><div class="small muted">${esc(t("role." + e.role))}</div></div>
          <span class="count" title="${esc(t("stats.books_read"))}">${esc(String(e.read_count))}</span></div>`).join("")}
          <p class="small muted" style="margin:10px 0 0">${esc(t("stats.owner_note"))}</p></div>
        <div style="display:flex;flex-direction:column;gap:20px">
          <div class="card"><h2>${esc(t("stats.top_books"))}</h2>${s.top_books.length ? s.top_books.map((b, i) =>
            `<div class="leader"><span class="place">${i + 1}</span><span class="swatch" style="background:${esc(b.cover_color)};width:26px;height:36px;margin:0"></span>
            <a href="#/book/${b.id}" style="min-width:0">${esc(b.title)}<div class="small muted">${esc(b.author)}</div></a><span class="count" style="font-size:18px">${b.reads}</span></div>`).join("")
            : `<p class="muted">${esc(t("stats.no_reads"))}</p>`}</div>
          <div class="card"><h2>${esc(t("stats.genres"))}</h2>${s.genres.map((g) => `<div class="bar-row"><span>${esc(genreName(g.name))}</span>
            <div class="bar"><i style="width:${(g.count / maxGenre) * 100}%"></i></div><b>${g.count}</b></div>`).join("")}</div>
        </div></div>`;
});

/* ======================================================================
   Редактор книги: добавление и изменение
   ====================================================================== */
route(/^\/books\/new$/, (view) => bookEditor(view, null), { auth: true });
route(/^\/books\/(\d+)\/edit$/, async (view, [id]) => bookEditor(view, await api(`/api/books/${id}`)), { auth: true });

async function bookEditor(view, book) {
    const isNew = !book;
    if (isNew && !can("book.add")) { view.innerHTML = emptyState("lock", t("error.forbidden_title"), t("error.forbidden")); return; }
    if (!isNew && !book.can_edit) { view.innerHTML = emptyState("lock", t("error.forbidden_title"), t("error.forbidden")); return; }
    let content = "";
    if (!isNew && book.has_text) content = (await api(`/api/books/${book.id}/read`)).content;
    const b = book || { title: "", author: "", year: null, language: "ru", genre: "", description: "", cover_color: COLORS[0], tags: [], external_url: "", is_paid: false, price: 0 };
    const genres = await api("/api/genres").catch(() => []);
    let tags = [...(b.tags || [])];
    setTitle(t(isNew ? "editor.new" : "editor.edit"));
    view.innerHTML = `<div class="page-head"><h1>${esc(t(isNew ? "editor.new" : "editor.edit"))}</h1></div>
      <form class="editor" id="book-form" novalidate>
        <div>
          <div class="form-error" id="ed-err"></div>
          <div class="card">
            <h2>${esc(t("editor.main"))}</h2>
            <label class="field"><span>${esc(t("book.title"))} *</span><input class="input" name="title" required maxlength="300" value="${esc(b.title)}"></label>
            <label class="field"><span>${esc(t("book.author"))} *</span><input class="input" name="author" required maxlength="200" value="${esc(b.author)}"></label>
            <div class="row">
              <label class="field"><span>${esc(t("book.year"))}</span><input class="input" name="year" type="number" min="0" max="2100" value="${b.year ?? ""}"></label>
              <label class="field"><span>${esc(t("book.language"))}</span><select class="select" name="language">${["ru", "kk", "en"].map((l) =>
                `<option value="${l}" ${b.language === l ? "selected" : ""}>${esc(t(LANG_NAMES[l]))}</option>`).join("")}</select></label>
              <label class="field"><span>${esc(t("book.genre"))}</span><input class="input" name="genre" list="genre-list" maxlength="60" value="${esc(b.genre)}">
                <datalist id="genre-list">${genres.map((g) => `<option value="${esc(g.name)}">`).join("")}</datalist></label>
            </div>
            <label class="field"><span>${esc(t("book.about"))}</span><textarea class="textarea" name="description" maxlength="5000">${esc(b.description)}</textarea></label>
            <div class="field"><span>${esc(t("filter.tags"))}</span><div class="tags-input" id="tags-box"><input id="tag-in" maxlength="40" placeholder="${esc(t("editor.tag_ph"))}"></div>
              <small class="hint">${esc(t("editor.tag_hint"))}</small></div>
            <label class="field"><span>${esc(t("editor.external"))}</span><input class="input" name="external_url" type="url" maxlength="500" placeholder="https://library.korkyt.kz/MegaPro/…" value="${esc(b.external_url)}">
              <small class="hint">${esc(t("editor.external_hint"))}</small></label>
          </div>
          <div class="card section">
            <h2>${esc(t("editor.content"))}</h2>
            <p class="muted small">${esc(t("editor.content_hint"))}</p>
            <label class="field"><span>${esc(t("editor.text"))}</span><textarea class="textarea" name="content" style="min-height:220px;font-family:var(--serif)" maxlength="5000000">${esc(content)}</textarea></label>
            <div class="row">
              <label class="drop">${icon("text")}<div>${esc(t("editor.load_txt"))}</div><input type="file" id="txt-file" accept=".txt,text/plain"></label>
              <label class="drop">${icon("pdf")}<div id="pdf-name">${esc(book && book.has_file ? t("editor.pdf_has") : t("editor.load_pdf"))}</div><input type="file" id="pdf-file" accept="application/pdf"></label>
            </div>
            ${book && book.has_file ? `<button type="button" class="btn sm danger" id="pdf-del" style="margin-top:10px">${icon("trash")}${esc(t("editor.pdf_delete"))}</button>` : ""}
          </div>
          ${isNew ? `<div class="card section"><h2>${esc(t("editor.access"))}</h2>
            <label class="check"><input type="checkbox" name="is_paid"><span>${esc(t("editor.paid"))}</span></label>
            <div class="row hidden" id="paid-box" style="margin-top:12px">
              <label class="field"><span>${esc(t("editor.price"))}</span><input class="input" name="price" type="number" min="0" max="1000000" value="990"></label>
              <label class="field"><span>${esc(t("editor.days"))}</span><input class="input" name="paid_days" type="number" min="1" max="3650" value="30"><small class="hint">${esc(t("editor.days_hint"))}</small></label>
            </div></div>` : ""}
          <div class="btn-row section"><button class="btn primary lg" id="ed-save">${esc(t(isNew ? "editor.publish" : "common.save"))}</button>
            <a class="btn lg" href="${isNew ? "#/catalog" : "#/book/" + b.id}">${esc(t("common.cancel"))}</a></div>
        </div>
        <aside class="editor-side"><div id="cover-preview" style="width:100%"></div>
          <div class="field"><span>${esc(t("editor.color"))}</span><div class="colors">${COLORS.map((c) =>
            `<button type="button" data-color="${c}" style="background:${c}" aria-pressed="${c === b.cover_color}" aria-label="${c}"></button>`).join("")}</div>
            <input type="color" name="cover_color" value="${esc(b.cover_color)}" style="width:100%;height:36px;border:0;background:none;cursor:pointer"></div>
          <label class="field"><span>${esc(t("editor.pattern"))}</span><select class="select" name="cover_pattern">${COVER_PATTERNS.map((p) =>
            `<option value="${p}" ${(b.cover_pattern || "auto") === p ? "selected" : ""}>${esc(t("pattern." + p))}</option>`).join("")}</select></label></aside>
      </form>`;

    const form = $("#book-form");
    const preview = () => {
        $("#cover-preview").innerHTML = cover({ id: book?.id, title: form.title.value || t("book.title"), author: form.author.value || t("book.author"),
            cover_color: form.cover_color.value, cover_pattern: form.cover_pattern.value,
            is_paid: form.is_paid?.checked, has_file: !!$("#pdf-file").files[0] || (book && book.has_file) });
    };
    ["title", "author"].forEach((n) => form[n].addEventListener("input", preview));
    form.cover_pattern.addEventListener("change", preview);
    form.cover_color.addEventListener("input", () => { $$("[data-color]").forEach((x) => x.setAttribute("aria-pressed", "false")); preview(); });
    $$("[data-color]").forEach((x) => x.addEventListener("click", () => {
        form.cover_color.value = x.dataset.color; $$("[data-color]").forEach((y) => y.setAttribute("aria-pressed", String(y === x))); preview();
    }));
    form.is_paid?.addEventListener("change", () => { $("#paid-box").classList.toggle("hidden", !form.is_paid.checked); preview(); });

    const renderTags = () => {
        $$("#tags-box .chip").forEach((c) => c.remove());
        $("#tag-in").insertAdjacentHTML("beforebegin", tags.map((x, i) => `<span class="chip">#${esc(x)}<button type="button" data-rmtag="${i}" aria-label="×">${icon("x", "i-sm")}</button></span>`).join(""));
        $$("[data-rmtag]").forEach((x) => x.addEventListener("click", () => { tags.splice(Number(x.dataset.rmtag), 1); renderTags(); }));
    };
    $("#tag-in").addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === ",") {
            e.preventDefault();
            const v = e.target.value.trim().toLowerCase().replace(/^#/, "");
            if (v && !tags.includes(v) && tags.length < 10) { tags.push(v); renderTags(); }
            e.target.value = "";
        } else if (e.key === "Backspace" && !e.target.value && tags.length) { tags.pop(); renderTags(); }
    });
    renderTags();

    $("#txt-file").addEventListener("change", async (e) => {
        const f = e.target.files[0];
        if (!f) return;
        if (f.size > 5 * 1024 * 1024) return toast(t("editor.txt_big"), "error");
        form.content.value = await f.text();
        toast(t("editor.txt_loaded"), "ok");
    });
    $("#pdf-file").addEventListener("change", (e) => {
        const f = e.target.files[0];
        if (f && f.size > 40 * 1024 * 1024) { e.target.value = ""; return toast(t("editor.pdf_big"), "error"); }
        $("#pdf-name").textContent = f ? f.name : t("editor.load_pdf");
        preview();
    });
    $("#pdf-del")?.addEventListener("click", async () => {
        if (!await confirmDialog({ title: t("editor.pdf_delete"), ok: t("common.delete"), danger: true })) return;
        try { await api(`/api/books/${book.id}/file`, { method: "DELETE" }); toast(t("common.saved"), "ok"); Oqu.router.render(); }
        catch (err) { toastError(err); }
    });
    preview();

    form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const err = $("#ed-err");
        err.textContent = "";
        // Пробелы вместо названия тоже считаем пустым полем.
        for (const n of ["title", "author"]) if (!form[n].value.trim()) form[n].value = "";
        if (!Oqu.validateForm(form)) return;
        const data = {
            title: form.title.value.trim(), author: form.author.value.trim(), year: form.year.value ? Number(form.year.value) : null,
            language: form.language.value, genre: form.genre.value.trim().toLowerCase(), description: form.description.value,
            content: form.content.value, external_url: form.external_url.value.trim(), cover_color: form.cover_color.value,
            cover_pattern: form.cover_pattern.value, tags,
        };
        if (isNew) {
            data.is_paid = form.is_paid.checked;
            if (data.is_paid) { data.price = Number(form.price.value) || 0; data.paid_days = Number(form.paid_days.value) || 30; }
        }
        const btn = $("#ed-save");
        btn.disabled = true;
        try {
            const saved = isNew ? await api("/api/books", { method: "POST", body: data })
                : await api(`/api/books/${book.id}`, { method: "PATCH", body: data });
            const pdf = $("#pdf-file").files[0];
            if (pdf) {
                btn.textContent = t("editor.uploading");
                const fd = new FormData(); fd.append("file", pdf);
                await api(`/api/books/${saved.id}/file`, { method: "POST", form: fd });
            }
            toast(t(isNew ? "editor.created" : "common.saved"), "ok");
            location.hash = "#/book/" + saved.id;
        } catch (ex) {
            btn.disabled = false;
            btn.textContent = t(isNew ? "editor.publish" : "common.save");
            if (!Oqu.showServerFieldErrors(form, ex)) {
                err.textContent = Oqu.errorText(ex);
                window.scrollTo({ top: 0, behavior: "smooth" });
            }
        }
    });
}

/* ======================================================================
   Соглашение, политика, о проекте
   ====================================================================== */
async function legalPage(view, name) {
    const lang = Oqu.state.lang;
    let html;
    try {
        const res = await fetch(`/static/legal/${name}.${lang}.html?v=${Oqu.version}`);
        if (!res.ok) throw new Error();
        html = await res.text();
    } catch {
        html = await (await fetch(`/static/legal/${name}.ru.html?v=${Oqu.version}`)).text();
    }
    // Файлы лежат на нашем сервере и не содержат пользовательских данных.
    view.innerHTML = `<article class="legal">${html}</article>`;
    setTitle($("h1", view)?.textContent || "");
}
route(/^\/terms$/, (view) => legalPage(view, "terms"));
route(/^\/privacy$/, (view) => legalPage(view, "privacy"));

route(/^\/about$/, (view) => {
    setTitle(t("footer.about"));
    view.innerHTML = `<article class="legal">
      <h1>${esc(t("about.title"))}</h1>
      <p class="muted">${esc(t("about.lead"))}</p>
      <h2>${esc(t("about.team"))}</h2>
      <ul><li><b>Мұхан Надирхалиф</b> — ${esc(t("about.role_muhan"))}</li><li><b>Хадизат</b> — ${esc(t("about.role_khadizat"))}</li></ul>
      <h2>${esc(t("about.tech"))}</h2>
      <p>${esc(t("about.tech_text"))}</p>
      <p><a class="btn" href="/docs" target="_blank" rel="noopener">${icon("api")}Swagger UI</a> <a class="btn" href="/redoc" target="_blank" rel="noopener">ReDoc</a></p>
      <h2>${esc(t("about.thanks"))}</h2>
      <p>${esc(t("about.thanks_text"))}</p>
      <p class="small muted">${esc(t("about.version", { v: "2.0.0" }))}</p></article>`;
});
})();
