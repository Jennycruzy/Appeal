import { initializeApp } from "https://www.gstatic.com/firebasejs/10.14.1/firebase-app.js";
import {
  getAuth,
  getIdTokenResult,
  onAuthStateChanged,
  signInWithEmailAndPassword,
  signOut
} from "https://www.gstatic.com/firebasejs/10.14.1/firebase-auth.js";

const firebaseApp = initializeApp(window.APPEAL_FIREBASE_CONFIG);
const auth = getAuth(firebaseApp);
const apiBase = window.APPEAL_API_BASE.replace(/\/$/, "");

const authCard = document.querySelector("#auth-card");
const appShell = document.querySelector("#app-shell");
const signInForm = document.querySelector("#sign-in-form");
const authMessage = document.querySelector("#auth-message");
const runtimeMessage = document.querySelector("#runtime-message");
const userEmail = document.querySelector("#user-email");
const tenantIdElement = document.querySelector("#tenant-id");
const caseList = document.querySelector("#case-list");
const caseDetail = document.querySelector("#case-detail");
const caseCount = document.querySelector("#case-count");

let tenantId = "";
let cases = [];
let selectedCaseId = "";

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function setMessage(element, message, kind = "") {
  element.textContent = message;
  element.className = `message ${kind}`.trim();
}

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  const user = auth.currentUser;
  if (user) {
    headers.set("Authorization", `Bearer ${await user.getIdToken()}`);
  }
  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`${apiBase}${path}`, { ...options, headers });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(`${response.status}: ${body.error || "request failed"}`);
  }
  return body;
}

function caseIdFor(view) {
  return view?.case?.case_id || view?.case_id || "unknown-case";
}

function stateFor(view) {
  return view?.case_state || view?.case?.state || "UNKNOWN";
}

function stateClass(state) {
  return `state-${String(state).toLowerCase().replaceAll("_", "-")}`;
}

function renderBoard() {
  caseCount.textContent = String(cases.length);
  if (!cases.length) {
    caseList.innerHTML = '<p class="muted">No cases yet. Load the evaluation case set to exercise the operating paths.</p>';
    caseDetail.innerHTML = '<div class="empty-state"><p class="eyebrow">Case detail</p><h2>No cases</h2><p class="muted">Load the governed evaluation cases into this tenant-scoped board.</p></div>';
    return;
  }
  caseList.innerHTML = cases.map((view) => {
    const id = caseIdFor(view);
    const state = stateFor(view);
    const active = id === selectedCaseId ? " active" : "";
    return `<button class="case-row${active}" data-case-id="${escapeHtml(id)}">
      <span class="case-row-title">${escapeHtml(id)}</span>
      <span class="pill ${stateClass(state)}">${escapeHtml(state)}</span>
    </button>`;
  }).join("");
  caseList.querySelectorAll("[data-case-id]").forEach((button) => {
    button.addEventListener("click", () => {
      selectedCaseId = button.dataset.caseId;
      renderBoard();
    });
  });
  if (!cases.some((view) => caseIdFor(view) === selectedCaseId)) {
    selectedCaseId = caseIdFor(cases[0]);
  }
  renderDetail();
}

function renderDetail() {
  const view = cases.find((candidate) => caseIdFor(candidate) === selectedCaseId);
  if (!view) return;
  const state = stateFor(view);
  const id = caseIdFor(view);
  const transitions = view.case?.transitions || [];
  const events = view.events || [];
  const payerDecision = view.payer_decision?.decision || "—";
  const actionButtons = [];
  if (state === "AWAITING_CLINICIAN") {
    actionButtons.push('<button id="approve-button" class="primary">Approve submission</button>');
    actionButtons.push('<button id="mobile-link-button" class="secondary">Create mobile approval link</button>');
  }
  if (state === "AWAITING_DETERMINATION") {
    actionButtons.push('<button id="adjudicate-button" class="primary">Receive payer determination</button>');
  }
  caseDetail.innerHTML = `<div class="detail-heading">
    <div><p class="eyebrow">Tenant-scoped case</p><h2>${escapeHtml(id)}</h2></div>
    <span class="pill ${stateClass(state)}">${escapeHtml(state)}</span>
  </div>
  <div class="metric-grid">
    <div class="metric"><span>Outcome</span><strong>${escapeHtml(view.outcome || "—")}</strong></div>
    <div class="metric"><span>External mutations</span><strong>${escapeHtml(view.external_mutation_count ?? 0)}</strong></div>
    <div class="metric"><span>Payer decision</span><strong>${escapeHtml(payerDecision)}</strong></div>
    <div class="metric"><span>Workflow events</span><strong>${escapeHtml(events.length)}</strong></div>
  </div>
  <div class="action-row">${actionButtons.join("") || '<span class="muted">No action is available in this state.</span>'}</div>
  <p id="case-action-message" class="message" role="status"></p>
  <div class="detail-grid">
    <section><h3>Failure / safety reason</h3><p class="muted">${escapeHtml(view.failure_reason || "None recorded")}</p></section>
    <section><h3>State transitions</h3><ul class="compact-list">${transitions.length ? transitions.map((item) => `<li><strong>${escapeHtml(item.to_state || item.state || "transition")}</strong><span>${escapeHtml(item.reason || item.actor || "")}</span></li>`).join("") : '<li class="muted">No transitions returned.</li>'}</ul></section>
  </div>
  <details><summary>View live response (references and metadata only)</summary><pre>${escapeHtml(JSON.stringify(view, null, 2))}</pre></details>`;

  document.querySelector("#approve-button")?.addEventListener("click", () => runAction("approve"));
  document.querySelector("#adjudicate-button")?.addEventListener("click", () => runAction("adjudicate"));
  document.querySelector("#mobile-link-button")?.addEventListener("click", createMobileLink);
}

async function refreshBoard(message = "") {
  if (!tenantId) return;
  if (message) setMessage(runtimeMessage, message, "working");
  try {
    const body = await api(`/api/cases/${encodeURIComponent(tenantId)}`);
    cases = Array.isArray(body.cases) ? body.cases : [];
    renderBoard();
    setMessage(runtimeMessage, `Loaded ${cases.length} case${cases.length === 1 ? "" : "s"} from Firestore.`, "success");
  } catch (error) {
    setMessage(runtimeMessage, error.message, "error");
  }
}

async function runAction(action) {
  const actionMessage = document.querySelector("#case-action-message");
  setMessage(actionMessage, `Running ${action} through the Submission Gate…`, "working");
  try {
    await api(`/api/cases/${encodeURIComponent(tenantId)}/${encodeURIComponent(selectedCaseId)}/${action}`, { method: "POST" });
    await refreshBoard("Action committed; board refreshed from Firestore.");
  } catch (error) {
    setMessage(actionMessage, error.message, "error");
  }
}

async function createMobileLink() {
  const actionMessage = document.querySelector("#case-action-message");
  setMessage(actionMessage, "Issuing a short-lived signed approval capability…", "working");
  try {
    const body = await api(`/api/cases/${encodeURIComponent(tenantId)}/${encodeURIComponent(selectedCaseId)}/approval-link`, { method: "POST" });
    const link = new URL("./mobile.html", window.location.href);
    link.searchParams.set("token", body.approval_link);
    actionMessage.innerHTML = `Mobile approval URL (expires ${escapeHtml(body.expires_at)}): <a href="${escapeHtml(link.href)}" target="_blank" rel="noopener">open mobile view</a>`;
    actionMessage.className = "message success";
  } catch (error) {
    setMessage(actionMessage, error.message, "error");
  }
}

async function createDemoCase(mode, index = 0) {
  const suffix = `${Date.now()}-${index}-${mode}`;
  return api("/api/demo/cases", {
    method: "POST",
    body: JSON.stringify({
      tenant_id: tenantId,
      case_id: `case-demo-dashboard-${suffix}`,
      injection: mode === "injection",
      missing_evidence: mode === "missing_evidence"
    })
  });
}

document.querySelector("#refresh-button").addEventListener("click", () => refreshBoard("Refreshing…"));
document.querySelector("#sign-out-button").addEventListener("click", () => signOut(auth));
document.querySelector("#seed-button").addEventListener("click", async () => {
  setMessage(runtimeMessage, "Loading six governed evaluation cases…", "working");
  try {
    for (const [index, mode] of ["clean", "clean", "missing_evidence", "injection", "clean", "clean"].entries()) {
      await createDemoCase(mode, index);
    }
    await refreshBoard("Six evaluation cases created and loaded from Firestore.");
  } catch (error) {
    setMessage(runtimeMessage, `Seed stopped: ${error.message}`, "error");
    await refreshBoard();
  }
});

signInForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  setMessage(authMessage, "Signing in…", "working");
  const email = document.querySelector("#email").value.trim();
  const password = document.querySelector("#password").value;
  try {
    await signInWithEmailAndPassword(auth, email, password);
  } catch (error) {
    setMessage(authMessage, error.message, "error");
  }
});

onAuthStateChanged(auth, async (user) => {
  if (!user) {
    tenantId = "";
    cases = [];
    authCard.hidden = false;
    appShell.hidden = true;
    return;
  }
  try {
    const tokenResult = await getIdTokenResult(user, true);
    const claim = tokenResult.claims.tenant_id;
    if (typeof claim !== "string" || !claim.trim()) {
      throw new Error("This account has no tenant_id custom claim yet.");
    }
    tenantId = claim.trim();
    userEmail.textContent = user.email || user.uid;
    tenantIdElement.textContent = `tenant: ${tenantId}`;
    authCard.hidden = true;
    appShell.hidden = false;
    setMessage(authMessage, "");
    await refreshBoard();
  } catch (error) {
    await signOut(auth);
    setMessage(authMessage, error.message, "error");
  }
});
