const WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];

function weekdayLabel(wd) {
  const n = Number(wd);
  if (n === -1) return "每天";
  return WEEKDAYS[n] || String(wd);
}

function actionLabel(action) {
  return action === "close" ? "定时关闭" : "定时启动";
}

const CATEGORY_LABELS = {
  entertainment: "游戏娱乐",
  study: "学习",
  work: "办公",
  other: "其他",
};

function categoryLabel(code) {
  return CATEGORY_LABELS[code] || "其他";
}

function categoryOptions(selected) {
  return Object.entries(CATEGORY_LABELS)
    .map(
      ([code, label]) =>
        `<option value="${code}" ${code === selected ? "selected" : ""}>${label}</option>`
    )
    .join("");
}

async function api(path, options = {}) {
  const opts = { headers: { "Content-Type": "application/json" }, ...options };
  if (opts.body && typeof opts.body === "object") opts.body = JSON.stringify(opts.body);
  const res = await fetch(path, opts);
  const ct = res.headers.get("content-type") || "";
  const data = ct.includes("application/json") ? await res.json() : await res.text();
  if (!res.ok) {
    const msg = (data && data.detail)
      ? (typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail))
      : res.statusText;
    throw new Error(msg);
  }
  return data;
}

function toast(msg) {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.classList.add("show");
  setTimeout(() => el.classList.remove("show"), 2800);
}

function fmtMin(seconds) {
  return (Number(seconds || 0) / 60).toFixed(1);
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}

function iconSrc(exePath, size = 32) {
  return `/api/icons?path=${encodeURIComponent(exePath || "")}&size=${size}`;
}

function appIconHtml(exePath, name, size = 32) {
  const letter = escapeHtml((name || "?").trim().charAt(0).toUpperCase() || "?");
  const cls = size >= 40 ? "app-icon lg" : "app-icon";
  return `
    <span class="icon-wrap">
      <img class="${cls}" src="${iconSrc(exePath, size)}" alt="" loading="lazy"
        onerror="this.style.display='none';this.nextElementSibling.style.display='grid'" />
      <span class="${cls} fallback" style="display:none">${letter}</span>
    </span>`;
}

document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById(`tab-${btn.dataset.tab}`).classList.add("active");
  });
});

let appsCache = [];
let rulesAppId = null;
let foregroundAppId = null;

async function loadStatus() {
  try {
    const s = await api("/api/system/status");
    const prevFg = foregroundAppId;
    foregroundAppId = s.foreground_app_id ?? null;
    const gPill = s.guard_running
      ? `<span class="pill ok">运行中</span>`
      : `<span class="pill off">停止</span>`;
    const lPill = s.launcher_running
      ? `<span class="pill ok">运行中</span>`
      : `<span class="pill off">停止</span>`;
    document.getElementById("status-box").innerHTML = `
      <div><strong>守护</strong> ${gPill} · ${s.last_guard_scan_at ? new Date(s.last_guard_scan_at).toLocaleTimeString() : "-"}</div>
      <div><strong>调度</strong> ${lPill} · ${s.last_launcher_check_at ? new Date(s.last_launcher_check_at).toLocaleTimeString() : "-"}</div>
      <div><strong>今日击杀</strong> ${s.today_kill_count} · 管控 ${s.tracked_apps} · 计时中 ${s.live_tracked ?? 0}</div>
      <div><strong>当前前台</strong> ${
        s.foreground_app_name
          ? escapeHtml(s.foreground_app_name)
          : (s.foreground_name ? escapeHtml(s.foreground_name) + "（未登记）" : "未检测到")
      }${s.usage_foreground_only ? " <span class=\"muted\">· 仅前台计时</span>" : ""}</div>
      <div class="muted">${escapeHtml(s.launcher_last_tick || "")} ${s.launcher_last_error ? "· err:" + escapeHtml(s.launcher_last_error) : ""}</div>
    `;
    if (prevFg !== foregroundAppId && appsCache.length) {
      renderAppsList();
    }
  } catch (e) {
    document.getElementById("status-box").textContent = "状态失败: " + e.message;
  }
}

document.getElementById("btn-toggle-form").onclick = () => {
  document.getElementById("app-form").classList.toggle("open");
};

async function loadApps() {
  appsCache = await api("/api/apps/");
  renderAppsList();
}

function filteredApps() {
  const cat = document.getElementById("apps-filter-cat").value;
  const q = (document.getElementById("apps-search")?.value || "").trim().toLowerCase();
  return appsCache.filter((a) => {
    if (cat && (a.category || "other") !== cat) return false;
    if (!q) return true;
    const hay = `${a.name || ""} ${a.process_name || ""} ${a.exe_path || ""} ${a.notes || ""}`.toLowerCase();
    return hay.includes(q);
  });
}

function renderAppsList() {
  const list = filteredApps();
  const box = document.getElementById("apps-list");
  const q = (document.getElementById("apps-search")?.value || "").trim();
  const cat = document.getElementById("apps-filter-cat").value;
  if (!list.length) {
    let msg = "暂无应用 — 去「发现」扫描导入，或点「手动登记」";
    if (appsCache.length) {
      if (q && cat) msg = "没有同时匹配搜索与分类的应用";
      else if (q) msg = "没有匹配搜索的应用";
      else msg = "该分类下暂无应用";
    }
    box.innerHTML = `<div class="empty-state">${msg}</div>`;
    return;
  }
  box.innerHTML = list.map((a, idx) => `
    <article class="app-row ${foregroundAppId === a.id ? "is-foreground" : ""}">
      ${appIconHtml(a.exe_path, a.name, 40)}
      <div class="meta">
        <h3>${escapeHtml(a.name)}${foregroundAppId === a.id ? ` <span class="tag fg">前台</span>` : ""}</h3>
        <div class="path">${escapeHtml(a.process_name)} · ${escapeHtml(a.exe_path)}</div>
        <div class="tags">
          ${a.usage_rank ? `<span class="tag rank" title="近7天使用排名">#${a.usage_rank}</span>` : `<span class="tag">未使用</span>`}
          <span class="tag usage" title="近7天前台时长">${fmtMinNice(a.usage_7d_minutes || 0)} / 7天</span>
          <label class="cat-inline" title="更改分类">
            <select class="cat-select cat-${escapeHtml(a.category || "other")}"
                    data-app-id="${a.id}" data-prev="${escapeHtml(a.category || "other")}"
                    onchange="changeAppCategory(${a.id}, this)">
              ${categoryOptions(a.category || "other")}
            </select>
          </label>
          <span class="tag ${a.enabled ? "on" : "off"}">${a.enabled ? "启用" : "停用"}</span>
          <span class="tag">日限 ${a.daily_limit_minutes ?? "不限"}</span>
          <span class="tag">会话 ${a.session_limit_minutes ?? "不限"}</span>
          <span class="tag">#${a.id}</span>
        </div>
      </div>
      <div class="app-ops">
        <button class="btn sm primary" onclick="openRules(${a.id})">规则</button>
        <button class="btn sm" onclick="applyDefaults(${a.id})" title="按分类重写时段与日限">套用默认</button>
        <button class="btn sm" onclick="editApp(${a.id})">编辑</button>
        <button class="btn sm" onclick="launchApp(${a.id})">启动</button>
        <button class="btn sm" onclick="killApp(${a.id})">结束</button>
        <button class="btn sm danger" onclick="deleteApp(${a.id})">删除</button>
      </div>
    </article>
  `).join("");
}

document.getElementById("apps-filter-cat").onchange = () => renderAppsList();
document.getElementById("apps-search").oninput = () => renderAppsList();

window.changeAppCategory = async function (id, selectEl) {
  const next = selectEl.value;
  const prev = selectEl.dataset.prev || "other";
  if (next === prev) return;
  if (!confirm(`确认将分类改为「${categoryLabel(next)}」？`)) {
    selectEl.value = prev;
    return;
  }
  const applyDefaults = confirm("是否套用该分类的默认时段与日限？\n确定=套用 · 取消=仅改分类");
  selectEl.disabled = true;
  try {
    await api(`/api/apps/${id}`, {
      method: "PUT",
      body: { category: next, apply_defaults: applyDefaults },
    });
    selectEl.dataset.prev = next;
    selectEl.className = `cat-select cat-${next}`;
    toast(applyDefaults ? "已更改分类并套用默认规则" : "已更改分类");
    await loadApps();
  } catch (e) {
    selectEl.value = prev;
    toast(e.message);
  } finally {
    selectEl.disabled = false;
  }
};

window.applyDefaults = async function (id) {
  if (!confirm("按当前分类重写时段与日限？\n游戏娱乐=周末06:00–22:20+日限2h\n其他=每天05:00–22:20")) return;
  try {
    await api(`/api/apps/${id}/apply-defaults`, { method: "POST" });
    toast("已套用分类默认规则");
    await loadApps();
  } catch (e) {
    toast(e.message);
  }
};

window.editApp = function (id) {
  const a = appsCache.find((x) => x.id === id);
  if (!a) return;
  const form = document.getElementById("app-form");
  form.classList.add("open");
  document.getElementById("app-id").value = a.id;
  document.getElementById("app-name").value = a.name;
  document.getElementById("app-exe").value = a.exe_path;
  document.getElementById("app-proc").value = a.process_name;
  document.getElementById("app-category").value = a.category || "other";
  document.getElementById("app-daily").value = a.daily_limit_minutes ?? "";
  document.getElementById("app-session").value = a.session_limit_minutes ?? "";
  document.getElementById("app-enabled").checked = !!a.enabled;
  document.getElementById("app-apply-defaults").checked = false;
  document.getElementById("app-notes").value = a.notes || "";
  form.scrollIntoView({ behavior: "smooth", block: "nearest" });
  toast("已载入到表单");
};

document.getElementById("btn-app-reset").onclick = () => {
  document.getElementById("app-form").reset();
  document.getElementById("app-id").value = "";
  document.getElementById("app-enabled").checked = true;
  document.getElementById("app-apply-defaults").checked = true;
  document.getElementById("app-category").value = "other";
};

document.getElementById("app-form").onsubmit = async (e) => {
  e.preventDefault();
  const id = document.getElementById("app-id").value;
  const body = {
    name: document.getElementById("app-name").value.trim(),
    exe_path: document.getElementById("app-exe").value.trim(),
    process_name: document.getElementById("app-proc").value.trim() || undefined,
    category: document.getElementById("app-category").value,
    daily_limit_minutes: document.getElementById("app-daily").value
      ? Number(document.getElementById("app-daily").value) : null,
    session_limit_minutes: document.getElementById("app-session").value
      ? Number(document.getElementById("app-session").value) : null,
    enabled: document.getElementById("app-enabled").checked,
    notes: document.getElementById("app-notes").value || null,
    apply_defaults: document.getElementById("app-apply-defaults").checked,
  };
  try {
    if (id) await api(`/api/apps/${id}`, { method: "PUT", body });
    else await api("/api/apps/", { method: "POST", body });
    toast("已保存");
    document.getElementById("btn-app-reset").click();
    document.getElementById("app-form").classList.remove("open");
    await loadApps();
  } catch (err) {
    toast("保存失败: " + err.message);
  }
};

window.deleteApp = async function (id) {
  if (!confirm("确认删除？")) return;
  try {
    await api(`/api/apps/${id}`, { method: "DELETE" });
    toast("已删除");
    await loadApps();
  } catch (err) {
    toast(err.message);
  }
};

window.killApp = async function (id) {
  try {
    await api(`/api/system/apps/${id}/kill-now`, { method: "POST" });
    toast("已请求结束");
    loadStatus();
  } catch (err) {
    toast(err.message);
  }
};

window.launchApp = async function (id) {
  try {
    await api(`/api/system/apps/${id}/launch-now`, { method: "POST" });
    toast("已启动");
  } catch (err) {
    toast(err.message);
  }
};

/* —— 规则模态 —— */
function openModal() {
  const m = document.getElementById("rules-modal");
  m.classList.remove("hidden");
  m.setAttribute("aria-hidden", "false");
}
function closeModal() {
  const m = document.getElementById("rules-modal");
  m.classList.add("hidden");
  m.setAttribute("aria-hidden", "true");
}
document.querySelectorAll("[data-close]").forEach((el) => {
  el.addEventListener("click", closeModal);
});

window.openRules = async function (id) {
  rulesAppId = Number(id);
  const a = appsCache.find((x) => x.id === rulesAppId);
  document.getElementById("rules-title").textContent = a ? a.name : "#" + id;
  document.getElementById("rules-app-badge").textContent =
    `应用 #${rulesAppId} · 修改不会影响其他应用`;
  const wrap = document.getElementById("rules-icon-wrap");
  if (a) wrap.innerHTML = appIconHtml(a.exe_path, a.name, 48);
  else wrap.innerHTML = `<span class="app-icon lg fallback">?</span>`;
  setWeekdays([0, 1, 2, 3, 4]);
  document.getElementById("win-start").value = "09:00";
  document.getElementById("win-end").value = "21:00";
  document.getElementById("sch-weekday").value = "-1";
  document.getElementById("sch-action").value = "launch";
  document.getElementById("sch-time").value = "09:00";
  openModal();
  await refreshRulesTables();
};

async function refreshRulesTables() {
  if (!rulesAppId) return;
  const wins = await api(`/api/windows/app/${rulesAppId}`);
  document.querySelector("#win-table tbody").innerHTML = wins.map((w) => `
    <tr>
      <td>${weekdayLabel(w.weekday)}</td>
      <td>${String(w.start_time).slice(0, 5)}</td>
      <td>${String(w.end_time).slice(0, 5)}</td>
      <td><button class="btn sm danger" onclick="deleteWindow(${w.id})">删</button></td>
    </tr>
  `).join("") || `<tr><td colspan="4">无时段（全天开放）</td></tr>`;

  const sch = await api(`/api/schedules/app/${rulesAppId}`);
  document.querySelector("#sch-table tbody").innerHTML = sch.map((s) => `
    <tr>
      <td>${weekdayLabel(s.weekday)}</td>
      <td>${actionLabel(s.action)}</td>
      <td>${String(s.launch_time).slice(0, 5)}</td>
      <td>${s.last_fired_date || "-"}</td>
      <td>
        <button class="btn sm" onclick="resetFired(${s.id})">重置触发</button>
        <button class="btn sm danger" onclick="deleteSchedule(${s.id})">删</button>
      </td>
    </tr>
  `).join("") || `<tr><td colspan="5">无定时启停</td></tr>`;
}

function selectedWeekdays() {
  return [...document.querySelectorAll("#win-days input:checked")].map((el) => Number(el.value));
}

function setWeekdays(list) {
  document.querySelectorAll("#win-days input").forEach((el) => {
    el.checked = list.includes(Number(el.value));
  });
}

document.getElementById("btn-win-workdays").onclick = () => setWeekdays([0, 1, 2, 3, 4]);
document.getElementById("btn-win-everyday").onclick = () => setWeekdays([0, 1, 2, 3, 4, 5, 6]);
document.getElementById("btn-sch-today").onclick = () => {
  document.getElementById("sch-weekday").value = String(
    new Date().getDay() === 0 ? 6 : new Date().getDay() - 1
  );
};

document.getElementById("btn-add-windows").onclick = async () => {
  if (!rulesAppId) return toast("请先从应用列表打开规则");
  const days = selectedWeekdays();
  if (!days.length) return toast("请至少勾选一个星期");
  try {
    await api(`/api/windows/app/${rulesAppId}/batch`, {
      method: "POST",
      body: {
        weekdays: days,
        start_time: document.getElementById("win-start").value,
        end_time: document.getElementById("win-end").value,
      },
    });
    toast(`已为应用 #${rulesAppId} 添加时段`);
    await refreshRulesTables();
  } catch (e) {
    toast(e.message);
  }
};

window.deleteWindow = async function (id) {
  if (!rulesAppId) return;
  await api(`/api/windows/${id}`, { method: "DELETE" });
  await refreshRulesTables();
};

document.getElementById("btn-add-schedule").onclick = async () => {
  if (!rulesAppId) return toast("请先从应用列表打开规则");
  try {
    const action = document.getElementById("sch-action").value;
    await api(`/api/schedules/app/${rulesAppId}`, {
      method: "POST",
      body: {
        weekday: Number(document.getElementById("sch-weekday").value),
        launch_time: document.getElementById("sch-time").value + ":00",
        action,
        enabled: true,
      },
    });
    toast(`已为应用 #${rulesAppId} 添加${actionLabel(action)}`);
    await refreshRulesTables();
  } catch (e) {
    toast(e.message);
  }
};

async function quickSchedule(minutes, action) {
  if (!rulesAppId) return toast("请先从应用列表打开规则");
  try {
    const sch = await api(`/api/schedules/app/${rulesAppId}/in-minutes`, {
      method: "POST",
      body: { minutes_from_now: minutes, action },
    });
    toast(
      `已预约约 ${minutes} 分钟后${actionLabel(action)}（${String(sch.launch_time).slice(0, 8)}）`
    );
    await refreshRulesTables();
    loadStatus();
  } catch (e) {
    toast(e.message);
  }
}

document.getElementById("btn-sch-1min").onclick = () => quickSchedule(1, "launch");
document.getElementById("btn-sch-1min-close").onclick = () => quickSchedule(1, "close");

window.deleteSchedule = async function (id) {
  if (!rulesAppId) return;
  await api(`/api/schedules/${id}`, { method: "DELETE" });
  await refreshRulesTables();
};

window.resetFired = async function (id) {
  await api(`/api/schedules/${id}/reset-fired`, { method: "POST" });
  toast("已清除今日触发标记");
  await refreshRulesTables();
};

/* —— 发现 —— */
function renderDiscover(rows) {
  const filter = (document.getElementById("discover-filter").value || "").trim().toLowerCase();
  const list = document.getElementById("discover-list");
  const filtered = !filter
    ? rows
    : rows.filter((r) =>
        `${r.name} ${r.exe_path} ${r.process_name}`.toLowerCase().includes(filter)
      );

  if (!filtered.length) {
    list.innerHTML = `<div class="empty-state">${rows.length ? "无匹配结果" : "未发现应用"}</div>`;
    return;
  }

    list.innerHTML = filtered.map((r) => {
    const i = rows.indexOf(r);
    const sug = r.suggested_category || "other";
    const forced = document.getElementById("discover-default-cat").value;
    const cat = forced || sug;
    return `
      <label class="disc-card ${r.already_registered ? "registered" : ""}">
        <input type="checkbox" class="disc-check" data-i="${i}" ${r.already_registered ? "disabled" : ""} />
        ${appIconHtml(r.exe_path, r.name, 36)}
        <div>
          <div class="name">${escapeHtml(r.name)}</div>
          <div class="path">${escapeHtml(r.exe_path)}</div>
          <div class="src">
            <span class="tag">${escapeHtml(r.source)}</span>
            <span class="tag ${r.already_registered ? "off" : "on"}">
              ${r.already_registered ? "已登记#" + r.registered_id : "可导入"}
            </span>
          </div>
          ${r.already_registered ? "" : `
            <select class="disc-cat" data-i="${i}" onclick="event.stopPropagation()" onmousedown="event.stopPropagation()">
              ${categoryOptions(cat)}
            </select>
          `}
        </div>
      </label>
    `;
  }).join("");
}

async function scanDiscover() {
  const list = document.getElementById("discover-list");
  const meta = document.getElementById("discover-meta");
  list.innerHTML = `<div class="empty-state">扫描中（运行中进程）…</div>`;
  toast("扫描中，请稍候…");
  try {
    const quick = await api("/api/discover/apps?include_start_menu=false");
    const quickItems = Array.isArray(quick) ? quick : (quick.items || []);
    list.innerHTML = `<div class="empty-state">已发现运行中 ${quickItems.length} 个，正在扫开始菜单…</div>`;
    window.__discoverRows = quickItems;
    renderDiscover(quickItems);

    const full = await api("/api/discover/apps?include_start_menu=true");
    const rows = Array.isArray(full) ? full : (full.items || []);
    const errors = Array.isArray(full) ? [] : (full.errors || []);
    const ok = Array.isArray(full) ? true : !!full.ok;
    window.__discoverRows = rows;
    renderDiscover(rows);
    meta.textContent = `${rows.length} 个 · 运行 ${full.running_count ?? "?"} · 菜单 ${full.start_menu_count ?? "?"}`;

    if (!ok && errors.length) toast(`发现 ${rows.length} 个（部分失败: ${errors[0]}）`);
    else toast(`发现 ${rows.length} 个应用`);
  } catch (e) {
    list.innerHTML = `<div class="empty-state" style="color:var(--danger)">扫描失败: ${escapeHtml(e.message)}</div>`;
    window.__discoverRows = [];
    throw e;
  }
}

document.getElementById("btn-scan").onclick = () => scanDiscover().catch((e) => toast(e.message));
document.getElementById("discover-check-all").onchange = (e) => {
  document.querySelectorAll(".disc-check:not(:disabled)").forEach((c) => {
    c.checked = e.target.checked;
  });
};
document.getElementById("discover-filter").oninput = () => {
  renderDiscover(window.__discoverRows || []);
};
document.getElementById("discover-default-cat").onchange = () => {
  renderDiscover(window.__discoverRows || []);
};

document.getElementById("btn-import-selected").onclick = async () => {
  const rows = window.__discoverRows || [];
  const items = [];
  document.querySelectorAll(".disc-check:checked").forEach((c) => {
    const i = Number(c.dataset.i);
    const r = rows[i];
    if (r && !r.already_registered) {
      const sel = document.querySelector(`.disc-cat[data-i="${i}"]`);
      items.push({
        name: r.name,
        exe_path: r.exe_path,
        process_name: r.process_name,
        category: sel ? sel.value : (r.suggested_category || "other"),
        enabled: true,
        apply_defaults: true,
      });
    }
  });
  if (!items.length) return toast("未勾选可导入项");
  try {
    const created = await api("/api/discover/import", { method: "POST", body: { items } });
    toast(`已导入 ${created.length} 个（已按分类写入默认时段）`);
    await loadApps();
    await scanDiscover();
  } catch (e) {
    toast(e.message);
  }
};

/* —— 统计 / 报告 / 柱状图 —— */
const CAT_BAR_COLORS = {
  entertainment: "linear-gradient(90deg, #f79009, #dc6803)",
  study: "linear-gradient(90deg, #2e90fa, #1570ef)",
  work: "linear-gradient(90deg, #6172f3, #444ce7)",
  other: "linear-gradient(90deg, #98a2b3, #667085)",
};

function fmtMinNice(minutes) {
  const m = Number(minutes || 0);
  if (m >= 60) {
    const h = Math.floor(m / 60);
    const rest = Math.round(m - h * 60);
    return rest ? `${h}h${rest}m` : `${h}h`;
  }
  return `${m.toFixed(m >= 10 ? 0 : 1)}m`;
}

function renderHBars(el, rows, opts = {}) {
  if (!el) return;
  const {
    nameKey = "label",
    valueKey = "minutes",
    shareKey = "share_pct",
    colorFn = () => null,
    emptyText = "暂无数据",
    maxItems = 12,
  } = opts;
  const sorted = [...(rows || [])]
    .sort((a, b) => Number(b[valueKey] || 0) - Number(a[valueKey] || 0))
    .slice(0, maxItems);
  if (!sorted.length) {
    el.innerHTML = `<div class="empty-state compact">${emptyText}</div>`;
    return;
  }
  const max = Math.max(...sorted.map((i) => Number(i[valueKey] || 0)), 0.1);
  el.innerHTML = sorted.map((i, idx) => {
    const val = Number(i[valueKey] || 0);
    const pct = Math.max(3, (val / max) * 100);
    const share = i[shareKey] != null ? `${Number(i[shareKey]).toFixed(1)}%` : "";
    const fill = colorFn(i) || "linear-gradient(90deg, var(--accent), var(--accent-2))";
    const name = escapeHtml(i[nameKey] || `#${idx + 1}`);
    return `
      <div class="h-bar-row" title="${name}">
        <div class="label"><span class="rank">${idx + 1}</span>${name}</div>
        <div class="h-bar-track"><div class="h-bar-fill" style="width:${pct}%;background:${fill}"></div></div>
        <div class="val">${fmtMinNice(val)}${share ? `<small>${share}</small>` : ""}</div>
      </div>
    `;
  }).join("");
}

function renderTodayBars(items) {
  renderHBars(
    document.getElementById("chart-today"),
    (items || []).map((i) => ({
      ...i,
      label: i.app_name || `#${i.app_id}`,
    })),
    {
      emptyText: "今日暂无用量",
      colorFn: (i) => CAT_BAR_COLORS[i.category] || CAT_BAR_COLORS.other,
    }
  );
}

function renderCategoryBars(elId, categories, emptyText) {
  renderHBars(
    document.getElementById(elId),
    (categories || []).map((c) => ({
      ...c,
      label: c.label || categoryLabel(c.category),
    })),
    {
      emptyText,
      maxItems: 8,
      colorFn: (i) => CAT_BAR_COLORS[i.category] || CAT_BAR_COLORS.other,
    }
  );
}

function renderWeekBars(dailySeries) {
  const el = document.getElementById("chart-week");
  const days = dailySeries || [];
  if (!days.length) {
    el.innerHTML = `<div class="empty-state compact">暂无历史数据</div>`;
    return;
  }
  const max = Math.max(...days.map((d) => Number(d.minutes || 0)), 0.1);
  const peak = Math.max(...days.map((d) => Number(d.minutes || 0)));
  el.innerHTML = days.map((d) => {
    const minutes = Number(d.minutes || 0);
    const pct = Math.max(2, (minutes / max) * 100);
    const isPeak = minutes > 0 && minutes === peak;
    const isWeekend = d.weekday === 5 || d.weekday === 6;
    return `
      <div class="v-bar-col ${isPeak ? "peak" : ""} ${isWeekend ? "weekend" : ""}"
           title="${d.date} 周${d.weekday_label || ""}: ${minutes.toFixed(1)} 分钟">
        <div class="val">${minutes >= 1 ? Math.round(minutes) : minutes.toFixed(1)}</div>
        <div class="v-bar-track">
          <div class="v-bar-fill" style="height:${pct}%"></div>
        </div>
        <div class="lab">${escapeHtml(d.label || d.date)}</div>
        <div class="lab sub">周${escapeHtml(d.weekday_label || "")}</div>
      </div>
    `;
  }).join("");
}

function renderKpis(el, items) {
  el.innerHTML = items.map((k) => `
    <div class="kpi">
      <div class="label">${escapeHtml(k.label)}</div>
      <div class="value">${k.value}<span class="unit">${escapeHtml(k.unit || "")}</span></div>
      ${k.hint ? `<div class="hint">${escapeHtml(k.hint)}</div>` : ""}
    </div>
  `).join("");
}

/** 时间轴（细视图 + 全日选区导航） */
const TL_DAY_SEC = 24 * 3600;
const TL_LABEL_W = 56;
let timelineData = null;
let tlRange = { start: 0, end: TL_DAY_SEC };
let tlPreset = "all";
let tlBrushDrag = null;
/** null = 尚未初始化（默认全选）；Set<number> = 可见 app_id */
let tlFilterIds = null;
let tlFilterSeen = new Set();

function localDateISO(d = new Date()) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function shiftDateISO(iso, deltaDays) {
  const [y, m, d] = iso.split("-").map(Number);
  const dt = new Date(y, m - 1, d);
  dt.setDate(dt.getDate() + deltaDays);
  return localDateISO(dt);
}

function fmtClock(sec, withSec = false) {
  const s = Math.max(0, Math.min(TL_DAY_SEC, Math.floor(sec)));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const ss = s % 60;
  if (withSec || ss) {
    return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(ss).padStart(2, "0")}`;
  }
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

function fmtDurNice(sec) {
  const s = Math.max(0, Math.round(Number(sec) || 0));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const ss = s % 60;
  if (h) return m ? `${h}h ${m}m` : `${h}h`;
  if (m) return ss ? `${m}m ${ss}s` : `${m}m`;
  return `${ss}s`;
}

function tlNowSec(data) {
  if (!data?.is_today || typeof data.now !== "string") return null;
  const parts = data.now.split(" ")[1] || "00:00:00";
  const [hh, mm, ss] = parts.split(":").map(Number);
  return hh * 3600 + mm * 60 + (ss || 0);
}

function tlChooseTicks(spanSec) {
  if (spanSec > 14 * 3600) return { major: 3600, minor: 1800 };
  if (spanSec > 8 * 3600) return { major: 1800, minor: 900 };
  if (spanSec > 3 * 3600) return { major: 900, minor: 300 };
  if (spanSec > 3600) return { major: 300, minor: 60 };
  if (spanSec > 900) return { major: 60, minor: 15 };
  return { major: 30, minor: 5 };
}

function tlClampRange(start, end) {
  let s = Math.max(0, Math.min(TL_DAY_SEC, start));
  let e = Math.max(0, Math.min(TL_DAY_SEC, end));
  if (e < s) [s, e] = [e, s];
  if (e - s < 5 * 60) {
    const mid = (s + e) / 2;
    s = Math.max(0, mid - 150);
    e = Math.min(TL_DAY_SEC, s + 300);
    s = Math.max(0, e - 300);
  }
  return { start: s, end: e };
}

function tlSetRange(start, end, preset = null, { light = false } = {}) {
  tlRange = tlClampRange(start, end);
  if (preset != null) tlPreset = preset;
  else if (!light) tlPreset = "custom";
  if (!light) {
    document.querySelectorAll("#tl-presets .btn").forEach((b) => {
      b.classList.toggle("active", b.dataset.preset === tlPreset);
    });
  }
  if (!timelineData) return;
  if (light) {
    document.getElementById("tl-range-chip").textContent =
      `${fmtClock(tlRange.start)} → ${tlRange.end >= TL_DAY_SEC ? "24:00" : fmtClock(tlRange.end)}`;
    const brush = document.getElementById("tl-brush");
    if (brush) {
      brush.style.left = `${(tlRange.start / TL_DAY_SEC) * 100}%`;
      brush.style.width = `${Math.max(1.2, ((tlRange.end - tlRange.start) / TL_DAY_SEC) * 100)}%`;
    }
    return;
  }
  renderTimelineView();
}

function tlSessionsFlat(data) {
  const out = [];
  for (const lane of data.lanes || []) {
    for (const s of lane.sessions || []) {
      out.push({ ...s, color: lane.color, app_name: lane.app_name, exe_path: lane.exe_path });
    }
  }
  return out.sort((a, b) => a.start_sec - b.start_sec);
}

function tlAppCatalog(data) {
  return (data.lanes || []).map((lane) => ({
    id: lane.app_id,
    name: lane.app_name,
    color: lane.color,
    exe_path: lane.exe_path,
    total_min: lane.total_min,
  }));
}

function tlSyncFilterWithData(data) {
  const ids = tlAppCatalog(data).map((a) => a.id);
  if (tlFilterIds == null) {
    tlFilterIds = new Set(ids);
    tlFilterSeen = new Set(ids);
    return;
  }
  for (const id of ids) {
    if (!tlFilterSeen.has(id)) {
      tlFilterIds.add(id);
      tlFilterSeen.add(id);
    }
  }
  for (const id of [...tlFilterIds]) {
    if (!ids.includes(id)) tlFilterIds.delete(id);
  }
}

function tlFilteredSessions(data) {
  const all = tlSessionsFlat(data);
  if (!tlFilterIds) return all;
  return all.filter((s) => tlFilterIds.has(s.app_id));
}

function tlIntersect(sessions, start, end) {
  return sessions
    .filter((s) => s.end_sec > start && s.start_sec < end)
    .map((s) => ({
      ...s,
      vStart: Math.max(s.start_sec, start),
      vEnd: Math.min(s.end_sec, end),
      vDur: Math.min(s.end_sec, end) - Math.max(s.start_sec, start),
    }));
}

function tlUnionSec(items) {
  const iv = items.map((s) => [s.vStart ?? s.start_sec, s.vEnd ?? s.end_sec]).filter(([a, b]) => b > a);
  if (!iv.length) return 0;
  iv.sort((a, b) => a[0] - b[0]);
  let total = 0;
  let cs = iv[0][0];
  let ce = iv[0][1];
  for (let i = 1; i < iv.length; i++) {
    const [s, e] = iv[i];
    if (s <= ce) ce = Math.max(ce, e);
    else {
      total += ce - cs;
      cs = s;
      ce = e;
    }
  }
  total += ce - cs;
  return total;
}

function renderTlFilter(data) {
  const el = document.getElementById("tl-filter");
  if (!el) return;
  const apps = tlAppCatalog(data);
  if (!apps.length) {
    el.innerHTML = `<span class="muted" style="font-size:12px">暂无可筛选应用</span>`;
    return;
  }
  const chips = apps.map((a) => {
    const on = tlFilterIds.has(a.id);
    return `
      <button type="button" class="tl-filter-chip ${on ? "" : "off"}" data-app-id="${a.id}" title="${escapeHtml(a.name)}">
        <span class="dot" style="background:${escapeHtml(a.color)}"></span>
        ${escapeHtml(a.name)}
      </button>
    `;
  }).join("");
  el.innerHTML = `
    ${chips}
    <span class="tl-filter-actions">
      <button type="button" class="btn sm" data-filter-act="all">全选</button>
      <button type="button" class="btn sm" data-filter-act="none">清空</button>
    </span>
  `;
}

function showTimelineTip(html, clientX, clientY) {
  const tip = document.getElementById("timeline-tip");
  tip.innerHTML = html;
  tip.classList.remove("hidden");
  const pad = 12;
  let left = clientX + pad;
  let top = clientY + pad;
  tip.style.left = `${left}px`;
  tip.style.top = `${top}px`;
  const rect = tip.getBoundingClientRect();
  if (rect.right > window.innerWidth - 8) left = clientX - rect.width - pad;
  if (rect.bottom > window.innerHeight - 8) top = clientY - rect.height - pad;
  tip.style.left = `${Math.max(8, left)}px`;
  tip.style.top = `${Math.max(8, top)}px`;
}

function hideTimelineTip() {
  document.getElementById("timeline-tip").classList.add("hidden");
}

function tlDefaultRange(data) {
  const sessions = tlSessionsFlat(data);
  const nowSec = tlNowSec(data);
  if (!sessions.length) {
    if (nowSec != null) {
      return tlClampRange(Math.max(0, nowSec - 3600), Math.min(TL_DAY_SEC, nowSec + 300));
    }
    return { start: 0, end: TL_DAY_SEC };
  }
  if (nowSec != null) {
    return tlClampRange(Math.max(0, nowSec - 2.5 * 3600), Math.min(TL_DAY_SEC, nowSec + 600));
  }
  const last = Math.max(...sessions.map((s) => s.end_sec));
  return tlClampRange(Math.max(0, last - 3 * 3600), Math.min(TL_DAY_SEC, last + 600));
}

function renderTimeline(data) {
  timelineData = data;
  renderTimelineView();
}

function renderTimelineView() {
  const data = timelineData;
  if (!data) return;

  tlSyncFilterWithData(data);
  renderTlFilter(data);

  const meta = document.getElementById("timeline-meta");
  const detail = document.getElementById("tl-detail-inner");
  const { start, end } = tlRange;
  const span = Math.max(1, end - start);
  const filtered = tlFilteredSessions(data);
  const visible = tlIntersect(filtered, start, end);

  const visCount = tlFilterIds ? tlFilterIds.size : 0;
  const appTotal = tlAppCatalog(data).length;
  meta.textContent = data.lane_count
    ? `${data.date} · 显示 ${visCount}/${appTotal} 应用 · ${visible.length} 段 · 滚轮缩放`
    : `${data.date} · 暂无会话（切到登记应用前台才会记）`;

  document.getElementById("tl-range-chip").textContent =
    `${fmtClock(start)} → ${end >= TL_DAY_SEC ? "24:00" : fmtClock(end)}`;

  const onlineAll = tlUnionSec(filtered.map((s) => ({ vStart: s.start_sec, vEnd: s.end_sec })));
  const onlineSel = tlUnionSec(visible);
  const first = filtered.length ? Math.min(...filtered.map((s) => s.start_sec)) : null;
  const last = filtered.length ? Math.max(...filtered.map((s) => s.end_sec)) : null;
  renderKpis(document.getElementById("tl-kpis"), [
    { label: "在线合计", value: fmtDurNice(onlineAll), unit: "", hint: "已筛应用·去重叠" },
    { label: "选区用量", value: fmtDurNice(onlineSel), unit: "", hint: "当前可见窗口" },
    { label: "首次在线", value: first == null ? "-" : fmtClock(first, true), unit: "", hint: "当日最早" },
    { label: "最近在线", value: last == null ? "-" : fmtClock(last, true), unit: "", hint: "当日最晚" },
  ]);

  const byApp = new Map();
  for (const s of visible) {
    const cur = byApp.get(s.app_id) || { name: s.app_name, color: s.color, sec: 0, exe: s.exe_path };
    cur.sec += s.vDur;
    byApp.set(s.app_id, cur);
  }
  const appRows = [...byApp.values()].sort((a, b) => b.sec - a.sec);
  const stackTotal = appRows.reduce((n, a) => n + a.sec, 0) || 1;
  const stackEl = document.getElementById("tl-stack");
  if (!appRows.length) {
    stackEl.innerHTML = `<div class="tl-stack-empty">选区内无应用活动</div>`;
  } else {
    stackEl.innerHTML = appRows.map((a) => {
      const pct = (a.sec / stackTotal) * 100;
      const label = pct >= 12 ? `${escapeHtml(a.name)} · ${fmtDurNice(a.sec)}` : "";
      return `<div class="tl-stack-seg" style="width:${pct}%;background:${escapeHtml(a.color)}" title="${escapeHtml(a.name)} ${fmtDurNice(a.sec)}">${label}</div>`;
    }).join("");
  }

  document.getElementById("tl-table-meta").textContent = `${visible.length} 条`;
  document.querySelector("#tl-session-table tbody").innerHTML =
    [...visible].sort((a, b) => b.vEnd - a.vEnd).map((s) => `
      <tr>
        <td>
          <div class="cell-app">
            <span class="swatch" style="width:8px;height:8px;border-radius:2px;background:${escapeHtml(s.color)};display:inline-block;flex-shrink:0"></span>
            ${appIconHtml(s.exe_path, s.app_name, 22)}
            <span>${escapeHtml(s.app_name)}</span>
          </div>
        </td>
        <td>${fmtClock(s.vStart, true)}</td>
        <td>${s.ongoing && s.vEnd >= (tlNowSec(data) || 0) - 2 ? "进行中" : fmtClock(s.vEnd, true)}</td>
        <td>${fmtDurNice(s.vDur)}</td>
        <td>${s.ongoing ? "进行中" : escapeHtml(s.end_reason || "正常")}</td>
      </tr>
    `).join("") || `<tr><td colspan="5">选区内暂无会话</td></tr>`;

  // 单轨时间轴：所有可见应用画在同一条轴上，同应用同色
  const ticks = tlChooseTicks(span);
  const scroll = document.getElementById("tl-detail-scroll");
  const avail = Math.max(420, (scroll?.clientWidth || 800) - TL_LABEL_W - 8);
  const width = avail;
  const pxPerSec = width / span;
  const nowSec = tlNowSec(data);

  const tickHtml = [];
  const firstTick = Math.ceil(start / ticks.minor) * ticks.minor;
  for (let t = firstTick; t <= end; t += ticks.minor) {
    const isMajor = t % ticks.major === 0;
    const left = (t - start) * pxPerSec;
    tickHtml.push(`
      <div class="tl-tick ${isMajor ? "major" : ""}" style="left:${left}px">
        ${isMajor ? `<span class="lab">${fmtClock(t)}</span>` : ""}
      </div>
    `);
  }

  let nowLine = "";
  if (nowSec != null && nowSec >= start && nowSec <= end) {
    nowLine = `<div class="tl-now" style="left:${(nowSec - start) * pxPerSec}px" title="现在"></div>`;
  }

  if (!visible.length) {
    detail.innerHTML = `<div class="timeline-empty">该时段没有可见会话 — 调整筛选或拖动下方选区</div>`;
  } else {
    const segs = visible.map((s) => {
      const left = (s.vStart - start) * pxPerSec;
      const w = Math.max(2, s.vDur * pxPerSec);
      const showLab = w >= 64;
      const st = fmtClock(s.vStart);
      const en = s.ongoing ? "…" : fmtClock(s.vEnd);
      const lab = showLab ? `${escapeHtml(s.app_name)} ${st}` : (w >= 36 ? escapeHtml(s.app_name) : "");
      return `
        <div class="tl-seg ${s.ongoing ? "ongoing" : ""}"
             style="left:${left}px;width:${w}px;background:${escapeHtml(s.color)}"
             tabindex="0"
             data-app="${escapeHtml(s.app_name)}"
             data-start="${escapeHtml(s.started_at || "")}"
             data-end="${s.ongoing ? "" : escapeHtml(s.ended_at || "")}"
             data-ongoing="${s.ongoing ? "1" : "0"}"
             data-dur="${s.vDur}">
          ${lab ? `<span class="seg-lab">${lab}${showLab && !s.ongoing ? `–${en}` : ""}</span>` : ""}
        </div>
      `;
    }).join("");

    detail.innerHTML = `
      <div class="tl-ruler" style="width:${width + TL_LABEL_W}px">
        <div></div>
        <div class="tl-ruler-track" style="width:${width}px">${tickHtml.join("")}${nowLine}</div>
      </div>
      <div class="tl-single" style="width:${width + TL_LABEL_W}px">
        <div class="tl-single-label">应用</div>
        <div class="tl-single-track" style="width:${width}px">${segs}${nowLine}</div>
      </div>
    `;

    detail.querySelectorAll(".tl-seg").forEach((el) => {
      el.addEventListener("mousemove", (ev) => {
        const tip = `
          <strong>${escapeHtml(el.dataset.app || "")}</strong>
          开始 ${escapeHtml(el.dataset.start || "")}<br/>
          结束 ${el.dataset.ongoing === "1" ? "进行中" : escapeHtml(el.dataset.end || "")}<br/>
          片段 ${fmtDurNice(Number(el.dataset.dur) || 0)}
        `;
        showTimelineTip(tip, ev.clientX, ev.clientY);
      });
      el.addEventListener("mouseleave", hideTimelineTip);
    });
  }

  renderTimelineOverview(data, filtered, nowSec);
}

function renderTimelineOverview(data, all, nowSec) {
  const ruler = document.getElementById("tl-overview-ruler");
  const bars = document.getElementById("tl-overview-bars");
  const brush = document.getElementById("tl-brush");
  const body = document.getElementById("tl-overview-body");
  if (!ruler || !bars || !brush || !body) return;

  const marks = [];
  for (let h = 0; h <= 24; h += 3) {
    const left = (h / 24) * 100;
    marks.push(`<span style="left:${left}%">${String(h).padStart(2, "0")}:00</span>`);
  }
  ruler.innerHTML = marks.join("");

  bars.innerHTML = all.map((s) => {
    const left = (s.start_sec / TL_DAY_SEC) * 100;
    const w = Math.max(0.15, ((s.end_sec - s.start_sec) / TL_DAY_SEC) * 100);
    return `<div class="tl-ov-seg" style="left:${left}%;width:${w}%;background:${escapeHtml(s.color)}"></div>`;
  }).join("");

  if (nowSec != null) {
    bars.innerHTML += `<div class="tl-now" style="left:${(nowSec / TL_DAY_SEC) * 100}%"></div>`;
  }

  const leftPct = (tlRange.start / TL_DAY_SEC) * 100;
  const widthPct = ((tlRange.end - tlRange.start) / TL_DAY_SEC) * 100;
  brush.style.left = `${leftPct}%`;
  brush.style.width = `${Math.max(1.2, widthPct)}%`;
}

function tlOverviewSecFromEvent(ev) {
  const body = document.getElementById("tl-overview-body");
  const rect = body.getBoundingClientRect();
  const x = Math.max(0, Math.min(rect.width, ev.clientX - rect.left));
  return (x / rect.width) * TL_DAY_SEC;
}

async function loadTimeline(resetRange = true) {
  const dayEl = document.getElementById("timeline-day");
  if (!dayEl.value) dayEl.value = localDateISO();
  const day = dayEl.value;
  const data = await api(`/api/stats/timeline?day=${encodeURIComponent(day)}`);
  timelineData = data;
  if (resetRange) {
    if (data.is_today) {
      tlRange = tlDefaultRange(data);
      tlPreset = "custom";
    } else {
      tlRange = { start: 0, end: TL_DAY_SEC };
      tlPreset = "all";
    }
    document.querySelectorAll("#tl-presets .btn").forEach((b) => {
      b.classList.toggle("active", b.dataset.preset === tlPreset);
    });
  }
  renderTimelineView();
}

async function loadStats() {
  const days = Number(document.getElementById("stats-range").value || 30);

  await loadTimeline(true).catch((e) => {
    const el = document.getElementById("timeline-meta");
    if (el) el.textContent = `时间轴加载失败: ${e.message}`;
  });

  const today = await api("/api/stats/today");
  document.getElementById("today-date-label").textContent = today.date || "";
  renderKpis(document.getElementById("stats-kpis"), [
    {
      label: "今日合计",
      value: fmtMinNice(today.total_minutes ?? Number(today.total_seconds || 0) / 60),
      unit: "",
      hint: today.top_app
        ? `前台去重叠 · 最长: ${today.top_app.app_name} ${fmtMinNice(today.top_app.minutes)}`
        : "前台窗口计时 · 同时段不叠加",
    },
    {
      label: "有用量应用",
      value: String(today.app_count ?? (today.items || []).length),
      unit: "个",
      hint: `启动 ${today.total_launches || 0} · 击杀 ${today.total_kills || 0}`,
    },
    {
      label: "娱乐占比",
      value: String(
        (today.categories || []).find((c) => c.category === "entertainment")?.share_pct ?? 0
      ),
      unit: "%",
      hint: "游戏娱乐分类",
    },
    {
      label: "学习+办公",
      value: String((() => {
        const study = (today.categories || []).find((c) => c.category === "study")?.share_pct || 0;
        const work = (today.categories || []).find((c) => c.category === "work")?.share_pct || 0;
        return Math.round((study + work) * 10) / 10;
      })()),
      unit: "%",
      hint: "偏生产类合计",
    },
  ]);
  renderTodayBars(today.items || []);
  renderCategoryBars("chart-today-cat", today.categories || [], "今日暂无分类数据");

  document.querySelector("#today-detail-table tbody").innerHTML =
    (today.items || []).map((i, idx) => `
      <tr>
        <td>${idx + 1}</td>
        <td>
          <div class="cell-app">
            ${appIconHtml(i.exe_path, i.app_name, 28)}
            <span>${escapeHtml(i.app_name)}</span>
          </div>
        </td>
        <td><span class="tag cat-${escapeHtml(i.category || "other")}">${escapeHtml(i.category_label || categoryLabel(i.category))}</span></td>
        <td>${i.minutes}</td>
        <td>${i.share_pct ?? 0}%</td>
        <td>${i.launch_count}</td>
        <td>${i.kill_count}</td>
      </tr>
    `).join("") || `<tr><td colspan="7">今日暂无明细</td></tr>`;

  const report = await api(`/api/stats/report?days=${days}`);
  document.getElementById("history-range-label").textContent =
    `${report.start} ~ ${report.end}（${report.days} 天）`;
  renderKpis(document.getElementById("history-kpis"), [
    {
      label: "区间总用量",
      value: fmtMinNice(report.total_minutes),
      unit: "",
      hint: `日均 ${fmtMinNice(report.avg_minutes_per_day)}`,
    },
    {
      label: "活跃应用",
      value: String(report.active_app_count || 0),
      unit: "个",
      hint: report.top_app ? `第一: ${report.top_app.app_name}` : "暂无",
    },
    {
      label: "峰值日",
      value: report.peak_day ? fmtMinNice(report.peak_day.minutes) : "0",
      unit: "",
      hint: report.peak_day ? report.peak_day.date : "-",
    },
    {
      label: "启动 / 击杀",
      value: `${report.total_launches || 0}/${report.total_kills || 0}`,
      unit: "",
      hint: "区间合计",
    },
  ]);
  renderWeekBars(report.daily_series || []);
  renderCategoryBars("chart-history-cat", report.categories || [], "区间暂无分类数据");
  renderHBars(
    document.getElementById("chart-rank"),
    (report.by_app || []).map((a) => ({
      ...a,
      label: a.app_name,
    })),
    {
      emptyText: "区间暂无应用排行",
      maxItems: 15,
      colorFn: (i) => CAT_BAR_COLORS[i.category] || CAT_BAR_COLORS.other,
    }
  );

  document.querySelector("#daily-table tbody").innerHTML =
    (report.details || []).map((r) => `
      <tr>
        <td>${r.date}</td>
        <td>${escapeHtml(r.app_name)}</td>
        <td><span class="tag cat-${escapeHtml(r.category || "other")}">${escapeHtml(r.category_label || categoryLabel(r.category))}</span></td>
        <td>${r.minutes}</td>
        <td>${r.kill_count}</td>
        <td>${r.launch_count}</td>
      </tr>
    `).join("") || `<tr><td colspan="6">暂无</td></tr>`;

  const audit = await api("/api/stats/audit?limit=80");
  document.querySelector("#audit-table tbody").innerHTML = audit.map((a) => `
    <tr>
      <td>${new Date(a.created_at).toLocaleString()}</td>
      <td>${escapeHtml(a.action)}</td>
      <td>${a.app_id ?? "-"}</td>
      <td style="max-width:360px;word-break:break-all">${escapeHtml(a.detail || "")}</td>
    </tr>
  `).join("") || `<tr><td colspan="4">暂无</td></tr>`;
}

document.getElementById("btn-refresh-apps").onclick = () => loadApps().then(loadStatus);
document.getElementById("btn-refresh-stats").onclick = () => loadStats().then(loadStatus);
document.getElementById("stats-range").onchange = () => loadStats().catch((e) => toast(e.message));

(() => {
  const dayEl = document.getElementById("timeline-day");
  dayEl.value = localDateISO();
  dayEl.onchange = () => loadTimeline(true).catch((e) => toast(e.message));
  document.getElementById("timeline-prev").onclick = () => {
    dayEl.value = shiftDateISO(dayEl.value || localDateISO(), -1);
    loadTimeline(true).catch((e) => toast(e.message));
  };
  document.getElementById("timeline-next").onclick = () => {
    dayEl.value = shiftDateISO(dayEl.value || localDateISO(), 1);
    loadTimeline(true).catch((e) => toast(e.message));
  };
  document.getElementById("timeline-today").onclick = () => {
    dayEl.value = localDateISO();
    loadTimeline(true).catch((e) => toast(e.message));
  };

  document.getElementById("tl-presets").onclick = (ev) => {
    const btn = ev.target.closest("[data-preset]");
    if (!btn) return;
    const p = btn.dataset.preset;
    const nowSec = tlNowSec(timelineData) ?? TL_DAY_SEC * 0.75;
    if (p === "all") tlSetRange(0, TL_DAY_SEC, "all");
    else if (p === "am") tlSetRange(0, 12 * 3600, "am");
    else if (p === "pm") tlSetRange(12 * 3600, 18 * 3600, "pm");
    else if (p === "evening") tlSetRange(18 * 3600, TL_DAY_SEC, "evening");
    else if (p === "hour") tlSetRange(Math.max(0, nowSec - 3600), Math.min(TL_DAY_SEC, nowSec + 300), "hour");
  };

  document.getElementById("tl-filter").onclick = (ev) => {
    const act = ev.target.closest("[data-filter-act]")?.dataset.filterAct;
    if (act === "all") {
      tlFilterIds = new Set(tlAppCatalog(timelineData || { lanes: [] }).map((a) => a.id));
      if (timelineData) renderTimelineView();
      return;
    }
    if (act === "none") {
      tlFilterIds = new Set();
      if (timelineData) renderTimelineView();
      return;
    }
    const chip = ev.target.closest("[data-app-id]");
    if (!chip || !tlFilterIds) return;
    const id = Number(chip.dataset.appId);
    if (tlFilterIds.has(id)) tlFilterIds.delete(id);
    else tlFilterIds.add(id);
    if (timelineData) renderTimelineView();
  };

  // 时间轴区域滚轮缩放（以指针位置为中心）
  const panel = document.getElementById("tl-detail-panel");
  panel.addEventListener(
    "wheel",
    (ev) => {
      if (!timelineData) return;
      ev.preventDefault();
      const rect = panel.getBoundingClientRect();
      const labelPad = TL_LABEL_W;
      const trackLeft = rect.left + labelPad;
      const trackW = Math.max(1, rect.width - labelPad);
      let ratio = (ev.clientX - trackLeft) / trackW;
      ratio = Math.max(0, Math.min(1, ratio));
      const span = tlRange.end - tlRange.start;
      const pivot = tlRange.start + span * ratio;
      const factor = ev.deltaY < 0 ? 0.8 : 1.25;
      const next = Math.min(TL_DAY_SEC, Math.max(5 * 60, span * factor));
      tlSetRange(pivot - next * ratio, pivot + next * (1 - ratio));
    },
    { passive: false }
  );

  const brush = document.getElementById("tl-brush");
  const body = document.getElementById("tl-overview-body");

  brush.addEventListener("mousedown", (ev) => {
    ev.preventDefault();
    ev.stopPropagation();
    const edge = ev.target.closest("[data-edge]")?.dataset.edge;
    tlBrushDrag = {
      mode: edge === "start" ? "start" : edge === "end" ? "end" : "move",
      originX: ev.clientX,
      originStart: tlRange.start,
      originEnd: tlRange.end,
    };
  });

  body.addEventListener("mousedown", (ev) => {
    if (ev.target.closest("#tl-brush")) return;
    const sec = tlOverviewSecFromEvent(ev);
    const span = tlRange.end - tlRange.start;
    tlSetRange(sec - span / 2, sec + span / 2);
  });

  window.addEventListener("mousemove", (ev) => {
    if (!tlBrushDrag) return;
    const bodyEl = document.getElementById("tl-overview-body");
    const rect = bodyEl.getBoundingClientRect();
    const dxSec = ((ev.clientX - tlBrushDrag.originX) / rect.width) * TL_DAY_SEC;
    if (tlBrushDrag.mode === "move") {
      const span = tlBrushDrag.originEnd - tlBrushDrag.originStart;
      let s = tlBrushDrag.originStart + dxSec;
      let e = s + span;
      if (s < 0) { s = 0; e = span; }
      if (e > TL_DAY_SEC) { e = TL_DAY_SEC; s = TL_DAY_SEC - span; }
      tlSetRange(s, e, null, { light: true });
    } else if (tlBrushDrag.mode === "start") {
      tlSetRange(tlBrushDrag.originStart + dxSec, tlBrushDrag.originEnd, null, { light: true });
    } else {
      tlSetRange(tlBrushDrag.originStart, tlBrushDrag.originEnd + dxSec, null, { light: true });
    }
  });

  window.addEventListener("mouseup", () => {
    if (tlBrushDrag) {
      tlBrushDrag = null;
      tlPreset = "custom";
      document.querySelectorAll("#tl-presets .btn").forEach((b) => b.classList.remove("active"));
      if (timelineData) renderTimelineView();
    }
  });

  window.addEventListener("resize", () => {
    if (timelineData) renderTimelineView();
  });
})();

async function boot() {
  await loadStatus();
  await loadApps();
  await loadStats();
  setInterval(loadStatus, 5000);
}

boot().catch((e) => toast(e.message));
