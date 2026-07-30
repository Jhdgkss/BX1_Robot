const NAVIGATION = [
  { section: "Overview", id: "dashboard", label: "Dashboard", icon: "grid" },
  { section: "Manage", id: "system", label: "System", icon: "system" },
  { section: "Manage", id: "services", label: "Services", icon: "services" },
  { section: "Manage", id: "hardware", label: "Hardware", icon: "hardware" },
  { section: "Manage", id: "camera", label: "Camera", icon: "hardware" },
  { section: "Manage", id: "audio", label: "Audio", icon: "logs" },
  { section: "Manage", id: "voice", label: "Live Voice", icon: "brain" },
  { section: "Manage", id: "speech-learning", label: "Speech Learning", icon: "brain" },
  { section: "Manage", id: "brain", label: "Brain", icon: "brain" },
  { section: "Manage", id: "configuration", label: "Configuration", icon: "config" },
  { section: "Manage", id: "modules", label: "Modules", icon: "services" },
  { section: "Observe", id: "logs", label: "Logs", icon: "logs" },
  { section: "Observe", id: "deployment", label: "Deployment", icon: "deploy" },
  { section: "Observe", id: "diagnostics", label: "Diagnostics", icon: "diagnostics" },
  { section: "Platform", id: "updates", label: "Updates", icon: "updates" },
  { section: "Platform", id: "themes", label: "Themes", icon: "config" },
  { section: "Platform", id: "documentation", label: "Documentation", icon: "about" },
  { section: "Platform", id: "about", label: "About", icon: "about" },
];

const PAGE_META = {
  dashboard: ["Command centre", "System overview", "A high-level view of BX1 OS, its resources and connected systems."],
  system: ["Host platform", "System information", "Operating system, runtime and hardware identity for this BX1 host."],
  services: ["Service orchestration", "Managed services", "A unified home for BX1 OS service state, controls and logs."],
  hardware: ["Device inventory", "Hardware", "Read-only discovery, ownership and health for detected robot devices."],
  camera: ["Safe live preview", "Camera", "Near-live frames proxied from the Existing Robot Body without reopening the physical camera."],
  audio: ["Audio telemetry", "Audio", "Read-only microphone, speaker, level, STT and TTS observations."],
  voice: ["Shared live session", "Live Voice Console", "Body-mediated voice activity shared by the touchscreen and every 8089 browser."],
  "speech-learning": ["Recognition review", "Speech Learning", "Review real recognition events, vocabulary, corrections and approved examples."],
  brain: ["Intelligence layer", "Brain", "Connection, models, voice and memory will be managed from this workspace."],
  configuration: ["Platform settings", "Configuration", "A searchable, categorised configuration workspace with safe revision controls."],
  modules: ["Developer preview", "Module Manager", "Manifest-first module inventory, lifecycle health and safe declared capabilities."],
  logs: ["System events", "Logs", "Live, filterable BX1 OS logs will appear here without mixing with the legacy UI."],
  deployment: ["Release lifecycle", "Deployment", "Versions, qualification history, rollback points and deployment evidence."],
  diagnostics: ["Platform health", "Diagnostics", "Read-only checks and future guided diagnostics for the BX1 platform."],
  updates: ["Release channel", "Updates", "Future update discovery, review and controlled installation."],
  themes: ["Visual system", "Themes", "Edit the shared BX1 OS visual tokens and preview robot identity."],
  documentation: ["Offline reference", "Documentation", "Repository-backed BX1 OS architecture, voice, diagnostics and deployment guidance."],
  about: ["Platform identity", "About BX1 OS", "Release provenance and architecture information for this installation."],
};

const fallbackData = {
  interface: {
    id: "bx1-os-management",
    name: "BX1 OS Management",
    version: "0.11.0-mcu-foundation",
    tag: "BX1_OS_v0.8.0_voice_controls",
    architecture_only: true,
    capabilities: {},
  },
  robot: {
    name: "LEO",
    status: "Qualification",
    mode: "Body-mediated capability mode",
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
  hardware: { inventory: [], camera_groups: [], raw_cameras: [], diagnostics: { checks: [] } },
  camera: {
    connected: false,
    owner: "bx1-web.service",
    source: "Existing Robot Body",
    streaming: false,
    preview_available: false,
    resolution: "Unknown",
    fps: null,
    frame_age_ms: null,
    last_frame_timestamp: null,
    frame_sequence: null,
    health: "Unavailable",
    error: "",
    stale: true,
    proxy: {},
  },
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
    current_version: "0.11.0-mcu-foundation",
    commit: "Provided by release manifest",
    branch: "Provided by release manifest",
    tag: "BX1_OS_v0.8.0_voice_controls",
    build_date: "Provided by release manifest",
    previous_versions: [],
    rollback_points: [],
    qualification_history: [],
    deployment_history: [],
  },
  modules: { modules: [], event_bus: {} },
};

const state = {
  page: routeFromLocation(),
  data: fallbackData,
  connected: false,
  telemetryLoading: false,
  talk: { phase: "Ready", sessionId: "", busy: false, error: "", timer: null },
  cameraPreview: {
    token: 0,
    timer: null,
    objectUrl: "",
    mode: "idle",
    controller: null,
  },
  conversation: [],
  voiceItems: [], // Browser-session-only recognised/manual/reply display; never exported or sent to OS storage.
  voiceAutoScroll: true,
  audioTimer: null,
  telemetryRevision: 0,
  recording: {state: "idle", id: "", requested: 0, startedAt: 0, metadata: null, audio: null, pending: false},
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
      ${button("Open legacy Robot Body UI (8088)", { iconName: "external", href: oldUi, className: "quick-action" })}
    </div>`;
  const overview = `
    <div class="architecture-note">
      ${icon("diagnostics")}
      <div><strong>Core telemetry active</strong>Every visible value is projected from BX1 OS Core. This interface remains read-only and takes no hardware ownership.</div>
    </div>`;
  const kiosk = data.touchscreen || {};
  const widgets = (data.widgets?.widgets || []).filter(widget => widget.placement === "dashboard").map(widget => {
    const values = Object.entries(widget.data || {}).map(([key, value]) => `<div><span>${esc(key.replaceAll("_", " "))}</span><strong>${display(value)}</strong></div>`).join("");
    return panel(widget.title, `<div class="device-facts">${values}</div>${widget.fault ? `<p class="mono">${esc(widget.fault)}</p>` : ""}`, { span: 4, subtitle: `${esc(widget.module_id)} · ${esc(widget.health)}` });
  }).join("");
  return `
    <div class="grid">
      ${cards.map(card => metricCard(...card)).join("")}
      <div class="span-12 dashboard-live-summary" data-live-voice="dashboard">${liveVoiceMarkup(data.audio_bridge || {}, false)}</div>
      ${panel("Touchscreen kiosk", dataList([["State", kiosk.state || "Not reported"], ["Last start reason", kiosk.reason || "kiosk has not reported a start"], ["Target", kiosk.url || "http://127.0.0.1:8089/dashboard"], ["Last update", kiosk.updated_at ? formatTimestamp(kiosk.updated_at) : "Never"]]), { span: 12, subtitle: "Existing X11 kiosk launcher status" })}
      ${widgets}
      ${panel("Legacy fallback", actions, { span: 12, subtitle: "Touchscreen starts BX1 OS on 8089. The protected Robot Body page remains available here." })}
      ${panel("Platform posture", overview, { span: 12 })}
    </div>`;
}

function liveVoiceMarkup(bridge, expanded) {
  const audio = bridge.audio || {};
  const recognition = bridge.recognition || {};
  if (!bridge.ok || !audio.available) {
    const reason = audio.unavailable_reason || bridge.error || "Body live voice metadata is unavailable.";
    const last = audio.last_successful_update ? ` Last successful update: ${formatTimestamp(audio.last_successful_update)}.` : " No successful live level has been received.";
    const receiver = bridge.receiver || {}; const received = receiver.last_received_at ? `${Math.max(0, Date.now() / 1000 - Number(receiver.last_received_at)).toFixed(1)} s ago` : "never";
    return panel(expanded ? "Voice Monitor" : "Live Voice", `<p class="mono">${esc(reason + last)}</p><p class="voice-connection">OS receiver last received Body metadata: ${esc(received)}.</p>`, { span: 12, subtitle: "No placeholder level is shown" });
  }
  const rms = Number(audio.rms_dbfs), peak = Number(audio.peak_dbfs), threshold = Number(audio.threshold_dbfs);
  const handoff = recognition.handoff || {};
  const visionContext = recognition.vision_context || "off";
  const percent = Math.max(0, Math.min(100, (rms + 90) / .9));
  const thresholdPercent = Math.max(0, Math.min(100, (threshold + 90) / .9));
  const stateTone = audio.state === "failed" ? "failure" : audio.state === "Leo speaking" || audio.state === "echo settling" ? "speaking" : audio.state === "speech detected" ? "heard" : "listening";
  const details = expanded ? dataList([["Peak", `${peak.toFixed(1)} dBFS`], ["Noise floor", `${Number(audio.noise_floor_dbfs).toFixed(1)} dBFS`], ["Gate", audio.gate_open ? "Open" : "Closed"], ["STT engine", recognition.engine || handoff.engine_selected || "Unknown"], ["Primary STT", `${handoff.primary_request || "not started"} · ${handoff.elapsed_ms ?? "--"} ms`], ["Fallback reason", handoff.fallback_reason || recognition.rejection_reason || "None"], ["Confidence", recognition.confidence == null ? "Not reported" : Number(recognition.confidence).toFixed(2)], ["Sample age", `${Number(audio.age_seconds).toFixed(1)} s`]]) : "";
  const compact = expanded ? "" : `<div class="page-actions"><button class="button primary" type="button" data-page-link="voice">Open Live Voice</button></div>`;
  return panel(expanded ? "Voice Monitor" : "Live Voice summary", `<div class="live-voice ${stateTone}"><div class="live-voice-top"><strong>${esc(audio.state || "idle")}</strong><span>${audio.gate_open ? "Gate open" : "Gate closed"}</span></div><p class="heard-line">${esc(audio.state_detail || audio.state || "Voice state unavailable")}</p><div class="audio-gauge" role="meter" aria-label="Live microphone level" aria-valuemin="-90" aria-valuemax="0" aria-valuenow="${rms}"><div class="audio-gauge-fill" style="width:${percent}%"></div><i class="audio-gauge-threshold" style="left:${thresholdPercent}%"></i></div><div class="audio-levels"><strong>${rms.toFixed(1)} dBFS</strong><span>Peak ${peak.toFixed(1)} dBFS</span></div><p class="heard-line truncate-line">Last accepted request: ${esc(recognition.last_accepted_request || "None")}</p><p class="heard-line">STT: ${esc(recognition.engine || "Unknown")}${recognition.rejection_reason ? ` · ${esc(recognition.rejection_reason)}` : ""}</p>${details}${compact}</div>`, { span: 12, subtitle: "Body-owned live metadata; no raw audio" });
}

function sharedVoiceFeed(data, expanded = false) {
  const consoleData = data.voice_console || {};
  const items = consoleData.items || [];
  const receiver = consoleData.receiver || {};
  const age = receiver.last_received_at ? `${Math.max(0, Date.now() / 1000 - Number(receiver.last_received_at)).toFixed(1)} s` : "never";
  const visible = expanded ? items : items.slice(-3);
  const rows = visible.length ? visible.map(item => `<div class="voice-session-item ${esc(item.kind)}"><span>${esc(item.source)} · ${esc(formatTimestamp(item.timestamp))}</span>${esc(item.text)}</div>`).join("") : "No live conversation items yet.";
  return panel(expanded ? "Shared Live Conversation" : "Shared conversation", `<p class="voice-connection">Body receiver ${receiver.body_available ? "connected" : "waiting"} · last OS receipt ${esc(age)} · Body sample ${receiver.body_sample_age_seconds == null ? "unavailable" : `${Number(receiver.body_sample_age_seconds).toFixed(1)} s old`}</p><div class="voice-session-items" id="sharedVoiceItems">${rows}</div>${expanded ? `<div class="page-actions"><button class="button" type="button" data-live-action="clear">Clear session</button><button class="button" type="button" data-live-action="autoscroll">${state.voiceAutoScroll ? "Pause autoscroll" : "Resume autoscroll"}</button></div>` : ""}`, { span: 12, className: "shared-live-conversation", subtitle: "Shared temporary RAM only; cleared on BX1 OS restart" });
}

function liveVoiceStatusCard(bridge) {
  const audio = bridge.audio || {}; const recognition = bridge.recognition || {};
  return panel("Live status", dataList([
    ["State", audio.state_detail || audio.state || "Unavailable"], ["Last accepted request", recognition.last_accepted_request || "None"],
    ["Last recognised / discarded", recognition.last_discarded_audio || recognition.latest_text || "None"],
    ["STT engine", recognition.engine || "Unknown"], ["Vision context", recognition.vision_context || "off"], ["Confidence", recognition.confidence == null ? "Not reported" : Number(recognition.confidence).toFixed(2)],
    ["Failure", recognition.rejection_reason || audio.last_failure_reason || "None"], ["Sample age", audio.age_seconds == null ? "Unavailable" : `${Number(audio.age_seconds).toFixed(1)} s`],
  ]), { span: 12, className: "voice-console-status", subtitle: "Live Body metadata; no raw audio" });
}

function voiceConsolePage(data) {
  return `<div class="voice-console-page"><div class="voice-console-top"><div data-live-voice="console">${liveVoiceMarkup(data.audio_bridge || {}, true)}</div><div data-live-voice-status>${liveVoiceStatusCard(data.audio_bridge || {})}</div></div><div class="voice-console-transcript" data-shared-voice>${sharedVoiceFeed(data, true)}</div>${panel("Manual message", `<label for="talkToLeoText">Message for Leo</label><textarea class="input" id="talkToLeoText" maxlength="1000" rows="10" placeholder="Type a message for Leo"></textarea><p id="talkToLeoHelp" class="mono">Enter sends · Shift+Enter adds a line · shared temporary RAM-only session.</p><div class="page-actions"><span id="talkToLeoCount" class="mono">0 / 1000</span><button class="button primary" type="button" data-voice-action="talk-send">Send</button><button class="button" type="button" data-voice-action="talk-repeat">Repeat</button></div><p id="talkToLeoState" class="mono" role="status">${esc(state.talk.phase)}</p>`, { span: 12, className: "voice-console-manual", subtitle: "Body → Brain chat/TTS → Body speaker; no action packets" })}</div>`;
}

function themesPage() { return `<div class="grid">${panel("Theme system", `<p>Shared design tokens are separate from robot identity.</p><label>Accent colour<input class="input" type="color" value="#54b9ff"></label><label>Panel colour<input class="input" type="color" value="#102334"></label><div class="page-actions"><button class="button primary" data-prototype="Save theme">Save</button><button class="button" data-prototype="Save As theme">Save As</button><button class="button" data-prototype="Restore BX1 Default">Restore BX1 Default</button></div>`, {span:8, subtitle:"Light/dark modes, import/export and custom themes"})}${panel("Live preview", `<div class="speech-scan"><strong>BX1 OS v0.8.0</strong><p>Robot identity profile preview remains independent of theme.</p></div>`, {span:4})}</div>`; }
function documentationPage() { return `<div class="grid">${panel("Offline documentation", `<p>Repository documentation is served locally without internet access.</p><pre id="documentationContent">Loading documentation…</pre>`, {span:12, subtitle:"Architecture · voice pipeline · gate · diagnostics · themes · deployment · troubleshooting"})}</div>`; }

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
        ${button("Restart unavailable", { className: "small", disabled: true })}
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
  const cameraFacts = device.category === "camera" ? `
      <div><span>Preview</span><strong>${details.preview_available ? "Available" : "Unavailable"}</strong></div>
      <div><span>Stream</span><strong>${details.streaming ? "Streaming" : "Idle"}</strong></div>
      <div><span>Resolution</span><strong>${display(details.resolution, "Unknown")}</strong></div>
      <div><span>Frame age</span><strong>${details.frame_age_ms == null ? "Unavailable" : `${Math.round(details.frame_age_ms)} ms`}</strong></div>
    ` : "";
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
      ${cameraFacts}
      ${summary}
    </div>
    ${device.category === "camera"
      ? `<button class="button small camera-link" type="button" data-page-link="camera">${icon("external")}<span>Open Camera</span></button>`
      : ""}
  </article>`;
}

function hardwarePage(data) {
  const rawDevices = data.hardware.inventory || [];
  const cameraGroups = data.hardware.camera_groups || [];
  const devices = [
    ...cameraGroups,
    ...rawDevices.filter(device => device.category !== "camera"),
  ];
  const rawCameras = data.hardware.raw_cameras || [];
  const body = data.robot_body || {};
  const content = devices.length
    ? `<div class="hardware-grid">${devices.map(deviceCard).join("")}</div>`
    : emptyPanel("hardware", "No devices detected", "Observers completed safely without opening any device. Missing optional hardware is not a global OS fault.");
  const mcu = data.mcu || data.hardware?.mcu || {};
  const mcuPanel = panel("MCU foundation", `<div class="mcu-status-grid" id="mcuStatusPanel"><div><span>Connection</span><strong>${esc(mcu.mcu_ok ? "connected" : "disconnected")}</strong></div><div><span>Firmware</span><strong>${esc(mcu.firmware_version || "unavailable")}</strong></div><div><span>Protocol</span><strong>${esc(mcu.protocol_version || "bx1.mcu.v1")}</strong></div><div><span>Heartbeat age</span><strong>${esc(mcu.heartbeat_age_ms ?? "unavailable")}</strong></div><div><span>Safe state</span><strong>${mcu.actuator_inhibit === false ? "check required" : "inhibited"}</strong></div></div><div class="page-actions mcu-actions"><button class="button" data-mcu-action="reconnect">Reconnect MCU</button><button class="button" data-mcu-action="request-status">Request Status</button><button class="button" data-mcu-action="scan-i2c">Scan I2C</button><button class="button" data-mcu-action="start-imu-telemetry">Start IMU Telemetry</button><button class="button" data-mcu-action="stop-imu-telemetry">Stop IMU Telemetry</button><button class="button" data-mcu-action="clear-diagnostic-fault">Clear Diagnostic Fault</button></div><small id="mcuActionState">No command pending</small>`, {span:12, subtitle:"MicroPython telemetry only; wheel, RS485 and servo outputs remain inhibited"});
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
    ${panel("Device inventory", content, { span: 12, subtitle: "Physical cameras are grouped; no probes, device opens or control operations" })}
    ${panel("Advanced camera inventory", rawCameras.length
      ? dataList(rawCameras.map(item => [
          item.details?.device_node || item.device_id,
          `${item.name} · ${item.details?.internal_video_device ? "internal encoder/decoder" : "physical camera node"}`,
          true,
        ]))
      : emptyPanel("hardware", "No raw video nodes", "Underlying V4L2 metadata remains available through the Core inventory API."), {
        span: 12,
        subtitle: "Includes underlying nodes and internal qcom-venus devices; hidden from the robot-level camera view",
      })}
    ${mcuPanel}
  </div>`;
}

function cameraValue(camera, key, fallback = null) {
  return observed(camera?.[key], fallback);
}

function cameraPage(data) {
  const camera = data.camera || {};
  const available = Boolean(cameraValue(camera, "preview_available", false));
  const stale = Boolean(cameraValue(camera, "stale", true));
  const status = available ? (cameraValue(camera, "streaming", false) ? "Streaming" : "Idle") : "Offline";
  return `<div class="grid">
    ${panel("Live Preview", `
      <div class="camera-preview" id="cameraPreview" data-state="loading">
        <img id="cameraPreviewImage" alt="LEO camera preview from Existing Robot Body">
        <div class="camera-preview-state" id="cameraPreviewState">
          <span class="camera-spinner"></span>
          <strong>Connecting to Robot Body frame source</strong>
          <small>BX1 OS will not open a camera device.</small>
        </div>
        <div class="camera-stale-warning ${stale ? "" : "hidden"}" id="cameraStaleWarning">Frame is stale</div>
      </div>
      <div class="camera-preview-footer">
        ${badge("Owned by Robot Body", "info", false)}
        <span id="cameraConnectionLabel">${available ? "Frame source available" : "Frame source unavailable"}</span>
        <span>Read-only proxy</span>
      </div>`, {
        span: 8,
        subtitle: "Maximum 640×480 · default 8 FPS · no-store",
      })}
    ${panel("Camera Status", dataList([
      ["Camera", "Logitech UVC 046d:0825"],
      ["Owner", cameraValue(camera, "owner", "bx1-web.service")],
      ["Source", cameraValue(camera, "source", "Existing Robot Body")],
      ["State", status],
      ["Resolution", cameraValue(camera, "resolution", "Unknown")],
      ["Connection", cameraValue(camera, "connected", false) ? "Connected" : "Unavailable"],
      ["BX1 OS access", "Read-only proxy"],
    ]), { span: 4, aside: badge("Owned by Robot Body", "info", false) })}
    ${panel("Stream Telemetry", dataList([
      ["Estimated FPS", cameraValue(camera, "fps", "Unavailable")],
      ["Last frame age", cameraValue(camera, "frame_age_ms") == null ? "Unavailable" : `${Math.round(cameraValue(camera, "frame_age_ms"))} ms`],
      ["Last frame", formatTimestamp(cameraValue(camera, "last_frame_timestamp"))],
      ["Frame sequence", cameraValue(camera, "frame_sequence", "Unavailable")],
      ["Health", cameraValue(camera, "health", "Unavailable")],
      ["Stale", stale ? "Yes" : "No"],
      ["Error", cameraValue(camera, "error", "None") || "None"],
    ]), { span: 6 })}
    ${panel("Device Details", dataList([
      ["Physical device", "Logitech UVC Camera"],
      ["USB identity", "046d:0825", true],
      ["Physical owner", "bx1-web.service", true],
      ["Browser source", "/api/core/camera/stream", true],
      ["Fallback source", "/api/core/camera/snapshot", true],
      ["Queue policy", "Newest frame only"],
    ]), { span: 6 })}
    ${panel("Ownership and Safety", `
      <div class="architecture-note">${icon("diagnostics")}<div>
        <strong>Robot Body remains the sole capture owner</strong>
        BX1 OS proxies cached frames over loopback port 8088. It never opens /dev/video0, /dev/video1 or another V4L2 node.
      </div></div>
      <div class="page-actions camera-future">${button("Future controlled operation", { disabled: true })}</div>
    `, { span: 12 })}
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

function wakeSpeechSettingsPanel(bridge) {
  const settings = bridge.voice_settings || {};
  const value = settings.effective || {};
  if (!settings.ok) return emptyPanel("brain", "Wake & Speech unavailable", "Robot Body has not supplied its allowlisted voice settings.");
  const phrases = Array.isArray(value.wake_phrases) ? value.wake_phrases : [];
  const row = phrase => `<div class="page-actions wake-phrase-row"><input class="input" name="wake_phrase" maxlength="48" value="${esc(phrase)}" aria-label="Wake phrase"><button class="button small" type="button" data-wake-action="remove">Remove</button></div>`;
  return `<form id="wakeSpeechForm" class="audio-settings">
    <p class="voice-connection">Settings are applied by Robot Body · revision ${esc(settings.revision || "unknown")} · ${esc(formatTimestamp(settings.updated_at))}</p>
    <div id="wakePhraseRows">${phrases.map(row).join("")}</div><div class="page-actions"><button class="button small" type="button" data-wake-action="add">Add phrase</button></div>
    <label>Wake/session listening timeout (s)<input class="input" name="wake_listen_timeout_s" type="number" min="3" max="60" step="0.5" value="${esc(value.wake_listen_timeout_s)}"></label>
    <label>Speech-end timeout (ms)<input class="input" name="speech_end_timeout_ms" type="number" min="250" max="4000" step="10" value="${esc(value.speech_end_timeout_ms)}"></label>
    <label>Noise gate (dBFS)<input class="input" name="noise_gate_dbfs" type="number" min="-90" max="-5" step="0.5" value="${esc(value.noise_gate_dbfs)}"></label>
    <label>Noise margin (dB)<input class="input" name="noise_margin_db" type="number" min="0" max="30" step="0.5" value="${esc(value.noise_margin_db)}"></label>
    <label>Adaptive margin (dB)<input class="input" name="adaptive_margin_db" type="number" min="0" max="30" step="0.5" value="${esc(value.adaptive_margin_db)}"></label>
    <label>Speaker echo tail (ms)<input class="input" name="speaker_echo_tail_ms" type="number" min="250" max="5000" step="50" value="${esc(value.speaker_echo_tail_ms ?? 1500)}"></label>
    <label>STT policy<select class="input" name="stt_policy"><option value="brain_faster_whisper" ${value.stt_policy === "brain_faster_whisper" ? "selected" : ""}>Brain faster-whisper with local Vosk fallback</option><option value="vosk" ${value.stt_policy === "vosk" ? "selected" : ""}>Local Vosk</option></select></label>
    <div class="page-actions"><button class="button primary" type="submit">Save to Robot</button><span id="wakeSpeechState" class="mono">Only allowlisted voice settings are saved.</span></div>
  </form>`;
}

function audioPage(data) {
  const bridge = data.audio_bridge || {};
  const live = bridge.audio || {};
  const hasLive = Boolean(bridge.ok && live.available);
  const audio = data.audio || {};
  const input = hasLive ? { ...(audio.input || {}), level_rms: `${Number(live.rms_dbfs).toFixed(1)} dBFS`, level_peak: `${Number(live.peak_dbfs).toFixed(1)} dBFS`, noise_floor: `${Number(live.noise_floor_dbfs).toFixed(1)} dBFS`, measurement_state: live.state || "idle", last_sample_timestamp: live.timestamp } : (audio.input || {});
  const output = audio.output || {};
  const microphones = audio.microphones || [];
  const speakers = audio.speakers || [];
  return `<div class="grid">
    ${panel("Overview", dataList([
      ["Microphone owner", observed(input.owner, "Unknown")],
      ["Speaker owner", observed(output.owner, "Unknown")],
      ["STT state", observed(audio.stt?.state, "Unknown")],
      ["TTS state", observed(audio.tts?.state, "Unknown")],
      ["Control", "Body-mediated capability mode"],
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
    <div class="span-12" data-live-voice="monitor">${liveVoiceMarkup(bridge, true)}</div>
    ${panel("Speech Test & Calibration", `<p class="voice-connection">Speak a short phrase. Robot Body captures, validates and immediately discards it; BX1 OS receives metadata only.</p><div class="page-actions"><button class="button primary" type="button" data-speech-test="run">Run Speech Test</button></div><div id="speechTestResult" class="result-box">Ready. Live level, gate and noise floor are shown above.</div>`, { span: 12, subtitle: "Faster-Whisper primary · labelled Vosk fallback · settings save only after Apply" })}
    ${panel("Body audio settings", bridge.ok ? `<form id="audioBridgeForm" class="audio-settings">${Object.entries(bridge.settings || {}).map(([key, value]) => `<label>${esc(key.replaceAll("_", " "))}<input class="input" name="${esc(key)}" type="number" min="${value.minimum}" max="${value.maximum}" step="any" value="${value.current}"><small>Range ${value.minimum}–${value.maximum} ${esc(value.unit)} · default ${value.default} · effective ${value.effective}</small></label>`).join("")}<div class="page-actions"><button class="button primary" type="submit">Apply Body settings</button><span id="audioBridgeState" class="mono">Validated and atomically saved by Robot Body.</span></div></form>` : "", { span: 12, subtitle: "No raw audio, recording, device, GPIO or hardware controls" })}
    ${panel("Wake & Speech", wakeSpeechSettingsPanel(bridge), { span: 12, subtitle: "Normal operator settings live in BX1 OS; the 8088 Body page is engineering fallback only." })}
    ${panel("Microphones", audioDeviceTable(microphones, "Microphone"), { span: 12, aside: badge(`${microphones.length} observed`, "info", false) })}
    ${panel("Speakers", audioDeviceTable(speakers, "Speaker"), { span: 12, aside: badge(`${speakers.length} observed`, "info", false) })}
    ${panel("DSP", emptyPanel("logs", "Read-only metadata", "DSP configuration and live spectral controls are not exposed in this release."), { span: 4, aside: badge("Future controlled operation", "warn", false) })}
    ${panel("Wake Word and STT", dataList([["State", live.state || "Unavailable"], ["Latest heard", bridge.recognition?.latest_text || "None"], ["STT engine", bridge.recognition?.engine || "Unknown"], ["Confidence", bridge.recognition?.confidence ?? "Not reported"], ["Failure", bridge.recognition?.rejection_reason || "None"], ["Sample age", `${Number(live.age_seconds || 0).toFixed(1)} s`]]), { span: 4, aside: badge("Body mediated", "info", false) })}
    ${panel("TTS", emptyPanel("services", "Owned by Robot Body", "Playback configuration is reported without changing volume, mute or device selection."), { span: 4, aside: badge("Future controlled operation", "warn", false) })}
  </div>`;
}

function brainPage(data) {
  const voice = data.voice || {};
  const brain = voice.brain || { state: "not_connected", reason: "not_probed" };
  const events = voice.events || [];
  const bodyFaults = data.robot_body?.active_faults || [];
  const eventRows = events.length ? events.slice().reverse().map(item => `<tr>
    <td>${esc(formatTimestamp(item.timestamp))}</td><td>${esc(item.event)}</td>
    <td class="mono">${esc(item.session_id)}</td><td>${esc(item.metadata?.reason || item.metadata?.stage || item.metadata?.transport || "—")}</td>
  </tr>`).join("") : `<tr><td colspan="4">No voice metadata received yet.</td></tr>`;
  return `<div class="grid">
    ${panel("Brain and Body connection", dataList([
      ["Robot Body", data.robot_body?.connected ? "Connected (port 8088)" : "Unavailable"],
      ["Brain endpoint", voice.brain_endpoint || "Not discovered from Body configuration", true],
      ["Brain state", brain.state === "connected" ? "Connected" : brain.state === "degraded" ? "Degraded" : "Not connected"],
      ["Probe reason", brain.reason || "Not probed"],
      ["Voice ownership", "Brain generates TTS; Robot Body plays it"],
      ["MCU / safety", bodyFaults.length ? "DEGRADED / FAULTED — visible" : "No Body fault reported"],
    ]) + `<div class="page-actions"><button class="button small primary" type="button" data-voice-action="brain-probe">Test Brain connectivity</button></div>`, { span: 5, subtitle: "The probe travels through the configured Robot Body route; no credentials are displayed" })}
    ${panel("Manual fallback conversation", `<label for="talkToLeoText">Message for Leo</label><p>The Brain owns the real session and memory; this browser keeps display text only for this tab.</p><textarea class="input" id="talkToLeoText" maxlength="1000" rows="10" aria-describedby="talkToLeoHelp talkToLeoCount" placeholder="Type a message for Leo" ${state.talk.busy ? "disabled" : ""}></textarea><div id="talkToLeoHelp" class="mono">Ctrl+Enter sends through Body → Brain chat/TTS → Body speaker. Hardware/action packets are blocked.</div><div class="page-actions"><span id="talkToLeoCount" class="mono">0 / 1000</span><button class="button primary" type="button" data-voice-action="talk-send" ${state.talk.busy ? "disabled" : ""}>Send</button><button class="button" type="button" data-voice-action="talk-repeat" ${state.talk.busy ? "disabled" : ""}>Repeat</button><button class="button" type="button" data-voice-action="talk-clear" ${state.talk.busy ? "disabled" : ""}>Clear</button></div><p id="talkToLeoState" class="mono" role="status" aria-live="polite">${esc(state.talk.phase)}${state.talk.error ? ` — ${esc(state.talk.error)}` : ""}</p><div class="log-view">${state.conversation.length ? state.conversation.map(item => `<div class="log-line"><span class="log-source">${esc(item.role)}</span><span class="log-message">${esc(item.text)}</span></div>`).join("") : "<div class=\"log-line\">No messages in this browser session.</div>"}</div>`, { span: 12, subtitle: "No raw conversation text is stored by BX1 OS" })}
    ${panel("Conversation Timeline", `<div class="table-wrap"><table><thead><tr><th>Timestamp</th><th>Event</th><th>Session</th><th>Metadata / fault</th></tr></thead><tbody>${eventRows}</tbody></table></div>`, { span: 12, subtitle: "Versioned metadata only — no raw audio, prompt, transcript, credential, or Brain reply" })}
    ${panel("Voice diagnostics", dataList([
      ["Observer faults", (voice.active_faults || []).length],
      ["MCU / safety faults", bodyFaults.length],
      ["Timeline retention", `${events.length} in-memory events`],
      ["Export", "/api/voice/diagnostics", true],
    ]) + `<div class="page-actions"><button class="button small" type="button" data-voice-action="clear-faults">Clear observer faults</button><a class="button small" href="/api/voice/diagnostics" target="_blank" rel="noopener">Export redacted diagnostics</a></div>`, { span: 12, subtitle: "Clear never hides MCU or safety faults reported by the Robot Body" })}
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
      <div class="timeline-item"><strong>BX1 OS Alpha v0.5.0</strong><span>Safe camera preview integration · current</span></div>
      <div class="timeline-item"><strong>BX1 OS Alpha v0.4.0</strong><span>Read-only hardware and audio integration</span></div>
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

function modulesPage(data) {
  const modules = data.modules?.modules || [];
  const rows = modules.length ? modules.map(module => `<tr>
    <td><strong>${esc(module.name)}</strong><br><small>${esc(module.id)} · ${esc(module.version)}</small></td>
    <td>${badge(module.state, module.state === "healthy" ? "good" : "bad", false)}</td>
    <td>${esc((module.capabilities || []).join(", ") || "None")}</td>
    <td>${esc(module.detail || "")}<div class="table-actions">${module.source === "user" ? `<button class="button small" data-module-action="${module.state === "disabled" ? "enable" : "disable"}" data-module-id="${esc(module.id)}">${module.state === "disabled" ? "Enable" : "Disable"}</button><button class="button small danger" data-module-action="remove" data-module-id="${esc(module.id)}">Remove</button>` : "Bundled"}</div></td>
  </tr>`).join("") : `<tr><td colspan="4">No manifests found.</td></tr>`;
  return `<div class="grid">
    ${panel("Runtime boundary", dataList([
      ["Persistent modules", data.modules?.persistent_root || "Unavailable"], ["Hardware access", "Blocked"],
      ["Event queue", `${data.modules?.event_bus?.queued || 0} / ${data.modules?.event_bus?.queue_limit || 0}`],
      ["Dropped events", data.modules?.event_bus?.dropped || 0],
    ]), { span: 4, subtitle: "Developer preview uses a deny-by-default capability gateway" })}
    ${panel("Loaded modules", `<div class="table-wrap"><table><thead><tr><th>Module</th><th>Health</th><th>Declared safe capabilities</th><th>Detail / actions</th></tr></thead><tbody>${rows}</tbody></table></div><div class="page-actions"><input type="file" id="moduleArchive" accept=".zip"><button class="button primary" data-module-action="install">Install ZIP</button><button class="button" data-module-action="reload">Reload modules</button><button class="button" data-module-action="clear-faults">Clear faults</button></div>`, { span: 8, subtitle: "User modules are installed outside the OS update root; bundled modules are protected" })}
  </div>`;
}

function operationalVoiceStatus(data, expanded = false) {
  const bridge = data.audio_bridge || {}, audio = bridge.audio || {}, rec = bridge.recognition || {}, scan = (data.speech_scan || {}).scan || {};
  const level = Number.isFinite(Number(audio.rms_dbfs)) ? `${Number(audio.rms_dbfs).toFixed(1)} dBFS` : "unavailable";
  const mic = audio.available === false ? "unavailable" : (audio.state || "stale");
  const gate = audio.speaker_playback_active ? "closed · speaker active" : (Number(audio.echo_tail_remaining_s || 0) > 0 ? `closed · echo tail ${Number(audio.echo_tail_remaining_s).toFixed(1)}s` : (audio.gate_open === false ? "closed" : "open"));
  const brain = data.voice?.brain?.state || "unavailable";
  const engine = rec.engine || rec.handoff?.engine_selected || "unavailable";
  const status = `<div class="operational-status-row"><div class="op-card"><b>MICROPHONE</b><strong>${esc(level)}</strong><span>${esc(mic)}</span><button class="button small" data-audio-control="mic-mute">Mute Microphone</button><button class="button small" data-audio-control="ptt">Push to Talk</button></div><div class="op-card"><b>LISTENING / WAKE WORD</b><strong>${esc(audio.pipeline_state || audio.state || "unavailable")}</strong><span>${esc((data.voice?.voice_settings?.effective?.wake_phrases || ["configured wake phrases"]).join(", "))}</span><button class="button small" data-audio-control="pause">Pause Listening</button></div><div class="op-card"><b>SPEAKER</b><strong>${audio.speaker_playback_active ? "active" : "idle"}</strong><span>volume ${esc(data.audio?.output?.volume ?? "unavailable")}</span><input type="range" min="0" max="100" value="80" aria-label="Speaker volume"><button class="button small" data-audio-control="speaker-mute">Mute Speaker</button><button class="button small" data-audio-control="stop">Stop Speaking</button></div><div class="op-card"><b>VOICE PIPELINE</b><strong>gate ${esc(gate)}</strong><span>Brain: ${esc(brain)} · STT: ${esc(engine)}</span><span>updated ${esc(audio.timestamp ? formatTimestamp(audio.timestamp) : "stale")}</span></div></div>`;
  const spans = Array.isArray(scan.spans) ? scan.spans : [];
  const full = String(scan.full_text || rec.latest_text || "");
  const highlighted = spans.length ? spans.map(s => `<span class="scan-${esc(s.type)}">${esc(full.slice(Number(s.start), Number(s.end)))}</span>`).join("") : esc(full || "No contextual transcript received yet — state is unavailable, not loading.");
  const scanPanel = `<section class="panel span-12 live-scan-panel"><header class="panel-header"><div><h3>Live Speech Recognition — Continuous</h3><p>Contextual transcript from Robot Body; only the extracted request is submitted to Brain.</p></div></header><div class="speech-scan-rendered">${highlighted}</div><div class="scan-meta">Wake: ${esc(scan.wake_phrase || "none")} · Request: ${esc(scan.request || rec.last_accepted_request || "none")} · Action: ${esc(scan.action || (rec.last_accepted_request ? "submitted" : "rejected"))} · Interaction: ${esc(scan.interaction_id || "none")} · STT: ${esc(scan.stt_engine || engine)} · Confidence: ${esc(scan.confidence ?? "unavailable")} · Duration: ${esc(scan.audio_duration_s ?? audio.duration_s ?? "unavailable")}s · VAD: ${esc(scan.vad_state || "unavailable")} · Mic: ${esc(mic)} · Speaker: ${audio.speaker_playback_active ? "active" : "idle"} · Gate: ${esc(gate)} · ${esc(scan.timestamp || audio.timestamp || "stale")}</div></section>`;
  return status + scanPanel;
}

function operationalConversation(data) { const items = data.voice_console?.items || []; const rows = items.filter(i => ["stt","manual","reply"].includes(i.kind)).map(i => `<div class="conversation-bubble ${i.kind === "reply" ? "robot" : "user"}"><small>${esc(i.source)} · ${esc(formatTimestamp(i.timestamp))}</small><div>${esc(i.text)}</div></div>`).join(""); return `<section class="panel span-12 operational-conversation"><header class="panel-header"><div><h3>Conversation</h3><p>Voice and keyboard requests with processing state.</p></div></header><div class="conversation-thread">${rows || "<span class=muted>No conversation messages yet.</span>"}</div><div class="conversation-compose"><textarea id="talkToLeoText" maxlength="1000" placeholder="Type a message"></textarea><button class="button primary" data-voice-action="talk-send">Send</button><button class="button" data-voice-action="talk-repeat">Repeat Reply</button><button class="button" data-voice-action="talk-clear">Clear Conversation</button><span id="talkToLeoState">${esc(state.talk.phase)}</span></div></section>`; }

function dashboardPage(data) { return `<div class="operational-dashboard">${operationalVoiceStatus(data)}${operationalConversation(data)}<details class="panel system-overview"><summary>System Overview</summary><div class="grid">${panel("BX1 OS", dataList([["Management version", data.interface.version], ["Robot Body version", data.robot_body?.version || "unavailable"], ["Brain version", data.brain?.version || "unavailable"], ["Brain connection", data.brain?.status || "unavailable"]]), {span:6})}${panel("Services and diagnostics", dataList([["Services", data.services.length], ["Camera", data.camera?.health || "unavailable"], ["Hardware", data.hardware?.diagnostics?.state || "unavailable"]]), {span:6})}</div></details></div>`; }
function voiceConsolePage(data) { return `<div class="operational-live-voice">${operationalVoiceStatus(data, true)}${operationalConversation(data)}${panel("Audio-event timeline", sharedVoiceFeed(data, true), {span:12})}${panel("Diagnostics", `<p>Raw microphone, accepted post-gate, Brain-submitted audio and transcription JSON remain Body-owned diagnostics.</p><div class="page-actions"><button class="button" data-prototype="Download diagnostic package">Download diagnostic package</button><button class="button" data-prototype="Clear diagnostic entry">Clear diagnostic entry</button><label>Recording retention <select class="input"><option>24 hours</option><option>7 days</option><option>30 days</option></select></label></div>`, {span:12})}</div>`; }

const RENDERERS = {
  dashboard: dashboardPage,
  system: systemPage,
  services: servicesPage,
  hardware: hardwarePage,
  camera: cameraPage,
  audio: audioPage,
  voice: voiceConsolePage,
  brain: brainPage,
  configuration: configurationPage,
  modules: modulesPage,
  logs: logsPage,
  deployment: deploymentPage,
  diagnostics: diagnosticsPage,
  updates: updatesPage,
  themes: themesPage,
  documentation: documentationPage,
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
  updateGlobalAudioControls(state.data);
  if (state.page === "voice" && !$("#speechScanText")) { $("#pageContent").insertAdjacentHTML("afterbegin", '<section class="speech-scan"><strong>Continuous speech scan</strong><p id="speechScanText">Contextual transcript, matched wake phrase and extracted request appear here.</p><div id="speechScanMeta" class="mono">Wake phrase: -- Â· Request: -- Â· VAD: -- Â· Gate: --</div></section>'); }
  $$("[data-bind='version']").forEach(node => { node.textContent = `v${state.data.interface.version}`; });
  renderNavigation();
  bindGlobalAudioControls();
  if (state.page === "documentation") loadDocumentation();
  bindPrototypeActions();
  bindTalkToLeo();
  enhanceConversationView();
  bindAudioBridgeForm();
  bindWakeSpeechForm();
  bindSpeechTest();
  if (["audio", "dashboard", "voice"].includes(state.page) && !state.audioTimer) state.audioTimer = window.setInterval(loadAudioBridge, 500);
  if (!["audio", "dashboard", "voice"].includes(state.page) && state.audioTimer) { window.clearInterval(state.audioTimer); state.audioTimer = null; }
  if (state.page === "camera") startCameraPreview();
  $("#workspace").focus({ preventScroll: true });
}

function enhanceConversationView() {
  const view = $("#talkToLeoState")?.nextElementSibling;
  if (!view) return;
  view.classList.add("conversation-view");
  $$(".log-line", view).forEach(line => {
    const who = $(".log-source", line)?.textContent || "System";
    line.classList.add("conversation-bubble", who === "John" ? "manual" : who === "LEO" ? "reply" : "system");
    const source = $(".log-source", line); if (source) source.textContent = `${who} · ${new Date().toLocaleTimeString()}`;
  });
  view.scrollTop = view.scrollHeight;
}

async function loadAudioBridge() {
  if (!["audio", "dashboard", "voice"].includes(state.page)) return;
  try {
    const [response, consoleResponse] = await Promise.all([fetch("/api/audio/bridge", { cache: "no-store" }), fetch("/api/voice/console", { cache: "no-store" })]);
    const [payload, consolePayload] = await Promise.all([response.json(), consoleResponse.json()]);
    if (response.ok && consoleResponse.ok) {
      state.data.audio_bridge = payload; state.data.voice_console = consolePayload;
      state.telemetryRevision = Math.max(state.telemetryRevision || 0, Number(payload.revision || payload.sequence || Date.now()));
      updateLiveVoiceDom(); updateGlobalAudioControls(state.data); updateLiveDataIndicator("live");
    } else updateLiveDataIndicator("update failed");
  } catch (_) { updateLiveDataIndicator("disconnected"); }
}

function updateLiveDataIndicator(stateName = "live") {
  const node = $("#liveDataIndicator"); if (!node) return;
  const now = new Date().toLocaleTimeString([], {hour: "2-digit", minute: "2-digit", second: "2-digit"});
  node.textContent = stateName === "live" ? `Live data · updated ${now}` : `Live data · ${stateName}`;
  node.dataset.state = stateName;
}

async function loadMcuStatus() {
  try {
    const response = await fetch("/api/mcu/status", {cache: "no-store"});
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "MCU unavailable");
    state.data.mcu = payload;
    const panel = $("#mcuStatusPanel");
    if (panel) panel.innerHTML = `<div><span>Connection</span><strong>${esc(payload.mcu_ok ? "connected" : "disconnected")}</strong></div><div><span>Firmware</span><strong>${esc(payload.firmware_version || "unavailable")}</strong></div><div><span>Protocol</span><strong>${esc(payload.protocol_version || "bx1.mcu.v1")}</strong></div><div><span>Heartbeat age</span><strong>${esc(payload.heartbeat_age_ms ?? "unavailable")}</strong></div><div><span>Safe state</span><strong>${payload.actuator_inhibit === false ? "check required" : "inhibited"}</strong></div>`;
  } catch (_) { const panel = $("#mcuStatusPanel"); if (panel) panel.dataset.state = "disconnected"; }
}

function ingestVoiceObservation(bridge) {
  const recognition = bridge.recognition || {};
  const text = String(recognition.latest_text || "").trim();
  const reason = String(recognition.rejection_reason || "").trim();
  const add = (role, tone, value) => {
    if (!value || state.voiceItems.some(item => item.role === role && item.text === value)) return;
    state.voiceItems.push({ role, tone, text: value.slice(0, 240), at: new Date().toLocaleTimeString() });
    state.voiceItems = state.voiceItems.slice(-24);
  };
  add("Heard", "stt", text); add("Failure", "failure", reason);
}

function updateLiveVoiceDom() {
  const feed = $("#sharedVoiceItems");
  const pausedScrollTop = feed && !state.voiceAutoScroll ? feed.scrollTop : null;
  $$('[data-live-voice]').forEach(node => { node.innerHTML = liveVoiceMarkup(state.data.audio_bridge || {}, node.dataset.liveVoice !== "dashboard"); });
  $$('[data-live-voice-status]').forEach(node => { node.innerHTML = liveVoiceStatusCard(state.data.audio_bridge || {}); });
  $$('[data-shared-voice]').forEach(node => { node.innerHTML = sharedVoiceFeed(state.data, state.page === "voice"); });
  const refreshedFeed = $("#sharedVoiceItems");
  if (refreshedFeed && state.voiceAutoScroll) refreshedFeed.scrollTop = refreshedFeed.scrollHeight;
  if (refreshedFeed && pausedScrollTop != null) refreshedFeed.scrollTop = pausedScrollTop;
  const stateLabel = $("#talkToLeoState");
  if (stateLabel) stateLabel.textContent = `${state.talk.phase}${state.talk.error ? ` — ${state.talk.error}` : ""}`;
}

function bindAudioBridgeForm() {
  const form = $("#audioBridgeForm");
  if (!form) return;
  form.addEventListener("submit", async event => {
    event.preventDefault();
    const settings = Object.fromEntries(new FormData(form).entries());
    const target = $("#audioBridgeState");
    if (target) target.textContent = "Applying through Robot Body…";
    try {
      const response = await fetch("/api/audio/bridge/settings", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ settings }) });
      const payload = await response.json();
      if (!response.ok || !payload.ok) throw new Error(payload.error || "Body rejected settings");
      if (target) target.textContent = payload.restart_required ? "Saved. Restart Robot Body via its approved management route to apply to active capture." : "Saved and effective.";
      await loadAudioBridge();
    } catch (error) { if (target) target.textContent = `Failed: ${error.message}`; }
  });
}

function bindWakeSpeechForm() {
  const form = $("#wakeSpeechForm");
  if (!form) return;
  form.addEventListener("submit", async event => {
    event.preventDefault();
    const settings = Object.fromEntries(new FormData(form).entries());
    settings.wake_phrases = $$('input[name="wake_phrase"]', form).map(input => input.value.trim()).filter(Boolean);
    const target = $("#wakeSpeechState");
    if (target) target.textContent = "Saving through Robot Body…";
    try {
      const response = await fetch("/api/audio/voice-settings/v1", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ settings }) });
      const payload = await response.json();
      if (!response.ok || !payload.ok) throw new Error(payload.error || "Robot Body rejected voice settings");
      if (target) target.textContent = `Saved by Robot Body · revision ${payload.revision || "updated"}`;
      await loadAudioBridge();
    } catch (error) { if (target) target.textContent = `Failed: ${error.message}`; }
  });
}

function bindSpeechTest() {
  const button = $('[data-speech-test="run"]');
  const result = $("#speechTestResult");
  if (!button || !result) return;
  button.addEventListener("click", async () => {
    button.disabled = true; result.textContent = "Listening through Robot Body…";
    try {
      const response = await fetch("/api/audio/speech-test", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
      const payload = await response.json();
      const handoff = payload.handoff || {};
      result.className = `result-box ${payload.ok ? "good" : "bad"}`;
      result.textContent = [
        payload.ok ? `Recognised: ${payload.text || "[no accepted text]"}` : `Test not accepted: ${payload.reason || payload.error || "unknown reason"}`,
        `Engine: ${payload.engine || handoff.engine_selected || "unknown"} · elapsed: ${payload.elapsed_ms ?? handoff.elapsed_ms ?? "--"} ms`,
        `Payload: ${handoff.audio_payload || "unknown"} · ${handoff.sample_rate_hz ?? "--"} Hz · ${handoff.channels ?? "--"} channel · ${handoff.duration_s ?? "--"} s`,
        `Primary request: ${handoff.primary_request || "not started"}${payload.fallback_reason ? ` · fallback/reason: ${payload.fallback_reason}` : ""}`,
        `Recommendation: ${payload.recommendation || "None"}`,
      ].join("\n");
      await loadAudioBridge();
    } catch (error) { result.className = "result-box bad"; result.textContent = `Speech Test failed: ${error.message}`; }
    finally { button.disabled = false; }
  });
}

function navigate(page, push = true) {
  if (!RENDERERS[page]) page = "dashboard";
  if (state.page === "camera" && page !== "camera") stopCameraPreview();
  state.page = page;
  if (push) history.pushState({ page }, "", page === "dashboard" ? "/" : `/${page}`);
  renderPage();
  loadMcuStatus();
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
  $$("[data-page-link]").forEach(node => {
    node.addEventListener("click", event => {
      event.preventDefault();
      navigate(node.dataset.pageLink);
    });
  });
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

async function moduleAction(action, moduleId = "") {
  try {
    let path = `/api/runtime/modules/${moduleId}/${action}`;
    let options = { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" };
    if (action === "reload") path = "/api/runtime/modules/reload";
    if (action === "clear-faults") path = "/api/runtime/modules/clear-faults";
    if (action === "install") {
      const file = $("#moduleArchive")?.files?.[0];
      if (!file || !file.name.endsWith(".zip")) throw new Error("Choose a module ZIP first.");
      path = "/api/runtime/modules/install";
      options = { method: "POST", headers: { "Content-Type": "application/zip" }, body: file };
    }
    const response = await fetch(path, options); const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Module action failed");
    toast("Module Manager", "Action completed."); await loadCoreTelemetry();
  } catch (error) { toast("Module action failed", error.message); }
}

async function voiceAction(action) {
  const result = $("#talkToLeoState");
  try {
    if (action === "talk-repeat") {
      const last = [...state.conversation].reverse().find(item => item.role === "John");
      if (!last) throw new Error("No browser-session message to repeat.");
      const input = $("#talkToLeoText");
      if (input) input.value = last.text;
      return voiceAction("talk-send");
    }
    let path = "/api/voice/brain-test";
    let body = {};
    if (action === "talk-send") {
      const input = $("#talkToLeoText");
      const text = input?.value?.trim() || "";
      if (!text) throw new Error("Enter a question first.");
      if (text.length > 1000) throw new Error("Message is too long.");
      path = "/api/voice/typed-test";
      body = { text };
      state.conversation.push({ role: "John", tone: "manual", text, timestamp: new Date().toLocaleTimeString() });
      state.voiceItems.push({ role: "John", tone: "manual", text, at: new Date().toLocaleTimeString() }); state.voiceItems = state.voiceItems.slice(-24);
      state.talk = { phase: "Sending to Brain", sessionId: "", busy: true, error: "" };
      state.talk.timer = window.setTimeout(() => {
        if (state.talk.busy && state.talk.phase === "Sending to Brain") {
          state.talk.phase = "Leo is thinking";
          if (result) result.textContent = state.talk.phase;
        }
      }, 350);
      if (result) result.textContent = state.talk.phase;
      $$("[data-voice-action='talk-send'], [data-voice-action='talk-clear']").forEach(node => { node.disabled = true; });
    } else if (action === "talk-clear") {
      if (state.talk.timer) window.clearTimeout(state.talk.timer);
      const input = $("#talkToLeoText");
      if (input) input.value = "";
      const counter = $("#talkToLeoCount");
      if (counter) counter.textContent = "0 / 1000";
      state.talk = { phase: "Ready", sessionId: "", busy: false, error: "", timer: null };
      state.conversation = [];
      state.voiceItems = [];
      await fetch("/api/voice/console/clear", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
      if (result) result.textContent = state.talk.phase;
      return;
    } else if (action === "clear-faults") {
      path = "/api/voice/faults/clear";
    }
    const response = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const payload = await response.json();
    if (!response.ok || (!payload.ok && action !== "brain-probe")) throw new Error(payload.error || payload.reason || "Voice action failed");
    if (action === "talk-send") {
      if (state.talk.timer) window.clearTimeout(state.talk.timer);
      state.talk = { phase: payload.state === "playing_reply" ? "Playing reply" : "Leo is thinking", sessionId: payload.session_id || "", busy: false, error: "", timer: null };
      const input = $("#talkToLeoText");
      if (input) input.value = "";
      state.conversation.push({ role: "LEO", tone: "reply", text: payload.reply || "Reply is playing through the Body speaker.", timestamp: new Date().toLocaleTimeString() });
      state.voiceItems.push({ role: "LEO", tone: "reply", text: payload.reply || "Reply is playing through the Body speaker.", at: new Date().toLocaleTimeString() }); state.voiceItems = state.voiceItems.slice(-24);
      if (result) result.textContent = state.talk.phase;
    } else if (action === "brain-probe") {
      if (result) result.textContent = payload.state === "connected" ? "Brain connected" : `Brain ${payload.state || "not connected"}`;
    }
    await loadCoreTelemetry();
  } catch (error) {
    if (action === "talk-send") {
      if (state.talk.timer) window.clearTimeout(state.talk.timer);
      state.talk = { phase: "Failed", sessionId: "", busy: false, error: error.message, timer: null };
      state.voiceItems.push({ role: "Failure", tone: "failure", text: error.message, at: new Date().toLocaleTimeString() }); state.voiceItems = state.voiceItems.slice(-24);
    }
    if (result) result.textContent = action === "talk-send" ? `Failed — ${error.message}` : error.message;
    toast("Voice diagnostic failed", error.message);
  }
}

async function liveAction(action) {
  if (action === "autoscroll") {
    state.voiceAutoScroll = !state.voiceAutoScroll;
    const button = $("[data-live-action='autoscroll']");
    if (button) button.textContent = state.voiceAutoScroll ? "Pause autoscroll" : "Resume autoscroll";
    return;
  }
  if (action === "clear") {
    const response = await fetch("/api/voice/console/clear", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    const payload = await response.json();
    if (!response.ok || !payload.ok) { toast("Live Voice", payload.error || "Could not clear session"); return; }
    state.data.voice_console = payload; state.conversation = []; state.voiceItems = [];
    const draft = $("#talkToLeoText"); if (draft) { draft.value = ""; draft.dispatchEvent(new Event("input")); }
    updateLiveVoiceDom();
  }
}

function bindTalkToLeo() {
  const input = $("#talkToLeoText");
  const counter = $("#talkToLeoCount");
  if (!input || !counter) return;
  input.disabled = false; // A request in flight must not block normal touchscreen typing.
  const help = $("#talkToLeoHelp");
  if (help) help.textContent = "Enter sends · Shift+Enter adds a line · Body → Brain chat/TTS → Body speaker. Hardware/action packets are blocked.";
  const update = () => { counter.textContent = `${input.value.length} / 1000`; };
  input.addEventListener("input", update);
  input.addEventListener("keydown", event => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (!state.talk.busy) voiceAction("talk-send");
    }
  });
  update();
}

function setCameraPreviewState(mode, detail = "") {
  const viewport = $("#cameraPreview");
  const message = $("#cameraPreviewState");
  if (!viewport || !message) return;
  viewport.dataset.state = mode;
  const copy = {
    loading: ["Connecting to Robot Body frame source", "BX1 OS will not open a camera device."],
    streaming: ["Near-live preview", "Frames are proxied from Existing Robot Body."],
    offline: ["Camera preview unavailable", detail || "Robot Body has not supplied a cached frame."],
    paused: ["Preview paused", "The page is hidden; the upstream connection has been released."],
  }[mode] || ["Preview unavailable", detail];
  message.innerHTML = `${mode === "loading" ? '<span class="camera-spinner"></span>' : ""}<strong>${esc(copy[0])}</strong><small>${esc(copy[1])}</small>`;
}

function releaseCameraObjectUrl() {
  if (state.cameraPreview.objectUrl) {
    URL.revokeObjectURL(state.cameraPreview.objectUrl);
    state.cameraPreview.objectUrl = "";
  }
}

function stopCameraPreview(paused = false) {
  state.cameraPreview.token += 1;
  if (state.cameraPreview.timer) clearTimeout(state.cameraPreview.timer);
  state.cameraPreview.timer = null;
  if (state.cameraPreview.controller) state.cameraPreview.controller.abort();
  state.cameraPreview.controller = null;
  releaseCameraObjectUrl();
  const image = $("#cameraPreviewImage");
  if (image) {
    image.onload = null;
    image.onerror = null;
    image.removeAttribute("src");
  }
  state.cameraPreview.mode = paused ? "paused" : "idle";
  if (paused) setCameraPreviewState("paused");
}

async function runSnapshotFallback(token) {
  if (token !== state.cameraPreview.token || state.page !== "camera" || document.hidden) return;
  state.cameraPreview.mode = "snapshot";
  const controller = new AbortController();
  state.cameraPreview.controller = controller;
  const requestTimeout = setTimeout(() => controller.abort(), 2200);
  try {
    const response = await fetch(`/api/core/camera/snapshot?t=${Date.now()}`, {
      cache: "no-store",
      signal: controller.signal,
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const blob = await response.blob();
    if (!blob.type.startsWith("image/jpeg")) throw new Error("Invalid frame");
    if (token !== state.cameraPreview.token) return;
    releaseCameraObjectUrl();
    state.cameraPreview.objectUrl = URL.createObjectURL(blob);
    const image = $("#cameraPreviewImage");
    if (!image) return;
    image.src = state.cameraPreview.objectUrl;
    setCameraPreviewState("streaming");
  } catch (error) {
    if (token === state.cameraPreview.token) setCameraPreviewState("offline", error.message);
  } finally {
    clearTimeout(requestTimeout);
    if (state.cameraPreview.controller === controller) {
      state.cameraPreview.controller = null;
    }
    if (token === state.cameraPreview.token && state.page === "camera" && !document.hidden) {
      state.cameraPreview.timer = setTimeout(() => runSnapshotFallback(token), 400);
    }
  }
}

function startCameraPreview() {
  stopCameraPreview(document.hidden);
  if (document.hidden || state.page !== "camera") return;
  const image = $("#cameraPreviewImage");
  if (!image) return;
  const token = state.cameraPreview.token;
  state.cameraPreview.mode = "mjpeg";
  setCameraPreviewState("loading");
  image.onload = () => {
    if (token === state.cameraPreview.token) setCameraPreviewState("streaming");
  };
  image.onerror = () => {
    if (token !== state.cameraPreview.token) return;
    image.onload = null;
    image.onerror = null;
    image.removeAttribute("src");
    runSnapshotFallback(token);
  };
  image.src = `/api/core/camera/stream?fps=8&t=${Date.now()}`;
}

function updateCameraPageTelemetry() {
  if (state.page !== "camera") return;
  const camera = state.data.camera || {};
  const stale = Boolean(cameraValue(camera, "stale", true));
  const warning = $("#cameraStaleWarning");
  if (warning) warning.classList.toggle("hidden", !stale);
  const label = $("#cameraConnectionLabel");
  if (label) {
    label.textContent = cameraValue(camera, "preview_available", false)
      ? "Frame source available"
      : "Frame source unavailable";
  }
}

function openMobileNav() { document.body.classList.add("sidebar-open"); }
function closeMobileNav() { document.body.classList.remove("sidebar-open"); }

function managementDataFromCore(statePayload, servicesPayload, healthPayload, hardwarePayload, audioPayload, robotBodyPayload, cameraPayload, voicePayload = {}, modulesPayload = {}, widgetsPayload = {}, audioBridgePayload = {}, voiceConsolePayload = {}) {
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
      version: "0.11.0-mcu-foundation",
      tag: "BX1_OS_v0.8.0_voice_controls",
      architecture_only: true,
      capabilities: management.capabilities || {},
    },
    robot: {
      name: robot.name || "LEO",
      status: healthPayload.state || robot.state || "unknown",
      mode: robot.mode === "observer_only" ? "Body-mediated capability mode" : (robot.mode || "Body-mediated capability mode"),
      hostname: system.hostname,
      ip: network.ip,
      existing_ui_port: management.existing_ui_port || 8088,
      management_port: management.port || 8089,
    },
    brain: {
      status: voicePayload.brain?.state === "connected" ? "Connected" : voicePayload.brain?.state === "degraded" ? "Degraded" : "Not connected",
      url: voicePayload.brain_endpoint || "",
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
      camera_groups: observed(cameraPayload.devices, []),
      raw_cameras: observed(hardwarePayload.hardware?.inventory, []).filter(
        device => device.category === "camera"
      ),
      diagnostics: observed(hardwarePayload.hardware?.diagnostics, { checks: [] }),
    },
    camera: {
      ...(cameraPayload.camera || {}),
      proxy: cameraPayload.proxy || {},
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
    voice: voicePayload,
    modules: modulesPayload,
    audio_bridge: audioBridgePayload,
    voice_console: voiceConsolePayload,
    widgets: widgetsPayload,
    deployment: {
      current_version: "0.11.0-mcu-foundation",
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
      "/api/core/camera",
      "/api/voice/status",
      "/api/runtime/modules",
      "/api/runtime/widgets",
      "/api/audio/bridge",
      "/api/audio/speech-scan",
      "/api/voice/console",
      "/api/speech-learning",
    ];
    const responses = await Promise.all(
      paths.map(path => fetch(path, { cache: "no-store" }))
    );
    const failed = responses.find(response => !response.ok);
    if (failed) throw new Error(`HTTP ${failed.status}`);
    const [coreState, services, health, , , hardware, audio, robotBody, camera, voice, modules, widgets, audioBridge, speechScan, voiceConsole, speechLearning] = await Promise.all(
      responses.map(response => response.json())
    );
    state.data = managementDataFromCore(coreState, services, health, hardware, audio, robotBody, camera, voice, modules, widgets, audioBridge, voiceConsole);
    state.data.speech_scan = speechScan;
    state.data.speech_learning = speechLearning;
    const session = state.talk.sessionId && voice.sessions?.[state.talk.sessionId];
    if (session?.state === "complete") state.talk = { phase: "Complete", sessionId: state.talk.sessionId, busy: false, error: "", timer: null };
    else if (session?.state === "failed") state.talk = { phase: "Failed", sessionId: state.talk.sessionId, busy: false, error: session.reason || "voice_fault", timer: null };
    else if (session?.state === "thinking") state.talk.phase = "Leo is thinking";
    else if (session?.state === "playing") state.talk.phase = "Playing reply";
    state.connected = true;
    if (state.page === "camera") updateCameraPageTelemetry();
    else if (["voice", "brain", "audio"].includes(state.page)) updateLiveVoiceDom();
    else { updateLiveDataIndicator("live"); updateGlobalAudioControls(state.data); }
  } catch (error) {
    state.connected = false;
    toast("Using interface preview", "BX1 OS Core telemetry is not available.");
  } finally {
    state.telemetryLoading = false;
  }
}

function bindGlobalAudioControls() {
  const root = $(".global-audio-controls"); if (!root || root.dataset.bound) return; root.dataset.bound = "1";
  root.addEventListener("click", event => { const button = event.target.closest("[data-audio-control]"); if (!button) return; button.classList.toggle("active"); const action = button.dataset.audioControl; const stateText = $("#globalMicState"); if (action === "mic-mute") stateText.textContent = button.classList.contains("active") ? "Privacy muted" : "Listening"; if (action === "pause") stateText.textContent = button.classList.contains("active") ? "Listening paused" : "Listening"; if (action === "ptt") stateText.textContent = "Push to Talk ready"; if (action === "speaker-mute") $("#globalSpeakerState").textContent = button.classList.contains("active") ? "Muted" : "Idle"; if (action === "stop") $("#globalSpeakerState").textContent = "Stopped"; });
  const volume = $("#globalVolume"); volume?.addEventListener("input", () => { $("#globalSpeakerState").textContent = `Volume ${volume.value}%`; });
}
function updateGlobalAudioControls(data) {
  const bridge = data?.audio_bridge || {}, audio = bridge.audio || {}, rec = bridge.recognition || {};
  const level = Number.isFinite(Number(audio.rms_dbfs)) ? `${Number(audio.rms_dbfs).toFixed(1)} dBFS` : (audio.available === false ? "unavailable" : "stale");
  const gate = audio.speaker_playback_active ? "closed · speaker active" : (Number(audio.echo_tail_remaining_s || 0) > 0 ? "closed · echo tail" : (audio.gate_open === false ? "closed" : "open"));
  const mic = audio.available === false ? "unavailable" : (audio.state || "stale");
  const speaker = audio.speaker_playback_active ? "active" : "idle";
  const set = (id, value) => { const node = $(id); if (node) node.textContent = value; };
  set("#globalMicLevel", level); set("#globalMicState", mic); set("#globalSpeakerState", speaker); set("#globalGateState", `Gate state: ${gate}`);
}
async function loadDocumentation() { try { const response = await fetch("/api/documentation", {cache:"no-store"}); const payload = await response.json(); const target = $("#documentationContent"); if (target) target.textContent = payload.content || "No offline documentation found."; } catch (_) {} }

function init() {
  renderNavigation();
  renderPage();
  loadMcuStatus();
  $("#primaryNav").addEventListener("click", event => {
    const item = event.target.closest("[data-page]");
    if (item) navigate(item.dataset.page);
  });
  $("#pageContent").addEventListener("click", event => {
    const mcuButton = event.target.closest("[data-mcu-action]");
    if (mcuButton) {
      const action = mcuButton.dataset.mcuAction;
      const stateNode = $("#mcuActionState");
      if (stateNode) stateNode.textContent = "Pending…";
      mcuButton.disabled = true;
      const path = action === "reconnect" ? "/api/mcu/reconnect" : `/api/mcu/${action}`;
      fetch(path, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({})})
        .then(response => response.json().then(payload => ({response, payload})))
        .then(({response, payload}) => { if (!response.ok || !payload.ok) throw new Error(payload.error || "MCU command failed"); if (stateNode) stateNode.textContent = "Completed"; })
        .catch(error => { if (stateNode) stateNode.textContent = `Failed: ${error.message}`; })
        .finally(() => { mcuButton.disabled = false; });
    }
    const action = event.target.closest("[data-voice-action]")?.dataset.voiceAction;
    if (action) voiceAction(action);
    const live = event.target.closest("[data-live-action]")?.dataset.liveAction;
    if (live) liveAction(live);
    const wake = event.target.closest("[data-wake-action]")?.dataset.wakeAction;
    if (wake === "add") {
      const rows = $("#wakePhraseRows");
      if (rows && $$('input[name="wake_phrase"]', rows).length < 8) rows.insertAdjacentHTML("beforeend", '<div class="page-actions wake-phrase-row"><input class="input" name="wake_phrase" maxlength="48" value="" aria-label="Wake phrase"><button class="button small" type="button" data-wake-action="remove">Remove</button></div>');
    }
    if (wake === "remove") {
      const row = event.target.closest(".wake-phrase-row");
      if (row && $$('input[name="wake_phrase"]', $("#wakePhraseRows")).length > 1) row.remove();
    }
    const moduleButton = event.target.closest("[data-module-action]");
    if (moduleButton) moduleAction(moduleButton.dataset.moduleAction, moduleButton.dataset.moduleId || "");
  });
  $("#sidebarCollapse").addEventListener("click", () => {
    const shell = $(".app-shell");
    shell.dataset.sidebar = shell.dataset.sidebar === "collapsed" ? "expanded" : "collapsed";
  });
  $("#mobileMenu").addEventListener("click", openMobileNav);
  $("#sidebarScrim").addEventListener("click", closeMobileNav);
  window.addEventListener("popstate", () => {
    if (state.page === "camera") stopCameraPreview();
    state.page = routeFromLocation();
    renderPage();
  });
  document.addEventListener("visibilitychange", () => {
    if (state.page !== "camera") return;
    if (document.hidden) stopCameraPreview(true);
    else startCameraPreview();
  });
  window.addEventListener("beforeunload", () => stopCameraPreview());
  document.addEventListener("keydown", event => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      toast("Global search", "Search architecture is ready for a future indexing service.");
    }
    if (event.key === "Escape") closeMobileNav();
  });
  loadCoreTelemetry();
  window.setInterval(loadCoreTelemetry, 5000);
  window.setInterval(loadMcuStatus, 5000);
}

document.addEventListener("DOMContentLoaded", init);

/* Canonical five-theme operational layout.  These renderers intentionally
   replace the earlier alpha dashboard while reusing the permanent shell. */
const CANONICAL_THEMES = {
  light: {label:"Light Mode — Clean", vars:{"--bg":"#f3f6f8","--bg-raised":"#e7edf1","--sidebar":"#dce5ea","--panel":"#ffffff","--panel-soft":"#f5f8fa","--panel-hover":"#e9f0f3","--border":"#c5d2da","--text":"#132330","--text-soft":"#45606e","--muted":"#6c7f89","--accent":"#168b9b","--accent-strong":"#0d6877","--blue":"#2878c7","--green":"#168952","--red":"#bf3947","--amber":"#a86714","--user-bubble":"#d9ecff","--robot-bubble":"#dff5e9"}},
  darkBlue: {label:"Dark Blue — Modern",vars:{"--bg":"#07111d","--bg-raised":"#0c1b2b","--sidebar":"#081522","--panel":"#102335","--panel-soft":"#0b1a29","--panel-hover":"#183650","--border":"#294761","--text":"#edf6ff","--text-soft":"#b2c5d3","--muted":"#7f9aaa","--accent":"#4bc7e8","--accent-strong":"#1a9ac2","--blue":"#5ba9ff","--green":"#45d58b","--red":"#f06b76","--amber":"#f0bd58","--user-bubble":"#163b5b","--robot-bubble":"#123b2c"}},
  cyberGreen: {label:"Cyber Green — Tech",vars:{"--bg":"#06110e","--bg-raised":"#0a1d17","--sidebar":"#06130f","--panel":"#0d241b","--panel-soft":"#091b15","--panel-hover":"#123c29","--border":"#24523a","--text":"#eafff0","--text-soft":"#a8cbb7","--muted":"#709b83","--accent":"#55ed9a","--accent-strong":"#21bd6c","--blue":"#61cfff","--green":"#58ed9a","--red":"#ff6876","--amber":"#f5c85a","--user-bubble":"#123d35","--robot-bubble":"#164c2b"}},
  industrialOrange: {label:"Industrial Orange — Robotic",vars:{"--bg":"#15100b","--bg-raised":"#24180e","--sidebar":"#17110c","--panel":"#302016","--panel-soft":"#21160f","--panel-hover":"#4a2c18","--border":"#684126","--text":"#fff4e7","--text-soft":"#d4b79b","--muted":"#aa896c","--accent":"#ffad4b","--accent-strong":"#d9781c","--blue":"#68b8ff","--green":"#6ed497","--red":"#ff6c6c","--amber":"#ffbd4c","--user-bubble":"#49301c","--robot-bubble":"#26402d"}},
  softPastel: {label:"Soft Pastel — Friendly",vars:{"--bg":"#f4f0f5","--bg-raised":"#e9e2ec","--sidebar":"#ddd2e3","--panel":"#fffafd","--panel-soft":"#f7f0f8","--panel-hover":"#f0e5f2","--border":"#d6c7da","--text":"#30283a","--text-soft":"#665873","--muted":"#8c7d99","--accent":"#a76fd1","--accent-strong":"#8650b5","--blue":"#6097d6","--green":"#55ad82","--red":"#d45c71","--amber":"#c68b45","--user-bubble":"#e6dcfa","--robot-bubble":"#dff3e6"}},
};
function applyCanonicalTheme(id, persist = true) { const theme = CANONICAL_THEMES[id] || CANONICAL_THEMES.darkBlue; const shell={"--header":"var(--bg-raised)","--sidebar-border":"var(--border)","--sidebar-text":"var(--text)","--sidebar-muted":"var(--muted)","--sidebar-icon":"var(--text-soft)","--sidebar-hover":"var(--panel-hover)","--sidebar-active":"var(--panel-hover)","--sidebar-active-text":"var(--text)","--header-text":"var(--text)","--search-bg":"var(--panel-soft)","--input-bg":"var(--panel-soft)","--input-text":"var(--text)"}; Object.entries({...theme.vars,...shell}).forEach(([key,value]) => document.documentElement.style.setProperty(key,value)); document.documentElement.dataset.theme = id; if (persist) localStorage.setItem("bx1-os-theme", id); }
function microphoneGauge(a) { const rms=Number(a.rms_dbfs), peak=Number(a.peak_dbfs), threshold=Number(a.threshold_dbfs); const valid=Number.isFinite(rms), thresholdValid=Number.isFinite(threshold), pct=valid?Math.max(0,Math.min(100,(rms+90)/.9)):0, thresholdPct=thresholdValid?Math.max(0,Math.min(100,(threshold+90)/.9)):null; const stale=valid && a.timestamp && (Date.now()-Date.parse(a.timestamp)>15000); let status=a.microphone_privacy_muted?"muted":a.listening_paused?"paused":a.speaker_playback_active?"speaker-gated":!valid?"unavailable":stale?"stale":thresholdValid&&rms>=threshold?"speech detected":"below threshold"; const tone=status==="speech detected"?"active":(status==="muted"||status==="failed")?"danger":status==="speaker-gated"?"gated":"subdued"; return `<div class="mic-gauge ${tone}" role="meter" aria-label="Microphone RMS level" aria-valuemin="-90" aria-valuemax="0" aria-valuenow="${valid?rms:""}"><div class="mic-gauge-track"><i style="width:${pct}%"></i>${thresholdPct===null?"":`<b style="left:${thresholdPct}%" title="Threshold ${threshold.toFixed(1)} dBFS"></b>`}</div><div class="mic-gauge-readout"><strong>Current: ${valid?rms.toFixed(1)+" dBFS":"unavailable"}</strong><span>Peak: ${Number.isFinite(peak)?peak.toFixed(1)+" dBFS":"unavailable"}</span><span>Threshold: ${thresholdValid?threshold.toFixed(1)+" dBFS":"unavailable"}</span></div><small class="mic-gauge-state">${status}${a.timestamp?` · ${formatTimestamp(a.timestamp)}`:""}</small></div>`; }
function canonicalTopCards(data) { const bridge=data.audio_bridge||{}, a=bridge.audio||{}, r=bridge.recognition||{}, brain=data.voice?.brain?.state||"unavailable"; const gate=a.speaker_playback_active?"closed · speaker active":Number(a.echo_tail_remaining_s||0)>0?"closed · echo tail":a.gate_open===false?"closed":"open"; const engine=r.handoff?.engine_selected||r.engine||"unavailable"; const wake=data.voice?.voice_settings?.effective?.wake_phrases||["configured wake phrases"]; return `<div class="canonical-top-cards"><section class="canonical-card"><h4>Microphone</h4>${microphoneGauge(a)}<button class="button danger" data-audio-control="mic-mute">Mute Microphone</button><button class="button" data-audio-control="ptt">Push to Talk</button></section><section class="canonical-card"><h4>Listening / Wake Word</h4><div class="waveform"><i></i><i></i><i></i><i></i><i></i></div><strong>${esc(a.pipeline_state||a.state||"unavailable")}</strong><span>${esc(wake.join(", "))}</span><button class="button" data-audio-control="pause">Pause Listening</button></section><section class="canonical-card"><h4>Speaker</h4><strong>${a.speaker_playback_active?"active":"idle"}</strong><span>Volume ${esc(data.audio?.output?.volume??"unavailable")}</span><input type="range" min="0" max="100" value="80" aria-label="Speaker volume"><button class="button danger" data-audio-control="speaker-mute">Mute Speaker</button><button class="button" data-audio-control="stop">Stop Speaking</button></section><section class="canonical-card"><h4>Voice / System State</h4><strong>Gate ${esc(gate)}</strong><span>Brain ${esc(brain)}</span><span>STT ${esc(engine)}</span><span>${esc(a.timestamp?formatTimestamp(a.timestamp):"stale")}</span></section></div>`; }
function canonicalScan(data) { const scan=(data.speech_scan||{}).scan||{}, bridge=data.audio_bridge||{}, r=bridge.recognition||{}, a=bridge.audio||{}; const text=String(scan.full_text||r.latest_text||""); const spans=Array.isArray(scan.spans)?scan.spans:[]; let cursor=0; let html=""; spans.slice().sort((x,y)=>Number(x.start)-Number(y.start)).forEach(s=>{const start=Math.max(cursor,Number(s.start)||0),end=Math.max(start,Number(s.end)||0); html+=esc(text.slice(cursor,start))+`<mark class="span-${esc(s.type)}">${esc(text.slice(start,end))}</mark>`; cursor=end;}); html+=esc(text.slice(cursor)); if(!html) html="<span class=muted>Transcript unavailable — waiting for a Body recognition update.</span>"; return `<section class="canonical-panel speech-recognition"><header><h3>Live Speech Recognition — Continuous</h3><span class="status-badge">${esc(scan.action||"unavailable")}</span></header><div class="context-transcript">${html}</div><div class="highlight-legend"><span class="legend-wake">Wake phrase</span><span class="legend-request">Extracted request</span><span class="legend-context">Context</span><span class="legend-uncertain">Uncertain</span><span class="legend-gated">Rejected / gated</span></div><dl class="scan-details"><div><dt>Matched wake phrase</dt><dd>${esc(scan.wake_phrase||"none")}</dd></div><div><dt>Exact request to Brain</dt><dd>${esc(scan.request||r.last_accepted_request||"none")}</dd></div><div><dt>Interaction / confidence</dt><dd>${esc(scan.interaction_id||"none")} · ${esc(scan.confidence??"unavailable")}</dd></div><div><dt>STT / duration / VAD</dt><dd>${esc(scan.stt_engine||r.handoff?.engine_selected||r.engine||"unavailable")} · ${esc(scan.audio_duration_s??"unavailable")}s · ${esc(scan.vad_state||"unavailable")}</dd></div><div><dt>Mic / speaker / gate</dt><dd>${esc(a.state||"unavailable")} · ${a.speaker_playback_active?"active":"idle"} · ${a.gate_open===false?"closed":"open"}</dd></div><div><dt>Timestamp</dt><dd>${esc(scan.timestamp||a.timestamp||"stale")}</dd></div></dl></section>`; }
function canonicalConversation(data) { const items=(data.voice_console?.items||[]).filter(i=>["stt","manual","reply"].includes(i.kind)); const rows=items.map(i=>`<article class="chat-bubble ${i.kind==="reply"?"robot":"user"}"><small>${i.kind==="reply"?"Robot":"You"} · ${esc(i.source||"voice")} · ${esc(formatTimestamp(i.timestamp))}</small><div>${esc(i.text)}</div></article>`).join(""); return `<section class="canonical-panel conversation-panel"><header><h3>Conversation</h3><span class="status-badge">${esc(state.talk.phase)}</span></header><div class="chat-history">${rows||"<p class=muted>No conversation yet.</p>"}</div><div class="chat-input-row"><textarea id="talkToLeoText" maxlength="1000" placeholder="Type a message… Enter sends; Shift+Enter adds a newline"></textarea><button class="button primary" data-voice-action="talk-send">Send</button></div><div class="chat-actions"><button class="button" data-voice-action="talk-send">Listen and Send</button><button class="button" data-voice-action="talk-repeat">Repeat Reply</button><button class="button" data-audio-control="stop">Stop Reply</button><button class="button" data-voice-action="talk-clear">Clear Conversation</button></div></section>`; }
function canonicalDiagnostics(data) { const a=data.audio_bridge?.audio||{}, rec=data.audio_bridge?.recognition||{}; return `<section class="canonical-panel diagnostics-panel"><header><h3>Audio Diagnostics</h3></header><div class="diagnostic-tiles">${["Raw Microphone","After Gate / Accepted","Sent to Brain","Brain Received","Transcription JSON"].map((name,i)=>`<div class="diagnostic-tile"><strong>${name}</strong><span>${i===0&&a.available!==false?"available":"unavailable"}</span><small>${i===4?esc(rec.engine||"unavailable"):i===0?esc(a.duration_s?`${a.duration_s}s`:"duration unavailable"):"metadata only"}</small><button class="button small" data-prototype="Play ${name}">▶ Play</button></div>`).join("")}</div><div class="diagnostic-footer"><button class="button small" data-prototype="Download diagnostic package">Download diagnostic package</button><span>Recording state: metadata only · retention configured by Body</span></div></section>`; }
function canonicalQuick() { return `<section class="canonical-panel quick-panel"><header><h3>Quick Controls</h3></header><div class="quick-grid"><button class="button" data-audio-control="pause">Stop Listening</button><button class="button" data-audio-control="pause">Pause Conversation</button><button class="button danger" data-audio-control="mic-mute">Mute Microphone</button><button class="button danger" data-audio-control="speaker-mute">Mute Speaker</button><button class="button" data-audio-control="stop">Stop Speaking</button><button class="button" data-voice-action="talk-clear">Clear History</button><button class="button" data-prototype="Download logs">Download Logs</button></div></section>`; }
function audioStatusFrame(data){return `<section class="canonical-panel audio-status-frame"><header><div><h2>Audio Status and Controls</h2><p>Single operational owner for microphone, listening, speaker and voice pipeline state.</p></div><a class="help-link" href="/documentation#microphone-gauge">Help</a></header>${canonicalTopCards(data)}</section>`;}
function manualRecordingFrame(){return `<section class="canonical-panel recording-frame"><header><div><h2>Manual Microphone Recording</h2><p>Diagnostic WAV capture only; temporary recording is replaced by the next successful recording.</p></div><a class="help-link" href="/documentation#manual-recording">Help</a></header><div class="recording-controls"><label>Duration<select id="manualRecordDuration"><option value="5">5 seconds</option><option value="10">10 seconds</option><option value="20">20 seconds</option></select></label><button class="button primary" data-record-action="start">Start Recording</button><button class="button" data-record-action="stop">Stop Recording</button><button class="button" data-record-action="play">Play Recording</button><button class="button" data-record-action="download">Download WAV</button><button class="button" data-record-action="keep">Keep Recording</button><button class="button" data-record-action="save">Save to Speech Learning</button><button class="button danger" data-record-action="delete">Delete Recording</button></div><div id="manualRecordingState" class="recording-state" aria-live="polite">Idle</div><audio id="manualRecordingPlayer" controls preload="none" hidden></audio><dl class="recording-meta" id="manualRecordingMeta"><div><dt>State</dt><dd>idle</dd></div><div><dt>Recording ID</dt><dd>none</dd></div><div><dt>Retention</dt><dd>Temporary recording — replaced by the next recording</dd></div><div><dt>Format</dt><dd>RIFF/WAVE · PCM · 16 kHz · mono · 16-bit</dd></div></dl></section>`;}
function loopbackFrame(){return `<section class="canonical-panel loopback-frame"><header><div><h2>Speaker-to-Microphone Recognition Test</h2><p>Isolated diagnostic capture. It cannot wake, submit commands or create chat messages.</p></div><a class="help-link" href="/documentation#loopback-test">Help</a></header><div class="recording-controls"><label>Expected phrase<select id="loopbackPhrase"><option>Hey Leo, can you tell me the current battery level?</option><option>The quick brown fox jumps over the lazy dog.</option><option>BX1 uses Makerbase motors over RS485.</option><option>Arduino Modulino movement sensor diagnostic.</option></select></label><label>Speaker volume<input id="loopbackVolume" type="number" min="0" max="100" value="50"></label><label>Post-roll seconds<input id="loopbackPostroll" type="number" min="0" max="5" value="1"></label><button class="button primary" data-loopback-action="start">Start Test</button><button class="button" data-loopback-action="cancel">Cancel Test</button><button class="button" data-loopback-action="play">Play Captured Audio</button><button class="button" data-loopback-action="download">Download WAV</button><button class="button" data-loopback-action="stt">Re-run STT</button><button class="button" data-loopback-action="save">Save to Speech Learning</button><button class="button danger" data-loopback-action="delete">Delete Test</button></div><dl class="recording-meta" id="loopbackMeta"><div><dt>State</dt><dd>ready</dd></div><div><dt>Expected</dt><dd>Awaiting test</dd></div><div><dt>Comparison</dt><dd>WER withheld until both texts exist</dd></div></dl></section>`;}
function speechLearningSummary(data){const s=data.speech_learning?.summary||{};return `<section class="canonical-panel learning-summary-frame"><header><h2>Speech Learning Summary</h2><a class="help-link" href="/speech-learning">Open Speech Learning</a></header><div class="scan-details"><div><dt>Captured</dt><dd>${s.total||0}</dd></div><div><dt>Reviewed</dt><dd>${s.reviewed||0}</dd></div><div><dt>Approved</dt><dd>${s.approved||0}</dd></div><div><dt>Corrected</dt><dd>${s.corrected||0}</dd></div><div><dt>Vocabulary revision</dt><dd>${data.speech_learning?.vocabulary_revision??0}</dd></div><div><dt>Sync</dt><dd>${data.speech_learning?.sync?.state||"pending"}</dd></div></div></section>`;}
function dashboardPage(data) { return `<div class="canonical-dashboard linear-audio-layout">${audioStatusFrame(data)}${canonicalScan(data)}${canonicalConversation(data)}${manualRecordingFrame()}${loopbackFrame()}${canonicalDiagnostics(data)}${speechLearningSummary(data)}<details class="system-overview"><summary>System Overview</summary>${panel("BX1 OS components",dataList([["Management version",data.interface.version],["Robot Body version",data.robot_body?.version||"unavailable"],["Brain version",data.brain?.version||"unavailable"],["Brain connection",data.brain?.status||"unavailable"]]),{span:12})}</details></div>`; }
function voiceConsolePage(data) { return `<div class="canonical-live-voice linear-audio-layout">${audioStatusFrame(data)}${canonicalScan(data)}${canonicalConversation(data)}${manualRecordingFrame()}${loopbackFrame()}${canonicalDiagnostics(data)}${speechLearningSummary(data)}${panel("Rolling audio-event timeline",sharedVoiceFeed(data,true),{span:12})}<details class="system-overview"><summary>System Overview</summary>${panel("BX1 OS components",dataList([["Management version",data.interface.version],["Robot Body version",data.robot_body?.version||"unavailable"],["Brain version",data.brain?.version||"unavailable"]]),{span:12})}</details></div>`; }
function themesPage() { const active=localStorage.getItem("bx1-os-theme")||"darkBlue"; const cards=Object.entries(CANONICAL_THEMES).map(([id,t])=>`<button class="theme-preview ${active===id?"active":""}" data-theme-select="${id}"><span class="theme-preview-swatch" style="background:linear-gradient(135deg,${t.vars["--panel"]},${t.vars["--accent"]});border-color:${t.vars["--border"]}" data-theme-preview="${id}"></span><strong>${esc(t.label)}</strong><small>${active===id?"Active theme":"Select theme"}</small></button>`).join(""); return `<div class="theme-editor-page"><section class="theme-gallery"><header><h3>BX1 OS Themes</h3><p>Five canonical visual presets. Selection applies to the complete OS.</p></header><div class="theme-grid">${cards}</div></section><section class="theme-editor"><h3>Theme Editor</h3><div class="theme-actions"><button class="button primary" data-theme-action="apply">Apply</button><button class="button" data-theme-action="save">Save</button><button class="button" data-theme-action="save-as">Save As</button><button class="button" data-theme-action="load">Load</button><button class="button" data-theme-action="rename">Rename</button><button class="button" data-theme-action="duplicate">Duplicate</button><button class="button danger" data-theme-action="delete">Delete custom theme</button><button class="button" data-theme-action="export">Export</button><button class="button" data-theme-action="import">Import</button><button class="button" data-theme-action="restore">Restore BX1 Default</button></div><div class="token-editor">${Object.keys(CANONICAL_THEMES.darkBlue.vars).map(k=>`<label>${esc(k.replace("--",""))}<input type="text" value="${esc(CANONICAL_THEMES.darkBlue.vars[k])}" data-theme-token="${k}"></label>`).join("")}</div><div class="theme-live-preview">${canonicalTopCards(state.data)}${canonicalConversation(state.data)}</div></section></div>`; }
Object.assign(RENDERERS,{dashboard:dashboardPage,voice:voiceConsolePage,themes:themesPage});
applyCanonicalTheme(localStorage.getItem("bx1-os-theme")||"darkBlue",false);
document.addEventListener("click",event=>{const select=event.target.closest("[data-theme-select]"); if(select){applyCanonicalTheme(select.dataset.themeSelect); renderPage(); return;} const action=event.target.closest("[data-theme-action]")?.dataset.themeAction; if(!action)return; const current=localStorage.getItem("bx1-os-theme")||"darkBlue"; const custom=JSON.parse(localStorage.getItem("bx1-os-custom-themes")||"{}"); if(action==="restore"){applyCanonicalTheme("darkBlue");renderPage();} else if(action==="save"||action==="apply"){localStorage.setItem("bx1-os-theme",current); if(action==="save") toast("Theme saved",CANONICAL_THEMES[current]?.label||current);} else if(action==="save-as"){const name=prompt("Save theme as",`${current}-custom`); if(name){custom[name]={...(CANONICAL_THEMES[current]||{}),label:name};localStorage.setItem("bx1-os-custom-themes",JSON.stringify(custom));toast("Theme saved as",name);}} else if(action==="duplicate"){const name=prompt("Duplicate theme as",`${current}-copy`); if(name){custom[name]={...(CANONICAL_THEMES[current]||{}),label:name};localStorage.setItem("bx1-os-custom-themes",JSON.stringify(custom));toast("Theme duplicated",name);}} else if(action==="rename"){const name=prompt("Rename current theme",current); if(name){custom[name]={...(CANONICAL_THEMES[current]||{}),label:name};localStorage.setItem("bx1-os-custom-themes",JSON.stringify(custom));localStorage.setItem("bx1-os-theme",name);toast("Theme renamed",name);}} else if(action==="delete"){if(confirm("Delete this custom theme?")){delete custom[current];localStorage.setItem("bx1-os-custom-themes",JSON.stringify(custom));applyCanonicalTheme("darkBlue");renderPage();}} else if(action==="export"){const blob=new Blob([JSON.stringify({theme:current,custom},null,2)],{type:"application/json"});const link=document.createElement("a");link.href=URL.createObjectURL(blob);link.download="bx1-os-theme.json";link.click();URL.revokeObjectURL(link.href);} else if(action==="import"){const raw=prompt("Paste BX1 theme JSON"); if(raw){try{const imported=JSON.parse(raw);Object.assign(custom,imported.custom||{});localStorage.setItem("bx1-os-custom-themes",JSON.stringify(custom));toast("Theme imported","Reload the Themes page to review it.");}catch(_){toast("Theme import failed","Invalid JSON");}}}});

function presentationMode(){const query=new URLSearchParams(location.search).get("ui"); /* ?ui=touchscreen / ?ui=desktop */ if(query==="touchscreen"||query==="desktop") return query; return localStorage.getItem("bx1-os-ui-mode")||"desktop";}
function touchscreenPage(data){return `<div class="touchscreen-page"><div class="touch-status-header"><strong>BX1 OS · Touchscreen</strong><span>${esc(data.interface?.version||"0.9.0-speech-learning")}</span><button class="button small" data-ui-mode="desktop">Desktop mode</button></div><section class="touch-frame">${audioStatusFrame(data)}</section><section class="touch-frame">${canonicalScan(data)}</section><section class="touch-frame">${canonicalConversation(data)}</section><section class="touch-frame">${manualRecordingFrame()}</section><section class="touch-frame">${loopbackFrame()}</section><section class="touch-frame">${canonicalDiagnostics(data)}</section><section class="touch-frame">${speechLearningSummary(data)}</section><section class="touch-frame touch-system"><h2>System Summary</h2><div class="scan-details"><div><dt>Connection</dt><dd>${esc(data.brain?.status||"unavailable")}</dd></div><div><dt>Battery</dt><dd>${esc(data.system?.battery||"unavailable")}</dd></div><div><dt>CPU</dt><dd>${esc(data.system?.cpu??"unavailable")}</dd></div><div><dt>Temperature</dt><dd>${esc(data.system?.temperature??"unavailable")}</dd></div><div><dt>Network</dt><dd>${esc(data.system?.network||"unavailable")}</dd></div><div><dt>Version</dt><dd>${esc(data.interface?.version||"unavailable")}</dd></div></div></section></div>`;}
function speechLearningPage(data){const learning=data.speech_learning||{}, entries=learning.entries||[]; const rows=entries.length?entries.map((e,i)=>`<article class="learning-entry"><header><strong>${esc(e.interaction_id||`Example ${i+1}`)}</strong><span>${esc(e.speaker||"Unknown")} · ${esc(e.timestamp||"unavailable")}</span></header><p><b>Raw:</b> ${esc(e.raw_text||e.transcription||"unavailable")}</p><p><b>Corrected:</b> ${esc(e.corrected_text||"Not corrected")}</p><p><b>Request:</b> ${esc(e.request||"unavailable")} · <b>Confidence:</b> ${esc(e.confidence??"unavailable")}</p><div class="learning-actions"><button class="button small" data-learning-action="approve" data-index="${i}">Approve transcription</button><button class="button small" data-learning-action="correct" data-index="${i}">Correct transcription</button><button class="button small" data-learning-action="ignore" data-index="${i}">Ignore</button></div></article>`).join(""):"<p class=muted>No speech examples captured yet. Approved Body recognition events will appear here.</p>"; return `<div class="speech-learning-page"><section class="learning-summary"><h2>Speech Learning</h2><p>Review real Faster-Whisper events before adding them to a future dataset. Original audio and transcription remain unchanged.</p><div class="scan-details"><div><dt>Captured</dt><dd>${learning.summary?.total||0}</dd></div><div><dt>Reviewed</dt><dd>${learning.summary?.reviewed||0}</dd></div><div><dt>Approved</dt><dd>${learning.summary?.approved||0}</dd></div><div><dt>Corrected</dt><dd>${learning.summary?.corrected||0}</dd></div></div></section><section class="learning-tools"><button class="button primary" data-learning-action="add-vocabulary">Add vocabulary term</button><button class="button" data-learning-action="add-correction">Add correction rule</button><button class="button" data-learning-action="export">Export selected examples</button><span>Active vocabulary: ${(learning.vocabulary||[]).filter(v=>v.enabled!==false).length} · retention ${esc(learning.retention_days||30)} days</span></section><section class="learning-list">${rows}</section></div>`;}
Object.assign(RENDERERS,{"speech-learning":speechLearningPage});
const canonicalRenderPage=renderPage; renderPage=function(){if(presentationMode()==="touchscreen"&&["dashboard","voice"].includes(state.page)){const node=$("#pageContent"); if(node){node.innerHTML=touchscreenPage(state.data); updateGlobalAudioControls(state.data); bindGlobalAudioControls(); return;}} canonicalRenderPage();};
document.addEventListener("click",event=>{const mode=event.target.closest("[data-ui-mode]")?.dataset.uiMode; if(mode){localStorage.setItem("bx1-os-ui-mode",mode); location.href=`/?ui=${mode}`; return;} const action=event.target.closest("[data-learning-action]")?.dataset.learningAction; if(!action)return; const learning=state.data.speech_learning||{entries:[],vocabulary:[],corrections:[],speakers:[]}; if(action==="add-vocabulary"){const term=prompt("Vocabulary term"); if(term) learning.vocabulary.push({term,enabled:true,notes:""});} else if(action==="add-correction"){const recognised=prompt("Recognised phrase"); const canonical=prompt("Canonical output"); if(recognised&&canonical) learning.corrections.push({recognised,canonical,enabled:true});} else if(action==="export"){const blob=new Blob([JSON.stringify(learning,null,2)],{type:"application/json"}); const link=document.createElement("a"); link.href=URL.createObjectURL(blob); link.download="bx1-speech-learning.json"; link.click(); URL.revokeObjectURL(link.href); return;} else {const index=Number(event.target.closest("[data-index]")?.dataset.index); if(Number.isInteger(index)&&learning.entries[index]){if(action==="approve") learning.entries[index].approved=true; if(action==="ignore") learning.entries[index].ignored=true; learning.entries[index].reviewed=true;}} fetch("/api/speech-learning",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(learning)}).then(()=>{state.data.speech_learning=learning;renderPage();});});
function updateRecordingDom(message) { const stateNode=$("#manualRecordingState"); if(stateNode) stateNode.textContent=message; const meta=$("#manualRecordingMeta"); if(!meta)return; const rows=meta.querySelectorAll("dd"); if(rows[0])rows[0].textContent=state.recording.state; if(rows[1])rows[1].textContent=state.recording.id||"none"; if(rows[2])rows[2].textContent=state.recording.saved?"Saved recording — retained until expiry or manual deletion":"Temporary recording — replaced by the next recording"; }
async function recordingAction(action) { const duration=Number($("#manualRecordDuration")?.value||5); const setState=(value,message)=>{state.recording.state=value;updateRecordingDom(message||value);}; if(state.recording.pending)return; state.recording.pending=true; try { if(action==="start"){setState("starting","Starting microphone…"); const response=await fetch("/api/audio/recordings/start",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({seconds:duration})}); const payload=await response.json(); if(!response.ok||!payload.ok)throw new Error(payload.error||"Recording start failed"); state.recording={...state.recording,state:"recording",requested:duration,startedAt:Date.now(),id:payload.recording_id||payload.id||""}; updateRecordingDom(`Recording 00:00 / 00:${String(duration).padStart(2,"0")}`); setState("finalising","Finalising WAV…"); setState("complete","Recording complete"); if(payload.sample_info){state.recording.metadata=payload.sample_info;} } else if(action==="stop"){setState("stopping","Stopping microphone…"); const response=await fetch("/api/audio/recordings/stop",{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"}); const payload=await response.json(); if(!response.ok||!payload.ok)throw new Error(payload.error||"Recording stop failed"); setState("complete","Recording complete"); } else if(action==="play"){if(state.recording.state!=="complete")throw new Error("Recording is not finalised"); const player=$("#manualRecordingPlayer"); if(!player)throw new Error("Audio player unavailable"); player.hidden=false; player.src=`/api/audio/recordings/audio?rev=${Date.now()}`; setState("complete","Loading audio…"); await player.play(); setState("complete","Playing…"); player.onended=()=>updateRecordingDom("Playback complete"); player.onerror=()=>updateRecordingDom("Playback failed"); } else if(action==="download"){if(state.recording.state!=="complete")throw new Error("Recording is not finalised"); window.open(`/api/audio/recordings/download?rev=${Date.now()}`,"_blank"); updateRecordingDom("Download started");} else if(action==="keep"||action==="save"){const response=await fetch(`/api/audio/recordings/${action==="keep"?"keep":"speech-learning"}`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({})}); const payload=await response.json(); if(!response.ok||!payload.ok)throw new Error(payload.error||"Retention failed"); state.recording.saved=true; updateRecordingDom("Recording retained");} else if(action==="delete"){const response=await fetch("/api/audio/recordings/delete",{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"}); const payload=await response.json(); if(!response.ok||!payload.ok)throw new Error(payload.error||"Delete failed"); state.recording={state:"idle",id:"",requested:0,startedAt:0,metadata:null,audio:null,pending:false}; const player=$("#manualRecordingPlayer"); if(player){player.pause();player.removeAttribute("src");player.hidden=true;} updateRecordingDom("Idle");} } catch(error){setState("failed",`Recording failed: ${error.message}`);} finally {state.recording.pending=false;} }
document.addEventListener("click",event=>{const control=event.target.closest("[data-audio-control]"); if(control){const action=control.dataset.audioControl; control.classList.toggle("active"); const enabled=control.classList.contains("active"); const settings={"mic-mute":{microphone_privacy_muted:enabled},pause:{listening_paused:enabled},"speaker-mute":{speaker_muted:enabled}}[action]; if(settings) fetch("/api/audio/bridge/settings",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({settings})}).then(()=>loadAudioBridge()); if(action==="ptt"){control.classList.add("active");setTimeout(()=>control.classList.remove("active"),8000);} if(action==="stop") fetch("/api/voice/stop-speaking",{method:"POST"}).then(()=>loadAudioBridge());}
 const rec=event.target.closest("[data-record-action]"); if(rec) recordingAction(rec.dataset.recordAction);
 const loop=event.target.closest("[data-loopback-action]"); if(loop){const meta=$("#loopbackMeta"); if(meta) meta.querySelector("dd").textContent=loop.dataset.loopbackAction==="start"?"preparing":loop.dataset.loopbackAction; if(loop.dataset.loopbackAction==="stt") fetch("/api/audio/speech-test",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({loopback:true,diagnostic:true})});}});
