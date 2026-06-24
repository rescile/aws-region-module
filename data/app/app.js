// ======================== APP STATE & HELPERS ========================
const MERMAID_CDN =
  "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js";

let mermaidReady = false;
let currentViewKey = null;
let currentTopoKey = null;
let isEnterprise = false;
let originalParams = {};
let currentZoom = 1;
let currentPanX = 0;
let currentPanY = 0;
let identityHeaders = [];
let identityData = [];
let buildEventSource = null;

// Global Utilities (used by app.js and graphql.js)
window.sanitizeId = function (str) {
  if (!str) return "unknown";
  return String(str)
    .replace(/[^a-zA-Z0-9_]/g, "_")
    .replace(/_{2,}/g, "_");
};

window.esc = function (str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/"/g, "#quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
};

window.resolveNames = function (rel) {
  if (!rel) return [];
  if (typeof rel === "string") return [rel];
  if (Array.isArray(rel)) {
    return rel
      .map((r) => {
        if (typeof r === "string") return r;
        if (r?.node?.name) return r.node.name;
        if (r?.name) return r.name;
        return null;
      })
      .filter(Boolean);
  }
  if (rel?.node?.name) return [rel.node.name];
  if (rel?.name) return [rel.name];
  return [];
};

function loadMermaid() {
  return new Promise((resolve, reject) => {
    if (mermaidReady) {
      resolve();
      return;
    }
    const script = document.createElement("script");
    script.src = MERMAID_CDN;
    script.onload = () => {
      mermaid.initialize({
        startOnLoad: false,
        theme: "base",
        securityLevel: "loose",
        themeVariables: {
          fontSize: "14px",
          primaryColor: "#f59e0b",
          fontFamily: "Inter, sans-serif",
        },
      });
      mermaidReady = true;
      resolve();
    };
    script.onerror = reject;
    document.head.appendChild(script);
  });
}

// ======================== API & GRAPHQL ========================
async function checkEnterpriseFeatures() {
  try {
    const res = await fetch("/api/features");
    if (res.ok) {
      const features = await res.json();
      if (features.includes("admin_assets")) {
        isEnterprise = true;
        document.getElementById("nav-account")?.classList.remove("hidden");
      } else {
        document.getElementById("readOnlyNotice")?.classList.remove("hidden");
      }
    } else {
      document.getElementById("readOnlyNotice")?.classList.remove("hidden");
    }
  } catch (err) {
    console.error("Failed to fetch features:", err);
    document.getElementById("readOnlyNotice")?.classList.remove("hidden");
  }
}

async function fetchGraphQL(query) {
  try {
    const response = await fetch("/graphql", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    });
    const result = await response.json();
    if (result.errors) {
      console.error("GraphQL Errors:", result.errors);
      const err = new Error(result.errors.map((e) => e.message).join(", "));
      err.query = query;
      throw err;
    }
    return result.data || {};
  } catch (error) {
    console.error("Failed to fetch graph data:", error);
    if (!error.query) error.query = query;
    throw error;
  }
}

// ======================== UI RENDERERS ========================
function setupNavigation() {
  const navMenu = document.getElementById("nav-menu");
  if (!navMenu) return;

  const settingsBtn = document.createElement("button");
  settingsBtn.className = `w-full text-left px-6 py-3 flex items-center text-sm font-medium transition-colors hover:bg-slate-800 hover:text-white text-slate-300 nav-btn hidden`;
  settingsBtn.id = `nav-account`;
  settingsBtn.innerHTML = `
        <svg class="w-5 h-5 mr-3 text-slate-500 group-hover:text-amber-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path></svg>
        Account
    `;
  settingsBtn.onclick = () => loadSettingsView();
  navMenu.appendChild(settingsBtn);

  if (window.VIEWS) {
    Object.keys(window.VIEWS).forEach((key) => {
      const view = window.VIEWS[key];
      const btn = document.createElement("button");
      btn.className = `w-full text-left px-6 py-3 flex items-center text-sm font-medium transition-colors hover:bg-slate-800 hover:text-white text-slate-300 nav-btn`;
      btn.id = `nav-${key}`;
      btn.innerHTML = `
                <svg class="w-5 h-5 mr-3 text-slate-500 group-hover:text-amber-500" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="${view.icon}"></path></svg>
                ${view.title}
            `;
      btn.onclick = () => loadView(key);
      navMenu.appendChild(btn);
    });
  }

  const pendingBtn = document.createElement("button");
  pendingBtn.className = `w-full text-left px-6 py-3 flex items-center text-sm font-medium transition-colors hover:bg-slate-800 hover:text-white text-slate-300 nav-btn`;
  pendingBtn.id = `nav-pending-changes`;
  pendingBtn.innerHTML = `
        <svg class="w-5 h-5 mr-3 text-slate-500 group-hover:text-amber-500" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
        Pending Changes
    `;
  pendingBtn.onclick = () => loadPendingChangesView();
  navMenu.appendChild(pendingBtn);

  if (window.TOPOLOGY_VIEWS) {
    const sep = document.createElement("span");
    sep.className = "nav-separator text-slate-500 mt-4";
    sep.textContent = "Topology Visualizations";
    navMenu.appendChild(sep);

    Object.keys(window.TOPOLOGY_VIEWS).forEach((key) => {
      const view = window.TOPOLOGY_VIEWS[key];
      const btn = document.createElement("button");
      btn.className = `w-full text-left px-6 py-3 flex items-center text-sm font-medium transition-colors hover:bg-slate-800 hover:text-white text-slate-300 nav-btn`;
      btn.id = `nav-${key}`;
      btn.innerHTML = `
                <svg class="w-5 h-5 mr-3 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="${view.icon}"></path></svg>
                ${view.title}
            `;
      btn.onclick = () => loadTopologyView(key);
      navMenu.appendChild(btn);
    });
  }
}

function setActiveNav(navId) {
  document.querySelectorAll(".nav-btn").forEach((btn) => {
    btn.classList.remove(
      "bg-slate-800",
      "text-white",
      "border-l-4",
      "border-amber-500",
    );
    btn.classList.add("text-slate-300");
  });
  const activeBtn = document.getElementById(navId);
  if (!activeBtn) return;
  activeBtn.classList.remove("text-slate-300");
  activeBtn.classList.add(
    "bg-slate-800",
    "text-white",
    "border-l-4",
    "border-amber-500",
  );
}

// Resilient Cell Data Formatter
function formatCellData(value) {
  if (value === null || value === undefined || value === "")
    return '<span class="text-slate-300">-</span>';
  if (typeof value === "boolean") {
    return value
      ? '<span class="px-2 py-1 text-xs font-semibold rounded-full bg-green-100 text-green-800">Yes</span>'
      : '<span class="px-2 py-1 text-xs font-semibold rounded-full bg-red-100 text-red-800">No</span>';
  }
  if (Array.isArray(value)) {
    if (value.length === 0) return '<span class="text-slate-300">-</span>';
    if (typeof value[0] === "object" && value[0] !== null) {
      // Unpack Relay/GraphQL nodes safely
      if ("node" in value[0]) {
        return value
          .map((v) => {
            const n = v?.node || {};
            return n.name || n.function || n.id || n.cidr || JSON.stringify(n);
          })
          .filter(Boolean)
          .join(", ");
      }
      return value.map((v) => JSON.stringify(v)).join(", ");
    }
    return value.join(", ");
  }
  if (typeof value === "object") {
    // Fallback for nested objects
    return `<pre class="text-xs text-slate-600 bg-slate-50 p-1 rounded border border-slate-100 max-h-24 overflow-y-auto">${JSON.stringify(value, null, 2)}</pre>`;
  }
  return String(value);
}

// Resilient Table Renderer
function renderTable(data, predefinedColumns) {
  if (!data || !Array.isArray(data) || data.length === 0) {
    return `<div class="p-12 text-center text-slate-500 flex flex-col items-center">
                    <svg class="w-12 h-12 mb-4 text-slate-300" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4"></path></svg>
                    <p>No records found for this infrastructure component.</p>
                </div>`;
  }

  // Dynamic fallback if columns aren't provided by GraphQL definitions
  let columns = predefinedColumns;
  if (!columns || columns.length === 0) {
    const keys = new Set();
    data.forEach((item) => {
      if (item)
        Object.keys(item).forEach((k) => k !== "__typename" && keys.add(k));
    });
    columns = Array.from(keys);
  }

  let thead = columns
    .map(
      (c) =>
        `<th class="px-6 py-3 text-left text-xs font-bold text-slate-600 uppercase tracking-wider bg-slate-50 sticky top-0 shadow-sm border-b border-slate-200">${c.replace(/_/g, " ")}</th>`,
    )
    .join("");

  let tbody = data
    .map((row) => {
      if (!row) return "";
      let tr = columns
        .map(
          (c) =>
            `<td class="px-6 py-4 text-sm text-slate-700 align-top border-t border-slate-100">${formatCellData(row[c])}</td>`,
        )
        .join("");
      return `<tr class="hover:bg-amber-50 transition-colors group">${tr}</tr>`;
    })
    .join("");

  return `<div class="table-container overflow-x-auto overflow-y-auto h-full max-h-[calc(100vh-8rem)]">
                <table class="min-w-full divide-y divide-slate-200">
                    <thead><tr>${thead}</tr></thead>
                    <tbody class="bg-white divide-y divide-slate-100">${tbody}</tbody>
                </table>
            </div>`;
}

// Loads basic list view
window.loadView = async function (viewKey) {
  if (!window.VIEWS || !window.VIEWS[viewKey]) return;

  currentViewKey = viewKey;
  currentTopoKey = null;
  const viewConfig = window.VIEWS[viewKey];

  document.getElementById("view-title").innerText = viewConfig.title;
  setActiveNav(`nav-${viewKey}`);

  const loader = document.getElementById("loader");
  const container = document.getElementById("content-container");

  loader?.classList.remove("hidden");

  try {
    const data = await fetchGraphQL(viewConfig.query);
    let nodes = data[viewConfig.node] || [];
    container.innerHTML = renderTable(nodes, viewConfig.columns);
  } catch (error) {
    container.innerHTML = `<div class="p-6 text-red-600 bg-red-50 m-4 rounded border border-red-200">
            <strong>Error fetching data:</strong> ${error.message}
            ${error.query ? `<pre class="mt-2 text-xs bg-white p-2 rounded overflow-auto max-h-48 text-slate-700 font-mono">${esc(error.query)}</pre>` : ""}
        </div>`;
  } finally {
    loader?.classList.add("hidden");
  }
};

window.loadPendingChangesView = async function () {
  currentViewKey = "pending-changes";
  currentTopoKey = null;

  document.getElementById("view-title").innerText = "Pending Changes";
  setActiveNav("nav-pending-changes");

  const loader = document.getElementById("loader");
  const container = document.getElementById("content-container");

  loader?.classList.remove("hidden");

  try {
    // Fetch declared state from GraphQL
    const data = await fetchGraphQL(
      `{ gateway { name pid private_dns_enabled } }`,
    );
    const gateways = data.gateway || [];

    // Fetch live state from provider APIs via our proxy
    let liveState = [];
    try {
      const res = await fetch("api/provider/state");
      if (res.ok) {
        liveState = await res.json();
      } else {
        console.warn("Could not fetch live state, using empty state");
      }
    } catch (e) {
      console.warn("Provider API error:", e);
    }

    // Combine for table
    const rows = gateways.map((g) => {
      const live = liveState.find((l) => l.id === g.pid) || {};
      return {
        resource: g.name || "Unknown",
        declared_state: JSON.stringify({
          pid: g.pid,
          private_dns_enabled: g.private_dns_enabled,
        }),
        live_state: Object.keys(live).length ? JSON.stringify(live) : "-",
      };
    });

    container.innerHTML = renderTable(rows, [
      "resource",
      "declared_state",
      "live_state",
    ]);
  } catch (error) {
    container.innerHTML = `<div class="p-6 text-red-600 bg-red-50 m-4 rounded border border-red-200">
            <strong>Error fetching data:</strong> ${error.message}
        </div>`;
  } finally {
    loader?.classList.add("hidden");
  }
};

// Loads diagram visualizations
window.loadTopologyView = async function (topoKey) {
  if (!window.TOPOLOGY_VIEWS || !window.TOPOLOGY_VIEWS[topoKey]) return;

  currentTopoKey = topoKey;
  currentViewKey = null;
  const topoConfig = window.TOPOLOGY_VIEWS[topoKey];
  let diagramDef = "";

  document.getElementById("view-title").innerText = topoConfig.title;
  setActiveNav(`nav-${topoKey}`);

  const loader = document.getElementById("loader");
  const container = document.getElementById("content-container");
  loader?.classList.remove("hidden");

  try {
    await loadMermaid();
    const query = topoConfig.buildQuery();
    const data = await fetchGraphQL(query);
    diagramDef = topoConfig.buildDiagram(data);

    const diagramId = "mermaid-" + topoKey + "-" + Date.now();
    const { svg } = await mermaid.render(diagramId, diagramDef);

    container.innerHTML = `
            <div class="diagram-toolbar">
                <span class="badge">${topoConfig.title}</span>
                <span class="text-xs text-slate-500 ml-2 hidden md:inline">${topoConfig.description}</span>
                <div class="flex gap-1 ml-auto border border-slate-200 rounded-lg p-0.5 bg-slate-100">
                    <button class="tab-btn active" id="tab-diagram-btn" onclick="switchDiagramTab('diagram')">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 5a1 1 0 011-1h14a1 1 0 011 1v2a1 1 0 01-1 1H5a1 1 0 01-1-1V5zM4 13a1 1 0 011-1h6a1 1 0 011 1v6a1 1 0 01-1 1H5a1 1 0 01-1-1v-6zM16 13a1 1 0 011-1h2a1 1 0 011 1v6a1 1 0 01-1 1h-2a1 1 0 01-1-1v-6z"></path></svg>
                        Visual
                    </button>
                    <button class="tab-btn" id="tab-code-btn" onclick="switchDiagramTab('code')">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4"></path></svg>
                        Source
                    </button>
                </div>
                <div class="flex gap-2">
                    <button onclick="zoomDiagram(1.2)" title="Zoom In">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0zM10 7v3m0 0v3m0-3h3m-3 0H7"></path></svg>
                    </button>
                    <button onclick="zoomDiagram(0.8)" title="Zoom Out">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0zM13 10H7"></path></svg>
                    </button>
                    <button onclick="zoomDiagram(0)" title="Reset Zoom">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path></svg>
                    </button>
                </div>
            </div>
            <div class="diagram-wrapper">
                <div class="diagram-container bg-slate-50" id="diagram-content">${svg}</div>
                <div class="diagram-code-container" id="diagram-code-content">
                    <div class="flex items-center justify-between mb-3">
                        <span class="text-sm font-medium text-slate-700">Mermaid Graph Code</span>
                        <button onclick="copyDiagramCode()" class="tab-btn text-xs" id="copy-code-btn">
                            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"></path></svg>
                            Copy Script
                        </button>
                    </div>
                    <pre id="diagram-code-text"></pre>
                </div>
            </div>
        `;

    const codeEl = document.getElementById("diagram-code-text");
    if (codeEl) codeEl.textContent = diagramDef;
    setupDiagramPanZoom();
  } catch (error) {
    container.innerHTML = `<div class="p-6 text-red-600 bg-red-50 m-4 rounded border border-red-200">
            <strong>Error rendering network topology:</strong> ${error.message}
            ${error.query ? `<pre class="mt-2 text-xs bg-white p-2 rounded overflow-auto max-h-48 text-slate-700 font-mono">${esc(error.query)}</pre>` : ""}
            <pre class="mt-2 text-xs bg-white p-2 rounded overflow-auto max-h-48">${error.stack || ""}</pre>
        </div>`;
  } finally {
    loader?.classList.add("hidden");
  }
};

// ======================== DIAGRAM INTERACTIONS ========================
window.switchDiagramTab = function (tab) {
  const diagramEl = document.getElementById("diagram-content");
  const codeEl = document.getElementById("diagram-code-content");
  const diagramBtn = document.getElementById("tab-diagram-btn");
  const codeBtn = document.getElementById("tab-code-btn");
  if (!diagramEl || !codeEl) return;

  if (tab === "code") {
    diagramEl.style.display = "none";
    codeEl.style.display = "block";
    diagramBtn?.classList.remove("active");
    codeBtn?.classList.add("active");
  } else {
    diagramEl.style.display = "block";
    codeEl.style.display = "none";
    diagramBtn?.classList.add("active");
    codeBtn?.classList.remove("active");
  }
};

window.copyDiagramCode = function () {
  const codeEl = document.getElementById("diagram-code-text");
  if (!codeEl) return;
  navigator.clipboard.writeText(codeEl.textContent).then(() => {
    const btn = document.getElementById("copy-code-btn");
    if (btn) {
      const orig = btn.innerHTML;
      btn.innerHTML =
        '<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg> Copied!';
      setTimeout(() => {
        btn.innerHTML = orig;
      }, 2000);
    }
  });
};

function setupDiagramPanZoom() {
  const el = document.getElementById("diagram-content");
  if (!el) return;
  currentZoom = 1;

  let isDragging = false;
  let startX, startY, scrollLeft, scrollTop;

  el.addEventListener("mousedown", (e) => {
    if (e.button !== 0) return;
    isDragging = true;
    el.classList.add("dragging");
    startX = e.pageX - el.offsetLeft;
    startY = e.pageY - el.offsetTop;
    scrollLeft = el.scrollLeft;
    scrollTop = el.scrollTop;
    e.preventDefault();
  });

  el.addEventListener("mousemove", (e) => {
    if (!isDragging) return;
    const x = e.pageX - el.offsetLeft;
    const y = e.pageY - el.offsetTop;
    el.scrollLeft = scrollLeft - (x - startX);
    el.scrollTop = scrollTop - (y - startY);
  });

  const stopDrag = () => {
    isDragging = false;
    el.classList.remove("dragging");
  };
  el.addEventListener("mouseup", stopDrag);
  el.addEventListener("mouseleave", stopDrag);

  el.addEventListener(
    "wheel",
    (e) => {
      e.preventDefault();
      const factor = e.deltaY < 0 ? 1.1 : 0.9;
      window.zoomDiagram(factor);
    },
    { passive: false },
  );
}

window.zoomDiagram = function (factor) {
  const el = document.getElementById("diagram-content");
  if (!el) return;
  const svg = el.querySelector("svg");
  if (!svg) return;

  if (factor === 0) {
    currentZoom = 1;
  } else {
    currentZoom *= factor;
  }
  currentZoom = Math.max(0.2, Math.min(currentZoom, 5));
  svg.style.transform = `scale(${currentZoom})`;
  svg.style.transformOrigin = "top left";
};

// ======================== SETTINGS & CONFIG ========================
function parseCSV(text) {
  const lines = text.trim().split("\n");
  if (lines.length === 0 || lines[0] === "") return { headers: [], rows: [] };
  const headers = lines[0].split(",").map((h) => h.trim());
  const rows = lines
    .slice(1)
    .filter((l) => l.trim() !== "")
    .map((line) => line.split(",").map((c) => c.trim()));
  return { headers, rows };
}

function serializeCSV(headers, rows) {
  const h = headers.join(",");
  const r = rows.map((row) => row.join(",")).join("\n");
  return h + (r ? "\n" + r : "");
}

function renderIdentityTable() {
  const thead = document.getElementById("identityThead");
  const tbody = document.getElementById("identityTbody");
  if (!thead || !tbody) return;

  if (identityHeaders.length === 0) {
    thead.innerHTML = "";
    tbody.innerHTML =
      '<tr><td class="p-4 text-center text-slate-500">No data</td></tr>';
    return;
  }

  let thHtml = "<tr>";
  identityHeaders.forEach((h) => {
    thHtml += `<th class="px-3 py-2 text-left font-medium text-slate-600">${esc(h)}</th>`;
  });
  thHtml += `<th class="px-3 py-2 text-right font-medium text-slate-600 w-16">Actions</th></tr>`;
  thead.innerHTML = thHtml;

  let tbHtml = "";
  if (identityData.length === 0) {
    tbHtml = `<tr><td colspan="${identityHeaders.length + 1}" class="p-4 text-center text-slate-500">No identities found. Add a row to start.</td></tr>`;
  } else {
    identityData.forEach((row, rowIndex) => {
      tbHtml += '<tr class="hover:bg-slate-50">';
      identityHeaders.forEach((_, colIndex) => {
        tbHtml += `<td class="px-2 py-1"><input type="text" value="${esc(row[colIndex] || "")}" onchange="updateIdentityData(${rowIndex}, ${colIndex}, this.value)" class="w-full text-xs p-1.5 border border-transparent hover:border-slate-300 focus:border-amber-500 rounded bg-transparent focus:bg-white transition-colors"></td>`;
      });
      tbHtml += `<td class="px-2 py-1 text-right"><button type="button" onclick="deleteIdentityRow(${rowIndex})" class="text-red-400 hover:text-red-600 p-1.5 rounded hover:bg-red-50 transition" title="Delete"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg></button></td></tr>`;
    });
  }
  tbody.innerHTML = tbHtml;
}

window.updateIdentityData = function (row, col, value) {
  if (identityData[row]) identityData[row][col] = value;
};

window.addIdentityRow = function () {
  if (identityHeaders.length === 0) {
    identityHeaders = ["type", "name", "function", "role"];
  }
  identityData.push(new Array(identityHeaders.length).fill(""));
  renderIdentityTable();
};

window.deleteIdentityRow = function (index) {
  identityData.splice(index, 1);
  renderIdentityTable();
};

window.loadSettingsView = async function () {
  currentViewKey = "account";
  currentTopoKey = null;
  document.getElementById("view-title").innerText = "Cloud Management";
  setActiveNav("nav-account");

  const container = document.getElementById("content-container");
  container.innerHTML = `
        <div class="p-8 overflow-y-auto flex-1 bg-white">
            <div class="mb-6">
                <h4 class="text-sm font-semibold text-slate-700 mb-3 border-b pb-2">Settings</h4>
                <form id="paramsForm" class="space-y-4">
                    <div id="paramsContainer" class="space-y-3">
                        <div class="text-sm text-slate-500">Loading parameters...</div>
                    </div>
                </form>
            </div>
            <div class="mb-6">
                <div class="flex justify-between items-center mb-3 border-b pb-2">
                    <h4 class="text-sm font-semibold text-slate-700">Administrators</h4>
                    <button type="button" onclick="addIdentityRow()" class="text-xs bg-amber-100 text-amber-700 hover:bg-amber-200 px-2 py-1 rounded font-medium flex items-center transition">
                        <svg class="w-3 h-3 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"></path></svg>
                        Add Row
                    </button>
                </div>
                <div class="overflow-x-auto border border-slate-200 rounded-lg max-h-60 overflow-y-auto">
                    <table class="min-w-full divide-y divide-slate-200 text-xs" id="identityTable">
                        <thead class="bg-slate-50 sticky top-0 z-10" id="identityThead"></thead>
                        <tbody class="bg-white divide-y divide-slate-100" id="identityTbody"></tbody>
                    </table>
                </div>
            </div>
            <div class="pt-4 border-t border-slate-200 flex justify-end gap-3">
                <button onclick="saveConfig()" class="px-4 py-2 text-sm font-medium text-white bg-amber-600 rounded hover:bg-amber-700 transition flex items-center">
                    <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>
                    Save & Rebuild
                </button>
            </div>
        </div>
    `;

  // Fetch Params
  try {
    const pRes = await fetch("/api/module-params");
    if (pRes.ok) {
      const fetchedParams = await pRes.json();
      originalParams = {};
      const paramsContainer = document.getElementById("paramsContainer");
      paramsContainer.innerHTML = "";
      for (const [key, paramData] of Object.entries(fetchedParams)) {
        let val = paramData.value !== undefined ? paramData.value : paramData;
        let allowed = paramData.allowed_values || [];
        originalParams[key] = val;

        let inputHtml = "";
        if (allowed.length > 0) {
          let options = allowed
            .map(
              (opt) =>
                `<option value="${esc(opt)}" ${opt === val ? "selected" : ""}>${esc(opt)}</option>`,
            )
            .join("");
          inputHtml = `<select id="param_${key}" class="w-full text-sm p-2 border border-slate-300 rounded focus:ring-amber-500 focus:border-amber-500 bg-white">${options}</select>`;
        } else {
          inputHtml = `<input type="text" id="param_${key}" value="${esc(val)}" class="w-full text-sm p-2 border border-slate-300 rounded focus:ring-amber-500 focus:border-amber-500">`;
        }
        paramsContainer.innerHTML += `
                    <div>
                        <label class="block text-xs font-semibold text-slate-600 mb-1">${esc(key)}</label>
                        ${inputHtml}
                    </div>
                `;
      }
    }
  } catch (err) {
    console.error("Failed to fetch module params:", err);
  }

  // Fetch CSV
  try {
    const aRes = await fetch("/api/assets/identity.csv");
    if (aRes.ok) {
      const csvContent = await aRes.text();
      const parsed = parseCSV(csvContent);
      identityHeaders = parsed.headers;
      identityData = parsed.rows;
      renderIdentityTable();
    }
  } catch (err) {
    console.error("Failed to fetch identity.csv:", err);
  }
};

window.saveConfig = async function () {
  const btn = document.querySelector("#content-container button.bg-amber-600");
  if (!btn) return;
  const origHtml = btn.innerHTML;
  btn.innerHTML = "Saving...";
  btn.disabled = true;

  try {
    const newParams = { ...originalParams };
    for (const key of Object.keys(originalParams)) {
      const el = document.getElementById(`param_${key}`);
      if (el) newParams[key] = el.value;
    }

    await fetch("/api/module-params", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(newParams),
    });

    const csvData = serializeCSV(identityHeaders, identityData);
    const formData = new FormData();
    formData.append("update", csvData);
    await fetch("/api/assets/identity.csv", {
      method: "POST",
      body: formData,
    });

    window.showBuildModal();
  } catch (err) {
    console.error("Failed to save config:", err);
    alert("Failed to save configuration. Check console for details.");
  } finally {
    btn.innerHTML = origHtml;
    btn.disabled = false;
  }
};

// ======================== BUILD & SYNC ========================
window.refreshCurrentView = function () {
  if (currentViewKey === "account") {
    window.loadSettingsView();
  } else if (currentViewKey) {
    window.loadView(currentViewKey);
  } else if (currentTopoKey) {
    window.loadTopologyView(currentTopoKey);
  }
  updateGraphStats();
};

async function updateGraphStats() {
  try {
    const data = await fetchGraphQL(`{ countNodes }`);
    const target = document.getElementById("total-nodes");
    if (target) target.innerText = data.countNodes || 0;
  } catch (e) {
    const target = document.getElementById("total-nodes");
    if (target) target.innerText = "Offline";
  }
}

window.showBuildModal = function () {
  const logsEl = document.getElementById("buildLogs");
  const closeBtn = document.getElementById("buildCloseBtn");
  const titleEl = document.getElementById("modalTitleText");
  if (titleEl) titleEl.textContent = "Building Graph...";
  if (!logsEl || !closeBtn) return;

  logsEl.textContent = "";
  closeBtn.disabled = true;
  closeBtn.textContent = "Building...";
  closeBtn.classList.remove(
    "text-white",
    "bg-amber-600",
    "hover:bg-amber-700",
    "cursor-pointer",
  );
  closeBtn.classList.add(
    "text-slate-400",
    "bg-slate-100",
    "cursor-not-allowed",
  );

  document.getElementById("buildModal")?.classList.remove("hidden");

  if (buildEventSource) buildEventSource.close();
  buildEventSource = new EventSource("/api/build/stream");

  buildEventSource.onmessage = function (event) {
    const msg = event.data;
    if (msg === "BUILD_COMPLETE") {
      buildEventSource.close();
      closeBtn.disabled = false;
      closeBtn.textContent = "Close & Refresh";
      closeBtn.classList.remove(
        "text-slate-400",
        "bg-slate-100",
        "cursor-not-allowed",
      );
      closeBtn.classList.add(
        "text-white",
        "bg-amber-600",
        "hover:bg-amber-700",
        "cursor-pointer",
      );
    } else {
      logsEl.textContent += msg + "\n";
      logsEl.scrollTop = logsEl.scrollHeight;
    }
  };

  buildEventSource.onerror = function () {
    buildEventSource.close();
    closeBtn.disabled = false;
    closeBtn.textContent = "Close (Error)";
    closeBtn.classList.remove(
      "text-slate-400",
      "bg-slate-100",
      "cursor-not-allowed",
    );
    closeBtn.classList.add(
      "text-white",
      "bg-red-600",
      "hover:bg-red-700",
      "cursor-pointer",
    );
  };
};

window.closeBuildModal = function () {
  document.getElementById("buildModal")?.classList.add("hidden");
  window.refreshCurrentView();
};

// ======================== BROWSER SIDE EXECUTION ENGINE ========================
// Replaces previous JS simulator with actual Rescile Action API calls using rescile-runner

window.executeEngine = async function (action) {
  const logsEl = document.getElementById("buildLogs");
  const closeBtn = document.getElementById("buildCloseBtn");
  const titleEl = document.getElementById("modalTitleText");
  if (titleEl) titleEl.textContent = "Executing Action...";

  document.getElementById("buildModal")?.classList.remove("hidden");
  if (logsEl)
    logsEl.textContent = `=== STARTING ACTION: ${action.toUpperCase()} ===\nRequesting execution bundle from Rescile Engine...\n`;
  if (closeBtn) {
    closeBtn.disabled = true;
    closeBtn.textContent = "Running...";
    closeBtn.classList.remove(
      "text-white",
      "bg-amber-600",
      "hover:bg-amber-700",
      "cursor-pointer",
    );
    closeBtn.classList.add(
      "text-slate-400",
      "bg-slate-100",
      "cursor-not-allowed",
    );
  }

  try {
    // 1. Fetch the execution bundle from Rescile Engine
    const bundleResponse = await fetch(
      `/api/actions/aws-transit-hub/${action}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      },
    );

    if (!bundleResponse.ok) {
      throw new Error(
        `Failed to fetch action bundle: ${bundleResponse.status} ${bundleResponse.statusText}`,
      );
    }

    const blob = await bundleResponse.blob();
    if (logsEl)
      logsEl.textContent += `Bundle downloaded. Starting rescile-runner daemon...\n`;

    // 2. Post the artifact to the daemon runner
    const formData = new FormData();
    formData.append("bundle", blob, `${action}.tar.gz`);
    formData.append("inputs", JSON.stringify({}));

    const runnerResponse = await fetch("api/runner/execute", {
      method: "POST",
      body: formData,
    });

    if (!runnerResponse.ok) {
      let errorText = await runnerResponse.text();
      throw new Error(
        `Runner failed to execute: ${runnerResponse.status} ${errorText}`,
      );
    }

    const data = await runnerResponse.json();
    const executionId = data.execution_id;

    if (!executionId) {
      throw new Error("No execution ID returned from the runner.");
    }

    if (logsEl)
      logsEl.textContent += `Runner accepted execution. Execution ID: ${executionId}\nStreaming logs...\n\n`;

    // 3. Listen to execution stream
    if (buildEventSource) buildEventSource.close();
    buildEventSource = new EventSource(`api/runner/execute/${executionId}`);

    buildEventSource.onmessage = function (event) {
      const msg = event.data;
      if (
        msg === "Execution completed successfully" ||
        msg.includes("EXECUTION_COMPLETE")
      ) {
        // Keep the stream open just to receive any trailing events,
        // but we know it's done. The runner should close it automatically.
        if (closeBtn) {
          closeBtn.disabled = false;
          closeBtn.textContent = "Close & Refresh";
          closeBtn.classList.remove(
            "text-slate-400",
            "bg-slate-100",
            "cursor-not-allowed",
          );
          closeBtn.classList.add(
            "text-white",
            "bg-amber-600",
            "hover:bg-amber-700",
            "cursor-pointer",
          );
        }
      }
      if (logsEl) {
        logsEl.textContent += msg + "\n";
        logsEl.scrollTop = logsEl.scrollHeight;
      }
    };

    buildEventSource.onerror = function () {
      buildEventSource.close();
      if (closeBtn && closeBtn.disabled) {
        closeBtn.disabled = false;
        closeBtn.textContent = "Close (Stream ended)";
        closeBtn.classList.remove(
          "text-slate-400",
          "bg-slate-100",
          "cursor-not-allowed",
        );
        closeBtn.classList.add(
          "text-white",
          "bg-blue-600",
          "hover:bg-blue-700",
          "cursor-pointer",
        );
      }
    };
  } catch (e) {
    if (logsEl) {
      logsEl.textContent += `\n[ERROR] Execution failed: ${e.message}\n`;
    }
    if (closeBtn) {
      closeBtn.disabled = false;
      closeBtn.textContent = "Close (Error)";
      closeBtn.classList.remove(
        "text-slate-400",
        "bg-slate-100",
        "cursor-not-allowed",
      );
      closeBtn.classList.add(
        "text-white",
        "bg-red-600",
        "hover:bg-red-700",
        "cursor-pointer",
      );
      closeBtn.onclick = () => {
        document.getElementById("buildModal")?.classList.add("hidden");
      };
    }
  } finally {
    if (closeBtn) {
      closeBtn.onclick = () => {
        document.getElementById("buildModal")?.classList.add("hidden");
        refreshCurrentView();
      };
    }
  }
};

// ======================== INITIALIZATION ========================
window.onload = () => {
  setupNavigation();
  checkEnterpriseFeatures();
  updateGraphStats();
  if (window.VIEWS && Object.keys(window.VIEWS).length > 0) {
    window.loadView(Object.keys(window.VIEWS)[0]);
  }
};
