/**
 * PALIMPSEST — Main Frontend JavaScript Controller
 * Handles REST API calls, UI reactivity, modals, and notifications.
 */

// Global State
const PALIMPSEST = {
  activeProjectId: null,
  activeProject: null,
};

// Initialize on DOM load
document.addEventListener("DOMContentLoaded", () => {
  const urlParams = new URLSearchParams(window.location.search);
  const projParam = urlParams.get("project_id");

  const projectSelect = document.getElementById("globalProjectSelect");
  if (projectSelect) {
    if (projParam) {
      projectSelect.value = projParam;
    }
    PALIMPSEST.activeProjectId = projectSelect.value;
    projectSelect.addEventListener("change", (e) => {
      const selectedId = e.target.value;
      const currentUrl = new URL(window.location.href);
      currentUrl.searchParams.set("project_id", selectedId);
      window.location.href = currentUrl.toString();
    });
  }

  // Bind New Project Form
  const newProjectForm = document.getElementById("newProjectForm");
  if (newProjectForm) {
    newProjectForm.addEventListener("submit", handleCreateProject);
  }
});

// Toast / Notification helper
function showToast(message, type = "info") {
  const container = document.getElementById("toastContainer");
  if (!container) return;

  const bgClass = type === "success" ? "bg-success" : (type === "error" ? "bg-danger" : "bg-primary");
  const toastHtml = `
    <div class="toast align-items-center text-white ${bgClass} border-0 show" role="alert" aria-live="assertive" aria-atomic="true">
      <div class="d-flex">
        <div class="toast-body">${message}</div>
        <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
      </div>
    </div>
  `;
  const el = document.createElement("div");
  el.innerHTML = toastHtml;
  const toastEl = el.firstElementChild;
  container.appendChild(toastEl);
  setTimeout(() => toastEl.remove(), 4000);
}

// API Helper
async function apiCall(endpoint, method = "GET", body = null) {
  const options = {
    method,
    headers: {
      "Content-Type": "application/json",
    },
  };
  if (body) {
    options.body = JSON.stringify(body);
  }
  try {
    const res = await fetch(endpoint, options);
    const data = await res.json();
    return data;
  } catch (err) {
    console.error("API Call failed:", err);
    return { success: false, error: err.message };
  }
}

// Handle New Project Creation
async function handleCreateProject(e) {
  e.preventDefault();
  const name = document.getElementById("projectNameInput").value.trim();
  const description = document.getElementById("projectDescInput").value.trim();
  const objective = document.getElementById("projectObjectiveInput").value.trim();
  const token_budget = parseInt(document.getElementById("projectBudgetInput").value) || 2048;

  if (!name) {
    showToast("Project name is required", "error");
    return;
  }

  const res = await apiCall("/api/projects", "POST", { name, description, objective, token_budget });
  if (res.success) {
    showToast("Project created successfully!", "success");
    const modalEl = document.getElementById("newProjectModal");
    if (modalEl) {
      const modal = bootstrap.Modal.getInstance(modalEl);
      if (modal) modal.hide();
    }
    window.location.search = `?project_id=${res.project.id}`;
  } else {
    showToast(res.error || "Failed to create project", "error");
  }
}

// Copy to Clipboard Helper
function copyTextToClipboard(textId) {
  const textEl = document.getElementById(textId);
  if (!textEl) return;
  const content = textEl.innerText || textEl.value;
  navigator.clipboard.writeText(content).then(() => {
    showToast("Copied to clipboard!", "success");
  });
}
