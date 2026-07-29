const NAVIGATION = [
  { section: "Overview", id: "dashboard", label: "Dashboard", icon: "grid" },
  { section: "Manage", id: "system", label: "System", icon: "system" },
  { section: "Manage", id: "services", label: "Services", icon: "services" },
  { section: "Manage", id: "hardware", label: "Hardware", icon: "hardware" },
  { section: "Manage", id: "camera", label: "Camera", icon: "hardware" },
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
  camera: ["Safe live preview", "Camera", "Near-live frames proxied from the Existing Robot Body without reopening the physical camera."],
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
    version: "0.6.1-development",
    tag: "BX1_OS_v0.6.1-development_voice_conversation",
    architecture_only: true,
    capabilities: {},
  },
  robot: {
    name: "LEO",
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
    current_version: "0.6.1-development",
    commit: "Provided by release manifest",
    branch: "Provided by release manifest",
    tag: "BX1_OS_v0.6.1-development_voice_conversation",
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
  talk: { phase: "Ready", sessionId: "", busy: false, error: "", timer: null },
  cameraPreview: {
    token: 0,
    timer: null,
    objectUrl: "",
    mode: "idle",
    controller: null,
  },
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
    ${panel("Talk to Leo", `<label for="talkToLeoText">Message for Leo</label><p>Sent once through Robot Body → Brain chat/TTS → Robot Body speaker. BX1 OS does not retain your text or Leo’s reply.</p><textarea class="input" id="talkToLeoText" maxlength="1000" rows="7" aria-describedby="talkToLeoHelp talkToLeoCount" placeholder="Type a message for Leo" ${state.talk.busy ? "disabled" : ""}></textarea><div id="talkToLeoHelp" class="mono">Ctrl+Enter sends. Action packets, motors, servos, cameras and MCU commands are blocked.</div><div class="page-actions"><span id="talkToLeoCount" class="mono">0 / 1000</span><button class="button primary" type="button" data-voice-action="talk-send" ${state.talk.busy ? "disabled" : ""}>Send to Leo</button><button class="button" type="button" data-voice-action="talk-clear" ${state.talk.busy ? "disabled" : ""}>Clear</button></div><p id="talkToLeoState" class="mono" role="status" aria-live="polite">${esc(state.talk.phase)}${state.talk.error ? ` — ${esc(state.talk.error)}` : ""}</p>`, { span: 7, subtitle: "Safe Body-owned conversation path" })}
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

const RENDERERS = {
  dashboard: dashboardPage,
  system: systemPage,
  services: servicesPage,
  hardware: hardwarePage,
  camera: cameraPage,
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
  bindTalkToLeo();
  if (state.page === "camera") startCameraPreview();
  $("#workspace").focus({ preventScroll: true });
}

function navigate(page, push = true) {
  if (!RENDERERS[page]) page = "dashboard";
  if (state.page === "camera" && page !== "camera") stopCameraPreview();
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

async function voiceAction(action) {
  const result = $("#talkToLeoState");
  try {
    let path = "/api/voice/brain-test";
    let body = {};
    if (action === "talk-send") {
      const input = $("#talkToLeoText");
      const text = input?.value?.trim() || "";
      if (!text) throw new Error("Enter a question first.");
      if (text.length > 1000) throw new Error("Message is too long.");
      path = "/api/voice/typed-test";
      body = { text };
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
      if (result) result.textContent = state.talk.phase;
    } else if (action === "brain-probe") {
      if (result) result.textContent = payload.state === "connected" ? "Brain connected" : `Brain ${payload.state || "not connected"}`;
    }
    await loadCoreTelemetry();
  } catch (error) {
    if (action === "talk-send") {
      if (state.talk.timer) window.clearTimeout(state.talk.timer);
      state.talk = { phase: "Failed", sessionId: "", busy: false, error: error.message, timer: null };
    }
    if (result) result.textContent = action === "talk-send" ? `Failed — ${error.message}` : error.message;
    toast("Voice diagnostic failed", error.message);
  }
}

function bindTalkToLeo() {
  const input = $("#talkToLeoText");
  const counter = $("#talkToLeoCount");
  if (!input || !counter) return;
  const update = () => { counter.textContent = `${input.value.length} / 1000`; };
  input.addEventListener("input", update);
  input.addEventListener("keydown", event => {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
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

function managementDataFromCore(statePayload, servicesPayload, healthPayload, hardwarePayload, audioPayload, robotBodyPayload, cameraPayload, voicePayload = {}) {
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
      version: deployment.version || "0.5.0",
      tag: deployment.tag || "BX1_OS_ALPHA_v0.5.0",
      architecture_only: true,
      capabilities: management.capabilities || {},
    },
    robot: {
      name: robot.name || "LEO",
      status: healthPayload.state || robot.state || "unknown",
      mode: robot.mode || "observer_only",
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
      "/api/core/camera",
      "/api/voice/status",
    ];
    const responses = await Promise.all(
      paths.map(path => fetch(path, { cache: "no-store" }))
    );
    const failed = responses.find(response => !response.ok);
    if (failed) throw new Error(`HTTP ${failed.status}`);
    const [coreState, services, health, , , hardware, audio, robotBody, camera, voice] = await Promise.all(
      responses.map(response => response.json())
    );
    state.data = managementDataFromCore(coreState, services, health, hardware, audio, robotBody, camera, voice);
    const session = state.talk.sessionId && voice.sessions?.[state.talk.sessionId];
    if (session?.state === "complete") state.talk = { phase: "Complete", sessionId: state.talk.sessionId, busy: false, error: "", timer: null };
    else if (session?.state === "failed") state.talk = { phase: "Failed", sessionId: state.talk.sessionId, busy: false, error: session.reason || "voice_fault", timer: null };
    else if (session?.state === "thinking") state.talk.phase = "Leo is thinking";
    else if (session?.state === "playing") state.talk.phase = "Playing reply";
    state.connected = true;
    if (state.page === "camera") updateCameraPageTelemetry();
    else renderPage();
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
  $("#pageContent").addEventListener("click", event => {
    const action = event.target.closest("[data-voice-action]")?.dataset.voiceAction;
    if (action) voiceAction(action);
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
}

document.addEventListener("DOMContentLoaded", init);
