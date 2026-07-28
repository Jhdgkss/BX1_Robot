const NAVIGATION = [
  { section: "Overview", id: "dashboard", label: "Dashboard", icon: "grid" },
  { section: "Manage", id: "system", label: "System", icon: "system" },
  { section: "Manage", id: "services", label: "Services", icon: "services" },
  { section: "Manage", id: "hardware", label: "Hardware", icon: "hardware" },
  { section: "Manage", id: "audio", label: "Audio", icon: "logs" },
  { section: "Manage", id: "brain", label: "Brain", icon: "brain" },
  { section: "Manage", id: "configuration", label: "Configuration", icon: "config" },
  { section: "Observe", id: "logs", label: "Logs", icon: "logs" },
  { section: "Observe", id: "deployment", label: "Deployment", icon: "deploy" },
  { section: "Observe", id: "diagnostics", label: "Diagnostics", icon: "diagnostics" },
  { section: "Platform", id: "updates", label: "Updates", icon: "updates" },
  { section: "Platform", id: "about", label: "About", icon: "about" },
];

const PAGE_META = {
  dashboard: ["Command centre", "System overview", "A high-level view of BX1 OS, its resources and connected systems."],
  system: ["Host platform", "System information", "Operating system, runtime and hardware identity for this BX1 host."],
  services: ["Service orchestration", "Managed services", "A unified home for BX1 OS service state, controls and logs."],
  hardware: ["Device inventory", "Hardware", "Read-only discovery, ownership and health for detected robot devices."],
  audio: ["Audio telemetry", "Audio", "Read-only microphone, speaker, level, STT and TTS observations."],
  brain: ["Intelligence layer", "Brain", "Connection, models, voice and memory will be managed from this workspace."],
  configuration: ["Platform settings", "Configuration", "A searchable, categorised configuration workspace with safe revision controls."],
  logs: ["System events", "Logs", "Live, filterable BX1 OS logs will appear here without mixing with the legacy UI."],
  deployment: ["Release lifecycle", "Deployment", "Versions, qualification history, rollback points and deployment evidence."],
  diagnostics: ["Platform health", "Diagnostics", "Read-only checks and future guided diagnostics for the BX1 platform."],
  updates: ["Release channel", "Updates", "Future update discovery, review and controlled installation."],
  about: ["Platform identity", "About BX1 OS", "Release provenance and architecture information for this installation."],
};

const fallbackData = {
  interface: {
    id: "bx1-os-management",
    name: "BX1 OS Management",
    version: "0.4.0",
    tag: "BX1_OS_ALPHA_v0.4.0",
    architecture_only: true,
    capabilities: {},
  },
  robot: {
    name: "BX1",
    status: "Qualification",
    mode: "Observer only",
    hostname: "bx1",
    ip: "Detected by browser",
    existing_ui_port: 8088,
    management_port: 8089,
  },
  brain: { status: "Not connected", url: "" },
  system: {
    python: "Pending",
    os: "Pending",
    kernel: "Pending",
    architecture: "Pending",
    hostname: "Pending",
    serial: "Pending integration",
    update_channel: "alpha",
    cpu: null,
    ram: null,
    disk: null,
    temperature: null,
    network: "Management interface online",
    uptime_seconds: 0,
  },
  services: [],
  hardware: { inventory: [], diagnostics: { checks: [] } },
  audio: {
    microphones: [],
    speakers: [],
    input: {},
    output: {},
    stt: {},
    tts: {},
  },
  robot_body: { connected: false, version: "unknown", health: "unavailable" },
  deployment: {
    current_version: "0.4.0",
    commit: "Provided by release manifest",
    branch: "Provided by release manifest",
    tag: "BX1_OS_ALPHA_v0.4.0",
    build_date: "Provided by release manifest",
    previous_versions: [],
    rollback_points: [],
    qualification_history: [],
    deployment_history: [],
  },
};

const state = {
  page: routeFromLocation(),
  data: fallbackData,
  connected: false,
  telemetryLoading: false,
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, char => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[char]));
const icon = (name) => `<svg aria-hidden="true"><use href="#icon-${name}"></use></svg>`;
const display = (value, fallback = "Pending integration") =>
  value === null || value === undefined || value === "" ? fallback : esc(value);
const formatUptime = (seconds) => {
  const total = Math.max(0, Number(seconds) || 0);
  const days = Math.floor(total / 86400);
  const hours = Math.floor((total % 86400) / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  return days ? `${days}d ${hours}h` : hours ? `${hours}h ${minutes}m` : `${minutes}m`;
};
const formatPercent = (value) =>
  value === null || value === undefined ? null : `${Number(value).toFixed(1)}%`;
const formatTemperature = (value) =>
  value === null || value === undefined ? null : `${Number(value).toFixed(1)} °C`;
const observed = (item, fallback = null) =>
  item && typeof item === "object" && Object.prototype.hasOwnProperty.call(item, "value")
    ? item.value
    : item ?? fallback;
const observedMeta = (item) => ({
  source: item?.source || "Unknown",
  timestamp: item?.timestamp || null,
  quality: item?.quality || "unknown",
  stale: Boolean(item?.stale),
});
const formatTimestamp = (value) => {
  if (!value) return "Never";
  const numeric = Number(value);
  const parsed = Number.isFinite(numeric)
    ? new Date(numeric * 1000)
    : new Date(String(value));
  return Number.isNaN(parsed.getTime()) ? "Unavailable" : parsed.toLocaleString();
};

function routeFromLocation() {
  const route = location.pathname.replace(/^\/+|\/+$/g, "");
  return NAVIGATION.some(item => item.id === route) ? route : "dashboard";
}

function button(label, options = {}) {
  const {
    iconName = "",
    className = "",
    prototype = "",
    href = "",
    disabled = false,
    coreRefresh = false,
  } = options;
  const attrs = [
    `class="button ${className}"`,
    prototype ? `data-prototype="${esc(prototype)}"` : "",
    coreRefresh ? 'data-core-refresh="true"' : "",
    disabled ? `aria-disabled="true"` : "",
  ].filter(Boolean).join(" ");
  const content = `${iconName ? icon(iconName) : ""}<span>${esc(label)}</span>`;
  return href
    ? `<a ${attrs} href="${esc(href)}" target="_blank" rel="noopener">${content}</a>`
    : `<button ${attrs} type="button">${content}</button>`;
}

function panel(title, body, options = {}) {
  const { span = 12, subtitle = "", aside = "", className = "" } = options;
  return `
    <section class="panel span-${span} ${className}">
      <header class="panel-header">
        <div><h3>${esc(title)}</h3>${subtitle ? `<p>${esc(subtitle)}</p>` : ""}</div>
        ${aside}
      </header>
      <div class="panel-body">${body}</div>
    </section>`;
}

function emptyPanel(iconName, title, text, action = "") {
  return `
    <div class="panel-empty">
      <div>
        <div class="empty-icon">${icon(iconName)}</div>
        <h3>${esc(title)}</h3>
        <p>${esc(text)}</p>
        ${action ? `<div class="page-actions" style="justify-content:center;margin-top:18px">${action}</div>` : ""}
      </div>
    </div>`;
}

function badge(label, tone = "", dot = true) {
  return `<span class="status-badge ${tone}">${dot ? '<span class="status-dot"></span>' : ""}${esc(label)}</span>`;
}

function dataList(rows) {
  return `<dl class="data-list">${rows.map(([key, value, mono = false]) =>
    `<div class="data-row"><dt>${esc(key)}</dt><dd class="${mono ? "mono" : ""}">${display(value)}</dd></div>`
  ).join("")}</dl>`;
}

function metricCard(label, value, detail, iconName, tone = "") {
  return `
    <article class="panel metric-card span-3">
      <div class="metric-top">
        <span class="metric-label">${esc(label)}</span>
        <span class="metric-icon ${tone}">${icon(iconName)}</span>
      </div>
      <div class="metric-value">${display(value)}</div>
      <div class="metric-detail">${esc(detail)}</div>
    </article>`;
}

function dashboardPage(data) {
  const oldUi = `http://${location.hostname}:${data.robot.existing_ui_port || 8088}`;
  const cards = [
    ["BX1 OS Version", `v${data.interface.version}`, data.interface.tag, "about", ""],
    ["Robot Status", data.robot.status, "Core health aggregation", "hardware", "blue"],
    ["Brain Status", data.brain.status, "External intelligence layer", "brain", "purple"],
    ["Current Mode", data.robot.mode, "No hardware ownership", "diagnostics", "amber"],
    ["Service Status", `${data.services.length} observed`, "Core service projection", "services", ""],
    ["CPU", formatPercent(data.system.cpu), "Core system plugin", "system", "blue"],
    ["RAM", formatPercent(data.system.ram), "Core system plugin", "system", "purple"],
    ["Disk", formatPercent(data.system.disk), "Core system plugin", "system", "amber"],
    ["Temperature", formatTemperature(data.system.temperature), "Core system plugin", "hardware", "amber"],
    ["Network", data.system.network, "Management port 8089", "services", ""],
    ["Robot IP", data.robot.ip, "Core network plugin", "system", "blue"],
    ["Uptime", formatUptime(data.system.uptime_seconds), "Core system plugin", "clock", "purple"],
  ];
  const actions = `
    <div class="quick-actions">
      ${button("Open Brain", { iconName: "external", prototype: "Open Brain" , className: "quick-action", disabled: true })}
      ${button("Open Existing Robot UI", { iconName: "external", href: oldUi, className: "quick-action" })}
      ${button("Restart BX1 OS", { iconName: "refresh", prototype: "Restart BX1 OS", className: "quick-action" })}
      ${button("Restart Robot", { iconName: "refresh", prototype: "Restart Robot", className: "quick-action danger" })}
      ${button("Shutdown Robot", { iconName: "power", prototype: "Shutdown Robot", className: "quick-action danger" })}
    </div>`;
  const overview = `
    <div class="architecture-note">
      ${icon("diagnostics")}
      <div><strong>Core telemetry active</strong>Every visible value is projected from BX1 OS Core. This interface remains read-only and takes no hardware ownership.</div>
    </div>`;
  return `
    <div class="grid">
      ${cards.map(card => metricCard(...card)).join("")}
      ${panel("Quick actions", actions, { span: 12, subtitle: "External links work; management actions remain intentionally disabled" })}
      ${panel("Platform posture", overview, { span: 12 })}
    </div>`;
}

function systemPage(data) {
  const platformRows = [
    ["Python version", data.system.python, true],
    ["Operating system", data.system.os],
    ["Kernel", data.system.kernel, true],
    ["Architecture", data.system.architecture, true],
    ["Hostname", data.system.hostname, true],
    ["Serial", data.system.serial, true],
  ];
  const releaseRows = [
    ["Installed version", `BX1 OS ${data.interface.version}`],
    ["Update channel", data.system.update_channel],
    ["Release tag", data.interface.tag, true],
    ["Management port", data.robot.management_port, true],
    ["Existing UI port", `${data.robot.existing_ui_port} (protected)`, true],
    ["Runtime mode", data.robot.mode],
  ];
  return `<div class="grid">
    ${panel("Host information", dataList(platformRows), { span: 6, subtitle: "Read-only host identity" })}
    ${panel("BX1 OS release", dataList(releaseRows), { span: 6, subtitle: "Installed platform metadata" })}
    ${panel("Resource telemetry", dataList([
      ["CPU utilisation", formatPercent(data.system.cpu)],
      ["Memory utilisation", formatPercent(data.system.ram)],
      ["Disk utilisation", formatPercent(data.system.disk)],
      ["Temperature", formatTemperature(data.system.temperature)],
      ["Network", data.system.network],
      ["Robot IP", data.robot.ip, true],
    ]), { span: 12, subtitle: "Live read-only values from BX1 OS Core plugins" })}
  </div>`;
}

function servicesPage(data) {
  const future = {
    name: "Future managed service",
    description: "Service registry expansion point",
    state: "planned",
    managed: false,
  };
  const rows = [...data.services, future].map(service => {
    const tone = service.state === "running" ? "good" : service.state === "external" ? "info" : "warn";
    return `<tr>
      <td><span class="service-name">${esc(service.name)}</span></td>
      <td>${esc(service.description)}</td>
      <td>${badge(service.state, tone)}</td>
      <td>${service.managed ? badge("Managed", "good", false) : badge("Protected / future", "info", false)}</td>
      <td><div class="table-actions">
        ${button("Logs", { className: "small", prototype: `View logs for ${service.name}` })}
        ${button("Restart", { className: "small", prototype: `Restart ${service.name}`, disabled: !service.managed })}
      </div></td>
    </tr>`;
  }).join("");
  return `<div class="grid">${panel("Service inventory", `
    <div class="table-wrap"><table>
      <thead><tr><th>Service</th><th>Description</th><th>State</th><th>Ownership</th><th></th></tr></thead>
      <tbody>${rows}</tbody>
    </table></div>`, { span: 12, subtitle: "Systemd integration is intentionally read-only in this release", aside: badge("2 discovered", "info") })}
  </div>`;
}

function deviceTone(state) {
  if (["online", "detected"].includes(state)) return "good";
  if (["offline", "permission_denied"].includes(state)) return "bad";
  if (["busy", "owned_elsewhere", "unsupported", "adapter_pending"].includes(state)) return "warn";
  return "info";
}

function deviceStateLabel(device) {
  if (device.ownership === "bx1-web.service") return "Owned by Robot Body";
  const labels = {
    online: "Online",
    offline: "Offline",
    detected: "Detected",
    busy: "Busy",
    owned_elsewhere: "Busy",
    permission_denied: "Permission denied",
    unsupported: "Unsupported",
    adapter_pending: "Adapter pending",
    unavailable: "Unavailable",
    unknown: "Unknown",
  };
  return labels[device.health?.state] || "Unknown";
}

function deviceCard(device) {
  const health = device.health || {};
  const details = device.details || {};
  const summary = Object.entries(details)
    .filter(([, value]) => ["string", "number", "boolean"].includes(typeof value))
    .slice(0, 4)
    .map(([key, value]) => `<div><span>${esc(key.replaceAll("_", " "))}</span><strong>${display(value)}</strong></div>`)
    .join("");
  return `<article class="hardware-item device-card">
    <div class="device-card-top">
      <span class="metric-icon">${icon(device.category === "camera" ? "hardware" : "diagnostics")}</span>
      ${badge(deviceStateLabel(device), deviceTone(health.state), false)}
    </div>
    <strong>${esc(device.name || device.device_id)}</strong>
    <small>${esc(device.category || "unknown")} · ${device.present ? "Present" : "Not detected"}</small>
    <div class="device-facts">
      <div><span>Owner</span><strong>${display(device.ownership, "Unknown")}</strong></div>
      <div><span>Source</span><strong>${display(device.source, "Unknown")}</strong></div>
      <div><span>Last update</span><strong>${esc(formatTimestamp(device.last_seen))}</strong></div>
      <div><span>Health</span><strong>${display(health.reason, health.state)}</strong></div>
      ${summary}
    </div>
  </article>`;
}

function hardwarePage(data) {
  const devices = data.hardware.inventory || [];
  const body = data.robot_body || {};
  const content = devices.length
    ? `<div class="hardware-grid">${devices.map(deviceCard).join("")}</div>`
    : emptyPanel("hardware", "No devices detected", "Observers completed safely without opening any device. Missing optional hardware is not a global OS fault.");
  return `<div class="grid">
    ${panel("Observer posture", dataList([
      ["Robot Body API", body.connected ? "Connected" : "Unavailable"],
      ["Robot Body version", body.version],
      ["Ownership taken", "No"],
      ["Device nodes opened", "No"],
      ["Control", "Blocked"],
    ]), { span: 4, subtitle: "Source: Existing Robot Body and system metadata" })}
    ${panel("Inventory summary", dataList([
      ["Devices reported", devices.length],
      ["Online", devices.filter(item => item.health?.state === "online").length],
      ["Detected", devices.filter(item => item.health?.state === "detected").length],
      ["Owned by Robot Body", devices.filter(item => item.ownership === "bx1-web.service").length],
      ["Permission denied", devices.filter(item => item.health?.state === "permission_denied").length],
    ]), { span: 8, subtitle: "Read-only, non-exclusive, best-effort discovery" })}
    ${panel("Device inventory", content, { span: 12, subtitle: "No probes, streams, serial writes, mixer writes or control operations" })}
  </div>`;
}

function audioDeviceTable(devices, category) {
  if (!devices.length) return emptyPanel(
    "logs",
    `No ${category.toLowerCase()} devices detected`,
    "ALSA or Robot Body metadata was unavailable. No device was opened."
  );
  return `<div class="table-wrap"><table>
    <thead><tr><th>Device</th><th>Path</th><th>Status</th><th>Owner</th><th>Format</th><th>Last update</th></tr></thead>
    <tbody>${devices.map(device => `<tr>
      <td><span class="service-name">${esc(device.name)}</span><small>${device.details?.default ? "Default" : ""}</small></td>
      <td class="mono">${display(device.details?.alsa_device, "Unavailable")}</td>
      <td>${badge(deviceStateLabel(device), deviceTone(device.health?.state), false)}</td>
      <td>${display(device.ownership, "Unknown")}</td>
      <td>${display(device.details?.current_format, "Metadata unavailable")} · ${display(device.details?.sample_rate, "—")} Hz · ${display(device.details?.channels, "—")} ch</td>
      <td>${esc(formatTimestamp(device.last_seen))}</td>
    </tr>`).join("")}</tbody>
  </table></div>`;
}

function audioPage(data) {
  const audio = data.audio || {};
  const input = audio.input || {};
  const output = audio.output || {};
  const microphones = audio.microphones || [];
  const speakers = audio.speakers || [];
  return `<div class="grid">
    ${panel("Overview", dataList([
      ["Microphone owner", observed(input.owner, "Unknown")],
      ["Speaker owner", observed(output.owner, "Unknown")],
      ["STT state", observed(audio.stt?.state, "Unknown")],
      ["TTS state", observed(audio.tts?.state, "Unknown")],
      ["Control", "Blocked — observer only"],
    ]), { span: 4, subtitle: "Source: Existing Robot Body" })}
    ${panel("Levels", dataList([
      ["RMS", observed(input.level_rms, "Measurement unavailable while owned")],
      ["Peak", observed(input.level_peak, "Measurement unavailable while owned")],
      ["Noise floor", observed(input.noise_floor, "Measurement unavailable while owned")],
      ["Measurement", observed(input.measurement_state, "Unavailable")],
      ["Quality", observedMeta(input.level_rms).quality],
      ["Last sample", formatTimestamp(observed(input.last_sample_timestamp))],
      ["Core update", formatTimestamp(observedMeta(input.level_rms).timestamp)],
    ]), { span: 8, subtitle: "Proxied only; BX1 OS never seizes the microphone" })}
    ${panel("Microphones", audioDeviceTable(microphones, "Microphone"), { span: 12, aside: badge(`${microphones.length} observed`, "info", false) })}
    ${panel("Speakers", audioDeviceTable(speakers, "Speaker"), { span: 12, aside: badge(`${speakers.length} observed`, "info", false) })}
    ${panel("DSP", emptyPanel("logs", "Read-only metadata", "DSP configuration and live spectral controls are not exposed in this release."), { span: 4, aside: badge("Future controlled operation", "warn", false) })}
    ${panel("Wake Word and STT", emptyPanel("brain", "Owned by Robot Body", "Wake-word and transcription state is observed through the existing API."), { span: 4, aside: badge("Future controlled operation", "warn", false) })}
    ${panel("TTS", emptyPanel("services", "Owned by Robot Body", "Playback configuration is reported without changing volume, mute or device selection."), { span: 4, aside: badge("Future controlled operation", "warn", false) })}
  </div>`;
}

function brainPage(data) {
  return `<div class="grid">
    ${panel("Brain connection", emptyPanel("brain", data.brain.status, "Connection state, latency and authentication will be surfaced here without moving Brain ownership onto the robot."), { span: 7 })}
    ${panel("Intelligence stack", dataList([
      ["LLM", "Pending integration"],
      ["Voice", "Pending integration"],
      ["Models", "Pending integration"],
      ["Memory", "Pending integration"],
    ]), { span: 5, subtitle: "Brain-owned capabilities" })}
  </div>`;
}

function configurationPage() {
  const categories = ["General", "Network", "Services", "Hardware", "Brain", "Security", "Advanced"];
  return `<div class="grid"><section class="panel span-12">
    <div class="split-layout">
      <aside class="category-list">${categories.map((name, index) =>
        `<button class="category-button ${index === 0 ? "active" : ""}" type="button" data-prototype="Configuration category: ${esc(name)}">${esc(name)}</button>`
      ).join("")}</aside>
      <div class="editor-shell">
        <div class="editor-toolbar">
          <input class="input search-input" type="search" placeholder="Search configuration…" aria-label="Search configuration">
          ${button("Backup", { className: "small", prototype: "Backup configuration" })}
          ${button("Restore", { className: "small", prototype: "Restore configuration" })}
          ${button("Save", { className: "small primary", prototype: "Save configuration" })}
        </div>
        <div class="code-editor" aria-label="Configuration editor preview"><span class="code-comment">// Read-only configuration architecture preview</span>
{
  <span class="code-key">"management_interface"</span>: {
    <span class="code-key">"enabled"</span>: <span class="code-string">true</span>,
    <span class="code-key">"mode"</span>: <span class="code-string">"architecture-only"</span>,
    <span class="code-key">"write_access"</span>: <span class="code-string">false</span>
  }
}</div>
      </div>
    </div>
  </section></div>`;
}

function logsPage() {
  const lines = [
    ["09:42:10", "INFO", "management", "BX1 OS Management Interface started"],
    ["09:42:10", "INFO", "qualification", "Observer-only isolation active"],
    ["09:42:11", "INFO", "http", "Management endpoint ready on port 8089"],
    ["09:42:12", "WARN", "architecture", "Live streaming adapter is not implemented"],
  ];
  return `<div class="grid"><section class="panel span-12">
    <header class="panel-header">
      <div><h3>System log stream</h3><p>Static preview — no journal access in this milestone</p></div>
      <div class="log-toolbar">
        <select class="select" aria-label="Log source"><option>All sources</option><option>BX1 OS</option><option>Services</option></select>
        <select class="select" aria-label="Log level"><option>All levels</option><option>Info</option><option>Warning</option><option>Error</option></select>
        ${button("Download", { className: "small", prototype: "Download logs" })}
      </div>
    </header>
    <div class="log-view">${lines.map(([time, level, source, message]) => `
      <div class="log-line"><span class="log-time">${time}</span><span class="log-level ${level === "WARN" ? "warn" : ""}">${level}</span><span class="log-source">${source}</span><span class="log-message">${message}</span></div>`
    ).join("")}</div>
  </section></div>`;
}

function deploymentPage(data) {
  const releaseRows = [
    ["Current version", data.deployment.current_version],
    ["Release tag", data.deployment.tag, true],
    ["Commit", data.deployment.commit, true],
    ["Branch", data.deployment.branch, true],
    ["Build date", data.deployment.build_date],
  ];
  const timeline = `
    <div class="timeline">
      <div class="timeline-item"><strong>BX1 OS Alpha v0.4.0</strong><span>Read-only hardware and audio integration · current</span></div>
      <div class="timeline-item"><strong>BX1 OS Alpha v0.3.0</strong><span>Core telemetry and plugin architecture</span></div>
      <div class="timeline-item"><strong>BX1 OS Alpha v0.2.0</strong><span>Management Interface framework</span></div>
      <div class="timeline-item"><strong>BX1 OS Alpha v0.1.2</strong><span>Process-isolation qualification correction</span></div>
      <div class="timeline-item"><strong>BX1 OS Alpha v0.1.1</strong><span>Side-by-side deployment foundation</span></div>
    </div>`;
  return `<div class="grid">
    ${panel("Current release", dataList(releaseRows), { span: 6, subtitle: "Release manifest adapter pending" })}
    ${panel("Version history", timeline, { span: 6, subtitle: "Repository release lineage" })}
    ${panel("Rollback points", emptyPanel("deploy", "No rollback points loaded", "Validated backup manifests will appear here when the deployment history adapter is connected."), { span: 6 })}
    ${panel("Qualification history", emptyPanel("diagnostics", "No qualification records loaded", "Install-only and canary qualification reports will be indexed here."), { span: 6 })}
  </div>`;
}

function diagnosticsPage(data) {
  const coreChecks = data.hardware.diagnostics?.checks || [];
  const checks = [
    { name: "Management interface", passed: true, detail: "Port 8089 read-only API is serving" },
    { name: "Observer isolation", passed: true, detail: "Hardware ownership and control remain blocked" },
    { name: "Existing Robot UI protected", passed: true, detail: "Port 8088 is queried with allowlisted GET requests only" },
    ...coreChecks,
  ];
  const rows = checks.map(check => `
    <div class="health-row">
      <span class="health-check">${icon(check.passed ? "check" : "diagnostics")}</span>
      <div class="health-copy"><strong>${esc(check.name)}</strong><small>${esc(check.detail || (check.required ? "Required observer check" : "Optional hardware"))}</small></div>
      ${badge(check.passed ? "Online" : check.required ? "Unavailable" : "Optional absent", check.passed ? "good" : check.required ? "bad" : "warn", false)}
    </div>`).join("");
  return `<div class="grid">
    ${panel("Observer health checks", rows, { span: 8, subtitle: "Absent optional hardware does not fault BX1 OS", aside: badge(`${checks.filter(item => item.passed).length}/${checks.length} available`, "info") })}
    ${panel("Diagnostic tools", emptyPanel("diagnostics", "Observation only", "No diagnostic command opens a device, changes settings or sends a probe.", button("Future controlled operation", { disabled: true })), { span: 4 })}
  </div>`;
}

function updatesPage(data) {
  return `<div class="grid">${panel("Software updates", emptyPanel(
    "updates",
    "Update service not connected",
    `BX1 OS is following the ${data.system.update_channel} channel. Review, download and installation controls will arrive behind a dedicated update policy.`,
    button("Check for updates", { iconName: "refresh", prototype: "Check for updates", disabled: true })
  ), { span: 12 })}</div>`;
}

function aboutPage(data) {
  return `<div class="grid">
    <section class="panel about-hero span-5">
      <div class="about-logo"><div class="brand-mark"><span></span><span></span><span></span></div><div><h3>BX1 OS</h3><p>Robot operating system management</p></div></div>
    </section>
    ${panel("Build information", dataList([
      ["Version", data.interface.version],
      ["Commit", data.deployment.commit, true],
      ["Branch", data.deployment.branch, true],
      ["Tag", data.interface.tag, true],
      ["Release", "BX1 OS Alpha"],
      ["Build date", data.deployment.build_date],
    ]), { span: 7 })}
    ${panel("Architecture", `<div class="architecture-note">${icon("code")}<div><strong>Independent management application</strong>Served by BX1 OS on port 8089. The existing Robot Body interface on port 8088 is not imported, altered or replaced.</div></div>`, { span: 12 })}
  </div>`;
}

const RENDERERS = {
  dashboard: dashboardPage,
  system: systemPage,
  services: servicesPage,
  hardware: hardwarePage,
  audio: audioPage,
  brain: brainPage,
  configuration: configurationPage,
  logs: logsPage,
  deployment: deploymentPage,
  diagnostics: diagnosticsPage,
  updates: updatesPage,
  about: aboutPage,
};

function renderNavigation() {
  let currentSection = "";
  $("#primaryNav").innerHTML = NAVIGATION.map(item => {
    const section = item.section !== currentSection
      ? `<div class="nav-section-label">${esc(item.section)}</div>`
      : "";
    currentSection = item.section;
    return `${section}<button class="nav-item ${item.id === state.page ? "active" : ""}" type="button" data-page="${item.id}" title="${esc(item.label)}">
      ${icon(item.icon)}<span>${esc(item.label)}</span><i class="nav-indicator"></i>
    </button>`;
  }).join("");
}

function renderPage() {
  const meta = PAGE_META[state.page] || PAGE_META.dashboard;
  const nav = NAVIGATION.find(item => item.id === state.page) || NAVIGATION[0];
  $("#breadcrumbPage").textContent = nav.label;
  $("#pageHeading").textContent = nav.label;
  $("#pageEyebrow").textContent = meta[0];
  $("#pageTitle").textContent = meta[1];
  $("#pageDescription").textContent = meta[2];
  $("#pageActions").innerHTML = state.page === "dashboard"
    ? button("Refresh status", { iconName: "refresh", className: "primary", coreRefresh: true })
    : "";
  $("#pageContent").innerHTML = RENDERERS[state.page](state.data);
  $$("[data-bind='version']").forEach(node => { node.textContent = `v${state.data.interface.version}`; });
  renderNavigation();
  bindPrototypeActions();
  $("#workspace").focus({ preventScroll: true });
}

function navigate(page, push = true) {
  if (!RENDERERS[page]) page = "dashboard";
  state.page = page;
  if (push) history.pushState({ page }, "", page === "dashboard" ? "/" : `/${page}`);
  renderPage();
  closeMobileNav();
}

function toast(title, detail = "This control is intentionally not implemented in the architecture milestone.") {
  const region = $("#toastRegion");
  const node = document.createElement("div");
  node.className = "toast";
  node.innerHTML = `<strong>${esc(title)}</strong><span>${esc(detail)}</span>`;
  region.appendChild(node);
  setTimeout(() => node.remove(), 4200);
}

function bindPrototypeActions() {
  $$("[data-core-refresh]").forEach(node => {
    node.addEventListener("click", event => {
      event.preventDefault();
      loadCoreTelemetry();
    });
  });
  $$("[data-prototype]").forEach(node => {
    node.addEventListener("click", event => {
      event.preventDefault();
      toast(node.dataset.prototype, "Framework only — no command was sent and no system state changed.");
    });
  });
}

function openMobileNav() { document.body.classList.add("sidebar-open"); }
function closeMobileNav() { document.body.classList.remove("sidebar-open"); }

function managementDataFromCore(statePayload, servicesPayload, healthPayload, hardwarePayload, audioPayload, robotBodyPayload) {
  const core = statePayload.state || {};
  const deployment = core.deployment || {};
  const system = core.system || {};
  const network = core.network || {};
  const robot = core.robot || {};
  const brain = core.brain || {};
  const management = core.management || {};
  return {
    interface: {
      id: management.id || "bx1-os-management",
      name: management.name || "BX1 OS Management",
      version: deployment.version || "0.4.0",
      tag: deployment.tag || "BX1_OS_ALPHA_v0.4.0",
      architecture_only: true,
      capabilities: management.capabilities || {},
    },
    robot: {
      name: robot.name || "BX1",
      status: healthPayload.state || robot.state || "unknown",
      mode: robot.mode || "observer_only",
      hostname: system.hostname,
      ip: network.ip,
      existing_ui_port: management.existing_ui_port || 8088,
      management_port: management.port || 8089,
    },
    brain: {
      status: brain.connected ? "Connected" : "Not connected",
      url: "",
    },
    system: {
      python: system.python,
      os: system.os,
      kernel: system.kernel,
      architecture: system.architecture,
      hostname: system.hostname,
      serial: system.serial,
      update_channel: "alpha",
      cpu: system.cpu,
      ram: system.memory,
      disk: system.disk,
      temperature: system.temperature,
      network: network.state,
      uptime_seconds: system.uptime,
    },
    services: servicesPayload.services || [],
    hardware: {
      inventory: observed(hardwarePayload.hardware?.inventory, []),
      diagnostics: observed(hardwarePayload.hardware?.diagnostics, { checks: [] }),
    },
    audio: {
      microphones: observed(audioPayload.devices?.microphones, []),
      speakers: observed(audioPayload.devices?.speakers, []),
      input: audioPayload.audio?.input || {},
      output: audioPayload.audio?.output || {},
      stt: audioPayload.audio?.stt || {},
      tts: audioPayload.audio?.tts || {},
    },
    robot_body: {
      connected: observed(robotBodyPayload.robot_body?.connected, false),
      version: observed(robotBodyPayload.robot_body?.version, "unknown"),
      health: observed(robotBodyPayload.robot_body?.health, "unavailable"),
      active_faults: observed(robotBodyPayload.robot_body?.active_faults, []),
    },
    deployment: {
      current_version: deployment.version,
      commit: deployment.commit,
      branch: deployment.branch,
      tag: deployment.tag,
      build_date: deployment.build_date,
      previous_versions: [],
      rollback_points: [],
      qualification_history: [],
      deployment_history: [],
    },
  };
}

async function loadCoreTelemetry() {
  if (state.telemetryLoading) return;
  state.telemetryLoading = true;
  try {
    const paths = [
      "/api/core/state",
      "/api/core/services",
      "/api/core/health",
      "/api/core/plugins",
      "/api/core/system",
      "/api/core/hardware",
      "/api/core/audio",
      "/api/core/robot-body",
    ];
    const responses = await Promise.all(
      paths.map(path => fetch(path, { cache: "no-store" }))
    );
    const failed = responses.find(response => !response.ok);
    if (failed) throw new Error(`HTTP ${failed.status}`);
    const [coreState, services, health, , , hardware, audio, robotBody] = await Promise.all(
      responses.map(response => response.json())
    );
    state.data = managementDataFromCore(coreState, services, health, hardware, audio, robotBody);
    state.connected = true;
    renderPage();
  } catch (error) {
    state.connected = false;
    toast("Using interface preview", "BX1 OS Core telemetry is not available.");
  } finally {
    state.telemetryLoading = false;
  }
}

function init() {
  renderNavigation();
  renderPage();
  $("#primaryNav").addEventListener("click", event => {
    const item = event.target.closest("[data-page]");
    if (item) navigate(item.dataset.page);
  });
  $("#sidebarCollapse").addEventListener("click", () => {
    const shell = $(".app-shell");
    shell.dataset.sidebar = shell.dataset.sidebar === "collapsed" ? "expanded" : "collapsed";
  });
  $("#mobileMenu").addEventListener("click", openMobileNav);
  $("#sidebarScrim").addEventListener("click", closeMobileNav);
  window.addEventListener("popstate", () => {
    state.page = routeFromLocation();
    renderPage();
  });
  document.addEventListener("keydown", event => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      toast("Global search", "Search architecture is ready for a future indexing service.");
    }
    if (event.key === "Escape") closeMobileNav();
  });
  loadCoreTelemetry();
  window.setInterval(loadCoreTelemetry, 5000);
}

document.addEventListener("DOMContentLoaded", init);
