/* =====================================================================
   «Парақ» — мини-игра-кликер (в духе Cookie Clicker) в стиле «Оқу».

   Кликаешь по раскрытой книге — собираешь страницы («парақ» по-казахски).
   За страницы покупаются улучшения: закладки усиливают клик, студенты,
   лампы, полки, читальные залы и типографии приносят страницы сами.
   Разовые улучшения — шутки про команду и одногруппников.
   Купленное наглядно заполняет маленький шкаф (маскот сайта).

   Прогресс гостя хранится в браузере; у вошедшего — на сервере
   (PUT /api/game/me), который проверяет, что такой прогресс можно было
   получить честно, и ведёт таблицу рекордов (видна в «Статистике»).
   ===================================================================== */
(() => {
const GAME_ICONS = {
    bookmark: "bookmark", student: "cap", lamp: "sun", shelf: "case", hall: "home",
    press: "text", library: "book", edige: "chat", altynbek: "shield", temirlan: "star", muhan: "crown",
};
const GAME_SPINE = {
    student: "#2f7f8f", lamp: "#a3782a", shelf: "#7a2e2e", hall: "#1f5f4a", press: "#3d3d3d",
    library: "#6b3fa0", bookmark: "#9b3b54",
};
const SAVE_EVERY_MS = 20000;
// Номер текущего запуска игры. Если страницу открыли заново (или сменили
// язык) пока старая ещё загружалась, старый цикл видит чужой номер и сам
// останавливается — иначе два цикла перерисовывали бы одни строки и
// интерфейс мигал.
let gameGen = 0;
/** Записать текст, только если он изменился (меньше лишних перерисовок). */
const setText = (el, text) => { if (el && el.textContent !== text) el.textContent = text; };

/** Короткая запись больших чисел: 1 234 → 1,2 тыс. */
function fmtBig(n) {
    n = Math.floor(n);
    if (n < 10000) return fmtNum(n);
    const loc = Oqu.state.lang === "kk" && KK_BROKEN ? "ru-RU" : LOCALES[Oqu.state.lang];
    return new Intl.NumberFormat(loc, { notation: "compact", maximumFractionDigits: 1 }).format(n);
}
const fmtRate = (n) => (n < 10 ? n.toFixed(1).replace(".", Oqu.state.lang === "en" ? "." : ",") : fmtBig(n));

Oqu.router.add(/^\/game$/, async (view) => {
    setTitle(t("game.title"));
    const gen = ++gameGen;
    const cfg = await api("/api/game/config");
    if (gen !== gameGen) return;
    const U = cfg.upgrades;
    const user = Oqu.state.user;
    const localKey = "game." + (user ? user.id : "guest");

    // ---- Состояние игры ----
    let st = { pages: 0, pages_total: 0, clicks: 0, upgrades: {} };
    if (user) {
        try { st = await api("/api/game/me"); } catch { /* офлайн — начнём с браузерной копии */ st = store.get(localKey, st); }
    } else {
        st = store.get(localKey, st);
    }
    if (gen !== gameGen) return;   // пока грузились, страницу уже открыли заново
    st.upgrades = { ...(st.upgrades || {}) };
    let dirty = false, lastSync = 0, syncing = false, lastSaveError = "";

    const owned = (k) => st.upgrades[k] || 0;
    const cost = (k) => U[k].cost * cfg.cost_growth ** owned(k);
    const clickPower = () => {
        let base = 1, mult = 1;
        for (const [k, n] of Object.entries(st.upgrades)) {
            base += (U[k].click || 0) * n;
            if (n) mult *= U[k].click_mult || 1;
        }
        return base * mult;
    };
    const rate = () => {
        let r = 0, mult = 1, auto = 0;
        for (const [k, n] of Object.entries(st.upgrades)) {
            r += (U[k].rate || 0) * n;
            auto += (U[k].autoclick || 0) * n;
            if (n) mult *= U[k].rate_mult || 1;
        }
        return r * mult + auto * clickPower();
    };

    const kinds = Object.keys(U);
    const regular = kinds.filter((k) => !U[k].once), special = kinds.filter((k) => U[k].once);
    const upgradeRow = (k) => `<button class="g-up" data-up="${k}" type="button">
        <span class="g-up-ic">${icon(GAME_ICONS[k] || "star")}</span>
        <span class="g-up-txt"><b>${esc(t(`game.u.${k}`))}</b><small>${esc(t(`game.u.${k}.d`))}</small></span>
        <span class="g-up-side"><span class="g-cost" data-cost="${k}"></span><span class="g-owned" data-owned="${k}"></span></span></button>`;

    view.innerHTML = `<div class="page-head"><div><h1>${esc(t("game.title"))}</h1>
        <p class="muted" style="margin:0">${esc(t("game.lead"))}</p></div></div>
      <div class="game">
        <section class="g-stage">
          <div class="g-counter"><b id="g-pages">0</b><span>${esc(t("game.pages"))}</span></div>
          <div class="g-sub"><span id="g-rate"></span> · <span id="g-click"></span></div>
          <button class="g-book" id="g-book" type="button" aria-label="${esc(t("game.click_aria"))}">
            <svg viewBox="0 0 200 140" aria-hidden="true">
              <path class="g-cover" d="M100 26C78 12 46 8 10 14v112c36-6 68-2 90 12 22-14 54-18 90-12V14c-36-6-68-2-90 12z"/>
              <path class="g-paper" d="M100 30C80 18 52 14 20 19v100c32-4 60 0 80 11zM100 30c20-12 48-16 80-11v100c-32-4-60 0-80 11z"/>
              <path class="g-lines" d="M34 40c18-2 36 0 52 6M34 54c18-2 36 0 52 6M34 68c18-2 36 0 52 6M34 82c18-2 36 0 52 6M114 46c16-6 34-8 52-6M114 60c16-6 34-8 52-6M114 74c16-6 34-8 52-6M114 88c16-6 34-8 52-6"/>
              <path class="g-flip" d="M100 30c20-12 48-16 80-11v100c-32-4-60 0-80 11z"/>
              <path class="g-ribbon" d="M140 18v40l7-6 7 6V16"/>
            </svg>
          </button>
          <div class="g-hint">${esc(t("game.hint"))}</div>
          <div class="g-mini-case" aria-hidden="true"><div class="g-case-row" id="g-row1"></div><div class="g-plank"></div>
            <div class="g-case-row" id="g-row2"></div><div class="g-plank"></div></div>
          <div class="g-meta"><span id="g-total"></span> · <span id="g-clicks"></span></div>
          <div class="g-save" id="g-save">${user ? "" : esc(t("game.guest"))}</div>
          <div class="btn-row" style="justify-content:center">
            ${user ? "" : `<button class="btn sm" id="g-login">${esc(t("auth.login"))}</button>`}
            <button class="btn sm ghost" id="g-reset">${icon("trash")}${esc(t("game.reset"))}</button></div>
        </section>
        <section class="g-shop">
          <h2>${esc(t("game.shop"))}</h2>
          <div class="g-list">${regular.map(upgradeRow).join("")}</div>
          <h3 class="g-special-h">${esc(t("game.special"))}</h3>
          <div class="g-list">${special.map(upgradeRow).join("")}</div>
          <div class="g-top"><div class="section-head"><h2>${esc(t("game.top"))}</h2><a href="#/stats">${esc(t("common.all"))} →</a></div>
            <div id="g-top"><div class="skeleton" style="height:120px"></div></div></div>
        </section>
      </div>`;

    // ---- Отрисовка ----
    let caseKey = "";
    const renderCase = () => {
        // Каждое улучшение — корешок в шкафу; разовые — предметы декора.
        const spines = [];
        for (const k of regular) for (let i = 0; i < Math.min(owned(k), 14); i++) spines.push(k);
        const key = spines.join() + special.map(owned).join();
        if (key === caseKey) return;
        caseKey = key;
        const sp = (k, i) => `<i class="g-spine" style="--c:${GAME_SPINE[k] || "#555"};--h:${70 + (hash(k + i) % 26)}%"></i>`;
        const decor = { edige: "clock", altynbek: "globe", temirlan: "candle", muhan: "plant" };
        const extras = special.filter((k) => owned(k)).map((k) => Oqu.decorHtml(decor[k], .62).html);
        const half = Math.ceil(spines.length / 2);
        $("#g-row1").innerHTML = spines.slice(0, half).map(sp).join("") + extras.slice(0, 2).join("")
            || `<span class="g-empty">${esc(t("game.empty_case"))}</span>`;
        $("#g-row2").innerHTML = spines.slice(half).map(sp).join("") + extras.slice(2).join("");
    };
    const root = $(".game", view);
    const render = () => {
        setText($("#g-pages", root), fmtBig(st.pages));
        setText($("#g-rate", root), t("game.per_sec", { n: fmtRate(rate()) }));
        setText($("#g-click", root), t("game.per_click", { n: fmtBig(clickPower()) }));
        setText($("#g-total", root), t("game.total", { n: fmtBig(st.pages_total) }));
        setText($("#g-clicks", root), t("game.clicks", { n: fmtNum(st.clicks) }));
        for (const k of kinds) {
            const btn = $(`[data-up="${k}"]`, root);
            const done = !!U[k].once && owned(k) >= 1;
            const disabled = done || st.pages < cost(k);
            if (btn.disabled !== disabled) btn.disabled = disabled;
            if (btn.classList.contains("done") !== done) btn.classList.toggle("done", done);
            setText($(`[data-cost="${k}"]`, root), done ? "✓" : fmtBig(Math.ceil(cost(k))));
            setText($(`[data-owned="${k}"]`, root), U[k].once ? "" : String(owned(k)));
        }
        renderCase();
    };

    // ---- Сохранение ----
    const saveLocal = () => store.set(localKey, st);
    const sync = async (force = false) => {
        if (!user || syncing || (!dirty && !force)) return;
        // Если за это время вышли или вошли под другим именем — не отправляем
        // чужой прогресс новому пользователю.
        if (Oqu.state.user?.id !== user.id) return;
        syncing = true;
        try {
            const body = { pages: st.pages, pages_total: st.pages_total, clicks: st.clicks, upgrades: st.upgrades };
            await api("/api/game/me", { method: "PUT", body });
            dirty = false; lastSync = Date.now(); lastSaveError = "";
            const el = $("#g-save");
            if (el) el.textContent = t("game.saved", { time: new Date().toLocaleTimeString(LOCALES[Oqu.state.lang], { hour: "2-digit", minute: "2-digit" }) });
        } catch (err) {
            // Сервер не принял сохранение (например, слишком быстрый рост).
            const msg = errorText(err);
            if (msg !== lastSaveError) { toast(msg, "error"); lastSaveError = msg; }
        } finally { syncing = false; }
    };

    // ---- Игровой цикл: страницы от улучшений каждые 100 мс ----
    let last = performance.now(), uiTick = 0;
    const timer = setInterval(() => {
        // Устаревший запуск (страницу открыли заново) — тихо останавливаемся.
        if (gen !== gameGen || !root.isConnected) { clearInterval(timer); return; }
        const now = performance.now();
        const dt = Math.min(5, (now - last) / 1000);   // после сна вкладки — не больше 5 с
        last = now;
        const gain = rate() * dt;
        if (gain > 0) { st.pages += gain; st.pages_total += gain; dirty = true; }
        if (++uiTick % 2 === 0) render();
        if (uiTick % 50 === 0) saveLocal();
        if (user && Date.now() - lastSync > SAVE_EVERY_MS) sync();
    }, 100);

    // ---- Клик по книге ----
    const book = $("#g-book");
    book.addEventListener("click", (e) => {
        const p = clickPower();
        st.pages += p; st.pages_total += p; st.clicks += 1; dirty = true;
        book.classList.remove("flip"); void book.offsetWidth; book.classList.add("flip");
        const r = book.getBoundingClientRect();
        const pop = document.createElement("span");
        pop.className = "g-pop";
        pop.textContent = "+" + fmtBig(p);
        pop.style.left = ((e.clientX || r.left + r.width / 2) - r.left) + "px";
        pop.style.top = ((e.clientY || r.top + r.height / 2) - r.top) + "px";
        book.appendChild(pop);
        setTimeout(() => pop.remove(), 900);
        render();
    });

    // ---- Покупка улучшений ----
    $$("[data-up]").forEach((btn) => btn.addEventListener("click", () => {
        const k = btn.dataset.up;
        if (U[k].once && owned(k)) return;
        const c = cost(k);
        if (st.pages < c) return;
        st.pages -= c;
        st.upgrades[k] = owned(k) + 1;
        dirty = true;
        if (U[k].once) toast(t(`game.u.${k}.toast`), "ok");
        render(); saveLocal(); sync(true);
    }));

    $("#g-login")?.addEventListener("click", () => openAuth("login", "#/game"));
    $("#g-reset").addEventListener("click", async () => {
        if (!await confirmDialog({ title: t("game.reset"), text: t("game.reset_q"), ok: t("game.reset"), danger: true })) return;
        st = { pages: 0, pages_total: 0, clicks: 0, upgrades: {} };
        if (user) { try { await api("/api/game/me", { method: "DELETE" }); } catch (err) { toastError(err); } }
        saveLocal(); dirty = false; render();
    });

    // ---- Рекорды ----
    api("/api/game/leaderboard").then((top) => {
        $("#g-top").innerHTML = top.length ? gameTopHtml(top.slice(0, 5)) : `<p class="muted small">${esc(t("game.top_empty"))}</p>`;
    }).catch(() => { $("#g-top").innerHTML = ""; });

    // При уходе со страницы и закрытии вкладки — сохранить.
    const onHide = () => {
        if (gen !== gameGen) { document.removeEventListener("visibilitychange", onHide); return; }
        if (document.visibilityState === "hidden") { saveLocal(); sync(); }
    };
    document.addEventListener("visibilitychange", onHide);
    Oqu.leave = () => { clearInterval(timer); document.removeEventListener("visibilitychange", onHide); saveLocal(); sync(); };
    render();
});

/** Таблица рекордов игры (используется и на странице «Статистика»). */
function gameTopHtml(top) {
    return top.map((e) => `<div class="leader${e.place === 1 ? " first" : ""}">
        <div class="place">${e.place}</div>
        ${Oqu.avatar(e.display_name || e.username)}
        <div><b>${esc(e.display_name || e.username)}</b><div class="small muted">${esc(e.rate > 0
            ? t("game.per_sec", { n: fmtRate(e.rate) }) : t("game.clicks", { n: fmtNum(e.clicks) }))}</div></div>
        <div class="count">${fmtBig(e.pages_total)}</div></div>`).join("");
}
Oqu.gameTopHtml = gameTopHtml;
})();
