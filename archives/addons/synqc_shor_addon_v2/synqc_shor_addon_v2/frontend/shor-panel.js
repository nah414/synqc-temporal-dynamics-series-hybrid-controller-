// SynQc Shor/RSA demo panel (frontend)
// Pure ES module. Safe to include even if the host div doesn't exist.

function qs(sel, root = document) {
  return root.querySelector(sel);
}

function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  Object.entries(attrs).forEach(([k, v]) => {
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  });
  (Array.isArray(children) ? children : [children]).forEach((c) => {
    if (c === null || c === undefined) return;
    node.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
  });
  return node;
}

function safeJson(obj) {
  try {
    return JSON.stringify(obj, null, 2);
  } catch {
    return String(obj);
  }
}

function getAuthHeader() {
  // Matches the hints in your UI screenshot.
  const token =
    window.localStorage.getItem("synqc_bearer_token") ||
    window.localStorage.getItem("synqc_api_key") ||
    window.localStorage.getItem("api_key");

  if (!token) return {};
  // If it's already "Bearer xxx" keep it, else wrap it.
  const value = token.toLowerCase().startsWith("bearer ") ? token : `Bearer ${token}`;
  return { Authorization: value };
}

function hasAuthToken() {
  return Boolean(getAuthHeader().Authorization);
}

async function apiPost(path, body, apiBase = "") {
  const res = await fetch(`${apiBase}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...getAuthHeader(),
    },
    body: JSON.stringify(body),
  });

  const text = await res.text();
  let data;
  try {
    data = JSON.parse(text);
  } catch {
    data = { raw: text };
  }

  if (!res.ok) {
    const msg = data?.detail || data?.message || `HTTP ${res.status}`;
    throw new Error(typeof msg === "string" ? msg : safeJson(msg));
  }
  return data;
}

async function apiGet(path, apiBase = "") {
  const res = await fetch(`${apiBase}${path}`, {
    headers: {
      ...getAuthHeader(),
    },
  });

  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return await res.json();
}

function parseIntField(value, name) {
  const v = (value || "").trim();
  if (!v) return null;
  if (!/^-?\d+$/.test(v)) throw new Error(`${name} must be an integer`);
  const n = Number(v);
  if (!Number.isFinite(n)) throw new Error(`${name} is not a finite number`);
  if (!Number.isSafeInteger(n)) throw new Error(`${name} exceeds JS safe integer range`);
  return n;
}

export function mountShorPanel(hostEl, options = {}) {
  const apiBase = options.apiBase || "";

  const out = el("pre", { class: "shor-output", id: "shor-output" }, "");
  const status = el("div", { class: "shor-status", id: "shor-status", text: "Checking backend…" });
  const backendBadge = el("div", { class: "shor-panel__badge shor-panel__badge--alert", text: "Hardware locked until set" });

  const inputN = el("input", { class: "shor-input", id: "shor-N", placeholder: "e.g. 3233" });
  const inputE = el("input", { class: "shor-input", id: "shor-e", placeholder: "e.g. 17 or 65537", value: "65537" });

  const inputBits = el("input", { class: "shor-input", id: "shor-bits", placeholder: "prime bits", value: "12" });

  const backendSel = el(
    "select",
    { class: "shor-select", id: "shor-backend" },
    [
      el("option", { value: "aer", text: "aer (local simulator)" }),
      el("option", { value: "ibm", text: "ibm (IBM Runtime)" }),
      el("option", { value: "custom", text: "custom (any Qiskit provider)" }),
    ]
  );

  const shotsInput = el("input", {
    class: "shor-input",
    id: "shor-shots",
    placeholder: "shots",
    value: "1024",
    type: "number",
    min: "1",
    max: "20000",
  });
  const ibmBackendInput = el("input", {
    class: "shor-input",
    id: "shor-ibm-backend",
    placeholder: "e.g. ibm_brisbane (optional)",
  });
  const providerLoaderInput = el("input", {
    class: "shor-input",
    id: "shor-provider-loader",
    placeholder: "module:Class or dotted path",
  });
  const providerBackendInput = el("input", {
    class: "shor-input",
    id: "shor-provider-backend",
    placeholder: "provider backend name (required)",
  });
  let ibmBackendLabel;
  let providerLoaderLabel;
  let providerBackendLabel;

  const inputPlainInt = el("input", { class: "shor-input", id: "shor-plain-int", placeholder: "integer plaintext (optional)" });
  const inputPlainText = el("input", { class: "shor-input", id: "shor-plain-text", placeholder: "text plaintext (optional)" });

  const inputCipher = el("input", { class: "shor-input", id: "shor-cipher", placeholder: "ciphertext integer" });

  const methodSel = el(
    "select",
    { class: "shor-select", id: "shor-method" },
    [
      el("option", { value: "auto", text: "auto (try Qiskit Shor, else fallback)" }),
      el("option", { value: "qiskit", text: "qiskit (force Shor)" }),
      el("option", { value: "classical", text: "classical fallback" }),
    ]
  );

  function setBusy(isBusy) {
    hostEl.querySelectorAll("button, input, select, textarea").forEach((n) => {
      if (n.id === "shor-output") return;
      n.disabled = isBusy;
    });
  }

  function log(obj) {
    out.textContent = safeJson(obj);
    out.scrollTop = 0;
  }

  // ----------------------------
  // Recent runs (plugs into SynQc "Experiment Runs" concept)
  // ----------------------------

  const runsStatus = el("div", { class: "shor-runs__status", text: "" });
  const runsList = el("div", { class: "shor-runs__list" }, []);
  const backendSummary = el("div", { class: "shor-chip shor-chip--warn" }, [
    el("span", { class: "shor-chip__dot" }),
    el("span", { text: "Select backend to unlock hardware" }),
  ]);

  function fmtTs(ts) {
    if (!ts) return "";
    // ISO string like 2025-12-26T05:30:00Z → show HH:MM:SS
    const m = String(ts).match(/T(\d\d:\d\d:\d\d)/);
    return m ? m[1] : String(ts);
  }

  async function openRun(runId) {
    try {
      const detail = await apiGet(`/api/shor/runs/${encodeURIComponent(runId)}`, apiBase);
      log({ action: "run_detail", ...detail });
    } catch (e) {
      log({ error: String(e) });
    }
  }

  async function refreshRuns() {
    runsStatus.textContent = "";
    runsList.innerHTML = "";
    try {
      const data = await apiGet(`/api/shor/runs?limit=12`, apiBase);
      const runs = data?.runs || [];

      if (!runs.length) {
        runsStatus.textContent = "No runs yet.";
        return;
      }

      runs.forEach((r) => {
        const btn = el(
          "button",
          {
            class: `shor-run ${r.ok ? "shor-run--ok" : "shor-run--bad"}`,
            onclick: () => openRun(r.run_id),
            title: r.run_id,
          },
          [
            el("div", { class: "shor-run__top" }, [
              el("span", { class: "shor-run__kind", text: r.kind || "run" }),
              el("span", { class: "shor-run__time", text: fmtTs(r.ts_utc) }),
            ]),
            el("div", { class: "shor-run__bot" }, [
              el("span", { class: "shor-run__status", text: r.ok ? "ok" : "fail" }),
              el("span", { class: "shor-run__ms", text: `${Math.round(r.runtime_ms || 0)} ms` }),
            ]),
          ]
        );
        runsList.appendChild(btn);
      });
    } catch (e) {
      runsStatus.textContent = "Runs unavailable (/api/shor/runs)";
    }
  }

  const runsBox = el("div", { class: "shor-runs" }, [
    el("div", { class: "shor-runs__header" }, [
      el("div", { class: "shor-runs__title", text: "Recent runs" }),
      el("button", { class: "shor-btn shor-btn--mini", onclick: refreshRuns, text: "Refresh" }),
    ]),
    runsStatus,
    runsList,
  ]);

  async function refreshHealth() {
    try {
      const h = await apiGet("/api/shor/health", apiBase);
      status.className = "shor-status shor-status--ok";
      status.textContent = `Backend OK (${h.feature})`;
      backendBadge.textContent = "API: /api/shor/*";
      backendBadge.classList.remove("shor-panel__badge--alert");
    } catch (e) {
      status.className = "shor-status shor-status--bad";
      status.textContent = "Backend unavailable (/api/shor/health)";
      backendBadge.textContent = "Backend unavailable";
      backendBadge.classList.add("shor-panel__badge--alert");
    }
  }

  function readQiskitOpts() {
    const backend_mode = backendSel.value;
    const shots = parseIntField(shotsInput.value, "shots") ?? 1024;
    const ibm_backend_name = (ibmBackendInput.value || "").trim() || null;
    const provider_loader = (providerLoaderInput.value || "").trim() || null;
    const provider_backend_name = (providerBackendInput.value || "").trim() || null;
    if (backend_mode !== "aer" && !hasAuthToken()) {
      throw new Error(
        "Hardware modes require an Authorization bearer token in localStorage (synqc_bearer_token / synqc_api_key / api_key)."
      );
    }
    if (backend_mode === "custom" && !provider_backend_name) {
      throw new Error("Provide a provider backend name for custom mode.");
    }
    return { backend_mode, shots, ibm_backend_name, provider_loader, provider_backend_name };
  }

  function updateBackendFields() {
    const mode = backendSel.value;
    const showIBM = mode === "ibm";
    const showCustom = mode === "custom";
    const hasAuth = hasAuthToken();

    [ibmBackendLabel, ibmBackendInput].forEach((el) => el.classList.toggle("shor-hidden", !showIBM));
    [providerLoaderLabel, providerLoaderInput, providerBackendLabel, providerBackendInput].forEach((el) =>
      el.classList.toggle("shor-hidden", !showCustom)
    );

    if (mode === "aer") {
      backendSummary.className = "shor-chip";
      backendSummary.replaceChildren(el("span", { class: "shor-chip__dot" }), el("span", { text: "Local simulator (aer)" }));
    } else if (mode === "ibm") {
      backendSummary.className = "shor-chip shor-chip--warn";
      backendSummary.replaceChildren(
        el("span", { class: "shor-chip__dot" }),
        el("span", {
          text: !hasAuth
            ? "Add bearer token for IBM Runtime"
            : ibmBackendInput.value
              ? `IBM Runtime: ${ibmBackendInput.value}`
              : "IBM Runtime (set backend)",
        })
      );
    } else {
      backendSummary.className = "shor-chip shor-chip--warn";
      backendSummary.replaceChildren(
        el("span", { class: "shor-chip__dot" }),
        el("span", {
          text: !hasAuth
            ? "Add bearer token for custom provider"
            : providerBackendInput.value
              ? `Custom provider: ${providerBackendInput.value}`
              : "Custom provider (name required)",
        })
      );
    }
  }

  backendSel.addEventListener("change", updateBackendFields);
  [ibmBackendInput, providerLoaderInput, providerBackendInput].forEach((n) =>
    n.addEventListener("input", updateBackendFields)
  );

  async function onGenerate() {
    setBusy(true);
    try {
      const bits = parseIntField(inputBits.value, "bits") ?? 12;
      const e = parseIntField(inputE.value, "e") ?? 65537;
      const data = await apiPost("/api/shor/rsa/generate", { bits, e }, apiBase);
      inputN.value = String(data.N);
      inputE.value = String(data.e);
      log({ action: "rsa_generate", ...data });
      refreshRuns();
    } catch (err) {
      log({ error: String(err) });
    } finally {
      setBusy(false);
    }
  }

  async function onEncrypt() {
    setBusy(true);
    try {
      const N = parseIntField(inputN.value, "N");
      const e = parseIntField(inputE.value, "e");
      if (N === null || e === null) throw new Error("Provide N and e.");

      const plainInt = parseIntField(inputPlainInt.value, "plaintext_int");
      const plainText = (inputPlainText.value || "").trim();

      const body = { N, e };
      if (plainInt !== null) body.plaintext_int = plainInt;
      else if (plainText) body.plaintext_text = plainText;
      else throw new Error("Provide plaintext_int or plaintext_text.");

      const data = await apiPost("/api/shor/rsa/encrypt", body, apiBase);
      inputCipher.value = String(data.ciphertext_int);
      log({ action: "rsa_encrypt", ...data });
      refreshRuns();
    } catch (err) {
      log({ error: String(err) });
    } finally {
      setBusy(false);
    }
  }

  async function onFactor() {
    setBusy(true);
    try {
      const N = parseIntField(inputN.value, "N");
      if (N === null) throw new Error("Provide N.");
      const method = methodSel.value;
      const opts = readQiskitOpts();
      const data = await apiPost("/api/shor/factor", { N, method, ...opts }, apiBase);
      log({ action: "factor", ...data });
      refreshRuns();
    } catch (err) {
      log({ error: String(err) });
    } finally {
      setBusy(false);
    }
  }

  async function onEstimate() {
    setBusy(true);
    try {
      const N = parseIntField(inputN.value, "N");
      if (N === null) throw new Error("Provide N.");
      const data = await apiPost("/api/shor/estimate", { N }, apiBase);
      log({ action: "estimate", ...data });
      refreshRuns();
    } catch (err) {
      log({ error: String(err) });
    } finally {
      setBusy(false);
    }
  }

  async function onDecrypt() {
    setBusy(true);
    try {
      const N = parseIntField(inputN.value, "N");
      const e = parseIntField(inputE.value, "e");
      const ciphertext_int = parseIntField(inputCipher.value, "ciphertext_int");
      if (N === null || e === null || ciphertext_int === null) throw new Error("Provide N, e, and ciphertext.");
      const method = methodSel.value;
      const opts = readQiskitOpts();
      const data = await apiPost("/api/shor/rsa/decrypt", { N, e, ciphertext_int, method, ...opts }, apiBase);
      log({ action: "rsa_decrypt", ...data });
      refreshRuns();
    } catch (err) {
      log({ error: String(err) });
    } finally {
      setBusy(false);
    }
  }

  const left = el("div", { class: "shor-card" }, [
    el("h3", { text: "Controls" }),
    el("div", { class: "shor-section" }, [
      el("div", { class: "shor-section__title", text: "RSA inputs" }),
      el("div", { class: "shor-grid" }, [
        el("label", { text: "Prime bits" }),
        inputBits,

        el("label", { text: "N (modulus)" }),
        inputN,

        el("label", { text: "e (public exp.)" }),
        inputE,

        el("label", { text: "Plaintext (int)" }),
        inputPlainInt,

        el("label", { text: "Plaintext (text)" }),
        inputPlainText,

        el("label", { text: "Ciphertext (int)" }),
        inputCipher,
      ]),
      el("div", { class: "shor-help shor-help--tight" }, "Use the integer path for deterministic testing; text converts to int under the hood."),
    ]),
    el("div", { class: "shor-section" }, [
      el("div", { class: "shor-section__title" }, [
        el("span", { text: "Execution profile" }),
        el("div", { class: "shor-chip-row" }, [
          backendSummary,
          el("div", { class: "shor-chip" }, [el("span", { class: "shor-chip__dot" }), el("span", { text: "Guardrails enabled" })]),
        ]),
      ]),
      el("div", { class: "shor-grid" }, [
        el("label", { text: "Method" }),
        methodSel,

        el("label", { text: "Qiskit backend" }),
        backendSel,

        el("label", { text: "Shots" }),
        shotsInput,

        (providerLoaderLabel = el("label", { text: "Provider loader", class: "" })),
        providerLoaderInput,

        (providerBackendLabel = el("label", { text: "Provider backend" })),
        providerBackendInput,

        (ibmBackendLabel = el("label", { text: "IBM backend name" })),
        ibmBackendInput,
      ]),
      el("div", { class: "shor-help shor-help--warn" }, "Hardware modes (IBM/custom) expect your credentials and backend names. The UI keeps classical fallback available."),
      el("div", { class: "shor-divider" }),
      el("div", { class: "shor-help shor-help--tight" }, "Custom providers accept dotted paths like qiskit_braket_provider.BraketProvider with the backend name exposed by the service."),
    ]),
    el("div", { class: "shor-actions" }, [
      el("button", { class: "shor-btn", onclick: onGenerate, text: "Generate demo RSA key" }),
      el("button", { class: "shor-btn", onclick: onEncrypt, text: "Encrypt" }),
      el("button", { class: "shor-btn", onclick: onDecrypt, text: "Decrypt (factor N)" }),
      el("button", { class: "shor-btn", onclick: onEstimate, text: "Estimate resources" }),
      el("button", { class: "shor-btn", onclick: onFactor, text: "Factor N" }),
    ]),
    el("div", { class: "shor-help" }, [
      el("div", { text: "Notes:" }),
      el("div", { text: "• Guarded RSA demo (no padding). Plaintext must be < N." }),
      el("div", { text: "• Shor runs when available to factor N; classical fallback stays available." }),
      el("div", { text: "• Backend enforces small N bit-length caps for safety." }),
      el("div", { text: "• Hardware modes require your existing credentials/config for the provider." }),
    ]),
  ]);

  const right = el("div", { class: "shor-card shor-card--output" }, [
    el("h3", { text: "Output" }),
    out,
    runsBox,
  ]);

  const panel = el("div", { class: "shor-panel" }, [
    el("div", { class: "shor-panel__header" }, [
      el("div", { class: "shor-panel__title" }, [
        el("strong", { text: "Shor / RSA Lab" }),
        el("span", { text: "Quantum factoring console with guarded hardware controls." }),
      ]),
      el("div", { class: "shor-panel__controls" }, [
        el("div", { class: "shor-panel__meta" }, [backendBadge, status]),
        el("button", { class: "shor-btn", onclick: refreshHealth, text: "Recheck" }),
      ]),
    ]),
    el("div", { class: "shor-panel__body" }, [left, right]),
  ]);

  hostEl.innerHTML = "";
  hostEl.appendChild(panel);

  updateBackendFields();
  refreshHealth();
  refreshRuns();
  return { refreshHealth, refreshRuns };
}

export function autoMountShorPanel(options = {}) {
  const host = document.getElementById("shor-panel-host");
  if (!host) return null;
  return mountShorPanel(host, options);
}

// Auto-mount on load (safe no-op if host doesn't exist).
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => autoMountShorPanel());
} else {
  autoMountShorPanel();
}
