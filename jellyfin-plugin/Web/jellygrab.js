(function () {
  "use strict";

  // API base: assume the page is served by the sidecar itself; otherwise allow override via ?api=...
  const params = new URLSearchParams(location.search);
  const API_BASE = params.get("api") || window.JELLYGRAB_API || location.origin;

  const $q = document.getElementById("q");
  const $btn = document.getElementById("search-btn");
  const $results = document.getElementById("results");
  const $jobs = document.getElementById("jobs");
  const $error = document.getElementById("error");

  const formatBytes = (n) => {
    if (!n) return "0 B";
    const units = ["B", "KB", "MB", "GB", "TB"];
    let i = 0;
    while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
    return `${n.toFixed(1)} ${units[i]}`;
  };

  const showError = (msg) => {
    if (!msg) { $error.hidden = true; return; }
    $error.textContent = msg;
    $error.hidden = false;
  };

  async function api(path, opts = {}) {
    const resp = await fetch(`${API_BASE}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...opts,
    });
    if (!resp.ok) {
      const text = await resp.text().catch(() => "");
      throw new Error(`${resp.status} ${resp.statusText}: ${text}`);
    }
    return resp.json();
  }

  async function search() {
    const query = $q.value.trim();
    if (!query) return;
    showError(null);
    $btn.disabled = true;
    $results.innerHTML = `<div class="empty">Searching…</div>`;
    try {
      const hits = await api(`/api/search?q=${encodeURIComponent(query)}`);
      renderResults(hits);
    } catch (e) {
      showError(`Search failed: ${e.message}`);
      $results.innerHTML = "";
    } finally {
      $btn.disabled = false;
    }
  }

  const PAGE_SIZE = 8;
  let currentHits = [];
  let currentPage = 0;

  function renderResults(hits) {
    currentHits = hits;
    currentPage = 0;
    renderPage();
  }

  function renderPage() {
    removePagination();
    if (!currentHits.length) {
      $results.innerHTML = `<div class="empty">No results.</div>`;
      return;
    }
    const totalPages = Math.max(1, Math.ceil(currentHits.length / PAGE_SIZE));
    if (currentPage >= totalPages) currentPage = totalPages - 1;
    const start = currentPage * PAGE_SIZE;
    const pageHits = currentHits.slice(start, start + PAGE_SIZE);

    $results.innerHTML = "";
    for (const hit of pageHits) {
      const card = document.createElement("div");
      card.className = "card";
      const posterStyle = hit.poster ? `background-image:url('${hit.poster}')` : "";
      card.innerHTML = `
        <div class="poster" style="${posterStyle}"></div>
        <div class="card-body">
          <h3>${escapeHtml(hit.title)}</h3>
          <div class="meta">
            ${hit.year ? `<span>${escapeHtml(hit.year)}</span>` : ""}
            <span class="badge kind">${hit.kind}</span>
            ${hit.in_library ? `<span class="badge in-lib">In library</span>` : ""}
          </div>
          <div class="options" data-detail="${encodeURIComponent(hit.detail_url)}" data-title="${encodeURIComponent(hit.title)}" data-kind="${encodeURIComponent(hit.kind || "")}" data-year="${encodeURIComponent(hit.year || "")}">
            <button class="secondary load-options">Load download options</button>
          </div>
        </div>
      `;
      $results.appendChild(card);
    }
    $results.querySelectorAll(".load-options").forEach((btn) => {
      btn.addEventListener("click", (e) => loadOptions(e.currentTarget.parentElement));
    });
    if (totalPages > 1) renderPagination(totalPages);
  }

  function removePagination() {
    const existing = document.getElementById("pagination");
    if (existing) existing.remove();
  }

  function renderPagination(totalPages) {
    const nav = document.createElement("div");
    nav.id = "pagination";
    nav.className = "pagination";
    const prev = document.createElement("button");
    prev.className = "secondary";
    prev.textContent = "← Prev";
    prev.disabled = currentPage === 0;
    prev.addEventListener("click", () => { currentPage--; renderPage(); });
    const next = document.createElement("button");
    next.className = "secondary";
    next.textContent = "Next →";
    next.disabled = currentPage >= totalPages - 1;
    next.addEventListener("click", () => { currentPage++; renderPage(); });
    const label = document.createElement("span");
    label.className = "pagination-label";
    label.textContent = `Page ${currentPage + 1} of ${totalPages}`;
    nav.append(prev, label, next);
    $results.insertAdjacentElement("afterend", nav);
  }

  async function loadOptions(container) {
    const detailUrl = decodeURIComponent(container.dataset.detail);
    const title = decodeURIComponent(container.dataset.title);
    const kind = decodeURIComponent(container.dataset.kind || "");
    const year = decodeURIComponent(container.dataset.year || "");
    container.innerHTML = `<span class="job-detail">Loading…</span>`;
    try {
      const options = await api(`/api/options?detail_url=${encodeURIComponent(detailUrl)}`);
      if (!options.length) {
        container.innerHTML = `<span class="job-detail">No direct links found.</span>`;
        return;
      }
      container.innerHTML = "";
      const movieOpts = options.filter((o) => !(o.episodes && o.episodes.length));
      const seriesOpts = options.filter((o) => o.episodes && o.episodes.length);

      const wrapper = document.createElement("details");
      wrapper.className = "options-wrapper";
      wrapper.open = true;
      const wrapperSummary = document.createElement("summary");
      wrapperSummary.className = "options-wrapper-header";
      const totalCount = movieOpts.length + seriesOpts.length;
      wrapperSummary.textContent = `Download options · ${totalCount}`;
      wrapper.appendChild(wrapperSummary);
      const wrapperBody = document.createElement("div");
      wrapperBody.className = "options-wrapper-body";
      wrapper.appendChild(wrapperBody);
      container.appendChild(wrapper);

      for (const opt of movieOpts) {
        wrapperBody.appendChild(buildOptionButton(opt, (btn) =>
          startDownload(title, opt.url, btn, kind, year)
        ));
      }

      const seasonGroups = new Map();
      for (const opt of seriesOpts) {
        const key = opt.season || "?";
        if (!seasonGroups.has(key)) seasonGroups.set(key, []);
        seasonGroups.get(key).push(opt);
      }
      const sortedKeys = [...seasonGroups.keys()].sort((a, b) => Number(a) - Number(b));
      for (const key of sortedKeys) {
        const group = document.createElement("details");
        group.className = "season-group";
        const summary = document.createElement("summary");
        summary.className = "season-header";
        const epCount = seasonGroups.get(key)[0].episodes.length;
        const label = key === "?" ? "Season ?" : `Season ${String(key).padStart(2, "0")}`;
        summary.textContent = `${label} · ${epCount} episode${epCount === 1 ? "" : "s"}`;
        group.appendChild(summary);
        const list = document.createElement("div");
        list.className = "season-options";
        for (const opt of seasonGroups.get(key)) {
          list.appendChild(buildOptionButton(opt, (btn) =>
            startSeriesPack(title, year, opt.season, opt.episodes, btn)
          ));
        }
        group.appendChild(list);
        wrapperBody.appendChild(group);
      }
    } catch (e) {
      container.innerHTML = `<span class="job-detail">Failed: ${escapeHtml(e.message)}</span>`;
    }
  }

  async function startSeriesPack(title, year, season, episodes, btn) {
    btn.disabled = true;
    const original = btn.textContent;
    btn.textContent = `Queuing ${episodes.length}…`;
    try {
      const resp = await api(`/api/download/series-pack`, {
        method: "POST",
        body: JSON.stringify({ title, year: year || null, season: season || null, episodes }),
      });
      btn.textContent = `Queued ${resp.job_ids ? resp.job_ids.length : episodes.length} ✓`;
      refreshJobs();
    } catch (e) {
      btn.disabled = false;
      btn.textContent = original;
      showError(`Download failed: ${e.message}`);
    }
  }

  async function startDownload(title, url, btn, kind, year) {
    btn.disabled = true;
    btn.textContent = "Queued…";
    try {
      await api(`/api/download`, {
        method: "POST",
        body: JSON.stringify({ title, url, kind: kind || "unknown", year: year || null }),
      });
      btn.textContent = "Queued ✓";
      refreshJobs();
    } catch (e) {
      btn.disabled = false;
      btn.textContent = "Retry";
      showError(`Download failed: ${e.message}`);
    }
  }

  function renderJobs(jobs) {
    if (!jobs.length) {
      $jobs.innerHTML = `<div class="empty">No downloads yet.</div>`;
      return;
    }
    $jobs.innerHTML = "";
    for (const job of jobs) {
      const pct = Math.round((job.progress || 0) * 100);
      const speed = job.speed_bps ? `${formatBytes(job.speed_bps)}/s` : "";
      const total = job.bytes_total ? ` / ${formatBytes(job.bytes_total)}` : "";
      const detail = job.state === "downloading"
        ? `${formatBytes(job.bytes_downloaded)}${total} · ${pct}%${speed ? " · " + speed : ""}`
        : job.state === "failed" ? (job.error || "failed")
        : job.state === "completed" ? formatBytes(job.bytes_downloaded)
        : job.state;
      const row = document.createElement("div");
      row.className = "job";
      row.innerHTML = `
        <div class="job-head">
          <span class="job-title">${escapeHtml(job.title)}</span>
          <span class="job-state ${job.state}">${job.state}</span>
        </div>
        <div class="progress-bar"><div class="progress-fill" style="width:${pct}%"></div></div>
        <div class="job-detail">${escapeHtml(detail)}</div>
      `;
      $jobs.appendChild(row);
    }
  }

  async function refreshJobs() {
    try {
      const jobs = await api(`/api/jobs`);
      renderJobs(jobs);
    } catch (e) {
      // silent: jobs panel just won't update
    }
  }

  function buildOptionButton(opt, onClick) {
    const b = document.createElement("button");
    b.className = "option-btn";
    const line1 = [opt.quality, opt.size].filter(Boolean).join(" · ");
    const tags = (opt.tags || []).join(", ");
    const line2 = [opt.encoder, tags].filter(Boolean).join(" | ");
    b.innerHTML = `<span class="opt-primary">${escapeHtml(line1)}</span>` +
      (line2 ? `<span class="opt-meta">${escapeHtml(line2)}</span>` : "");
    b.addEventListener("click", () => onClick(b));
    return b;
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    })[c]);
  }

  $btn.addEventListener("click", search);
  $q.addEventListener("keydown", (e) => { if (e.key === "Enter") search(); });

  const $clear = document.getElementById("clear-jobs");
  if ($clear) {
    $clear.addEventListener("click", async () => {
      $clear.disabled = true;
      try {
        await api(`/api/jobs/clear`, { method: "POST" });
        refreshJobs();
      } catch (e) {
        showError(`Clear failed: ${e.message}`);
      } finally {
        $clear.disabled = false;
      }
    });
  }

  refreshJobs();
  setInterval(refreshJobs, 2000);
})();
