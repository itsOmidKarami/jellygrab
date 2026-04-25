(function () {
  "use strict";

  // API base: assume the page is served by the sidecar itself; otherwise allow override via ?api=...
  const params = new URLSearchParams(location.search);
  const API_BASE = params.get("api") || window.JELLYNAMA_API || location.origin;

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

  function renderResults(hits) {
    if (!hits.length) {
      $results.innerHTML = `<div class="empty">No results.</div>`;
      return;
    }
    $results.innerHTML = "";
    for (const hit of hits) {
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
          <div class="options" data-detail="${encodeURIComponent(hit.detail_url)}" data-title="${encodeURIComponent(hit.title)}">
            <button class="secondary load-options">Load download options</button>
          </div>
        </div>
      `;
      $results.appendChild(card);
    }
    $results.querySelectorAll(".load-options").forEach((btn) => {
      btn.addEventListener("click", (e) => loadOptions(e.currentTarget.parentElement));
    });
  }

  async function loadOptions(container) {
    const detailUrl = decodeURIComponent(container.dataset.detail);
    const title = decodeURIComponent(container.dataset.title);
    container.innerHTML = `<span class="job-detail">Loading…</span>`;
    try {
      const options = await api(`/api/options?detail_url=${encodeURIComponent(detailUrl)}`);
      if (!options.length) {
        container.innerHTML = `<span class="job-detail">No direct links found.</span>`;
        return;
      }
      container.innerHTML = "";
      for (const opt of options) {
        const b = document.createElement("button");
        b.textContent = `${opt.quality}${opt.size ? ` · ${opt.size}` : ""}`;
        b.addEventListener("click", () => startDownload(title, opt.url, b));
        container.appendChild(b);
      }
    } catch (e) {
      container.innerHTML = `<span class="job-detail">Failed: ${escapeHtml(e.message)}</span>`;
    }
  }

  async function startDownload(title, url, btn) {
    btn.disabled = true;
    btn.textContent = "Queued…";
    try {
      await api(`/api/download`, {
        method: "POST",
        body: JSON.stringify({ title, url }),
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

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    })[c]);
  }

  $btn.addEventListener("click", search);
  $q.addEventListener("keydown", (e) => { if (e.key === "Enter") search(); });

  refreshJobs();
  setInterval(refreshJobs, 2000);
})();
