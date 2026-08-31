import { initializeApp } from "https://www.gstatic.com/firebasejs/10.14.1/firebase-app.js";
import {
  getAuth,
  getIdTokenResult,
  onAuthStateChanged,
  signInWithEmailAndPassword
} from "https://www.gstatic.com/firebasejs/10.14.1/firebase-auth.js";

const auth = getAuth(initializeApp(window.APPEAL_FIREBASE_CONFIG));
const apiBase = window.APPEAL_API_BASE.replace(/\/$/, "");
const token = new URLSearchParams(window.location.search).get("token") || "";
const authForm = document.querySelector("#mobile-sign-in-form");
const authMessage = document.querySelector("#mobile-auth-message");
const caseCard = document.querySelector("#mobile-case-card");
const actionMessage = document.querySelector("#mobile-action-message");
let tenantId = "";

function setMessage(element, message, kind = "") {
  element.textContent = message;
  element.className = `message ${kind}`.trim();
}

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  headers.set("Authorization", `Bearer ${await auth.currentUser.getIdToken()}`);
  if (options.body) headers.set("Content-Type", "application/json");
  const response = await fetch(`${apiBase}${path}`, { ...options, headers });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(`${response.status}: ${body.error || "request failed"}`);
  return body;
}

async function preview() {
  if (!token) throw new Error("The approval token is missing from this URL.");
  const body = await api(`/api/mobile/approval/${encodeURIComponent(token)}`);
  document.querySelector("#mobile-case-id").textContent = body.case_id;
  const state = document.querySelector("#mobile-state");
  state.textContent = body.case_state;
  state.className = `pill state-${body.case_state.toLowerCase().replaceAll("_", "-")}`;
  document.querySelector("#mobile-expiry").textContent = `Link expires ${body.expires_at}.`;
  caseCard.hidden = false;
}

authForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  setMessage(authMessage, "Signing in…", "working");
  try {
    await signInWithEmailAndPassword(
      auth,
      document.querySelector("#mobile-email").value.trim(),
      document.querySelector("#mobile-password").value
    );
  } catch (error) {
    setMessage(authMessage, error.message, "error");
  }
});

document.querySelector("#mobile-approve-button").addEventListener("click", async () => {
  setMessage(actionMessage, "Submitting the clinician decision…", "working");
  try {
    const body = await api(`/api/mobile/approval/${encodeURIComponent(token)}`, {
      method: "POST",
      body: JSON.stringify({ decision: "approve" })
    });
    setMessage(actionMessage, `Approved. Case is now ${body.case_state}.`, "success");
    document.querySelector("#mobile-approve-button").disabled = true;
  } catch (error) {
    setMessage(actionMessage, error.message, "error");
  }
});

onAuthStateChanged(auth, async (user) => {
  if (!user) return;
  try {
    const tokenResult = await getIdTokenResult(user, true);
    if (typeof tokenResult.claims.tenant_id !== "string" || !tokenResult.claims.tenant_id.trim()) {
      throw new Error("This account has no tenant_id custom claim yet.");
    }
    tenantId = tokenResult.claims.tenant_id.trim();
    await preview();
    setMessage(authMessage, `Signed in for ${tenantId}.`, "success");
  } catch (error) {
    setMessage(authMessage, error.message, "error");
  }
});
