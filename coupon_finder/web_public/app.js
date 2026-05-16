(() => {
  const MSG_NOT_FOUND =
    "Không tìm thấy mã. Kiểm tra lại domain, URL shop hoặc tên brand.";
  const MSG_APIFY_TOKEN = "Token chưa sẵn sàng hoặc đã hết hạn";
  const MSG_SYSTEM = "Có lỗi xảy ra, Vui lòng thử lại sau";

  const MIGRATE_LS_KEY = "coupon_finder_ui_sessions_v1";
  const MAX_COUPONS_PER_SESSION = 400;
  const MAX_BATCH_DOMAINS = 5;
  const HISTORY_PAGE_SIZE = 10;

  const $ = (id) => document.getElementById(id);
  const domainInput = $("domain");
  const btnSearch = $("btn-search");
  const btnStop = $("btn-stop");
  const btnVerify = $("btn-verify");
  const meta = $("meta");
  const err = $("error");
  const searchProgress = $("search-progress");
  const searchProgressFill = $("search-progress-fill");
  const searchProgressLabel = $("search-progress-label");
  const searchProgressPct = $("search-progress-pct");
  const searchProgressTrack = $("search-progress-track");
  const panelResults = $("panel-results");
  const panelVerify = $("panel-verify");
  const currentResultsList = $("current-results-list");
  const tblVerify = $("tbl-verify").querySelector("tbody");
  const historyList = $("history-list");
  const historyEmpty = $("history-empty");
  const historyNoMatch = $("history-no-match");
  const historySearch = $("history-search");
  const historyDateBtn = $("history-date-btn");
  const historyDateMenu = $("history-date-menu");
  const historyDatePicker = $("history-date-picker");
  const historyFilterMeta = $("history-filter-meta");
  const historyPagination = $("history-pagination");
  const historyPrev = $("history-prev");
  const historyNext = $("history-next");
  const historyPageInfo = $("history-page-info");
  const tabBtnFind = $("tab-btn-find");
  const tabBtnHistory = $("tab-btn-history");
  const tabBtnSettings = $("tab-btn-settings");
  const tabPanelFind = $("tab-panel-find");
  const tabPanelHistory = $("tab-panel-history");
  const tabPanelSettings = $("tab-panel-settings");
  const settingsForm = $("settings-form");
  const settingsEnvPath = $("settings-env-path");
  const settingsMsg = $("settings-msg");
  const btnEnvSave = $("btn-env-save");
  const btnEnvReload = $("btn-env-reload");
  const licenseBanner = $("license-banner");
  const licenseStatus = $("license-status");

  let verifyFeatureEnabled = false;
  let licenseOk = false;
  /** @type {object|null} */
  let licenseInfo = null;

  let lastDomain = "";
  let lastWebsite = "";
  let rows = [];
  let searchAbortController = null;
  let historyPage = 1;
  let historyDatePreset = "today";
  let historyCustomDate = "";
  /** @type {Array<{domainInput:string,website:string,brandHint:string,coupons:object[],userMessage:string|null,errorCode:string|null,status:string,rawCount:number,normalizedCount:number}>} */
  let currentBatchResults = [];
  /** @type {object[]} */
  let sessionsCache = [];
  let sessionsLoadPromise = null;

  function showError(msg) {
    if (msg) {
      err.textContent = msg;
      err.hidden = false;
      if (tabPanelHistory && !tabPanelHistory.hidden) {
        setActiveTab("find");
      }
    } else {
      err.hidden = true;
    }
  }

  function apiErr(data, fallback) {
    const d = data && data.detail;
    if (typeof d === "string") return d;
    if (d && typeof d === "object" && !Array.isArray(d) && d.message) return d.message;
    if (Array.isArray(d)) return d.map((x) => x.msg || JSON.stringify(x)).join("; ");
    return fallback;
  }

  function isLicenseErrorCode(code) {
    return typeof code === "string" && code.startsWith("license");
  }

  function formatLicenseStatus(info) {
    if (!info) return "Chưa kiểm tra license.";
    if (info.ok) {
      const rem = info.searches_remaining;
      const limit = info.daily_search_limit;
      const machines = info.machines_count;
      const maxM = info.max_machines;
      let s = "License hợp lệ.";
      if (typeof rem === "number" && typeof limit === "number") {
        s += ` Còn ${rem}/${limit} lượt tìm hôm nay.`;
      }
      if (typeof machines === "number" && typeof maxM === "number") {
        s += ` Máy: ${machines}/${maxM}.`;
      }
      return s;
    }
    return info.message || "License chưa hợp lệ.";
  }

  function updateLicenseUi() {
    const msg = formatLicenseStatus(licenseInfo);
    if (licenseStatus) licenseStatus.textContent = msg;
    if (licenseBanner) {
      if (licenseOk) {
        licenseBanner.hidden = true;
        licenseBanner.textContent = "";
      } else {
        licenseBanner.hidden = false;
        licenseBanner.textContent =
          msg + " — Vào tab Cài đặt, nhập URL server license và mã license, rồi Lưu.";
        licenseBanner.className = "license-banner license-banner--warn";
      }
    }
    if (btnSearch && !domainInput?.disabled) {
      btnSearch.disabled = !licenseOk;
      btnSearch.title = licenseOk ? "" : "Cần license hợp lệ trước khi tìm";
    }
  }

  async function loadLicenseStatus() {
    try {
      const r = await fetch("/api/ui/license");
      licenseInfo = r.ok ? await r.json() : { ok: false, message: "Không kiểm tra được license." };
    } catch {
      licenseInfo = { ok: false, message: "Không kết nối được API license." };
    }
    licenseOk = Boolean(licenseInfo && licenseInfo.ok);
    updateLicenseUi();
    return licenseInfo;
  }

  function setLoading(is) {
    btnSearch.disabled = is || !licenseOk;
    btnSearch.textContent = is ? "Đang tìm..." : "Tìm coupon";
    domainInput.disabled = is;
    if (btnStop) btnStop.hidden = !is;
  }

  function couponsFromPayload(data) {
    return data.coupons && data.coupons.length ? data.coupons : data.collected_preview || [];
  }

  function setSearchProgress(percent, message) {
    const pct = Math.max(0, Math.min(100, Number(percent) || 0));
    if (searchProgress) searchProgress.hidden = false;
    if (searchProgressFill) searchProgressFill.style.width = `${pct}%`;
    if (searchProgressPct) searchProgressPct.textContent = `${pct}%`;
    if (searchProgressLabel && message) searchProgressLabel.textContent = message;
    if (searchProgressTrack) searchProgressTrack.setAttribute("aria-valuenow", String(pct));
  }

  function hideSearchProgress() {
    if (searchProgress) searchProgress.hidden = true;
    if (searchProgressFill) searchProgressFill.style.width = "0%";
    if (searchProgressPct) searchProgressPct.textContent = "0%";
    if (searchProgressLabel) searchProgressLabel.textContent = "Đang tìm…";
    if (searchProgressTrack) searchProgressTrack.setAttribute("aria-valuenow", "0");
  }

  function parseDomainLines(text) {
    const seen = new Set();
    const out = [];
    for (const line of String(text || "").split(/\r?\n/)) {
      const s = line.trim();
      if (!s) continue;
      const key = s.toLowerCase();
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(s);
      if (out.length >= MAX_BATCH_DOMAINS) break;
    }
    return out;
  }

  function countNonEmptyDomainLines(text) {
    let n = 0;
    const seen = new Set();
    for (const line of String(text || "").split(/\r?\n/)) {
      const s = line.trim();
      if (!s) continue;
      const key = s.toLowerCase();
      if (seen.has(key)) continue;
      seen.add(key);
      n += 1;
    }
    return n;
  }

  async function loadSessionsFromServer() {
    const res = await fetch("/api/ui/history");
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(apiErr(data, res.statusText || "Không tải được lịch sử"));
    sessionsCache = Array.isArray(data.sessions) ? data.sessions : [];
    return sessionsCache;
  }

  function ensureSessionsLoaded() {
    if (sessionsLoadPromise) return sessionsLoadPromise;
    sessionsLoadPromise = loadSessionsFromServer().catch(() => {
      sessionsCache = [];
      return sessionsCache;
    });
    return sessionsLoadPromise;
  }

  function getSessions() {
    return sessionsCache;
  }

  async function pushSession(entry) {
    const res = await fetch("/api/ui/history", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(entry),
    });
    const data = await res.json().catch(() => ({}));
    if (res.ok && Array.isArray(data.sessions)) {
      sessionsCache = data.sessions;
      return;
    }
    sessionsCache.unshift(entry);
  }

  async function migrateLocalStorageHistory() {
    try {
      const raw = localStorage.getItem(MIGRATE_LS_KEY);
      if (!raw) return;
      const arr = JSON.parse(raw);
      if (!Array.isArray(arr) || !arr.length) {
        localStorage.removeItem(MIGRATE_LS_KEY);
        return;
      }
      const res = await fetch("/api/ui/history/migrate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sessions: arr }),
      });
      if (res.ok) {
        const data = await res.json().catch(() => ({}));
        if (Array.isArray(data.sessions)) sessionsCache = data.sessions;
        localStorage.removeItem(MIGRATE_LS_KEY);
      }
    } catch {
      /* giữ file JSON, bỏ qua migrate */
    }
  }

  async function saveSessionFromPayload(data, domain) {
    const list =
      data.coupons && data.coupons.length ? data.coupons : data.collected_preview || [];
    const couponsForStore = (list || []).slice(0, MAX_COUPONS_PER_SESSION);
    await pushSession({
      id: crypto.randomUUID(),
      at: Date.now(),
      domainInput: domain,
      website: data.website || "",
      brandHint: data.brand_hint || "",
      rawCount: data.raw_count ?? 0,
      normalizedCount: data.normalized_count ?? 0,
      coupons: couponsForStore,
      trace: data.trace || [],
      userMessage: data.user_message || null,
      errorCode: data.error_code || null,
    });
  }

  function initCurrentBatch(domains) {
    currentBatchResults = domains.map((d) => ({
      domainInput: d,
      website: "",
      brandHint: d,
      coupons: [],
      userMessage: null,
      errorCode: null,
      status: "pending",
      rawCount: 0,
      normalizedCount: 0,
    }));
    renderCurrentBatchResults();
    panelResults.hidden = false;
  }

  function updateCurrentBrand(domain, data, status) {
    const list = couponsFromPayload(data);
    const idx = currentBatchResults.findIndex((b) => b.domainInput === domain);
    const entry = {
      domainInput: domain,
      website: data.website || "",
      brandHint: data.brand_hint || domain,
      coupons: list,
      userMessage: data.user_message || null,
      errorCode: data.error_code || null,
      status,
      rawCount: data.raw_count ?? 0,
      normalizedCount: data.normalized_count ?? 0,
    };
    if (idx >= 0) currentBatchResults[idx] = entry;
    else currentBatchResults.push(entry);
    renderCurrentBatchResults();
  }

  function syncRowsForVerify() {
    if (currentBatchResults.length === 1) {
      const br = currentBatchResults[0];
      rows = br.coupons || [];
      lastDomain = br.domainInput;
      lastWebsite = br.website || "";
    } else {
      rows = [];
      lastDomain = "";
      lastWebsite = "";
    }
    updateVerifyBtn();
  }

  function renderCurrentBatchResults() {
    if (!currentResultsList) return;
    currentResultsList.innerHTML = "";
    if (!currentBatchResults.length) {
      panelResults.hidden = true;
      syncRowsForVerify();
      return;
    }
    panelResults.hidden = false;
    currentBatchResults.forEach((br) => {
      const det = document.createElement("details");
      det.className = "current-result-item";
      if (br.status === "pending") det.classList.add("is-pending");
      if (br.status === "error" || br.status === "empty") det.classList.add("is-error");
      det.open = true;

      const n = (br.coupons && br.coupons.length) || 0;
      const sum = document.createElement("summary");
      if (br.status === "pending") {
        sum.textContent = `${br.domainInput} · Đang tìm…`;
      } else if (br.status === "cancelled") {
        sum.textContent = `${br.domainInput} · Đã dừng`;
      } else {
        sum.textContent = `${br.domainInput} → ${br.website || "—"} · ${n} mã · raw ${br.rawCount ?? 0}`;
      }
      det.appendChild(sum);

      const body = document.createElement("div");
      body.className = "current-result-body";
      body.dataset.domainInput = br.domainInput;
      body.dataset.website = br.website || "";

      if (br.status !== "pending" && br.status !== "cancelled") {
        const metaP = document.createElement("p");
        metaP.className = "current-result-meta muted";
        metaP.textContent = `Brand: ${br.brandHint || "—"} · Chuẩn hoá: ${br.normalizedCount ?? 0}`;
        body.appendChild(metaP);
      }

      if (br.userMessage && (!n || br.status === "cancelled")) {
        const errP = document.createElement("p");
        errP.className = "error history-item-error";
        errP.textContent = br.userMessage;
        body.appendChild(errP);
      }

      if (n > 0) {
        const tw = document.createElement("div");
        tw.className = "table-wrap";
        tw.innerHTML = `
          <table class="table current-brand-table">
            <thead>
              <tr>
                <th class="th-check"><input type="checkbox" class="cur-chk-master" title="Chọn tất cả" /></th>
                <th>Mã</th>
                <th>Giảm giá</th>
                <th>Mô tả</th>
                <th>Xác xuất</th>
              </tr>
            </thead>
            <tbody></tbody>
          </table>`;
        renderCouponsInto(tw.querySelector("tbody"), br.coupons);
        body.appendChild(tw);

        if (verifyFeatureEnabled && currentBatchResults.length > 1) {
          const tb = document.createElement("div");
          tb.className = "toolbar";
          tb.innerHTML = `<div class="toolbar-actions"><button type="button" class="btn accent cur-verify" type="button">Verify đã chọn</button></div>`;
          if (!(br.website || "").trim()) {
            const btn = tb.querySelector(".cur-verify");
            btn.disabled = true;
            btn.title = "Verify cần URL shop hợp lệ.";
          }
          body.appendChild(tb);
        }
      }

      det.appendChild(body);
      currentResultsList.appendChild(det);
    });
    syncRowsForVerify();
  }

  function applyBatchSummary(summary, { stopped = false } = {}) {
    const total = summary.total ?? currentBatchResults.length;
    const okCount =
      summary.ok_count ??
      currentBatchResults.filter((b) => b.status === "ok" && (b.coupons || []).length).length;
    const errors = summary.errors || [];
    const errCount = summary.error_count ?? errors.length;
    const prefix = stopped ? "Đã dừng · " : "Hoàn tất · ";
    meta.textContent = `${prefix}${okCount + errCount}/${total} brand xử lý · ${errCount ? `${errCount} lỗi` : "không lỗi"}`;

    const hasAny = currentBatchResults.some((b) => (b.coupons || []).length > 0);
    if (!hasAny && !currentBatchResults.some((b) => b.status === "pending")) {
      const first = errors[0] || currentBatchResults.find((b) => b.userMessage);
      const msg = (first && (first.message || first.userMessage)) || MSG_NOT_FOUND;
      const code = first && (first.error_code || first.errorCode);
      showError(code === "apify_token" || msg === MSG_APIFY_TOKEN ? MSG_APIFY_TOKEN : msg);
    } else if (errCount > 0 || stopped) {
      const names = errors.length
        ? errors.map((e) => e.domain_input).join(", ")
        : currentBatchResults.filter((b) => b.status === "error").map((b) => b.domainInput).join(", ");
      showError(
        stopped
          ? `Đã dừng. ${names ? `Brand chưa/lỗi: ${names}.` : ""} Kết quả đã xong vẫn hiển thị bên dưới.`
          : `Một số brand lỗi (${names}).`
      );
    } else {
      showError("");
    }
    if (currentBatchResults.length) panelResults.hidden = false;
  }

  async function handleStreamItemDone(ev) {
    await saveSessionFromPayload(ev.payload, ev.domain_input);
    const list = couponsFromPayload(ev.payload);
    const status = list.length ? "ok" : "empty";
    updateCurrentBrand(ev.domain_input, ev.payload, status);
  }

  async function handleStreamItemError(ev) {
    const payload = {
      coupons: [],
      collected_preview: [],
      website: "",
      brand_hint: ev.domain_input,
      raw_count: 0,
      normalized_count: 0,
      user_message: ev.message,
      error_code: ev.error_code,
      trace: [],
    };
    await saveSessionFromPayload(payload, ev.domain_input);
    updateCurrentBrand(ev.domain_input, payload, "error");
  }

  async function postSearchBatchStream(domains, { signal } = {}) {
    const res = await fetch("/api/ui/search/batch/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ domains }),
      signal,
    });
    if (!res.ok || !res.body) {
      const data = await res.json().catch(() => ({}));
      throw { kind: "http", status: res.status, data };
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let batchSummary = null;
    let streamError = null;
    let stopped = false;

    try {
      while (true) {
        if (signal && signal.aborted) {
          await reader.cancel().catch(() => {});
          throw { kind: "aborted" };
        }
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const chunks = buffer.split("\n\n");
        buffer = chunks.pop() || "";
        for (const chunk of chunks) {
          const line = chunk.split("\n").find((l) => l.startsWith("data: "));
          if (!line) continue;
          let ev;
          try {
            ev = JSON.parse(line.slice(6));
          } catch {
            continue;
          }
          if (ev.type === "progress") {
            setSearchProgress(ev.percent, ev.message);
          } else if (ev.type === "item_done") {
            await handleStreamItemDone(ev);
          } else if (ev.type === "item_error") {
            await handleStreamItemError(ev);
          } else if (ev.type === "done" || ev.type === "stopped") {
            batchSummary = ev;
            stopped = ev.type === "stopped";
          } else if (ev.type === "error") {
            streamError = ev;
          }
        }
      }
    } catch (e) {
      if (e && e.kind === "aborted") throw e;
      if (e && e.name === "AbortError") throw { kind: "aborted" };
      throw e;
    }

    if (streamError) {
      throw { kind: "search", event: streamError };
    }
    if (!batchSummary) {
      throw { kind: "empty" };
    }
    return { summary: batchSummary, stopped };
  }

  function setVerifyLoading(is) {
    if (!verifyFeatureEnabled) return;
    if (is) {
      btnVerify.disabled = true;
      btnVerify.textContent = "Đang verify...";
    } else {
      updateVerifyBtn();
    }
  }

  function escapeHtml(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function escapeAttr(s) {
    return escapeHtml(s).replace(/'/g, "&#39;");
  }

  function renderCouponsInto(tbody, coupons) {
    tbody.innerHTML = "";
    (coupons || []).forEach((c, i) => {
      const tr = document.createElement("tr");
      const disc = (c.source_discount || "").trim() || "—";
      const moTa = (c.source_item_description || "").trim() || "—";
      const health = (c.source_health_score || "").trim() || "—";
      tr.innerHTML = `
        <td><input type="checkbox" class="row-chk" data-idx="${i}" data-code="${escapeAttr(c.code)}" /></td>
        <td><strong>${escapeHtml(c.code)}</strong></td>
        <td>${escapeHtml(disc)}</td>
        <td class="cell-desc">${escapeHtml(moTa)}</td>
        <td class="cell-health-score" title="data-health-score (Simply Codes)">${escapeHtml(health)}</td>`;
      tbody.appendChild(tr);
    });
  }

  function selectedCodesIn(root) {
    const scope = root != null ? root : currentResultsList || tabPanelFind;
    return [...scope.querySelectorAll(".row-chk:checked")].map((el) => el.dataset.code);
  }

  function updateVerifyBtn() {
    if (!verifyFeatureEnabled) {
      btnVerify.hidden = true;
      btnVerify.disabled = true;
      return;
    }
    const multi = currentBatchResults.length > 1;
    btnVerify.hidden = multi;
    if (multi) return;
    const n = selectedCodesIn(currentResultsList).length;
    const canVerify = Boolean(lastWebsite);
    btnVerify.disabled = rows.length === 0 || n === 0 || !canVerify;
    btnVerify.title = canVerify
      ? ""
      : "Verify cần domain/URL shop (nhập ví dụ nike.com), không chỉ tên brand.";
    btnVerify.textContent = n ? `Verify (${n})` : "Verify đã chọn";
  }

  if (currentResultsList) {
    currentResultsList.addEventListener("change", (e) => {
      if (e.target.classList.contains("row-chk")) {
        updateVerifyBtn();
      }
      if (e.target.classList.contains("cur-chk-master")) {
        const table = e.target.closest(".current-brand-table");
        const on = e.target.checked;
        table.querySelectorAll(".row-chk").forEach((b) => {
          b.checked = on;
        });
        e.target.indeterminate = false;
        updateVerifyBtn();
      }
    });

    currentResultsList.addEventListener("click", async (e) => {
      const t = e.target;
      if (!(t instanceof HTMLElement) || !t.classList.contains("cur-verify")) return;
      const body = t.closest(".current-result-body");
      if (!body) return;
      const website = (body.dataset.website || "").trim();
      const domainInputVal = (body.dataset.domainInput || "").trim();
      const codes = selectedCodesIn(body);
      if (!codes.length) return;
      if (!website) {
        showError("Verify cần URL shop hợp lệ cho brand này.");
        return;
      }
      const prev = t.textContent;
      t.disabled = true;
      t.textContent = "Đang verify...";
      try {
        showError("");
        const data = await postVerify(website, codes, 30);
        panelVerify.hidden = false;
        renderVerifyRows(tblVerify, data.results || []);
      } catch (ex) {
        showError(String(ex.message || ex));
      } finally {
        t.disabled = false;
        t.textContent = prev;
      }
    });
  }

  function escapeXmlText(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function couponsForExport(session, root) {
    const all = session.coupons || [];
    if (!root) return all;
    const selected = selectedCodesIn(root);
    if (!selected.length) return all;
    const picked = new Set(selected.map((c) => String(c).toUpperCase()));
    return all.filter((c) => picked.has(String(c.code || "").toUpperCase()));
  }

  function exportSessionCouponsExcel(s, root) {
    const coupons = couponsForExport(s, root);
    if (!coupons.length) return;
    const rows = coupons.map((c) => {
      const disc = (c.source_discount || "").trim() || "—";
      const moTa = (c.source_item_description || "").trim() || "—";
      const health = (c.source_health_score || "").trim() || "—";
      return `<tr><td>${escapeXmlText(c.code)}</td><td>${escapeXmlText(disc)}</td><td>${escapeXmlText(
        moTa
      )}</td><td>${escapeXmlText(health)}</td></tr>`;
    });
    const thead =
      "<thead><tr><th>Mã</th><th>Giảm giá</th><th>Mô tả</th><th>Xác xuất</th></tr></thead>";
    const html = `<!DOCTYPE html><html xmlns:o="urn:schemas-microsoft-com:office:office"><head><meta charset="UTF-8"/></head><body><table border="1">${thead}<tbody>${rows.join(
      ""
    )}</tbody></table></body></html>`;
    const blob = new Blob([html], { type: "application/vnd.ms-excel;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    const stamp = new Date(s.at).toISOString().slice(0, 19).replace(/[:T]/g, "-");
    const safe = String(s.domainInput || "coupons")
      .replace(/[/\\?%*:|"<>]/g, "_")
      .slice(0, 72);
    a.href = url;
    a.download = `coupon_${safe}_${stamp}.xls`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  function renderVerifyRows(tbody, results) {
    tbody.innerHTML = "";
    (results || []).forEach((r) => {
      const tr = document.createElement("tr");
      const ok = r.is_working;
      tr.innerHTML = `
        <td><strong>${escapeHtml(r.code)}</strong></td>
        <td><span class="badge ${ok ? "ok" : "fail"}">${ok ? "Hoạt động" : "Không"}</span></td>
        <td>${escapeHtml(r.discount_text || r.source_discount || "—")}</td>
        <td class="cell-desc">${escapeHtml(r.source_item_description || "—")}</td>
        <td class="cell-health-score" title="data-health-score (Simply Codes)">${escapeHtml(
          (r.source_health_score || "").trim() || "—"
        )}</td>
        <td>${(r.confidence ?? 0).toFixed(2)}</td>
        <td>${escapeHtml(String(r.coupon_type || ""))}</td>`;
      tbody.appendChild(tr);
    });
  }

  async function postVerify(domain, codes, maxCodes) {
    const res = await fetch("/api/ui/verify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ domain, codes, max_codes: maxCodes }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(apiErr(data, res.statusText || "Lỗi verify"));
    return data;
  }

  btnVerify.addEventListener("click", async () => {
    if (!verifyFeatureEnabled) return;
    const codes = selectedCodesIn(currentResultsList);
    if (!codes.length || !lastDomain) return;
    if (!lastWebsite) {
      showError("Verify cần domain/URL shop hợp lệ. Nhập lại (ví dụ nike.com) rồi tìm lại.");
      return;
    }
    showError("");
    setVerifyLoading(true);
    panelVerify.hidden = true;
    tblVerify.innerHTML = "";
    try {
      const data = await postVerify(lastWebsite, codes, 30);
      renderVerifyRows(tblVerify, data.results || []);
      panelVerify.hidden = false;
    } catch (e) {
      showError(String(e.message || e));
    } finally {
      setVerifyLoading(false);
      updateVerifyBtn();
    }
  });

  if (btnStop) {
    btnStop.addEventListener("click", () => {
      if (searchAbortController) searchAbortController.abort();
    });
  }

  btnSearch.addEventListener("click", async () => {
    showError("");
    if (!licenseOk) {
      showError(formatLicenseStatus(licenseInfo));
      setActiveTab("settings");
      return;
    }
    const domains = parseDomainLines(domainInput.value);
    if (!domains.length) {
      showError("Nhập ít nhất một domain, URL shop hoặc tên brand (mỗi dòng một mục).");
      return;
    }
    const lineCount = countNonEmptyDomainLines(domainInput.value);
    if (lineCount > MAX_BATCH_DOMAINS) {
      showError(`Chỉ xử lý ${MAX_BATCH_DOMAINS} brand đầu tiên (bạn nhập ${lineCount} dòng).`);
    }
    searchAbortController = new AbortController();
    setLoading(true);
    setSearchProgress(0, `Chuẩn bị tìm ${domains.length} brand…`);
    panelVerify.hidden = true;
    tblVerify.innerHTML = "";
    initCurrentBatch(domains);
    try {
      const { summary, stopped } = await postSearchBatchStream(domains, {
        signal: searchAbortController.signal,
      });
      setSearchProgress(100, stopped ? "Đã dừng" : "Hoàn tất");
      await refreshHistoryListAsync();
      applyBatchSummary(summary, { stopped });
    } catch (e) {
      if (e && e.kind === "aborted") {
        currentBatchResults.forEach((b) => {
          if (b.status === "pending") {
            b.status = "cancelled";
            b.userMessage = "Đã dừng trước khi hoàn thành";
          }
        });
        renderCurrentBatchResults();
        setSearchProgress(100, "Đã dừng");
        await refreshHistoryListAsync();
        applyBatchSummary(
          {
            total: domains.length,
            ok_count: currentBatchResults.filter((b) => b.status === "ok").length,
            error_count: currentBatchResults.filter((b) => b.status === "error" || b.status === "empty")
              .length,
            errors: [],
          },
          { stopped: true }
        );
      } else if (e && e.kind === "search") {
        const ev = e.event;
        const msg = ev.message || MSG_SYSTEM;
        showError(
          msg === MSG_APIFY_TOKEN || ev.error_code === "apify_token" ? MSG_APIFY_TOKEN : msg
        );
      } else if (e && e.kind === "http") {
        const detail = apiErr(e.data, "");
        const errCode =
          (e.data && e.data.detail && e.data.detail.error_code) || e.data?.error_code || "";
        if (isLicenseErrorCode(errCode) || isLicenseErrorCode(String(errCode))) {
          licenseOk = false;
          licenseInfo = {
            ok: false,
            message: detail || "License không hợp lệ.",
            error_code: errCode,
          };
          updateLicenseUi();
          setActiveTab("settings");
        }
        showError(
          detail === MSG_APIFY_TOKEN || e.data.error_code === "apify_token"
            ? MSG_APIFY_TOKEN
            : detail || MSG_SYSTEM
        );
      } else {
        showError(MSG_SYSTEM);
      }
    } finally {
      searchAbortController = null;
      setLoading(false);
      hideSearchProgress();
    }
  });

  domainInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      btnSearch.click();
    }
  });

  /* ---- Tabs ---- */
  async function setActiveTab(which) {
    const isFind = which === "find";
    const isHistory = which === "history";
    const isSettings = which === "settings";
    tabBtnFind.classList.toggle("active", isFind);
    tabBtnHistory.classList.toggle("active", isHistory);
    tabBtnSettings.classList.toggle("active", isSettings);
    tabBtnFind.setAttribute("aria-selected", isFind ? "true" : "false");
    tabBtnHistory.setAttribute("aria-selected", isHistory ? "true" : "false");
    tabBtnSettings.setAttribute("aria-selected", isSettings ? "true" : "false");
    tabPanelFind.hidden = !isFind;
    tabPanelHistory.hidden = !isHistory;
    if (tabPanelSettings) tabPanelSettings.hidden = !isSettings;
    if (isFind) closeHistoryDateMenu();
    if (isHistory) {
      await ensureSessionsLoaded();
      refreshHistoryList();
    }
    if (isSettings) {
      await loadEnvSettingsForm();
    }
  }

  tabBtnFind.addEventListener("click", () => {
    void setActiveTab("find");
  });
  tabBtnHistory.addEventListener("click", () => {
    void setActiveTab("history");
  });
  if (tabBtnSettings) {
    tabBtnSettings.addEventListener("click", () => {
      void setActiveTab("settings");
    });
  }

  /* ---- Settings (.env) ---- */
  function showSettingsMsg(text, isError) {
    if (!settingsMsg) return;
    if (text) {
      settingsMsg.textContent = text;
      settingsMsg.hidden = false;
      settingsMsg.classList.toggle("error", !!isError);
      settingsMsg.classList.toggle("settings-msg-ok", !isError);
    } else {
      settingsMsg.hidden = true;
      settingsMsg.textContent = "";
    }
  }

  function renderEnvSettingsForm(data) {
    if (!settingsForm) return;
    if (settingsEnvPath) {
      settingsEnvPath.textContent = data.env_path
        ? `File cấu hình: ${data.env_path}`
        : "";
    }
    settingsForm.innerHTML = "";
    let currentGroup = "";
    (data.fields || []).forEach((f) => {
      if (f.group !== currentGroup) {
        currentGroup = f.group;
        const h = document.createElement("h3");
        h.className = "settings-group-title";
        h.textContent = currentGroup;
        settingsForm.appendChild(h);
      }
      const wrap = document.createElement("div");
      wrap.className = "settings-field";

      const lab = document.createElement("label");
      lab.className = "settings-label";
      lab.htmlFor = `env-${f.key}`;
      lab.textContent = f.label;
      wrap.appendChild(lab);

      if (f.description) {
        const hint = document.createElement("p");
        hint.className = "settings-hint muted";
        hint.textContent = f.description;
        wrap.appendChild(hint);
      }

      let input;
      if (f.type === "bool") {
        input = document.createElement("input");
        input.type = "checkbox";
        input.checked = f.value === "true" || f.value === true;
        input.className = "settings-checkbox";
      } else if (f.type === "secret") {
        input = document.createElement("input");
        input.type = "password";
        input.className = "settings-input";
        input.placeholder = f.has_value ? `${f.masked || "••••••••"} — nhập mới để đổi` : "Nhập token / key";
        input.autocomplete = "off";
      } else {
        input = document.createElement("input");
        input.type = f.type === "int" ? "number" : "text";
        input.className = "settings-input";
        input.value = f.value != null ? String(f.value) : "";
        if (f.type === "int") {
          input.step = "1";
          input.min = "0";
        }
      }
      input.id = `env-${f.key}`;
      input.dataset.envKey = f.key;
      input.dataset.envType = f.type;
      wrap.appendChild(input);
      settingsForm.appendChild(wrap);
    });
  }

  function collectEnvFormValues() {
    const values = {};
    if (!settingsForm) return values;
    settingsForm.querySelectorAll("[data-env-key]").forEach((el) => {
      const key = el.dataset.envKey;
      const t = el.dataset.envType;
      if (t === "bool") values[key] = el.checked;
      else values[key] = el.value;
    });
    return values;
  }

  async function loadEnvSettingsForm() {
    showSettingsMsg("");
    try {
      const res = await fetch("/api/ui/env");
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(apiErr(data, "Không tải được cài đặt"));
      renderEnvSettingsForm(data);
    } catch (e) {
      showSettingsMsg(String(e.message || e), true);
    }
  }

  async function saveEnvSettingsForm() {
    showSettingsMsg("");
    if (btnEnvSave) btnEnvSave.disabled = true;
    try {
      const res = await fetch("/api/ui/env", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ values: collectEnvFormValues() }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(apiErr(data, "Lưu thất bại"));
      renderEnvSettingsForm(data);
      showSettingsMsg("Đã lưu vào .env. Một số thay đổi áp dụng ngay; restart API nếu cần.", false);
      await loadUiSettings();
    } catch (e) {
      showSettingsMsg(String(e.message || e), true);
    } finally {
      if (btnEnvSave) btnEnvSave.disabled = false;
    }
  }

  if (btnEnvSave) btnEnvSave.addEventListener("click", () => void saveEnvSettingsForm());
  if (btnEnvReload) btnEnvReload.addEventListener("click", () => void loadEnvSettingsForm());

  /* ---- History ---- */
  const HISTORY_DATE_LABELS = {
    today: "Hôm nay",
    yesterday: "Hôm qua",
    last7: "7 ngày qua",
    all: "Tất cả ngày",
  };

  function localDateKey(d) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  }

  function startOfLocalDay(d) {
    return new Date(d.getFullYear(), d.getMonth(), d.getDate(), 0, 0, 0, 0);
  }

  function endOfLocalDay(d) {
    return new Date(d.getFullYear(), d.getMonth(), d.getDate(), 23, 59, 59, 999);
  }

  function sessionMatchesDateFilter(s) {
    const at = Number(s.at);
    if (!at) return false;
    const t = new Date(at);
    const now = new Date();
    if (historyDatePreset === "all") return true;
    if (historyDatePreset === "today") {
      return t >= startOfLocalDay(now) && t <= endOfLocalDay(now);
    }
    if (historyDatePreset === "yesterday") {
      const y = new Date(now);
      y.setDate(y.getDate() - 1);
      return t >= startOfLocalDay(y) && t <= endOfLocalDay(y);
    }
    if (historyDatePreset === "last7") {
      const start = startOfLocalDay(now);
      start.setDate(start.getDate() - 6);
      return t >= start && t <= endOfLocalDay(now);
    }
    if (historyDatePreset === "custom" && historyCustomDate) {
      const [yy, mm, dd] = historyCustomDate.split("-").map((x) => parseInt(x, 10));
      const day = new Date(yy, mm - 1, dd);
      return t >= startOfLocalDay(day) && t <= endOfLocalDay(day);
    }
    return true;
  }

  function sessionMatchesSearchQuery(s, q) {
    if (!q) return true;
    const hay = [s.domainInput, s.website, s.brandHint]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return hay.includes(q);
  }

  function filterHistorySessions(sessions) {
    const q = (historySearch && historySearch.value.trim().toLowerCase()) || "";
    return sessions.filter((s) => sessionMatchesDateFilter(s) && sessionMatchesSearchQuery(s, q));
  }

  function historyDateButtonLabel() {
    if (historyDatePreset === "custom" && historyCustomDate) {
      const [y, m, d] = historyCustomDate.split("-");
      return `${d}/${m}/${y}`;
    }
    return HISTORY_DATE_LABELS[historyDatePreset] || "Hôm nay";
  }

  function updateHistoryDateButton() {
    if (!historyDateBtn) return;
    historyDateBtn.textContent = historyDateButtonLabel();
    if (historyDatePicker && historyCustomDate) {
      historyDatePicker.value = historyCustomDate;
    }
  }

  function closeHistoryDateMenu() {
    if (!historyDateMenu) return;
    historyDateMenu.hidden = true;
    if (historyDateBtn) historyDateBtn.setAttribute("aria-expanded", "false");
  }

  function openHistoryDateMenu() {
    if (!historyDateMenu) return;
    historyDateMenu.hidden = false;
    if (historyDateBtn) historyDateBtn.setAttribute("aria-expanded", "true");
  }

  function setHistoryDatePreset(preset, customDate) {
    historyDatePreset = preset || "today";
    historyCustomDate = customDate || "";
    historyPage = 1;
    updateHistoryDateButton();
    closeHistoryDateMenu();
    refreshHistoryList();
  }

  function formatSessionSummary(s) {
    const t = new Date(s.at).toLocaleString("vi-VN");
    const n = (s.coupons && s.coupons.length) || 0;
    const err =
      n === 0 && s.userMessage
        ? ` · ${s.userMessage.length > 48 ? `${s.userMessage.slice(0, 48)}…` : s.userMessage}`
        : "";
    return `${t} · ${s.domainInput} → ${s.website || "—"} · ${n} mã · raw ${s.rawCount ?? "—"}${err}`;
  }

  function buildHistorySessionBody(det, s) {
    const wrap = document.createElement("div");
    wrap.className = "history-body-inner";
    wrap.dataset.sid = s.id;
    wrap.dataset.website = s.website || "";
    wrap.dataset.domainInput = s.domainInput || "";

    const metaP = document.createElement("p");
    metaP.className = "meta muted";
    metaP.textContent = `Brand: ${s.brandHint || "—"} · Website: ${s.website || "—"} · Raw: ${s.rawCount} · Chuẩn hoá: ${s.normalizedCount}`;
    wrap.appendChild(metaP);
    if (s.userMessage && !(s.coupons && s.coupons.length)) {
      const errP = document.createElement("p");
      errP.className = "error history-item-error";
      errP.textContent = s.userMessage;
      wrap.appendChild(errP);
    }

    const tb = document.createElement("div");
    tb.className = "toolbar";
    tb.innerHTML = verifyFeatureEnabled
      ? `<h3 class="history-table-title">Mã trong lần tìm này</h3><div class="toolbar-actions"><button type="button" class="btn accent hist-verify" data-sid="${escapeAttr(
          s.id
        )}">Verify đã chọn</button></div>`
      : `<h3 class="history-table-title">Mã trong lần tìm này</h3>`;
    wrap.appendChild(tb);

    const hVerify = wrap.querySelector(".hist-verify");
    if (hVerify && !(s.website || "").trim()) {
      hVerify.disabled = true;
      hVerify.title = "Verify cần URL shop hợp lệ (ví dụ nike.com), không chỉ tên brand.";
    }

    const tw = document.createElement("div");
    tw.className = "table-wrap";
    tw.innerHTML = `
      <table class="table hist-coupon-table">
        <thead>
          <tr>
            <th class="th-check"><input type="checkbox" class="hist-chk-master" data-sid="${escapeAttr(s.id)}" title="Chọn tất cả" /></th>
            <th>Mã</th>
            <th>Giảm giá</th>
            <th>Mô tả</th>
            <th>Xác xuất</th>
          </tr>
        </thead>
        <tbody></tbody>
      </table>`;
    const histTbody = tw.querySelector("tbody");
    renderCouponsInto(histTbody, s.coupons || []);
    wrap.appendChild(tw);

    if (verifyFeatureEnabled) {
      const pv = document.createElement("section");
      pv.className = "card hist-verify-panel";
      pv.hidden = true;
      pv.dataset.sid = s.id;
      pv.innerHTML = `
      <h3>Sau khi verify</h3>
      <div class="table-wrap">
        <table class="table hist-tbl-verify">
          <thead>
            <tr>
              <th>Mã</th>
              <th>Trạng thái</th>
              <th>Giảm giá</th>
              <th>Mô tả</th>
              <th>Xác xuất</th>
              <th>Độ tin cậy</th>
              <th>Loại</th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>`;
      wrap.appendChild(pv);
    }

    det.appendChild(wrap);

    const master = wrap.querySelector(".hist-chk-master");
    master.addEventListener("change", () => {
      const on = master.checked;
      wrap.querySelectorAll(".row-chk").forEach((b) => {
        b.checked = on;
      });
      master.indeterminate = false;
    });
    wrap.querySelector(".hist-coupon-table").addEventListener("change", (e) => {
      if (e.target.classList.contains("row-chk")) {
        const boxes = [...wrap.querySelectorAll(".row-chk")];
        master.checked = boxes.length > 0 && boxes.every((b) => b.checked);
        master.indeterminate = boxes.some((b) => b.checked) && !boxes.every((b) => b.checked);
      }
    });
  }

  historyList.addEventListener("click", async (e) => {
    const t = e.target;
    if (!(t instanceof HTMLElement)) return;

    if (t.classList.contains("hist-export") || t.classList.contains("hist-export-inline")) {
      e.preventDefault();
      e.stopPropagation();
      const sid = t.dataset.sid;
      if (!sid) return;
      const session = getSessions().find((x) => x.id === sid);
      if (!session) return;
      const inner = historyList.querySelector(`.history-body-inner[data-sid="${sid}"]`);
      exportSessionCouponsExcel(session, inner);
      return;
    }

    const sid = t.dataset.sid;
    if (!sid) return;
    const inner = historyList.querySelector(`.history-body-inner[data-sid="${sid}"]`);
    if (!inner) return;

    if (t.classList.contains("hist-verify")) {
      const codes = selectedCodesIn(inner);
      const website = (inner.dataset.website || "").trim();
      const domainInputVal = (inner.dataset.domainInput || "").trim();
      const domain = website || domainInputVal;
      if (!codes.length) return;
      if (!website) {
        showError("Phiên này không có URL shop — verify cần domain hợp lệ (ví dụ nike.com).");
        return;
      }
      const btn = t;
      btn.disabled = true;
      const prev = btn.textContent;
      btn.textContent = "Đang verify...";
      const pv = inner.querySelector(`.hist-verify-panel[data-sid="${sid}"]`);
      const vtbody = pv && pv.querySelector("tbody");
      try {
        showError("");
        const data = await postVerify(domain, codes, 30);
        if (vtbody) renderVerifyRows(vtbody, data.results || []);
        if (pv) pv.hidden = false;
      } catch (ex) {
        showError(String(ex.message || ex));
      } finally {
        btn.disabled = false;
        btn.textContent = prev;
      }
    }
  });

  function renderHistoryPage(sessions) {
    historyList.innerHTML = "";
    sessions.forEach((s) => {
      const det = document.createElement("details");
      det.className = "history-item";
      const sum = document.createElement("summary");
      sum.className = "history-summary";
      sum.innerHTML = `<span class="history-caret" aria-hidden="true">▸</span><div class="history-summary-row"><span class="history-summary-txt">${escapeHtml(
        formatSessionSummary(s)
      )}</span><button type="button" class="btn ghost hist-export hist-export-inline" data-sid="${escapeAttr(
        s.id
      )}" title="Xuất mã đã tick; không tick thì xuất hết">Xuất Excel</button></div>`;
      det.appendChild(sum);
      det.addEventListener("toggle", () => {
        if (det.open && !det.dataset.ready) {
          det.dataset.ready = "1";
          buildHistorySessionBody(det, s);
        }
      });
      historyList.appendChild(det);
    });
  }

  function updateHistoryPagination(totalFiltered, pageCount) {
    if (!historyPagination) return;
    const show = totalFiltered > HISTORY_PAGE_SIZE;
    historyPagination.hidden = !show;
    if (historyPageInfo) {
      historyPageInfo.textContent = `Trang ${historyPage} / ${Math.max(1, pageCount)}`;
    }
    if (historyPrev) historyPrev.disabled = historyPage <= 1;
    if (historyNext) historyNext.disabled = historyPage >= pageCount;
  }

  function refreshHistoryList() {
    const all = getSessions();
    const filtered = filterHistorySessions(all);
    const totalFiltered = filtered.length;
    const pageCount = Math.max(1, Math.ceil(totalFiltered / HISTORY_PAGE_SIZE) || 1);
    if (historyPage > pageCount) historyPage = pageCount;
    if (historyPage < 1) historyPage = 1;

    const start = (historyPage - 1) * HISTORY_PAGE_SIZE;
    const pageItems = filtered.slice(start, start + HISTORY_PAGE_SIZE);

    const hasAny = all.length > 0;
    const hasMatch = totalFiltered > 0;

    if (historyEmpty) historyEmpty.hidden = hasAny;
    if (historyNoMatch) historyNoMatch.hidden = !hasAny || hasMatch;
    if (historyFilterMeta) {
      if (!hasAny) {
        historyFilterMeta.hidden = true;
      } else {
        historyFilterMeta.hidden = false;
        const q = (historySearch && historySearch.value.trim()) || "";
        const parts = [`${totalFiltered} bản ghi`, historyDateButtonLabel()];
        if (q) parts.push(`tìm «${q}»`);
        if (totalFiltered > HISTORY_PAGE_SIZE) {
          parts.push(`trang ${historyPage}/${pageCount}`);
        }
        historyFilterMeta.textContent = parts.join(" · ");
      }
    }

    renderHistoryPage(pageItems);
    updateHistoryPagination(totalFiltered, pageCount);
  }

  if (historySearch) {
    let historySearchTimer = null;
    historySearch.addEventListener("input", () => {
      historyPage = 1;
      clearTimeout(historySearchTimer);
      historySearchTimer = setTimeout(refreshHistoryList, 200);
    });
  }

  if (historyDateBtn && historyDateMenu) {
    historyDateBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      if (historyDateMenu.hidden) openHistoryDateMenu();
      else closeHistoryDateMenu();
    });
    historyDateMenu.querySelectorAll(".history-date-opt").forEach((btn) => {
      btn.addEventListener("click", () => {
        setHistoryDatePreset(btn.dataset.preset || "today", "");
      });
    });
    if (historyDatePicker) {
      historyDatePicker.addEventListener("change", () => {
        const v = historyDatePicker.value;
        if (v) setHistoryDatePreset("custom", v);
      });
    }
    document.addEventListener("click", (e) => {
      if (!(e.target instanceof HTMLElement)) return;
      if (e.target.closest(".history-date-wrap")) return;
      closeHistoryDateMenu();
    });
  }

  if (historyPrev) {
    historyPrev.addEventListener("click", () => {
      if (historyPage > 1) {
        historyPage -= 1;
        refreshHistoryList();
        tabPanelHistory.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    });
  }

  if (historyNext) {
    historyNext.addEventListener("click", () => {
      const filtered = filterHistorySessions(getSessions());
      const pageCount = Math.max(1, Math.ceil(filtered.length / HISTORY_PAGE_SIZE));
      if (historyPage < pageCount) {
        historyPage += 1;
        refreshHistoryList();
        tabPanelHistory.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    });
  }

  if (historyDatePicker) {
    historyDatePicker.value = localDateKey(new Date());
  }
  closeHistoryDateMenu();
  updateHistoryDateButton();

  function applyVerifyVisibility() {
    panelVerify.hidden = true;
    updateVerifyBtn();
  }

  async function refreshHistoryListAsync() {
    await ensureSessionsLoaded();
    refreshHistoryList();
  }

  async function loadUiSettings() {
    try {
      const r = await fetch("/api/ui/settings");
      if (r.ok) {
        const j = await r.json();
        verifyFeatureEnabled = Boolean(j.verify_enabled);
        if (j.license) {
          licenseInfo = j.license;
          licenseOk = Boolean(j.license.ok);
        }
      } else {
        verifyFeatureEnabled = false;
      }
    } catch {
      verifyFeatureEnabled = false;
    }
    if (!licenseInfo) {
      await loadLicenseStatus();
    } else {
      updateLicenseUi();
    }
    applyVerifyVisibility();
    await migrateLocalStorageHistory();
    await ensureSessionsLoaded();
  }

  void loadUiSettings();
})();
