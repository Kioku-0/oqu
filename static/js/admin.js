/* =====================================================================
   Оқу — панель модерации и администрирования.
   Каждая вкладка видна только тем, у кого есть право (принцип наименьших
   привилегий); сервер всё равно проверяет права у каждого запроса.
   ===================================================================== */
"use strict";

(() => {
const { $, $$, esc, icon, t, api, can, toast, toastError, openModal, confirmDialog, formDialog,
    setTitle, emptyState, pager, fmtDate, fmtAgo, avatar, roleBadge, debounce } = Oqu;

const ROLES = ["user", "student", "author", "editor", "moderator"];
// Готовые сроки бана в секундах (в том числе «секунда» — для демонстрации).
const BAN_TERMS = [[1, "ban.t_sec"], [3600, "ban.t_hour"], [86400, "ban.t_day"], [604800, "ban.t_week"],
    [2592000, "ban.t_month"], ["", "ban.forever"], ["custom", "ban.t_custom"]];

Oqu.router.add(/^\/admin(?:\/(\w+))?$/, async (view, [tab]) => {
    const tabs = [
        ["users", "admin.users", "user.list"],
        ["unban", "admin.unban", "unban.manage"],
        ["students", "admin.students", "user.verify_student"],
        ["log", "admin.log", "log.read"],
    ].filter(([, , perm]) => can(perm));
    if (!tabs.length) { view.innerHTML = emptyState("lock", t("error.forbidden_title"), t("error.forbidden")); return; }
    tab = tabs.some(([k]) => k === tab) ? tab : tabs[0][0];
    setTitle(t("nav.admin"));
    view.innerHTML = `<div class="page-head"><div><h1>${esc(t("nav.admin"))}</h1>
        <p class="muted" style="margin:0">${esc(t("admin.lead", { role: t("role." + Oqu.state.user.role) }))}</p></div></div>
      <div class="tabs" role="tablist">${tabs.map(([k, l]) => `<button role="tab" data-tab="${k}" aria-selected="${k === tab}">${icon({ users: "user", unban: "lock", students: "cap", log: "clock" }[k])}${esc(t(l))}</button>`).join("")}</div>
      <div id="admin-body"></div>`;
    $$("[data-tab]").forEach((b) => b.addEventListener("click", () => { location.hash = "#/admin/" + b.dataset.tab; }));
    const body = $("#admin-body");
    await { users: usersTab, unban: unbanTab, students: studentsTab, log: logTab }[tab](body);
}, { auth: true });

/* ---------- Пользователи --------------------------------------------- */
async function usersTab(body) {
    let page = 1, query = "";
    body.innerHTML = `<div class="admin-filters"><input class="input" id="u-q" maxlength="64" placeholder="${esc(t("admin.user_search"))}"></div><div id="u-list"></div>`;
    $("#u-q").addEventListener("input", debounce((e) => { query = e.target.value.trim(); page = 1; load(); }, 350));
    const me = Oqu.state.user;
    const isOwner = me.role === "owner";

    async function load() {
        const d = await api(`/api/admin/users?page=${page}&page_size=15&query=${encodeURIComponent(query)}`);
        $("#u-list").innerHTML = `<div class="table-wrap"><table class="data"><thead><tr><th>${esc(t("admin.user"))}</th><th>${esc(t("admin.role"))}</th>
          <th>${esc(t("admin.status"))}</th><th>${esc(t("admin.registered"))}</th><th></th></tr></thead><tbody>
          ${d.items.map((u) => `<tr><td><div style="display:flex;gap:10px;align-items:center">${avatar(u.display_name || u.username)}<div>
            <b>${esc(u.display_name || u.username)}</b><div class="small muted">@${esc(u.username)} · ${esc(u.email)}</div></div></div></td>
            <td>${isOwner && u.role !== "owner" ? `<select class="select" data-role="${u.id}" style="min-height:34px;width:auto">${ROLES.map((r) =>
                `<option value="${r}" ${u.role === r ? "selected" : ""}>${esc(t("role." + r))}</option>`).join("")}</select>` : roleBadge(u.role)}</td>
            <td>${u.banned ? `<span class="badge danger" title="${esc(u.ban_reason)}">${icon("lock", "i-sm")} ${esc(u.ban_until ? t("admin.banned_until", { d: fmtDate(u.ban_until, true) }) : t("ban.forever"))}</span>`
                : u.is_student ? `<span class="badge free">${icon("cap", "i-sm")} ${esc(t("profile.verified"))}</span>` : `<span class="muted">—</span>`}</td>
            <td class="nowrap">${esc(fmtDate(u.created_at))}</td>
            <td class="nowrap">${u.role === "owner" || u.id === me.id ? "" : `<div class="btn-row" style="flex-wrap:nowrap">
              ${can("user.ban") ? (u.banned ? `<button class="btn sm" data-unban="${u.id}">${esc(t("admin.unban_btn"))}</button>`
                : `<button class="btn sm danger" data-ban="${u.id}" data-name="${esc(u.username)}">${esc(t("admin.ban_btn"))}</button>`) : ""}
              ${can("user.verify_student") && !u.is_student ? `<button class="btn sm" data-verify="${u.id}" title="${esc(t("admin.verify"))}">${icon("cap", "i-sm")}</button>` : ""}
              ${isOwner ? `<button class="btn sm ghost" data-udel="${u.id}" data-name="${esc(u.username)}" title="${esc(t("common.delete"))}">${icon("trash", "i-sm")}</button>` : ""}
            </div>`}</td></tr>`).join("")}</tbody></table></div>
          ${pager(d, (n) => { page = n; load(); })}`;
        bind();
    }

    function bind() {
        $$("[data-role]").forEach((s) => s.addEventListener("change", async () => {
            try { await api(`/api/admin/users/${s.dataset.role}/role`, { method: "POST", body: { role: s.value } }); toast(t("admin.role_set"), "ok"); load(); }
            catch (e) { toastError(e); load(); }
        }));
        $$("[data-ban]").forEach((b) => b.addEventListener("click", () => banDialog(Number(b.dataset.ban), b.dataset.name).then((ok) => ok && load())));
        $$("[data-unban]").forEach((b) => b.addEventListener("click", async () => {
            try { await api(`/api/admin/users/${b.dataset.unban}/unban`, { method: "POST" }); toast(t("admin.unbanned"), "ok"); load(); }
            catch (e) { toastError(e); }
        }));
        $$("[data-verify]").forEach((b) => b.addEventListener("click", async () => {
            if (!await confirmDialog({ title: t("admin.verify_q") })) return;
            try { await api(`/api/admin/users/${b.dataset.verify}/verify-student`, { method: "POST" }); toast(t("admin.verified"), "ok"); load(); }
            catch (e) { toastError(e); }
        }));
        $$("[data-udel]").forEach((b) => b.addEventListener("click", async () => {
            if (!await confirmDialog({ title: t("admin.delete_q", { name: b.dataset.name }), text: t("admin.delete_text"), ok: t("common.delete"), danger: true })) return;
            try { await api(`/api/admin/users/${b.dataset.udel}`, { method: "DELETE" }); toast(t("admin.deleted"), "ok"); load(); }
            catch (e) { toastError(e); }
        }));
    }
    await load();
}

function banDialog(userId, name) {
    return new Promise((resolve) => {
        let done = false;
        const card = openModal(`<h2>${esc(t("admin.ban_title", { name }))}</h2>
          <form id="ban-form"><div class="form-error" id="ban-err"></div>
            <label class="field"><span>${esc(t("ban.reason"))} *</span><textarea class="textarea" name="reason" maxlength="500" required placeholder="${esc(t("admin.ban_reason_ph"))}"></textarea></label>
            <div class="field"><span>${esc(t("admin.ban_term"))}</span><div class="chips">${BAN_TERMS.map(([v, k], i) =>
                `<button type="button" class="chip" data-term="${v}" aria-pressed="${i === 2}">${esc(t(k))}</button>`).join("")}</div></div>
            <div class="row hidden" id="custom-term"><label class="field"><span>${esc(t("admin.ban_amount"))}</span><input class="input" type="number" name="amount" min="1" value="2"></label>
              <label class="field"><span>${esc(t("admin.ban_unit"))}</span><select class="select" name="unit">
                <option value="1">${esc(t("unit.seconds"))}</option><option value="60">${esc(t("unit.minutes"))}</option>
                <option value="3600" selected>${esc(t("unit.hours"))}</option><option value="86400">${esc(t("unit.days"))}</option></select></label></div>
            <div class="btn-row" style="justify-content:flex-end"><button type="button" class="btn" data-close>${esc(t("common.cancel"))}</button>
              <button class="btn danger">${esc(t("admin.ban_btn"))}</button></div></form>`, { onClose: () => { if (!done) resolve(false); } });
        let term = "86400";
        $$("[data-term]", card).forEach((b) => b.addEventListener("click", () => {
            term = b.dataset.term;
            $$("[data-term]", card).forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
            $("#custom-term", card).classList.toggle("hidden", term !== "custom");
        }));
        $("#ban-form", card).addEventListener("submit", async (e) => {
            e.preventDefault();
            const reason = e.target.reason.value.trim();
            if (!reason) { $("#ban-err", card).textContent = t("admin.need_reason"); return; }
            let seconds = term === "" ? null : Number(term);
            if (term === "custom") seconds = Math.max(1, Number(e.target.amount.value) || 1) * Number(e.target.unit.value);
            try {
                await api(`/api/admin/users/${userId}/ban`, { method: "POST", body: { reason, seconds } });
                done = true; Oqu.closeModal(); toast(t("admin.banned"), "ok"); resolve(true);
            } catch (err) { $("#ban-err", card).textContent = Oqu.errorText(err); }
        });
    });
}

/* ---------- Заявки на разбан ----------------------------------------- */
async function unbanTab(body) {
    const items = await api("/api/admin/unban-requests");
    if (!items.length) { body.innerHTML = emptyState("check", t("admin.no_requests")); return; }
    body.innerHTML = `<div class="comments">${items.map((r) => `<div class="card"><div class="comment-head">${avatar(r.username)}<b>@${esc(r.username)}</b>
        <span class="small muted">${esc(fmtAgo(r.created_at))}</span></div>
        <p class="small muted" style="margin:6px 0">${esc(t("ban.reason"))}: ${esc(r.ban_reason || "—")}</p>
        <p class="comment-text">${esc(r.text)}</p>
        <div class="btn-row"><button class="btn primary sm" data-res="${r.id}" data-ok="1">${icon("check")}${esc(t("admin.approve"))}</button>
        <button class="btn sm" data-res="${r.id}" data-ok="0">${icon("x")}${esc(t("admin.reject"))}</button></div></div>`).join("")}</div>`;
    $$("[data-res]", body).forEach((b) => b.addEventListener("click", async () => {
        try {
            await api(`/api/admin/unban-requests/${b.dataset.res}/resolve`, { method: "POST", body: { approve: b.dataset.ok === "1" } });
            toast(t("admin.resolved"), "ok"); unbanTab(body);
        } catch (e) { toastError(e); }
    }));
}

/* ---------- Заявки студентов ----------------------------------------- */
async function studentsTab(body) {
    const items = await api("/api/admin/student-requests");
    if (!items.length) { body.innerHTML = emptyState("check", t("admin.no_requests")); return; }
    body.innerHTML = `<div class="comments">${items.map((r) => `<div class="card req">
        <img data-img="${r.id}" alt="${esc(t("admin.card_photo"))}">
        <div style="flex:1;min-width:200px"><div class="comment-head">${avatar(r.display_name || r.username)}<b>${esc(r.display_name)}</b>
          <span class="small muted">@${esc(r.username)} · ${esc(fmtAgo(r.created_at))}</span></div>
          <p class="small muted">${esc(t("admin.student_hint"))}</p>
          <div class="btn-row"><button class="btn primary sm" data-sres="${r.id}" data-ok="1">${icon("check")}${esc(t("admin.approve"))}</button>
          <button class="btn sm" data-sres="${r.id}" data-ok="0">${icon("x")}${esc(t("admin.reject"))}</button></div></div></div>`).join("")}</div>`;
    // Фото защищено правами, поэтому грузим его с токеном и показываем как blob.
    for (const img of $$("[data-img]", body)) {
        api(`/api/admin/student-requests/${img.dataset.img}/image`, { blob: true }).then((blob) => {
            img.src = URL.createObjectURL(blob);
            img.addEventListener("click", () => openModal(`<img src="${img.src}" alt="" style="width:100%;border-radius:8px">`, { wide: true }));
        }).catch(() => { img.alt = "—"; });
    }
    $$("[data-sres]", body).forEach((b) => b.addEventListener("click", async () => {
        try {
            await api(`/api/admin/student-requests/${b.dataset.sres}/resolve`, { method: "POST", body: { approve: b.dataset.ok === "1" } });
            toast(t("admin.resolved"), "ok"); studentsTab(body);
        } catch (e) { toastError(e); }
    }));
}

/* ---------- Журнал действий (усложнение варианта 11) ------------------- */
async function logTab(body) {
    const f = { action: "", date_from: "", date_to: "", page: 1 };
    body.innerHTML = `<p class="muted">${esc(t("log.lead"))}</p>
      <div class="admin-filters">
        <select class="select" id="l-action"><option value="">${esc(t("log.all_actions"))}</option>
          ${["login", "login_failed", "register", "read_book", "book_add", "book_edit", "book_delete", "comment_add", "comment_edit", "comment_delete",
             "ban", "unban", "role_change", "purchase", "student_request", "student_review", "unban_request", "account_delete", "password_change", "log_export"]
             .map((a) => `<option value="${a}">${esc(t("log.a." + a))}</option>`).join("")}</select>
        <input class="input" type="date" id="l-from" aria-label="${esc(t("filter.from"))}">
        <input class="input" type="date" id="l-to" aria-label="${esc(t("filter.to"))}">
        <button class="btn" id="l-csv">${icon("download")}CSV</button>
      </div><div id="l-list"></div>`;
    $("#l-action").addEventListener("change", (e) => { f.action = e.target.value; f.page = 1; load(); });
    $("#l-from").addEventListener("change", (e) => { f.date_from = e.target.value; f.page = 1; load(); });
    $("#l-to").addEventListener("change", (e) => { f.date_to = e.target.value; f.page = 1; load(); });
    $("#l-csv").addEventListener("click", async () => {
        try {
            const blob = await api("/api/admin/log.csv", { blob: true });
            const a = document.createElement("a");
            a.href = URL.createObjectURL(blob); a.download = "oqu-log.csv"; a.click();
            setTimeout(() => URL.revokeObjectURL(a.href), 1000);
        } catch (e) { toastError(e); }
    });

    async function load() {
        const q = new URLSearchParams({ page: f.page, page_size: 30 });
        for (const k of ["action", "date_from", "date_to"]) if (f[k]) q.set(k, f[k]);
        const d = await api("/api/admin/log?" + q);
        $("#l-list").innerHTML = d.items.length ? `<div class="table-wrap"><table class="data"><thead><tr>
          <th>${esc(t("log.time"))}</th><th>${esc(t("admin.user"))}</th><th>${esc(t("log.action"))}</th><th>${esc(t("log.details"))}</th><th>IP</th></tr></thead>
          <tbody>${d.items.map((r) => `<tr><td class="nowrap" title="UTC ${esc(r.created_at)}">${esc(fmtDate(r.created_at, true))}</td>
            <td>${r.username ? "@" + esc(r.username) : `<span class="muted">${esc(t("log.guest"))}</span>`}</td>
            <td><span class="log-action">${esc(Oqu.state.t["log.a." + r.action] || r.action)}</span></td>
            <td class="small">${esc(r.details)}</td><td class="small muted">${esc(r.ip)}</td></tr>`).join("")}</tbody></table></div>
          ${pager(d, (n) => { f.page = n; load(); })}
          <p class="small muted">${esc(t("log.total", { n: d.total }))} · ${esc(t("log.file_hint"))}</p>`
          : emptyState("clock", t("log.empty"));
    }
    await load();
}
})();
