/**
 * Manga SMB Suite — Client Application Script
 * Real-time SSE streaming, sequential queue management, dry run modal popup, and report previewer.
 */

// Global State
let evtSource = null;
let currentSelectedScriptId = null;
let isDryRunSelected = true;
let isEngineRunning = false;
let currentActiveJobData = null;
let currentQueueCount = 0;
let selectedDetectionMode = "name_and_hash";

const DUPLICATE_SCRIPT_ID = "manga_folder_duplicates";
const DETECTION_MODE_LABELS = {
  name_and_hash: "Name and Hash",
  visual_similarity: "Visual Similarity",
  exact_hash: "Exact Hash Check",
};

function detectionModeLabel(mode) {
  return DETECTION_MODE_LABELS[mode] || "";
}

function detectionModeBadge(mode) {
  const label = detectionModeLabel(mode);
  if (!label) return "";
  return `<span class="badge badge-secondary" style="margin-left: 6px;">${escapeHtml(label)}</span>`;
}

function selectDetectionMode(mode) {
  selectedDetectionMode = DETECTION_MODE_LABELS[mode] ? mode : "name_and_hash";
  document.querySelectorAll(".detection-mode-card").forEach((card) => {
    card.classList.toggle("selected", card.dataset.mode === selectedDetectionMode);
  });
}

function syncDetectionModeVisibility(scriptId) {
  const section = document.getElementById("detection-mode-section");
  if (!section) return;
  const show = scriptId === DUPLICATE_SCRIPT_ID;
  section.style.display = show ? "block" : "none";
  if (show) selectDetectionMode("name_and_hash");
}

// Toast Notification System
function showToast(message, type = "info") {
  let container = document.getElementById("toast-container");
  if (!container) {
    container = document.createElement("div");
    container.id = "toast-container";
    container.className = "toast-container";
    document.body.appendChild(container);
  }

  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `
    <span>${message}</span>
    <button style="background:none; border:none; color:#94a3b8; cursor:pointer; font-size:16px; margin-left:8px;" onclick="this.parentElement.remove()">&times;</button>
  `;

  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transition = "opacity 0.4s ease";
    setTimeout(() => toast.remove(), 400);
  }, 4500);
}

// SSE Connection & Live Updates
function initSSE() {
  if (evtSource) return;

  evtSource = new EventSource("/api/events");

  evtSource.addEventListener("status", (e) => {
    try {
      const data = JSON.parse(e.data);
      updateGlobalStatus(data);
    } catch (err) {
      console.error("Failed to parse status event", err);
    }
  });

  evtSource.addEventListener("job_started", (e) => {
    try {
      const data = JSON.parse(e.data);
      handleJobStarted(data);
    } catch (err) {
      console.error("Failed to parse job_started event", err);
    }
  });

  evtSource.addEventListener("job_finished", (e) => {
    try {
      const data = JSON.parse(e.data);
      handleJobFinished(data);
    } catch (err) {
      console.error("Failed to parse job_finished event", err);
    }
  });

  evtSource.addEventListener("log", (e) => {
    try {
      const data = JSON.parse(e.data);
      appendLogLine(data);
    } catch (err) {
      console.error("Failed to parse log event", err);
    }
  });

  evtSource.addEventListener("queue_updated", (e) => {
    try {
      const data = JSON.parse(e.data);
      handleQueueUpdated(data);
    } catch (err) {
      console.error("Failed to parse queue_updated event", err);
    }
  });

  evtSource.onerror = (err) => {
    console.warn("SSE connection interrupted, retrying in 3s...", err);
  };
}

function updateGlobalStatus(data) {
  const isRunning = Boolean(data.is_running);
  const activeJob = data.active_run || (data.active_job ? data.active_job : null);
  
  let queueCount = null;
  if (data.queue_count !== undefined) {
    queueCount = data.queue_count;
  } else if (data.queued_runs !== undefined && Array.isArray(data.queued_runs)) {
    queueCount = data.queued_runs.length;
  }

  isEngineRunning = isRunning;
  currentActiveJobData = activeJob;
  currentQueueCount = queueCount !== null ? queueCount : 0;

  // Update scripts page banner if present
  const scriptsBanner = document.getElementById("scripts-active-banner");
  const scriptsActiveName = document.getElementById("scripts-active-job-name");
  const scriptsQueueCount = document.getElementById("scripts-queue-count");
  if (scriptsBanner) {
    scriptsBanner.style.display = (isRunning && activeJob) ? "block" : "none";
  }
  if (scriptsActiveName && activeJob) {
    scriptsActiveName.textContent = activeJob.script_name;
  }
  if (scriptsQueueCount) {
    scriptsQueueCount.textContent = currentQueueCount;
  }

  // If dry-run-modal is open, refresh its running indicators and buttons
  const modal = document.getElementById("dry-run-modal");
  if (modal && modal.classList.contains("active")) {
    const activeNotice = document.getElementById("modal-active-job-notice");
    const activeJobNameEl = document.getElementById("modal-active-job-name");
    const queueTargetPosEl = document.getElementById("modal-queue-target-pos");
    if (activeNotice) activeNotice.style.display = (isRunning && activeJob) ? "block" : "none";
    if (activeJobNameEl && activeJob) activeJobNameEl.textContent = activeJob.script_name;
    if (queueTargetPosEl) queueTargetPosEl.textContent = `#${currentQueueCount + 1}`;
    updateModalButtons();
  }

  const dot = document.getElementById("global-status-dot");
  const text = document.getElementById("global-status-text");
  const cancelBtn = document.getElementById("btn-cancel-active");

  if (dot) {
    dot.className = isRunning ? "pulse-dot syncing" : "pulse-dot";
  }

  if (text) {
    if (isRunning && activeJob) {
      const dryTag = activeJob.dry_run ? " [Dry Run]" : "";
      const qTag = (queueCount !== null && queueCount > 0) ? ` (Queued: ${queueCount})` : "";
      text.textContent = `Running: ${activeJob.script_name}${dryTag}${qTag}`;
    } else if (queueCount !== null && queueCount > 0) {
      text.textContent = `Idle (Queued: ${queueCount})`;
    } else if (!isRunning) {
      text.textContent = "Engine Idle";
    }
  }

  if (cancelBtn) {
    cancelBtn.style.display = isRunning ? "inline-flex" : "none";
  }

  // Update active page elements if currently viewing /active
  updateActivePageUI(isRunning, activeJob, data.queued_runs);
}

function handleJobStarted(data) {
  showToast(`Started: ${data.job.script_name}${data.job.dry_run ? " (Dry Run)" : ""}`, "info");
  updateGlobalStatus({ is_running: true, active_job: data.job });
  
  // Clear live console on new job start
  const terminal = document.getElementById("live-terminal");
  if (terminal) {
    terminal.innerHTML = "";
  }

  // Sync queue state immediately
  handleQueueUpdated();
}

function handleJobFinished(data) {
  const type = data.status === "completed" ? "success" : (data.status === "cancelled" ? "warning" : "error");
  showToast(`Job ${data.status.toUpperCase()} in ${data.duration_seconds.toFixed(1)}s`, type);
  
  // Refresh queue status
  handleQueueUpdated();
}

function appendLogLine(data) {
  const terminal = document.getElementById("live-terminal");
  if (!terminal) return;

  const lineEl = document.createElement("div");
  lineEl.className = "log-entry";
  
  const text = data.line || "";
  if (text.includes("Error") || text.includes("CRITICAL") || text.includes("FAILED")) {
    lineEl.style.color = "#f87171";
  } else if (text.includes("Success") || text.includes("passed") || text.includes("Saved")) {
    lineEl.style.color = "#34d399";
  } else if (text.includes("DRY RUN") || text.includes("Would")) {
    lineEl.style.color = "#fbbf24";
  } else if (text.includes("===") || text.includes("---")) {
    lineEl.style.color = "#818cf8";
    lineEl.style.fontWeight = "600";
  }

  lineEl.textContent = text;
  terminal.appendChild(lineEl);

  // Auto-scroll terminal to bottom
  terminal.scrollTop = terminal.scrollHeight;
}

function handleQueueUpdated(data) {
  fetch("/api/queue/status")
    .then((r) => r.json())
    .then((status) => updateGlobalStatus(status))
    .catch((err) => console.error("Failed to fetch queue", err));
}

function updateActivePageUI(isRunning, activeJob, queuedRuns) {
  const activeTitle = document.getElementById("active-job-title");
  const activeBadge = document.getElementById("active-job-badge");
  const activeCategory = document.getElementById("active-job-category");
  const queueTableBody = document.getElementById("queue-table-body");
  const queueCountEl = document.getElementById("queue-count-display");

  if (activeTitle) {
    if (isRunning && activeJob) {
      activeTitle.textContent = activeJob.script_name;
      if (activeBadge) {
        activeBadge.className = activeJob.dry_run ? "badge badge-warning" : "badge badge-primary";
        activeBadge.textContent = activeJob.dry_run ? "DRY RUN ACTIVE" : "LIVE RUN ACTIVE";
      }
      if (activeCategory) {
        activeCategory.textContent = activeJob.category;
      }
      const detectionEl = document.getElementById("active-job-detection");
      const detectionLabel = detectionModeLabel(activeJob.detection_mode);
      if (detectionEl) {
        detectionEl.style.display = detectionLabel ? "block" : "none";
        detectionEl.innerHTML = detectionLabel
          ? `<span class="badge badge-secondary">${escapeHtml(detectionLabel)}</span>`
          : "";
      }
    } else {
      activeTitle.textContent = "No Job Currently Running";
      if (activeBadge) {
        activeBadge.className = "badge badge-secondary";
        activeBadge.textContent = "IDLE";
      }
      if (activeCategory) {
        activeCategory.textContent = "Queue engine is standing by";
      }
      const detectionEl = document.getElementById("active-job-detection");
      if (detectionEl) {
        detectionEl.style.display = "none";
        detectionEl.innerHTML = "";
      }
    }
  }

  if (queueCountEl && queuedRuns !== undefined) {
    queueCountEl.textContent = queuedRuns.length;
  }

  if (queueTableBody && queuedRuns !== undefined) {
    const hasActive = isRunning && activeJob;
    const hasQueued = queuedRuns && queuedRuns.length > 0;

    if (!hasActive && !hasQueued) {
      queueTableBody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-muted); padding: 24px;">Queue is empty. Select scripts from the Scripts catalog to add.</td></tr>`;
      return;
    }

    let rowsHtml = "";

    // 1. Show currently active job at the top of the queue table with a distinct "ACTIVE NOW" indicator
    if (hasActive) {
      rowsHtml += `
        <tr class="queue-row queue-row-active" style="background: rgba(99, 102, 241, 0.08); border-left: 3px solid var(--accent-primary);">
          <td style="width: 48px; text-align: center;">
            <div class="pulse-dot syncing" style="display: inline-block;" title="Currently Executing"></div>
          </td>
          <td>
            <div style="font-weight: 600; color: #fff;">${escapeHtml(activeJob.script_name)}${detectionModeBadge(activeJob.detection_mode)}</div>
            <div style="font-size: 0.8rem; color: var(--accent-secondary); font-weight: 600;">${escapeHtml(activeJob.category || '')} &bull; <span style="color: var(--accent-primary);">ACTIVE NOW</span></div>
          </td>
          <td>
            <span class="badge ${activeJob.dry_run ? 'badge-warning' : 'badge-primary'}">
              ${activeJob.dry_run ? 'Dry Run' : 'Live'}
            </span>
          </td>
          <td style="font-size: 0.85rem; color: var(--text-secondary);">
            ${activeJob.started_at ? activeJob.started_at.replace('T', ' ').slice(0, 19) : 'In Progress'}
          </td>
          <td style="text-align: right;">
            <button class="btn btn-danger btn-sm" onclick="cancelActiveJob()" title="Cancel Active Job">Cancel</button>
          </td>
        </tr>
      `;
    }

    // 2. Show all pending queued jobs
    if (hasQueued) {
      rowsHtml += queuedRuns.map((job, idx) => `
        <tr class="queue-row">
          <td style="font-weight: 700; color: var(--accent-primary); width: 48px;">#${idx + 1}</td>
          <td>
            <div style="font-weight: 600; color: #fff;">${escapeHtml(job.script_name)}${detectionModeBadge(job.detection_mode)}</div>
            <div style="font-size: 0.8rem; color: var(--text-muted);">${escapeHtml(job.category || '')} &bull; <span style="color: var(--text-secondary);">Queued</span></div>
          </td>
          <td>
            <span class="badge ${job.dry_run ? 'badge-warning' : 'badge-primary'}">
              ${job.dry_run ? 'Dry Run' : 'Live'}
            </span>
          </td>
          <td style="font-size: 0.85rem; color: var(--text-secondary);">${job.enqueued_at ? job.enqueued_at.replace('T', ' ').slice(0, 19) : '-'}</td>
          <td style="text-align: right;">
            <div style="display: inline-flex; gap: 4px;">
              <button class="btn btn-secondary btn-sm" onclick="reorderQueue('${job.run_id}', 'up')" title="Move Up" ${idx === 0 ? 'disabled' : ''}>↑</button>
              <button class="btn btn-secondary btn-sm" onclick="reorderQueue('${job.run_id}', 'down')" title="Move Down" ${idx === queuedRuns.length - 1 ? 'disabled' : ''}>↓</button>
              <button class="btn btn-danger btn-sm" onclick="removeFromQueue('${job.run_id}')" title="Remove">&times;</button>
            </div>
          </td>
        </tr>
      `).join("");
    }

    queueTableBody.innerHTML = rowsHtml;
  }
}

// Dry Run Confirmation Modal
function updateModalButtons() {
  const submitBtn = document.getElementById("modal-confirm-btn");
  const addQueueBtn = document.getElementById("modal-add-queue-btn");
  const queueChk = document.getElementById("modal-queue-if-running-chk");
  const queueIfRunning = queueChk ? queueChk.checked : true;
  const noQueueWarning = document.getElementById("modal-no-queue-warning");

  if (isEngineRunning && currentActiveJobData) {
    if (queueIfRunning) {
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.textContent = isDryRunSelected ? "Queue as Dry Run (Next in Line)" : "Queue Live Run (Next in Line)";
        submitBtn.className = isDryRunSelected ? "btn btn-secondary" : "btn btn-primary";
      }
      if (addQueueBtn) {
        addQueueBtn.disabled = false;
        addQueueBtn.textContent = "Add to Queue";
      }
      if (noQueueWarning) noQueueWarning.style.display = "none";
    } else {
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = "Active Job Running (Parallel Disabled)";
        submitBtn.className = "btn btn-secondary disabled";
      }
      if (addQueueBtn) {
        addQueueBtn.disabled = true;
      }
      if (noQueueWarning) noQueueWarning.style.display = "block";
    }
  } else {
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.textContent = isDryRunSelected ? "Run as Dry Run" : "Run Live (Execute)";
      submitBtn.className = isDryRunSelected ? "btn btn-secondary" : "btn btn-primary";
    }
    if (addQueueBtn) {
      addQueueBtn.disabled = false;
      addQueueBtn.textContent = "Add to Queue";
    }
    if (noQueueWarning) noQueueWarning.style.display = "none";
  }
}

function toggleQueueOption(checked) {
  updateModalButtons();
}

async function openDryRunModal(scriptId, scriptName, category, supportsDryRun = true) {
  currentSelectedScriptId = scriptId;
  isDryRunSelected = supportsDryRun; // Default to Dry Run if supported for safety

  const modal = document.getElementById("dry-run-modal");
  const modalTitle = document.getElementById("modal-script-title");
  const modalCategory = document.getElementById("modal-script-category");
  const reportOnlyNotice = document.getElementById("modal-report-only-notice");
  const activeNotice = document.getElementById("modal-active-job-notice");
  const activeJobNameEl = document.getElementById("modal-active-job-name");
  const queueTargetPosEl = document.getElementById("modal-queue-target-pos");
  const queueChk = document.getElementById("modal-queue-if-running-chk");
  const noQueueWarning = document.getElementById("modal-no-queue-warning");

  if (modalTitle) modalTitle.textContent = scriptName;
  if (modalCategory) modalCategory.textContent = category;
  syncDetectionModeVisibility(scriptId);

  if (reportOnlyNotice) {
    reportOnlyNotice.style.display = supportsDryRun ? "none" : "block";
  }

  // Reset queue checkbox to checked by default (auto-queue sequentially without parallel execution)
  if (queueChk) queueChk.checked = true;
  if (noQueueWarning) noQueueWarning.style.display = "none";

  // Fetch latest status to ensure fresh active job detection
  try {
    const res = await fetch("/api/queue/status");
    if (res.ok) {
      const qStatus = await res.json();
      isEngineRunning = Boolean(qStatus.is_running);
      currentActiveJobData = qStatus.active_run || null;
      currentQueueCount = qStatus.queue_count || 0;
    }
  } catch (e) {
    console.warn("Could not fetch latest queue status", e);
  }

  if (isEngineRunning && currentActiveJobData) {
    if (activeNotice) activeNotice.style.display = "block";
    if (activeJobNameEl) activeJobNameEl.textContent = currentActiveJobData.script_name || "Active Job";
    if (queueTargetPosEl) queueTargetPosEl.textContent = `#${currentQueueCount + 1}`;
  } else {
    if (activeNotice) activeNotice.style.display = "none";
  }

  selectExecutionMode(isDryRunSelected);

  if (modal) {
    modal.classList.add("active");
  }
}

function closeDryRunModal() {
  const modal = document.getElementById("dry-run-modal");
  if (modal) modal.classList.remove("active");
  currentSelectedScriptId = null;
}

function selectExecutionMode(isDryRun) {
  isDryRunSelected = isDryRun;
  const dryCard = document.getElementById("mode-card-dry");
  const liveCard = document.getElementById("mode-card-live");

  if (dryCard) {
    if (isDryRun) {
      dryCard.classList.add("selected");
    } else {
      dryCard.classList.remove("selected");
    }
  }

  if (liveCard) {
    if (!isDryRun) {
      liveCard.classList.add("selected");
    } else {
      liveCard.classList.remove("selected");
    }
  }

  updateModalButtons();
}

async function confirmAndEnqueue(redirectActive = true) {
  if (!currentSelectedScriptId) return;

  const queueChk = document.getElementById("modal-queue-if-running-chk");
  const queueIfRunning = queueChk ? queueChk.checked : true;

  if (isEngineRunning && currentActiveJobData && !queueIfRunning) {
    showToast("Cannot execute immediately: parallel execution is disabled. Enable 'Queue this job' to run sequentially.", "warning");
    return;
  }

  try {
    const res = await fetch("/api/queue/enqueue", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        script_id: currentSelectedScriptId,
        dry_run: isDryRunSelected,
        queue_if_running: queueIfRunning,
        detection_mode: currentSelectedScriptId === DUPLICATE_SCRIPT_ID ? selectedDetectionMode : null,
      }),
    });

    const data = await res.json();
    if (res.status === 409) {
      showToast(data.detail || "Job cannot run immediately while another is active. Please queue it.", "warning");
      return;
    }
    if (!res.ok) throw new Error(data.detail || "Failed to enqueue");

    if (data.will_wait_in_queue || data.active_job_running) {
      showToast(data.message || `Added to queue (#${data.position}): ${data.script_name}`, "info");
    } else {
      showToast(`Started: ${data.script_name} (${data.dry_run ? "Dry Run" : "Live"})`, "success");
    }
    closeDryRunModal();

    if (redirectActive) {
      window.location.href = "/active";
    }
  } catch (err) {
    showToast(`Error: ${err.message}`, "error");
  }
}

// Queue Actions
async function cancelActiveJob() {
  if (!confirm("Are you sure you want to cancel the currently executing job?")) return;
  try {
    const res = await fetch("/api/queue/cancel-active", { method: "POST" });
    const data = await res.json();
    if (data.status === "success") {
      showToast("Cancellation signal sent.", "warning");
    } else {
      showToast(data.message || "Failed to cancel", "info");
    }
  } catch (err) {
    showToast(`Error: ${err.message}`, "error");
  }
}

async function removeFromQueue(runId) {
  try {
    const res = await fetch(`/api/queue/remove/${runId}`, { method: "DELETE" });
    if (res.ok) {
      showToast("Removed job from queue", "info");
      handleQueueUpdated();
    }
  } catch (err) {
    showToast(`Error: ${err.message}`, "error");
  }
}

async function reorderQueue(runId, direction) {
  try {
    const res = await fetch(`/api/queue/reorder/${runId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ direction }),
    });
    if (res.ok) {
      handleQueueUpdated();
    }
  } catch (err) {
    showToast(`Error: ${err.message}`, "error");
  }
}

async function clearQueue() {
  if (!confirm("Are you sure you want to clear all queued jobs?")) return;
  try {
    const res = await fetch("/api/queue/clear", { method: "DELETE" });
    const data = await res.json();
    showToast(`Cleared ${data.cleared_count} queued jobs`, "info");
    handleQueueUpdated();
  } catch (err) {
    showToast(`Error: ${err.message}`, "error");
  }
}

async function enqueueAllScripts(dryRun = true) {
  let confirmMsg = dryRun
    ? "Enqueue all 14 scripts in Dry Run mode?"
    : "WARNING: Enqueue all 14 scripts in LIVE mode? File modifications and deletions will occur.";

  if (isEngineRunning && currentActiveJobData) {
    confirmMsg = `Active job currently running: '${currentActiveJobData.script_name}'.\n\nTo prevent file corruption and SMB share saturation, scripts do NOT run in parallel.\n\nAll 14 scripts will be added to the queue to execute strictly sequentially 1-by-1 after the active job finishes.\n\nProceed to queue all scripts (${dryRun ? 'Dry Run' : 'Live'})?`;
  }
  if (!confirm(confirmMsg)) return;

  try {
    const resScripts = await fetch("/api/scripts");
    const scriptsData = await resScripts.json();
    const allIds = scriptsData.scripts.map((s) => s.id);

    const res = await fetch("/api/queue/enqueue-batch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        script_ids: allIds,
        dry_run: dryRun,
        queue_if_running: true,
      }),
    });

    const data = await res.json();
    showToast(data.message || `Enqueued ${data.enqueued_count} scripts (${dryRun ? 'Dry Run' : 'Live'})`, "success");
    window.location.href = "/active";
  } catch (err) {
    showToast(`Error: ${err.message}`, "error");
  }
}

// Report Viewer Modal
async function openReportPreview(filename) {
  const modal = document.getElementById("report-modal");
  const modalTitle = document.getElementById("report-modal-title");
  const modalBody = document.getElementById("report-modal-body");
  const downloadBtn = document.getElementById("report-modal-download-btn");

  if (!modal || !modalBody) return;

  modalTitle.textContent = `Report: ${filename}`;
  if (downloadBtn) {
    downloadBtn.href = `/api/reports/${encodeURIComponent(filename)}/download`;
  }
  modalBody.innerHTML = `<div style="text-align:center; padding: 40px; color: var(--text-muted);"><div class="pulse-dot" style="margin: 0 auto 12px auto;"></div>Loading preview...</div>`;
  modal.classList.add("active");

  try {
    const res = await fetch(`/api/reports/${encodeURIComponent(filename)}/preview`);
    if (!res.ok) throw new Error("Could not load report preview.");
    const data = await res.json();

    if (data.type === "text" || data.type === "csv") {
      modalBody.innerHTML = `
        <div class="terminal-box" style="max-height: 520px; font-size: 0.82rem; white-space: pre-wrap;">${escapeHtml(data.content || JSON.stringify(data.rows, null, 2))}</div>
      `;
    } else if (data.type === "excel") {
      renderExcelSheets(data.sheets, modalBody);
    }
  } catch (err) {
    modalBody.innerHTML = `<div class="badge badge-danger" style="padding: 12px; display: block; text-align: center;">Error loading preview: ${err.message}</div>`;
  }
}

function renderExcelSheets(sheets, container) {
  if (!sheets || sheets.length === 0) {
    container.innerHTML = `<div style="color: var(--text-muted); padding: 20px;">No worksheets found in this workbook.</div>`;
    return;
  }

  let html = `<div class="excel-tabs">`;
  sheets.forEach((sh, idx) => {
    html += `<button class="excel-tab-btn ${idx === 0 ? 'active' : ''}" onclick="switchExcelSheet(${idx})">${escapeHtml(sh.sheet_name)} (${sh.rows.length} rows)</button>`;
  });
  html += `</div>`;

  sheets.forEach((sh, idx) => {
    html += `
      <div class="excel-sheet-pane" id="sheet-pane-${idx}" style="display: ${idx === 0 ? 'block' : 'none'};">
        <div class="preview-table-container">
          <table class="preview-table">
            <thead>
              <tr>${sh.columns.map(c => `<th>${escapeHtml(c)}</th>`).join("")}</tr>
            </thead>
            <tbody>
              ${sh.rows.length === 0 ? '<tr><td colspan="' + sh.columns.length + '" style="text-align:center; color: var(--text-muted); padding: 16px;">Empty sheet</td></tr>' : ''}
              ${sh.rows.map(row => `<tr>${row.map(cell => `<td>${escapeHtml(cell)}</td>`).join("")}</tr>`).join("")}
            </tbody>
          </table>
        </div>
      </div>
    `;
  });

  container.innerHTML = html;
}

function switchExcelSheet(sheetIndex) {
  document.querySelectorAll(".excel-tab-btn").forEach((btn, idx) => {
    if (idx === sheetIndex) btn.classList.add("active");
    else btn.classList.remove("active");
  });
  document.querySelectorAll(".excel-sheet-pane").forEach((pane, idx) => {
    pane.style.display = idx === sheetIndex ? "block" : "none";
  });
}

function closeReportModal() {
  const modal = document.getElementById("report-modal");
  if (modal) modal.classList.remove("active");
}

// Log Viewer Modal
async function openLogModal(runId) {
  const modal = document.getElementById("report-modal");
  const modalTitle = document.getElementById("report-modal-title");
  const modalBody = document.getElementById("report-modal-body");
  const downloadBtn = document.getElementById("report-modal-download-btn");

  if (!modal || !modalBody) return;

  modalTitle.textContent = `Execution Log: ${runId.slice(0, 8)}`;
  if (downloadBtn) {
    downloadBtn.href = `/api/runs/${runId}/logs`;
  }
  modalBody.innerHTML = `<div style="text-align:center; padding: 40px; color: var(--text-muted);">Loading log...</div>`;
  modal.classList.add("active");

  try {
    const res = await fetch(`/api/runs/${runId}/logs`);
    const text = await res.text();
    modalBody.innerHTML = `
      <div class="terminal-box" style="max-height: 520px; font-size: 0.82rem; white-space: pre-wrap;">${escapeHtml(text)}</div>
    `;
  } catch (err) {
    modalBody.innerHTML = `<div style="color: var(--status-danger);">Failed to load log: ${err.message}</div>`;
  }
}

// Confirm Dialog Modal (in-app, cannot be blocked by iframes / CasaOS)
function showConfirmDialog(title, message, confirmBtnText, onConfirm) {
  const modal = document.getElementById("confirm-modal");
  const titleEl = document.getElementById("confirm-modal-title");
  const msgEl = document.getElementById("confirm-modal-message");
  const actBtn = document.getElementById("confirm-modal-action-btn");

  if (modal && titleEl && msgEl && actBtn) {
    titleEl.textContent = title || "Confirm Action";
    msgEl.innerHTML = message || "Are you sure you want to proceed?";
    actBtn.textContent = confirmBtnText || "Confirm";
    actBtn.onclick = async () => {
      closeConfirmModal();
      if (typeof onConfirm === "function") {
        try {
          await onConfirm();
        } catch (err) {
          console.error("Action error:", err);
          showToast(`Error: ${err.message}`, "error");
        }
      }
    };
    modal.classList.add("active");
  } else {
    // Fallback if modal DOM element is not present
    const plainText = message ? message.replace(/<[^>]+>/g, '') : "Are you sure?";
    if (window.confirm(plainText)) {
      if (typeof onConfirm === "function") {
        onConfirm();
      }
    }
  }
}

function closeConfirmModal() {
  const modal = document.getElementById("confirm-modal");
  if (modal) modal.classList.remove("active");
}

// Run History Management
async function deleteRunRecord(runId, redirectToList = false, scriptName = "") {
  if (!runId) return;

  // Retrieve script name if not explicitly passed
  if (!scriptName) {
    const row = document.getElementById(`run-row-${runId}`);
    if (row) {
      const btn = row.querySelector(".btn-delete-run");
      if (btn && btn.getAttribute("data-script-name")) {
        scriptName = btn.getAttribute("data-script-name");
      } else {
        const titleEl = row.querySelector(".run-script-name, strong, div");
        if (titleEl) scriptName = titleEl.textContent.trim();
      }
    }
  }

  const nameHtml = scriptName ? `<strong>${escapeHtml(scriptName)}</strong> ` : "";
  const msg = `Are you sure you want to remove ${nameHtml}(<span style="font-family: var(--font-mono);">${runId.slice(0, 8)}</span>) from history?`;

  showConfirmDialog("Delete Run Record", msg, "Delete Run", async () => {
    try {
      const res = await fetch(`/api/runs/${runId}`, {
        method: "DELETE",
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Failed to remove run from history");
      }

      showToast("Run removed from history.", "info");

      if (redirectToList) {
        window.location.href = "/runs";
      } else {
        const row = document.getElementById(`run-row-${runId}`);
        if (row) {
          row.style.opacity = "0";
          row.style.transition = "opacity 0.25s ease";
          setTimeout(() => {
            row.remove();
            updateSelectedRunsCount();
            const tbody = document.querySelector(".data-table tbody");
            if (tbody && tbody.children.length === 0) {
              window.location.reload();
            }
          }, 250);
        } else {
          window.location.reload();
        }
      }
    } catch (err) {
      showToast(`Error: ${err.message}`, "error");
    }
  });
}

function toggleSelectAllRuns(master) {
  const checkboxes = document.querySelectorAll(".run-select-cb:not([disabled])");
  checkboxes.forEach((cb) => {
    cb.checked = master.checked;
  });
  updateSelectedRunsCount();
}

function updateSelectedRunsCount() {
  const checked = document.querySelectorAll(".run-select-cb:checked");
  const count = checked.length;

  const countEl = document.getElementById("selected-runs-count");
  const countInlineEl = document.getElementById("selected-runs-count-inline");
  const btnDeleteSelected = document.getElementById("btn-delete-selected");
  const btnDeleteSelectedInline = document.getElementById("btn-delete-selected-inline");
  const selectAll = document.getElementById("select-all-runs");
  const allSelectable = document.querySelectorAll(".run-select-cb:not([disabled])");

  if (countEl) countEl.textContent = count;
  if (countInlineEl) countInlineEl.textContent = count;

  const displayStyle = count > 0 ? "inline-flex" : "none";
  if (btnDeleteSelected) btnDeleteSelected.style.display = displayStyle;
  if (btnDeleteSelectedInline) btnDeleteSelectedInline.style.display = displayStyle;

  if (selectAll && allSelectable.length > 0) {
    selectAll.checked = count === allSelectable.length;
    selectAll.indeterminate = count > 0 && count < allSelectable.length;
  }
}

async function deleteSelectedRuns() {
  const checked = Array.from(document.querySelectorAll(".run-select-cb:checked")).map((cb) => cb.value);
  if (checked.length === 0) return;

  const msg = `Are you sure you want to remove <strong>${checked.length}</strong> selected run(s) from history? Associated log files will also be removed.`;

  showConfirmDialog("Delete Selected Runs", msg, `Delete ${checked.length} Runs`, async () => {
    try {
      const res = await fetch("/api/runs/batch-delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ run_ids: checked }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Failed to remove selected runs");
      }

      showToast(`Removed ${data.deleted_count} run(s) from history.`, "info");
      setTimeout(() => {
        window.location.reload();
      }, 350);
    } catch (err) {
      showToast(`Error: ${err.message}`, "error");
    }
  });
}

async function clearHistory(statusFilter = "") {
  const label = statusFilter ? `all <strong>${escapeHtml(statusFilter)}</strong>` : "all completed, failed, and cancelled";
  const msg = `Are you sure you want to remove ${label} runs from history? Active or queued runs will not be deleted.`;

  showConfirmDialog("Clear Run History", msg, "Clear History", async () => {
    try {
      const url = statusFilter ? `/api/runs/clear?status=${encodeURIComponent(statusFilter)}` : "/api/runs/clear";
      const res = await fetch(url, {
        method: "DELETE",
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Failed to clear history");
      }

      showToast(`Cleared ${data.cleared_count} run(s) from history.`, "info");
      setTimeout(() => {
        window.location.reload();
      }, 350);
    } catch (err) {
      showToast(`Error: ${err.message}`, "error");
    }
  });
}

// Global Event Delegation for Delete Buttons
document.addEventListener("click", (e) => {
  const deleteBtn = e.target.closest(".btn-delete-run");
  if (deleteBtn) {
    const runId = deleteBtn.getAttribute("data-run-id");
    const redirect = deleteBtn.getAttribute("data-redirect") === "true";
    const scriptName = deleteBtn.getAttribute("data-script-name") || "";
    if (runId) {
      deleteRunRecord(runId, redirect, scriptName);
    }
  }
});

// Explicit window bindings
window.showConfirmDialog = showConfirmDialog;
window.closeConfirmModal = closeConfirmModal;
window.deleteRunRecord = deleteRunRecord;
window.toggleSelectAllRuns = toggleSelectAllRuns;
window.updateSelectedRunsCount = updateSelectedRunsCount;
window.deleteSelectedRuns = deleteSelectedRuns;
window.clearHistory = clearHistory;

// Sidebar Drawer
function toggleSidebar(open) {
  const sidebar = document.getElementById("sidebar-nav");
  const backdrop = document.getElementById("sidebar-backdrop");
  if (sidebar && backdrop) {
    if (open) {
      sidebar.classList.add("open");
      backdrop.classList.add("open");
      document.body.classList.add("sidebar-open");
    } else {
      sidebar.classList.remove("open");
      backdrop.classList.remove("open");
      document.body.classList.remove("sidebar-open");
    }
  }
}

function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// Init SSE on DOM Load
document.addEventListener("DOMContentLoaded", () => {
  initSSE();
});

