// --------------------------------------------
    // Visual particles
    // --------------------------------------------
    (function initParticles() {
      const layer = document.getElementById('particleLayer');
      const count = 30;
      for (let i = 0; i < count; i++) {
        const p = document.createElement('div');
        p.className = 'particle';
        const x = Math.random() * 100;
        const y = 20 + Math.random() * 80;
        const delay = Math.random() * 18;
        const scale = 0.8 + Math.random() * 0.7;
        p.style.left = x + 'vw';
        p.style.top = y + 'vh';
        p.style.animationDelay = (-delay) + 's';
        p.style.transform = 'scale(' + scale.toFixed(2) + ')';
        layer.appendChild(p);
      }
    })();

    // --------------------------------------------
    // Mode pills
    // --------------------------------------------
    document.querySelectorAll('.mode-pill').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.mode-pill').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
      });
    });

    // --------------------------------------------
    // Primary nav -> view switching (v0.4)
    // --------------------------------------------
    const navButtons = Array.from(document.querySelectorAll('.nav-links button[data-view]'));
    const views = {
      console: document.getElementById('view-console'),
      experiments: document.getElementById('view-experiments'),
      hardware: document.getElementById('view-hardware'),
      details: document.getElementById('view-details'),
    };

    let lastNonDetailsView = 'console';

    function setActiveView(viewName, { pushHash = true } = {}) {
      if (!views[viewName]) viewName = 'console';

      navButtons.forEach(b => b.classList.toggle('active', b.dataset.view === viewName));
      Object.entries(views).forEach(([k, el]) => {
        if (!el) return;
        el.classList.toggle('active', k === viewName);
      });

      if (viewName !== 'details') lastNonDetailsView = viewName;

      if (pushHash) {
        try { window.location.hash = viewName; } catch (_) { /* ignore */ }
      }

      // Best-effort refresh when opening data-backed views
      if (viewName === 'experiments') refreshExperimentsView();
      if (viewName === 'hardware') refreshHardwareView();
      if (viewName === 'details') refreshDetailsView();
    }

    navButtons.forEach(btn => {
      btn.addEventListener('click', () => setActiveView(btn.dataset.view || 'console'));
    });

    // Initialize from hash
    (function initViewFromHash(){
      const hv = (window.location.hash || '').replace('#','').trim();
      if (hv && views[hv]) setActiveView(hv, { pushHash: false });
    })();

    // --------------------------------------------
    // Agent tabs (Agent / Setup)
    // --------------------------------------------
    const agentTabs = document.querySelectorAll('.agent-tabs button');
    const chatPanel = document.getElementById('agentChatLog');
    const setupPanel = document.getElementById('agentSetupPanel');

    agentTabs.forEach(btn => {
      btn.addEventListener('click', () => {
        agentTabs.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        const tab = btn.getAttribute('data-tab');
        if (tab === 'chat') {
          chatPanel.style.display = 'flex';
          setupPanel.style.display = 'none';
        } else {
          chatPanel.style.display = 'flex';
          setupPanel.style.display = 'flex';
        }
      });
    });

    // --------------------------------------------
    // DOM references
    // --------------------------------------------
    const agentInput = document.getElementById('agentInput');
    const agentSend = document.getElementById('agentSend');

    const scenePresetLabel = document.getElementById('scenePresetLabel');
    const sceneHardwareLabel = document.getElementById('sceneHardwareLabel');
    const hardwareSelect = document.getElementById('hardwareSelect');
    const presetSelect = document.getElementById('presetSelect');
    const sceneInterpretation = document.getElementById('sceneInterpretation');

    const shotInput = document.getElementById('shotInput');
    const shotLabel = document.getElementById('shotLabel');
    const notesInput = document.getElementById('notesInput');
    const runPresetBtn = document.getElementById('runPresetBtn');
    const runStatus = document.getElementById('runStatus');

    // Console history
    const historyBody = document.getElementById('historyBody');
    const historyFiltersConsole = document.getElementById('historyFiltersConsole');

    // Experiments page
    const experimentsBody = document.getElementById('experimentsBody');
    const historyFiltersExperiments = document.getElementById('historyFiltersExperiments');
    const refreshExperimentsBtn = document.getElementById('refreshExperimentsBtn');

    // Hardware page
    const hardwareMeta = document.getElementById('hardwareMeta');
    const hardwareList = document.getElementById('hardwareList');
    const refreshHardwareBtn = document.getElementById('refreshHardwareBtn');

    // Details page
    const detailsBackBtn = document.getElementById('detailsBackBtn');
    const detailsReloadBtn = document.getElementById('detailsReloadBtn');
    const detailsHeader = document.getElementById('detailsHeader');
    const detailsJson = document.getElementById('detailsJson');
    const detailsInterpretation = document.getElementById('detailsInterpretation');

    const detailsKpiFidelity = document.getElementById('detailsKpiFidelity');
    const detailsKpiLatency = document.getElementById('detailsKpiLatency');
    const detailsKpiBackaction = document.getElementById('detailsKpiBackaction');
    const detailsKpiShots = document.getElementById('detailsKpiShots');
    const detailsKpiStatus = document.getElementById('detailsKpiStatus');

    // --------------------------------------------
    // Backend wiring
    // --------------------------------------------
    function defaultApiBase() {
      const params = new URLSearchParams(window.location.search);
      const override = params.get('api');
      if (override) return override.replace(/\/$/, "");

      // If opened as a local file, assume the backend is running on localhost:8001.
      if (window.location.protocol === 'file:') return 'http://localhost:8001';

      // If served via a dev server (e.g., Live Server / http.server), assume backend on the same host:8001.
      return `${window.location.protocol}//${window.location.hostname}:8001`;
    }

    const API_BASE = defaultApiBase();

    let MAX_SHOTS_PER_EXPERIMENT = 200000;
    let DEFAULT_SHOT_BUDGET = 2048;

    let lastRun = null;
    let recentRunsCache = [];
    let hardwareTargetsCache = [];
    let healthCache = null;

    let selectedExperimentId = null;

    function setRunStatus(text) {
      runStatus.textContent = text;
    }

    async function apiGet(path) {
      const res = await fetch(API_BASE + path, { method: 'GET' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    }

    async function apiPost(path, payload) {
      const res = await fetch(API_BASE + path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        let detail = '';
        try {
          const data = await res.json();
          detail = data?.detail ? ` — ${data.detail}` : '';
        } catch (_) { /* ignore */ }
        throw new Error(`HTTP ${res.status}${detail}`);
      }
      return await res.json();
    }

    function fmtTimeFromEpochSeconds(epochSec) {
      const d = new Date(epochSec * 1000);
      return d.toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
    }

    function presetLabel(preset) {
      if (preset === 'health') return 'Health (T1/T2/RB)';
      if (preset === 'latency') return 'Latency probe';
      if (preset === 'backend_compare') return 'Backend compare';
      if (preset === 'dpd_demo') return 'DPD demo';
      return preset;
    }

    function statusLabel(status) {
      if (status === 'ok') return 'OK';
      if (status === 'warn') return 'WARN';
      if (status === 'fail') return 'FAIL';
      return String(status || '').toUpperCase() || 'OK';
    }

    function statusClass(status) {
      if (status === 'fail') return 'status-fail';
      if (status === 'warn') return 'status-warn';
      return 'status-ok';
    }

    function setKpiClass(el, status) {
      el.classList.remove('kpi-good', 'kpi-warn', 'kpi-bad');
      if (status === 'fail') el.classList.add('kpi-bad');
      else if (status === 'warn') el.classList.add('kpi-warn');
      else el.classList.add('kpi-good');
    }

    function clamp01(x) {
      if (!Number.isFinite(x)) return 0;
      return Math.max(0, Math.min(1, x));
    }

    function hardwareNameForId(id) {
      // Prefer cache from /hardware/targets
      const found = (hardwareTargetsCache || []).find(t => t.id === id);
      if (found && found.name) return found.name;

      // Fall back to current select option
      const opt = Array.from(hardwareSelect.options || []).find(o => o.value === id);
      return opt ? opt.textContent : id;
    }

    // --------------------------------------------
    // Visual KPI mapping (console scene)
    // --------------------------------------------
    function applyRunToVisuals(run) {
      const kpis = run?.kpis || {};
      const fidelity = (kpis.fidelity == null) ? null : Number(kpis.fidelity);
      const latency = (kpis.latency_us == null) ? null : Number(kpis.latency_us);
      const backaction = (kpis.backaction == null) ? null : Number(kpis.backaction);

      const atm = document.getElementById('blochAtmosphere');
      const noise = document.getElementById('blochNoise');
      const state = document.getElementById('blochState');
      const ringA = document.getElementById('blochRingA');
      const ringB = document.getElementById('blochRingB');
      const ringC = document.getElementById('blochRingC');
      const trace = document.getElementById('blochTrace');
      const orbitDot = document.getElementById('blochOrbitDot');
      const spark = document.getElementById('timelineSpark');

      if (atm) {
        const alpha = (fidelity == null || !Number.isFinite(fidelity))
          ? 0.38
          : (0.18 + clamp01(fidelity) * 0.55);
        atm.style.opacity = String(alpha.toFixed(3));
      }

      if (noise) {
        const n = (backaction == null || !Number.isFinite(backaction)) ? 0.18 : Math.max(0, Math.min(backaction, 0.6));
        noise.style.opacity = String((0.02 + (n / 0.6) * 0.18).toFixed(3));
      }

      const lat = (latency == null || !Number.isFinite(latency)) ? 60 : Math.max(5, Math.min(latency, 800));
      const spin = 12 + (lat / 800) * 22;          // 12–34s
      const dash = 2.6 + (lat / 800) * 2.2;        // 2.6–4.8s
      const sparkSpeed = 3.2 + (lat / 800) * 2.0;  // 3.2–5.2s

      const back = (backaction == null || !Number.isFinite(backaction)) ? 0.22 : Math.max(0, Math.min(backaction, 0.6));
      const orbit = 9 - (back / 0.6) * 3.5;        // 5.5–9.0s

      if (ringA) ringA.style.animationDuration = `${spin.toFixed(1)}s`;
      if (ringB) ringB.style.animationDuration = `${(spin * 1.3).toFixed(1)}s`;
      if (ringC) ringC.style.animationDuration = `${(spin * 1.9).toFixed(1)}s`;
      if (trace) trace.style.animationDuration = `${(spin * 1.4).toFixed(1)}s`;
      if (spark) spark.style.animationDuration = `${sparkSpeed.toFixed(1)}s`;
      if (state) state.style.animationDuration = `${orbit.toFixed(1)}s`;
      if (orbitDot) orbitDot.style.animationDuration = `${(spin * 0.55).toFixed(1)}s`;

      const paths = trace?.querySelectorAll?.('path') || [];
      paths.forEach((p, idx) => {
        const d = (idx === 0) ? dash : (dash * 1.2);
        p.style.animationDuration = `${d.toFixed(2)}s`;
      });
    }

    // --------------------------------------------
    // KPI rendering
    // --------------------------------------------
    function applyRunToKpis(run, ids) {
      const kpis = run?.kpis || {};
      const status = kpis.status || 'ok';

      const elFid = document.getElementById(ids.fidelity);
      const elLat = document.getElementById(ids.latency);
      const elBack = document.getElementById(ids.backaction);
      const elShots = document.getElementById(ids.shots);
      const elStatus = ids.status ? document.getElementById(ids.status) : null;

      // Fidelity
      if (!elFid) return;
      if (kpis.fidelity == null) {
        elFid.textContent = '—';
        elFid.classList.remove('kpi-good', 'kpi-warn', 'kpi-bad');
      } else {
        elFid.textContent = Number(kpis.fidelity).toFixed(3);
        setKpiClass(elFid, status);
      }

      // Latency
      if (elLat) {
        elLat.textContent = (kpis.latency_us == null) ? '—' : `${Number(kpis.latency_us).toFixed(1)} µs`;
      }

      // Backaction
      if (elBack) {
        if (kpis.backaction == null) {
          elBack.textContent = '—';
          elBack.classList.remove('kpi-good', 'kpi-warn', 'kpi-bad');
        } else {
          elBack.textContent = Number(kpis.backaction).toFixed(2);
          const ba = Number(kpis.backaction);
          if (ba > 0.35) setKpiClass(elBack, 'fail');
          else if (ba > 0.25) setKpiClass(elBack, 'warn');
          else setKpiClass(elBack, 'ok');
        }
      }

      // Shots
      if (elShots) {
        const used = Number(kpis.shots_used || 0);
        const budget = Number(kpis.shot_budget || 0);
        elShots.textContent = `${used.toLocaleString()} / ${budget.toLocaleString()}`;
      }

      if (elStatus) {
        elStatus.textContent = statusLabel(status);
        elStatus.classList.remove('kpi-good', 'kpi-warn', 'kpi-bad');
        // For a status value, color it similarly
        if (status === 'fail') elStatus.classList.add('kpi-bad');
        else if (status === 'warn') elStatus.classList.add('kpi-warn');
        else elStatus.classList.add('kpi-good');
      }

      // Only the console has visuals, but it doesn't hurt to try.
      try { applyRunToVisuals(run); } catch (_) { /* non-fatal */ }
    }

    const CONSOLE_KPI_IDS = {
      fidelity: 'kpiFidelity',
      latency: 'kpiLatency',
      backaction: 'kpiBackaction',
      shots: 'kpiShots',
      status: null,
    };

    const DETAILS_KPI_IDS = {
      fidelity: 'detailsKpiFidelity',
      latency: 'detailsKpiLatency',
      backaction: 'detailsKpiBackaction',
      shots: 'detailsKpiShots',
      status: 'detailsKpiStatus',
    };

    // --------------------------------------------
    // Interpretation text
    // --------------------------------------------
    function deriveInterpretationFromRun(run) {
      const hwName = hardwareNameForId(run.hardware_target);
      const k = run.kpis || {};
      const status = k.status || 'ok';

      if (run.preset === 'health') {
        if (k.fidelity == null) {
          return `Health run completed on ${hwName}. Fidelity is not reported by this backend; inspect the record and provider logs.`;
        }
        const fid = Number(k.fidelity);
        const lat = (k.latency_us == null) ? null : Number(k.latency_us);
        const ba = (k.backaction == null) ? null : Number(k.backaction);

        const verdict =
          (status === 'fail') ? 'This looks unstable for production.' :
          (status === 'warn') ? 'This is borderline; watch drift and repeat a confirm run.' :
          'This looks stable inside normal bounds.';

        let extras = '';
        if (lat != null) extras += ` Latency was ~${lat.toFixed(1)} µs.`;
        if (ba != null) extras += ` Backaction was ${ba.toFixed(2)} (lower is better).`;

        return `Health diagnostics completed on ${hwName}. Estimated fidelity: ${fid.toFixed(3)}. ${verdict}${extras}`;
      }

      if (run.preset === 'latency') {
        const lat = (k.latency_us == null) ? null : Number(k.latency_us);
        if (lat == null) return `Latency characterization completed on ${hwName}. Latency was not reported; inspect the record.`;
        const note = lat > 50 ? 'This is fairly slow; consider tighter scheduling / batching.' :
                     lat > 25 ? 'Moderate delay; keep an eye on drift and queueing.' :
                     'Fast path looks healthy.';
        return `Latency characterization completed on ${hwName}. End-to-end latency: ~${lat.toFixed(1)} µs. ${note}`;
      }

      if (run.preset === 'backend_compare') {
        return `Backend comparison run completed on ${hwName}. This API version returns a single KPI bundle; multi-backend A/B is a planned extension.`;
      }

      if (run.preset === 'dpd_demo') {
        return `DPD demo completed on ${hwName}. Use this run to validate the Drive–Probe–Drive timing story, then graduate to health/latency presets.`;
      }

      return `Experiment completed on ${hwName}.`;
    }

    function updateInterpretationText() {
      const preset = presetSelect.value;
      const hwName = hardwareSelect.options[hardwareSelect.selectedIndex]?.text || hardwareSelect.value;

      if (lastRun && lastRun.preset === preset && lastRun.hardware_target === hardwareSelect.value) {
        sceneInterpretation.textContent = deriveInterpretationFromRun(lastRun);
        return;
      }

      if (preset === 'health') {
        sceneInterpretation.textContent =
          'A Qubit Health Diagnostics bundle will estimate T1 and T2-like coherence times, ' +
          'and optionally gate error, on ' + hwName + '. The console will summarize whether this backend ' +
          'is within your historical stability band.';
      } else if (preset === 'latency') {
        sceneInterpretation.textContent =
          'Latency Characterization will run short DPD probes to measure control-to-readout delay on ' +
          hwName + ', helping you understand timing overhead and drift.';
      } else if (preset === 'backend_compare') {
        sceneInterpretation.textContent =
          'Backend A/B Comparison will replay a reference experiment on two backends and report ' +
          'relative fidelity, coherence, and latency, so you can choose which is better for your workload.';
      } else if (preset === 'dpd_demo') {
        sceneInterpretation.textContent =
          'Guided SynQc DPD Example will show how a Drive–Probe–Drive sequence manipulates a single qubit ' +
          'over time, illustrating the link between SynQc theory and observable dynamics.';
      }
    }

    // --------------------------------------------
    // Table rendering + filtering
    // --------------------------------------------
    function clearTbody(tbody) {
      while (tbody.firstChild) tbody.removeChild(tbody.firstChild);
    }

    function applyFilterToBody(tbody, filter) {
      const rows = tbody.querySelectorAll('tr');
      rows.forEach(row => {
        const p = row.dataset.preset || '';
        const show =
          (filter === 'all') ||
          (filter === 'health' && p === 'health') ||
          (filter === 'latency' && p === 'latency') ||
          (filter === 'compare' && p === 'backend_compare') ||
          (filter === 'dpd' && p === 'dpd_demo');
        row.style.display = show ? '' : 'none';
      });
    }

    function createRunRow(run, { includeId = false } = {}) {
      const tr = document.createElement('tr');
      tr.dataset.preset = run.preset;
      tr.dataset.id = run.id;

      const tdTime = document.createElement('td');
      tdTime.textContent = fmtTimeFromEpochSeconds(run.created_at);

      const tdId = document.createElement('td');
      const shortId = (run.id || '').split('-')[0] || run.id;
      tdId.textContent = includeId ? shortId : '';

      const tdPreset = document.createElement('td');
      tdPreset.textContent = presetLabel(run.preset);

      const tdHw = document.createElement('td');
      tdHw.textContent = run.hardware_target;

      const tdFid = document.createElement('td');
      tdFid.textContent = (run.kpis?.fidelity == null) ? '–' : Number(run.kpis.fidelity).toFixed(3);

      const tdLat = document.createElement('td');
      tdLat.textContent = (run.kpis?.latency_us == null) ? '–' : `${Number(run.kpis.latency_us).toFixed(1)} µs`;

      const tdStatus = document.createElement('td');
      const pill = document.createElement('span');
      pill.className = `status-pill ${statusClass(run.kpis?.status)}`;
      pill.textContent = statusLabel(run.kpis?.status);
      tdStatus.appendChild(pill);

      tr.appendChild(tdTime);
      if (includeId) tr.appendChild(tdId);
      tr.appendChild(tdPreset);
      tr.appendChild(tdHw);
      tr.appendChild(tdFid);
      tr.appendChild(tdLat);
      tr.appendChild(tdStatus);

      tr.addEventListener('click', () => openDetails(run.id));
      return tr;
    }

    let consoleFilter = 'all';
    let experimentsFilter = 'all';

    function wireFilterPills(container, { onChange }) {
      if (!container) return;
      const pills = Array.from(container.querySelectorAll('.filter-pill'));
      pills.forEach(pill => {
        pill.addEventListener('click', () => {
          pills.forEach(x => x.classList.remove('active'));
          pill.classList.add('active');
          const f = pill.dataset.filter || 'all';
          onChange(f);
        });
      });
    }

    wireFilterPills(historyFiltersConsole, {
      onChange: (f) => {
        consoleFilter = f;
        applyFilterToBody(historyBody, consoleFilter);
      }
    });

    wireFilterPills(historyFiltersExperiments, {
      onChange: (f) => {
        experimentsFilter = f;
        applyFilterToBody(experimentsBody, experimentsFilter);
      }
    });

    // --------------------------------------------
    // Backend refresh + render
    // --------------------------------------------
    async function refreshFromBackend() {
      try {
        const h = await apiGet('/health');
        healthCache = h;

        if (h && typeof h.max_shots_per_experiment === 'number') {
          MAX_SHOTS_PER_EXPERIMENT = h.max_shots_per_experiment;
          shotInput.max = String(MAX_SHOTS_PER_EXPERIMENT);
          if (shotLabel && Number.isFinite(MAX_SHOTS_PER_EXPERIMENT)) {
            shotLabel.textContent = `Shot budget (max ${MAX_SHOTS_PER_EXPERIMENT.toLocaleString()})`;
          }
        }

        if (h && typeof h.default_shot_budget === 'number') {
          DEFAULT_SHOT_BUDGET = h.default_shot_budget;
          const existing = Number.parseInt(String(shotInput?.value || ''), 10);
          if (!Number.isFinite(existing) || existing <= 0) shotInput.value = String(DEFAULT_SHOT_BUDGET);
        }

        setRunStatus(`Backend: connected (${API_BASE}) · env=${h.env ?? 'unknown'}`);

        // Targets
        try {
          const targets = await apiGet('/hardware/targets');
          const list = Array.isArray(targets?.targets) ? targets.targets : [];
          hardwareTargetsCache = list;

          // Update setup dropdown
          const current = hardwareSelect.value;
          while (hardwareSelect.firstChild) hardwareSelect.removeChild(hardwareSelect.firstChild);
          list.forEach(t => {
            const opt = document.createElement('option');
            opt.value = t.id;
            opt.textContent = t.name;
            hardwareSelect.appendChild(opt);
          });
          if (Array.from(hardwareSelect.options).some(o => o.value === current)) {
            hardwareSelect.value = current;
          }
          hardwareSelect.dispatchEvent(new Event('change'));

          // Update hardware page
          renderHardwareList();
        } catch (_) { /* best effort */ }

        // Runs
        try {
          const recents = await apiGet('/experiments/recent?limit=50');
          recentRunsCache = Array.isArray(recents) ? recents : [];

          // Console history
          clearTbody(historyBody);
          if (recentRunsCache.length === 0) {
            const tr = document.createElement('tr');
            const td = document.createElement('td');
            td.colSpan = 6;
            td.textContent = 'No runs yet.';
            td.className = 'hint';
            tr.appendChild(td);
            historyBody.appendChild(tr);
          } else {
            recentRunsCache.forEach(r => historyBody.appendChild(createRunRow(r, { includeId: false })));
          }
          applyFilterToBody(historyBody, consoleFilter);

          // Experiments page table
          renderExperimentsTable();
        } catch (_) { /* ignore */ }

      } catch (err) {
        setRunStatus(`Backend: not reachable (${API_BASE}). Start it and refresh.`);
      }
    }

    function renderExperimentsTable() {
      clearTbody(experimentsBody);
      if (!recentRunsCache || recentRunsCache.length === 0) {
        const tr = document.createElement('tr');
        const td = document.createElement('td');
        td.colSpan = 7;
        td.textContent = 'No runs loaded.';
        td.className = 'hint';
        tr.appendChild(td);
        experimentsBody.appendChild(tr);
      } else {
        recentRunsCache.forEach(r => experimentsBody.appendChild(createRunRow(r, { includeId: true })));
      }
      applyFilterToBody(experimentsBody, experimentsFilter);
    }

    function renderHardwareList() {
      if (!hardwareList) return;
      while (hardwareList.firstChild) hardwareList.removeChild(hardwareList.firstChild);

      const allowRemote = healthCache?.allow_remote_hardware;
      const maxShots = healthCache?.max_shots_per_experiment;

      if (hardwareMeta) {
        const parts = [];
        parts.push(`Backend: ${API_BASE}`);
        if (typeof allowRemote === 'boolean') parts.push(`allow_remote_hardware=${allowRemote}`);
        if (typeof maxShots === 'number') parts.push(`max_shots_per_experiment=${maxShots.toLocaleString()}`);
        hardwareMeta.textContent = parts.join(' · ');
      }

      const list = hardwareTargetsCache || [];
      if (!list.length) {
        const empty = document.createElement('div');
        empty.className = 'hint';
        empty.textContent = 'No targets loaded.';
        hardwareList.appendChild(empty);
        return;
      }

      list.forEach(t => {
        const item = document.createElement('div');
        item.className = 'hardware-item';
        item.setAttribute('role', 'listitem');

        const top = document.createElement('div');
        top.className = 'hardware-top';

        const name = document.createElement('div');
        name.className = 'hardware-name';
        name.textContent = t.name;

        const badge = document.createElement('div');
        badge.className = 'hardware-badge';
        badge.textContent = t.kind;

        top.appendChild(name);
        top.appendChild(badge);

        const meta1 = document.createElement('div');
        meta1.className = 'hardware-meta';
        meta1.textContent = `id: ${t.id}`;

        const meta2 = document.createElement('div');
        meta2.className = 'hardware-meta';
        meta2.textContent = t.description || '';

        item.appendChild(top);
        item.appendChild(meta1);
        item.appendChild(meta2);

        hardwareList.appendChild(item);
      });
    }

    async function runSelectedPreset() {
      const preset = presetSelect.value;
      const hardware_target = hardwareSelect.value;

      let shot_budget = Number.parseInt(String(shotInput.value || ''), 10);
      if (!Number.isFinite(shot_budget) || shot_budget <= 0) shot_budget = DEFAULT_SHOT_BUDGET;
      shot_budget = Math.min(Math.max(shot_budget, 1), MAX_SHOTS_PER_EXPERIMENT);

      const notes = (notesInput?.value || '').trim() || null;

      runPresetBtn.disabled = true;
      setRunStatus('Running preset…');

      try {
        const run = await apiPost('/experiments/run', { preset, hardware_target, shot_budget, notes });
        lastRun = run;

        // Update labels
        scenePresetLabel.textContent = presetLabel(preset).replace(' (T1/T2/RB)', '');
        sceneHardwareLabel.textContent = hardwareNameForId(hardware_target);

        applyRunToKpis(run, CONSOLE_KPI_IDS);
        sceneInterpretation.textContent = deriveInterpretationFromRun(run);

        // Refresh lists
        await refreshFromBackend();

        setRunStatus(`Run complete · id=${run.id}`);
      } catch (err) {
        setRunStatus(`Run failed: ${err.message}`);
      } finally {
        runPresetBtn.disabled = false;
      }
    }

    runPresetBtn.addEventListener('click', runSelectedPreset);

    // --------------------------------------------
    // Details view: load experiment record
    // --------------------------------------------
    async function openDetails(experimentId) {
      selectedExperimentId = experimentId;
      setActiveView('details');
      await refreshDetailsView();
    }

    async function refreshDetailsView() {
      if (!selectedExperimentId) {
        detailsHeader.textContent = 'No experiment selected yet. Go to Experiments and click a row.';
        detailsInterpretation.textContent = 'Select a run to see a plain-language summary here.';
        detailsJson.textContent = '{}';
        applyRunToKpis({ kpis: {} }, DETAILS_KPI_IDS);
        return;
      }

      try {
        const run = await apiGet(`/experiments/${selectedExperimentId}`);

        detailsHeader.textContent = `id=${run.id} · preset=${run.preset} · hardware=${hardwareNameForId(run.hardware_target)}`;
        detailsInterpretation.textContent = deriveInterpretationFromRun(run);
        detailsJson.textContent = JSON.stringify(run, null, 2);
        applyRunToKpis(run, DETAILS_KPI_IDS);
      } catch (err) {
        detailsHeader.textContent = `Could not load id=${selectedExperimentId}`;
        detailsInterpretation.textContent = `Error: ${err.message}`;
        detailsJson.textContent = '{}';
      }
    }

    detailsBackBtn.addEventListener('click', () => setActiveView(lastNonDetailsView));
    detailsReloadBtn.addEventListener('click', () => refreshDetailsView());

    // --------------------------------------------
    // Experiments / Hardware page controls
    // --------------------------------------------
    refreshExperimentsBtn.addEventListener('click', async () => {
      await refreshFromBackend();
      renderExperimentsTable();
    });

    refreshHardwareBtn.addEventListener('click', async () => {
      await refreshFromBackend();
      renderHardwareList();
    });

    function refreshExperimentsView(){
      // If we already have cache, render immediately; otherwise fetch.
      if (recentRunsCache && recentRunsCache.length) {
        renderExperimentsTable();
      } else {
        refreshFromBackend();
      }
    }

    function refreshHardwareView(){
      if (hardwareTargetsCache && hardwareTargetsCache.length) {
        renderHardwareList();
      } else {
        refreshFromBackend();
      }
    }

    // --------------------------------------------
    // Chat: safe rendering (no innerHTML)
    // --------------------------------------------
    function appendMessage(text, who) {
      const div = document.createElement('div');
      div.className = 'msg ' + (who === 'user' ? 'msg-user' : 'msg-agent');

      const label = document.createElement('strong');
      label.textContent = (who === 'user' ? 'You:' : 'SynQc Guide:');

      div.appendChild(label);
      div.appendChild(document.createTextNode(' '));
      div.appendChild(document.createTextNode(String(text)));

      chatPanel.appendChild(div);
      chatPanel.scrollTop = chatPanel.scrollHeight;
    }

    function interpretIntent(msg) {
      const lower = msg.toLowerCase();
      if (lower.includes('health') || lower.includes('stable') || lower.includes('coherence')) {
        presetSelect.value = 'health';
        scenePresetLabel.textContent = 'Qubit Health Diagnostics';
        return 'I will configure the Qubit Health Diagnostics suite (T1/T2*/echo, optional RB) ' +
               'for your selected backend. You can refine shot budget or backend in the Setup tab.';
      }
      if (lower.includes('latency')) {
        presetSelect.value = 'latency';
        scenePresetLabel.textContent = 'Latency Characterization';
        return 'I will prepare a Latency Characterization bundle with low-shot DPD probes to measure ' +
               'end-to-end and backend-only delay.';
      }
      if (lower.includes('compare') || lower.includes('backend')) {
        presetSelect.value = 'backend_compare';
        scenePresetLabel.textContent = 'Backend A/B Comparison';
        return 'I will set up a backend comparison run: your reference experiment will be replayed on two ' +
               'backends so we can compare fidelity and latency directly.';
      }
      if (lower.includes('example') || lower.includes('demo')) {
        presetSelect.value = 'dpd_demo';
        scenePresetLabel.textContent = 'Guided SynQc DPD Example';
        return 'I will walk you through a guided SynQc Drive–Probe–Drive example on a local simulator, ' +
               'explaining each step as we go.';
      }
      return 'I have recorded your goal. Use the Setup tab to pick the closest preset (Health, Latency, ' +
             'Backend Compare, or DPD Demo) and I will adapt it to your backend and constraints.';
    }

    agentSend.addEventListener('click', () => {
      const text = agentInput.value.trim();
      if (!text) return;
      appendMessage(text, 'user');
      agentInput.value = '';
      const reply = interpretIntent(text);
      appendMessage(reply, 'agent');
      updateInterpretationText();
    });

    agentInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') agentSend.click();
    });

    hardwareSelect.addEventListener('change', () => {
      sceneHardwareLabel.textContent = hardwareSelect.options[hardwareSelect.selectedIndex]?.text || hardwareSelect.value;
      updateInterpretationText();
    });

    presetSelect.addEventListener('change', () => {
      const val = presetSelect.value;
      scenePresetLabel.textContent = presetLabel(val);
      updateInterpretationText();
    });

    // --------------------------------------------
    // Boot
    // --------------------------------------------
    refreshFromBackend();
    updateInterpretationText();