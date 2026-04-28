/* JellyNama search-view injector
 * Loaded into every Jellyfin web page via index.html patching. Watches for
 * navigation to the search view and adds a "Search 30nama" affordance that
 * opens a modal driven by the JellyNama sidecar API.
 */
(function () {
  "use strict";

  const PLUGIN_ID = "3a8d4f2e-7c1b-4e6a-9f8d-2b5e1a9c4d7e";
  const MARKER_ATTR = "data-jellynama-injected";
  const MODAL_ID = "jellynama-modal";

  let sidecarUrl = null;
  let configPromise = null;

  function getConfig() {
    if (configPromise) return configPromise;
    if (typeof ApiClient === "undefined" || !ApiClient.getPluginConfiguration) {
      return Promise.reject(new Error("ApiClient unavailable"));
    }
    configPromise = ApiClient.getPluginConfiguration(PLUGIN_ID).then((cfg) => {
      sidecarUrl = (cfg && cfg.SidecarUrl) || "http://localhost:8765";
      return sidecarUrl;
    });
    return configPromise;
  }

  function api(path, opts) {
    return getConfig().then((base) =>
      fetch(base.replace(/\/$/, "") + path, Object.assign({
        headers: { "Content-Type": "application/json" }
      }, opts || {})).then((r) => {
        if (!r.ok) return r.text().then((t) => { throw new Error(r.status + " " + (t || r.statusText)); });
        return r.json();
      })
    );
  }

  function escapeHtml(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    })[c]);
  }

  function isSearchView() {
    const h = location.hash || "";
    return h.indexOf("search.html") !== -1 || h.indexOf("/search") !== -1;
  }

  function getQueryFromUrl() {
    const h = location.hash || "";
    const q = h.match(/[?&]query=([^&]+)/);
    return q ? decodeURIComponent(q[1].replace(/\+/g, " ")) : "";
  }

  function getQueryFromInput() {
    const input = document.querySelector(
      ".pageContainer:not(.hide) .searchFields input, " +
      ".pageContainer:not(.hide) input[type=search], " +
      ".searchFields input"
    );
    return input ? input.value.trim() : "";
  }

  function currentQuery() {
    return getQueryFromInput() || getQueryFromUrl();
  }

  /* ---------- search-page banner ---------- */

  function findSearchPage() {
    const candidates = document.querySelectorAll(
      ".pageContainer:not(.hide), .page:not(.hide), [data-type='search']:not(.hide)"
    );
    for (const el of candidates) {
      const hash = el.getAttribute("data-hash") || "";
      if (hash.indexOf("search") !== -1 ||
          el.querySelector(".searchFields") ||
          el.querySelector(".searchResults")) {
        return el;
      }
    }
    return document.querySelector(".pageContainer:not(.hide)") || null;
  }

  function injectBanner() {
    if (!isSearchView()) return;
    const page = findSearchPage();
    if (!page) return;
    if (page.querySelector("." + MARKER_ATTR.replace(/^data-/, ""))) return;
    if (page.hasAttribute(MARKER_ATTR)) return;

    page.setAttribute(MARKER_ATTR, "1");

    const banner = document.createElement("div");
    banner.className = "jellynama-banner verticalSection";
    banner.style.cssText = "padding:12px 16px;margin:8px 0;background:linear-gradient(90deg,rgba(0,164,220,0.10),rgba(0,164,220,0.02));border:1px solid rgba(0,164,220,0.3);border-radius:6px;display:flex;align-items:center;gap:12px;";
    banner.innerHTML =
      '<span style="font-size:22px;line-height:1;">🎬</span>' +
      '<div style="flex:1;min-width:0;">' +
        '<div style="font-weight:600;font-size:14px;">Not in your library?</div>' +
        '<div style="font-size:12px;color:#8a98a8;" class="jn-banner-sub">Search 30nama for the title in your search box.</div>' +
      '</div>' +
      '<button is="emby-button" type="button" class="raised jn-search-btn" style="white-space:nowrap;">' +
        '<span>Search 30nama</span>' +
      '</button>';

    // Try to insert above the search results, otherwise at the top of the page.
    const results = page.querySelector(".searchResults") || page.querySelector(".pageTabContent") || page.firstElementChild;
    if (results && results.parentNode) {
      results.parentNode.insertBefore(banner, results);
    } else {
      page.insertBefore(banner, page.firstChild);
    }

    const sub = banner.querySelector(".jn-banner-sub");
    const updateSub = () => {
      const q = currentQuery();
      sub.textContent = q
        ? `Search 30nama for "${q}"`
        : "Type a query above, then click to search 30nama.";
    };
    updateSub();
    document.addEventListener("input", updateSub, true);

    banner.querySelector(".jn-search-btn").addEventListener("click", () => {
      const q = currentQuery();
      if (!q) {
        alert("Type something in the search box first.");
        return;
      }
      openModal(q);
    });
  }

  /* ---------- modal ---------- */

  function ensureModal() {
    let modal = document.getElementById(MODAL_ID);
    if (modal) return modal;

    modal = document.createElement("div");
    modal.id = MODAL_ID;
    modal.style.cssText = "position:fixed;inset:0;background:rgba(0,0,0,0.7);z-index:99999;display:none;align-items:flex-start;justify-content:center;overflow:auto;padding:40px 16px;";
    modal.innerHTML =
      '<div class="jn-modal-card" style="background:#101418;color:#e8eef4;border:1px solid #2a323d;border-radius:8px;max-width:1100px;width:100%;padding:20px;box-shadow:0 20px 60px rgba(0,0,0,0.6);">' +
        '<div style="display:flex;align-items:center;gap:12px;margin-bottom:14px;">' +
          '<h2 style="margin:0;flex:1;font-size:18px;">JellyNama · 30nama search</h2>' +
          '<button is="emby-button" type="button" class="raised jn-modal-retry"><span>Retry</span></button>' +
          '<button is="emby-button" type="button" class="raised jn-modal-close"><span>Close</span></button>' +
        '</div>' +
        '<div class="jn-modal-error" style="color:#e53935;font-size:13px;margin-bottom:8px;" hidden></div>' +
        '<div class="jn-modal-results" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px;"></div>' +
        '<div style="margin-top:18px;">' +
          '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;">' +
            '<h3 style="font-size:14px;margin:0;color:#8a98a8;">Downloads</h3>' +
            '<button is="emby-button" type="button" class="raised jn-modal-clear" style="font-size:11px;padding:4px 10px;"><span>Clear finished</span></button>' +
          '</div>' +
          '<div class="jn-modal-jobs"></div>' +
        '</div>' +
      '</div>';
    document.body.appendChild(modal);

    modal.addEventListener("click", (e) => {
      if (e.target === modal) closeModal();
    });
    modal.querySelector(".jn-modal-close").addEventListener("click", closeModal);
    modal.querySelector(".jn-modal-clear").addEventListener("click", (e) => {
      const btn = e.currentTarget;
      btn.disabled = true;
      api("/api/jobs/clear", { method: "POST" })
        .then(() => refreshJobs(modal))
        .catch((err) => showError(modal, "Clear failed: " + err.message))
        .finally(() => { btn.disabled = false; });
    });
    modal.querySelector(".jn-modal-retry").addEventListener("click", () => {
      const q = modal.dataset.jnQuery;
      if (q) runSearch(modal, q);
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && modal.style.display === "flex") closeModal();
    });

    return modal;
  }

  let jobsTimer = null;

  function runSearch(modal, query) {
    modal.dataset.jnQuery = query;
    showError(modal, null);
    const results = modal.querySelector(".jn-modal-results");
    results.innerHTML = '<div style="color:#8a98a8;padding:8px;">Searching 30nama for "' + escapeHtml(query) + '"…</div>';
    api("/api/search?q=" + encodeURIComponent(query))
      .then((hits) => renderResults(modal, hits))
      .catch((e) => {
        showError(modal, "Search failed: " + e.message);
        results.innerHTML = "";
      });
  }

  function openModal(query) {
    const modal = ensureModal();
    modal.style.display = "flex";
    runSearch(modal, query);
    refreshJobs(modal);
    if (jobsTimer) clearInterval(jobsTimer);
    jobsTimer = setInterval(() => refreshJobs(modal), 2000);
  }

  function closeModal() {
    const modal = document.getElementById(MODAL_ID);
    if (modal) modal.style.display = "none";
    if (jobsTimer) { clearInterval(jobsTimer); jobsTimer = null; }
  }

  function showError(modal, msg) {
    const el = modal.querySelector(".jn-modal-error");
    if (!msg) { el.hidden = true; return; }
    el.textContent = msg;
    el.hidden = false;
  }

  const PAGE_SIZE = 8;
  let currentHits = [];
  let currentPage = 0;

  function renderResults(modal, hits) {
    currentHits = hits;
    currentPage = 0;
    renderPage(modal);
  }

  function renderPage(modal) {
    const root = modal.querySelector(".jn-modal-results");
    const oldNav = modal.querySelector(".jn-pagination");
    if (oldNav) oldNav.remove();

    if (!currentHits.length) {
      root.innerHTML = '<div style="color:#8a98a8;padding:8px;">No results.</div>';
      return;
    }
    const totalPages = Math.max(1, Math.ceil(currentHits.length / PAGE_SIZE));
    if (currentPage >= totalPages) currentPage = totalPages - 1;
    const start = currentPage * PAGE_SIZE;
    const pageHits = currentHits.slice(start, start + PAGE_SIZE);

    root.innerHTML = "";
    pageHits.forEach((h) => {
      const card = document.createElement("div");
      card.style.cssText = "background:#1a2027;border:1px solid #2a323d;border-radius:6px;overflow:hidden;display:flex;flex-direction:column;";
      const poster = h.poster
        ? "background-image:url('" + h.poster + "');background-size:cover;background-position:center;"
        : "background:#0a0d10;";
      const inLib = h.in_library
        ? '<span style="background:rgba(76,175,80,0.18);color:#4caf50;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:600;">In library</span>'
        : "";
      card.innerHTML =
        '<div style="aspect-ratio:2/3;' + poster + '"></div>' +
        '<div style="padding:10px;display:flex;flex-direction:column;gap:6px;">' +
          '<div style="font-weight:600;font-size:13px;">' + escapeHtml(h.title) + '</div>' +
          '<div style="font-size:11px;color:#8a98a8;">' + (h.year ? escapeHtml(h.year) + ' · ' : '') + escapeHtml(h.kind || "") + ' ' + inLib + '</div>' +
          '<div class="jn-opts" data-detail="' + encodeURIComponent(h.detail_url) + '" data-title="' + encodeURIComponent(h.title) + '" data-kind="' + encodeURIComponent(h.kind || "") + '" data-year="' + encodeURIComponent(h.year || "") + '">' +
            '<button is="emby-button" type="button" class="raised jn-load-opts" style="font-size:12px;padding:6px 10px;"><span>Load options</span></button>' +
          '</div>' +
        '</div>';
      root.appendChild(card);
    });
    root.querySelectorAll(".jn-load-opts").forEach((b) => {
      b.addEventListener("click", (e) => loadOptions(modal, e.currentTarget.parentElement));
    });
    if (totalPages > 1) renderPagination(modal, totalPages);
  }

  function renderPagination(modal, totalPages) {
    const nav = document.createElement("div");
    nav.className = "jn-pagination";
    nav.style.cssText = "display:flex;align-items:center;justify-content:center;gap:16px;margin-top:16px;";
    const prev = document.createElement("button");
    prev.setAttribute("is", "emby-button");
    prev.type = "button";
    prev.className = "raised";
    prev.style.cssText = "font-size:12px;padding:6px 12px;";
    prev.innerHTML = "<span>← Prev</span>";
    prev.disabled = currentPage === 0;
    prev.addEventListener("click", () => { currentPage--; renderPage(modal); });
    const next = document.createElement("button");
    next.setAttribute("is", "emby-button");
    next.type = "button";
    next.className = "raised";
    next.style.cssText = "font-size:12px;padding:6px 12px;";
    next.innerHTML = "<span>Next →</span>";
    next.disabled = currentPage >= totalPages - 1;
    next.addEventListener("click", () => { currentPage++; renderPage(modal); });
    const label = document.createElement("span");
    label.style.cssText = "color:#8a98a8;font-size:12px;";
    label.textContent = "Page " + (currentPage + 1) + " of " + totalPages;
    nav.append(prev, label, next);
    const root = modal.querySelector(".jn-modal-results");
    root.insertAdjacentElement("afterend", nav);
  }

  function renderEmpty(modal, container, message, color) {
    container.innerHTML = "";
    const wrap = document.createElement("div");
    wrap.style.cssText = "display:flex;align-items:center;gap:8px;flex-wrap:wrap;";
    const span = document.createElement("span");
    span.style.cssText = "font-size:11px;color:" + (color || "#8a98a8") + ";";
    span.textContent = message;
    wrap.appendChild(span);
    const btn = document.createElement("button");
    btn.setAttribute("is", "emby-button");
    btn.type = "button";
    btn.className = "raised";
    btn.style.cssText = "font-size:11px;padding:4px 8px;";
    btn.innerHTML = "<span>Retry</span>";
    btn.addEventListener("click", () => loadOptions(modal, container));
    wrap.appendChild(btn);
    container.appendChild(wrap);
  }

  function loadOptions(modal, container) {
    const detail = decodeURIComponent(container.dataset.detail);
    const title = decodeURIComponent(container.dataset.title);
    const kind = decodeURIComponent(container.dataset.kind || "");
    const year = decodeURIComponent(container.dataset.year || "");
    container.innerHTML = '<span style="font-size:11px;color:#8a98a8;">Loading…</span>';
    api("/api/options?detail_url=" + encodeURIComponent(detail))
      .then((opts) => {
        if (!opts.length) {
          renderEmpty(modal, container, "No links.");
          return;
        }
        container.innerHTML = "";
        const movieOpts = opts.filter((o) => !(o.episodes && o.episodes.length));
        const seriesOpts = opts.filter((o) => o.episodes && o.episodes.length);

        const wrapper = document.createElement("details");
        wrapper.open = true;
        wrapper.style.cssText = "margin-top:4px;";
        const wrapperSummary = document.createElement("summary");
        wrapperSummary.style.cssText = "font-size:12px;font-weight:600;color:#e8eef5;padding:6px 8px;background:#232b34;border-radius:4px;cursor:pointer;list-style:none;user-select:none;";
        const wrapperCaret = document.createElement("span");
        wrapperCaret.textContent = "▸";
        wrapperCaret.style.cssText = "display:inline-block;width:10px;margin-right:6px;transition:transform 0.15s ease;transform:rotate(90deg);";
        wrapperSummary.appendChild(wrapperCaret);
        wrapperSummary.appendChild(document.createTextNode("Download options · " + opts.length));
        wrapper.addEventListener("toggle", () => {
          wrapperCaret.style.transform = wrapper.open ? "rotate(90deg)" : "rotate(0deg)";
        });
        wrapper.appendChild(wrapperSummary);
        const wrapperBody = document.createElement("div");
        wrapperBody.style.cssText = "padding-top:6px;";
        wrapper.appendChild(wrapperBody);
        container.appendChild(wrapper);

        movieOpts.forEach((o) => {
          wrapperBody.appendChild(buildOptionRow(o, (btn) =>
            startDownload(modal, title, o.url, btn, kind, year)
          ));
        });

        const groups = new Map();
        seriesOpts.forEach((o) => {
          const k = o.season || "?";
          if (!groups.has(k)) groups.set(k, []);
          groups.get(k).push(o);
        });
        const keys = [...groups.keys()].sort((a, b) => Number(a) - Number(b));
        keys.forEach((k, idx) => {
          const details = document.createElement("details");
          details.style.cssText = "margin-top:" + (idx === 0 ? "4px" : "8px") + ";border-top:" + (idx === 0 ? "none" : "1px solid #2a323d") + ";padding-top:" + (idx === 0 ? "0" : "4px") + ";";
          const summary = document.createElement("summary");
          const epCount = groups.get(k)[0].episodes.length;
          const label = k === "?" ? "Season ?" : "Season " + String(k).padStart(2, "0");
          summary.style.cssText = "font-size:10px;color:#8a98a8;text-transform:uppercase;letter-spacing:0.05em;padding:6px 0 2px;cursor:pointer;list-style:none;user-select:none;";
          const caret = document.createElement("span");
          caret.textContent = "▸";
          caret.style.cssText = "display:inline-block;width:10px;margin-right:4px;transition:transform 0.15s ease;";
          summary.appendChild(caret);
          summary.appendChild(document.createTextNode(label + " · " + epCount + " episode" + (epCount === 1 ? "" : "s")));
          details.addEventListener("toggle", () => {
            caret.style.transform = details.open ? "rotate(90deg)" : "rotate(0deg)";
          });
          details.appendChild(summary);
          const body = document.createElement("div");
          body.style.cssText = "padding-top:4px;";
          groups.get(k).forEach((o) => {
            body.appendChild(buildOptionRow(o, (btn) =>
              startSeriesPack(modal, title, year, o.season, o.episodes, btn)
            ));
          });
          details.appendChild(body);
          wrapperBody.appendChild(details);
        });
      })
      .catch((e) => {
        renderEmpty(modal, container, e.message, "#e53935");
      });
  }

  function buildOptionRow(o, onClick) {
    const row = document.createElement("div");
    row.style.cssText = "display:flex;flex-direction:column;gap:2px;margin:4px 0;padding:6px 8px;background:#0e1216;border:1px solid #232a33;border-radius:4px;cursor:pointer;";
    const line1Parts = [o.quality, o.size].filter(Boolean);
    const tags = (o.tags || []).join(", ");
    const line2Parts = [o.encoder, tags].filter(Boolean);

    const line1 = document.createElement("div");
    line1.style.cssText = "font-size:12px;font-weight:600;color:#e8eef5;";
    line1.textContent = line1Parts.join(" · ");
    row.appendChild(line1);

    if (line2Parts.length) {
      const line2 = document.createElement("div");
      line2.style.cssText = "font-size:10px;color:#8a98a8;";
      line2.textContent = line2Parts.join(" | ");
      row.appendChild(line2);
    }

    row.addEventListener("click", () => onClick(row));
    row.addEventListener("mouseenter", () => { row.style.background = "#151b22"; });
    row.addEventListener("mouseleave", () => { row.style.background = "#0e1216"; });
    return row;
  }

  function startDownload(modal, title, url, btn, kind, year) {
    btn.style.pointerEvents = "none";
    btn.style.opacity = "0.6";
    btn.textContent = "Queued…";
    api("/api/download", { method: "POST", body: JSON.stringify({ title, url, kind: kind || "unknown", year: year || null }) })
      .then(() => { btn.textContent = "Queued ✓"; refreshJobs(modal); })
      .catch((e) => { btn.style.pointerEvents = ""; btn.style.opacity = ""; btn.textContent = "Retry"; showError(modal, e.message); });
  }

  function startSeriesPack(modal, title, year, season, episodes, btn) {
    btn.style.pointerEvents = "none";
    btn.style.opacity = "0.6";
    btn.textContent = "Queuing " + episodes.length + "…";
    api("/api/download/series-pack", {
      method: "POST",
      body: JSON.stringify({ title, year: year || null, season: season || null, episodes }),
    })
      .then((resp) => {
        const n = resp && resp.job_ids ? resp.job_ids.length : episodes.length;
        btn.textContent = "Queued " + n + " ✓";
        refreshJobs(modal);
      })
      .catch((e) => { btn.style.pointerEvents = ""; btn.style.opacity = ""; btn.textContent = "Retry"; showError(modal, e.message); });
  }

  function refreshJobs(modal) {
    api("/api/jobs").then((jobs) => renderJobs(modal, jobs)).catch(() => {});
  }

  function formatBytes(n) {
    if (!n) return "0 B";
    const u = ["B", "KB", "MB", "GB", "TB"]; let i = 0;
    while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
    return n.toFixed(1) + " " + u[i];
  }

  function renderJobs(modal, jobs) {
    const root = modal.querySelector(".jn-modal-jobs");
    if (!jobs.length) {
      root.innerHTML = '<div style="color:#8a98a8;font-size:12px;">No downloads yet.</div>';
      return;
    }
    root.innerHTML = jobs.map((j) => {
      const pct = Math.round((j.progress || 0) * 100);
      const detail = j.state === "downloading"
        ? formatBytes(j.bytes_downloaded) + (j.bytes_total ? " / " + formatBytes(j.bytes_total) : "") + " · " + pct + "%"
        : (j.state === "failed" ? (j.error || "failed") : (j.state === "completed" ? formatBytes(j.bytes_downloaded) : j.state));
      return '<div style="background:#1a2027;border:1px solid #2a323d;border-radius:4px;padding:10px;margin-bottom:6px;">' +
        '<div style="display:flex;justify-content:space-between;font-size:13px;"><span>' + escapeHtml(j.title) + '</span><span style="color:#8a98a8;">' + escapeHtml(j.state) + '</span></div>' +
        '<div style="height:4px;background:#0a0d10;border-radius:2px;margin:6px 0;overflow:hidden;"><div style="height:100%;width:' + pct + '%;background:#00a4dc;"></div></div>' +
        '<div style="font-size:11px;color:#8a98a8;">' + escapeHtml(detail) + '</div>' +
      '</div>';
    }).join("");
  }

  /* ---------- bootstrap ---------- */

  function tick() {
    try { injectBanner(); } catch (e) { /* DOM not ready, try again */ }
  }

  // Jellyfin web is a SPA — observe DOM + listen for hash changes.
  const observer = new MutationObserver(() => tick());
  function start() {
    observer.observe(document.body, { childList: true, subtree: true });
    window.addEventListener("hashchange", tick);
    tick();
  }

  if (document.body) {
    start();
  } else {
    document.addEventListener("DOMContentLoaded", start);
  }
})();
