from __future__ import annotations

import json
import html
import re
import threading
import time
import traceback
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse


class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


INDEX_HTML = r'''
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>BX1 Robot Control 10.39</title>
<style>
:root{
  --bg:#071019;--bg2:#0b1722;--panel:#111e2b;--panel2:#0b1620;--line:#2b4258;
  --text:#edf6ff;--muted:#9bb0c2;--blue:#54b9ff;--cyan:#43e5ff;--good:#42db8b;
  --warn:#ffc857;--bad:#ff6876;--purple:#b18cff;--lcars:#f0a050;--shadow:0 15px 40px rgba(0,0,0,.28)
}
*{box-sizing:border-box}html,body{height:100%}body{margin:0;background:radial-gradient(circle at 10% 0,#183a56 0,#08131d 37%,#04080c 100%);color:var(--text);font:15px/1.45 "Segoe UI",Arial,sans-serif}
button,input,select,textarea{font:inherit}button{cursor:pointer}.app{min-height:100%;display:grid;grid-template-columns:250px minmax(0,1fr)}
.sidebar{position:sticky;top:0;height:100vh;padding:18px 14px;background:rgba(5,12,18,.96);border-right:1px solid var(--line);overflow:auto}
.logo{margin-bottom:18px}.logo .eyebrow{color:var(--lcars);font-weight:800;letter-spacing:.18em;font-size:11px}.logo h1{font-size:22px;line-height:1.05;margin:5px 0}.logo small{color:var(--muted)}
.nav{display:grid;gap:8px}.nav button{width:100%;text-align:left;border:1px solid var(--line);border-left:12px solid #365f80;background:#0c1823;color:var(--text);border-radius:6px 18px 18px 6px;padding:11px 12px;font-weight:750}.nav button:hover{filter:brightness(1.15)}.nav button.active{border-left-color:var(--lcars);background:#18324a;color:#fff}
.sidebar-note{margin-top:18px;border:1px solid var(--line);border-radius:12px;padding:11px;color:var(--muted);font-size:12px;background:#08121b}.owner-mark{display:inline-block;margin-top:7px;color:var(--good);font-weight:750}
.workspace{min-width:0}.topbar{position:sticky;top:0;z-index:10;background:rgba(6,14,21,.94);backdrop-filter:blur(12px);border-bottom:1px solid var(--line);padding:13px 20px}
.topline{display:flex;justify-content:space-between;gap:20px;align-items:center}.topline h2{margin:0;font-size:19px}.topline .meta{color:var(--muted);font-size:12px;text-align:right}.clock{color:var(--cyan);font-size:18px;font-variant-numeric:tabular-nums;font-weight:800}
.status-rail{display:grid;grid-template-columns:repeat(6,minmax(120px,1fr));gap:8px;margin-top:11px}.status-card{border:1px solid var(--line);background:#0b1722;border-radius:10px;padding:8px 10px;min-width:0}.status-card .name{font-size:10px;color:var(--muted);letter-spacing:.12em;text-transform:uppercase}.status-card .value{font-weight:800;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:2px}.status-card.good{border-bottom:4px solid var(--good)}.status-card.warn{border-bottom:4px solid var(--warn)}.status-card.bad{border-bottom:4px solid var(--bad)}.status-card.off{border-bottom:4px solid #5b6670}
main{padding:20px;max-width:1900px;margin:0 auto}.page{display:none}.page.active{display:block}.page-title{display:flex;align-items:flex-end;justify-content:space-between;gap:15px;margin-bottom:14px}.page-title h3{font-size:25px;margin:0}.page-title p{margin:3px 0 0;color:var(--muted)}
.grid{display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:14px}.span-12{grid-column:span 12}.span-8{grid-column:span 8}.span-7{grid-column:span 7}.span-6{grid-column:span 6}.span-5{grid-column:span 5}.span-4{grid-column:span 4}
.card{background:linear-gradient(145deg,rgba(18,32,45,.96),rgba(9,20,29,.96));border:1px solid var(--line);border-radius:14px;padding:15px;box-shadow:var(--shadow);min-width:0}.card h4{margin:0 0 9px;font-size:16px}.card h5{margin:13px 0 6px;color:var(--cyan)}.muted,.help{color:var(--muted)}.help{font-size:12px}.rule{height:1px;background:var(--line);margin:13px 0}
.badge{display:inline-flex;align-items:center;gap:6px;padding:5px 9px;border:1px solid var(--line);border-radius:999px;background:#08131d;font-size:12px;font-weight:750}.badge.good{color:var(--good);border-color:#2f7755}.badge.warn{color:var(--warn);border-color:#80652e}.badge.bad{color:var(--bad);border-color:#833640}.badge.info{color:var(--blue)}
.buttons{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}button{border:1px solid #3b5972;color:var(--text);background:linear-gradient(#244562,#142b3e);border-radius:9px;padding:9px 12px;font-weight:750}button.primary{border-color:#3295c8;background:linear-gradient(#1c719c,#124761)}button.good{border-color:#34875e;background:linear-gradient(#23704c,#133c2b)}button.warn{border-color:#8f6b2b;background:linear-gradient(#75511e,#3c290f)}button.danger{border-color:#9b3d4a;background:linear-gradient(#7d2837,#43131c)}button:disabled{opacity:.55;cursor:wait}
label{display:block;color:var(--muted);font-size:12px;margin-bottom:5px}.field{margin:9px 0}.fields{display:grid;grid-template-columns:1fr 1fr;gap:10px}.fields.three{grid-template-columns:repeat(3,1fr)}input,select,textarea{width:100%;color:var(--text);background:#07121b;border:1px solid #334c62;border-radius:8px;padding:9px}input[type=checkbox]{width:auto;margin-right:6px}textarea{min-height:100px;resize:vertical}input[readonly]{opacity:.75}
.metric-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:9px}.metric{background:#08131d;border:1px solid var(--line);border-radius:10px;padding:10px}.metric .k{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em}.metric .v{font-size:18px;font-weight:850;margin-top:3px;word-break:break-word}.metric .s{font-size:11px;color:var(--muted);margin-top:3px}
.meter-row{display:grid;grid-template-columns:95px minmax(0,1fr) 90px;align-items:center;gap:10px;margin:10px 0}.meter{height:20px;border:1px solid var(--line);border-radius:999px;background:#050a0e;overflow:hidden}.meter>span{height:100%;display:block;width:0;background:linear-gradient(90deg,#37a6de,#43db8b,#ffc857,#ff6876);transition:width .15s linear}.value-right{text-align:right;font-variant-numeric:tabular-nums}
.wave{height:120px;width:100%;border:1px solid var(--line);border-radius:10px;background:#050c12}.result-box{border:1px solid var(--line);background:#07121b;border-radius:10px;padding:12px;min-height:78px;white-space:pre-wrap;word-break:break-word}.result-box.good{border-color:#2c7d55}.result-box.bad{border-color:#8a3440}.result-big{font-size:20px;font-weight:800;color:var(--cyan)}
.owner-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.owner-card{border:1px solid var(--line);border-radius:11px;padding:12px;background:#08131d}.owner-card.brain{border-left:7px solid var(--purple)}.owner-card.body{border-left:7px solid var(--good)}.owner-card ul{margin:7px 0 0;padding-left:20px;color:var(--muted)}
.fault-list{display:grid;gap:8px}.fault{display:grid;grid-template-columns:115px minmax(0,1fr) auto;gap:10px;align-items:center;border:1px solid var(--line);border-radius:10px;padding:10px;background:#08131d}.fault strong{color:var(--text)}.fault small{display:block;color:var(--muted)}
.log-tools{display:flex;gap:8px;flex-wrap:wrap;align-items:end}.log-tools .field{margin:0;min-width:150px}.log{height:560px;overflow:auto;border:1px solid var(--line);background:#050c12;border-radius:10px;padding:7px}.log-entry{border-bottom:1px solid #182a39;padding:9px}.log-entry:last-child{border-bottom:0}.log-meta{font-size:11px;color:var(--muted);display:flex;justify-content:space-between;gap:10px}.log-body{margin-top:3px;word-break:break-word}.log-entry.error .log-body,.log-entry.rejected_input .log-body{color:var(--bad)}.log-entry.input .log-body{color:var(--blue)}.log-entry.bx1 .log-body{color:var(--good)}.log-entry.system .log-body{color:#dbe8f2}.count{color:var(--warn);font-weight:800}
.chat-log{height:520px;overflow:auto;border:1px solid var(--line);background:#050c12;border-radius:12px;padding:14px;display:flex;flex-direction:column;gap:10px}.chat-msg{max-width:82%;padding:10px 12px;border-radius:14px;border:1px solid var(--line);white-space:pre-wrap;word-break:break-word}.chat-msg.user{align-self:flex-end;background:#16334b;border-color:#35698f}.chat-msg.robot{align-self:flex-start;background:#102b23;border-color:#2d7258}.chat-msg.error{align-self:center;background:#35171d;border-color:#843743}.chat-msg .who{font-size:10px;text-transform:uppercase;letter-spacing:.1em;color:var(--muted);margin-bottom:4px}.chat-compose{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px;align-items:end}.chat-compose textarea{min-height:82px}.inline-fields{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:9px}.zone-editor{display:grid;grid-template-columns:minmax(140px,1.5fr) 90px 90px 90px;gap:8px;align-items:center}.zone-editor .head{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.08em}
pre{white-space:pre-wrap;word-break:break-word;background:#050c12;border:1px solid var(--line);border-radius:10px;padding:10px;max-height:470px;overflow:auto;color:#cfe8fa}.table-wrap{overflow:auto}table{border-collapse:collapse;width:100%;min-width:650px}th,td{text-align:left;border-bottom:1px solid var(--line);padding:9px}th{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.08em}
details{border:1px solid var(--line);border-radius:10px;background:#08131d;padding:9px;margin-top:10px}summary{cursor:pointer;font-weight:750;color:var(--blue)}.toast{position:fixed;right:18px;bottom:18px;z-index:99;padding:11px 14px;border:1px solid var(--line);border-radius:10px;background:#101f2d;box-shadow:var(--shadow);max-width:520px}.toast.good{border-color:#2c7d55}.toast.bad{border-color:#8a3440}
.lcars-bar{height:10px;border-radius:10px;background:linear-gradient(90deg,var(--lcars) 0 24%,var(--purple) 24% 41%,var(--blue) 41% 73%,var(--good) 73%)}
@media(max-width:1200px){.app{grid-template-columns:205px minmax(0,1fr)}.status-rail{grid-template-columns:repeat(3,1fr)}.span-8,.span-7,.span-6,.span-5,.span-4{grid-column:span 12}.metric-grid{grid-template-columns:repeat(2,1fr)}}
@media(max-width:760px){.app{display:block}.sidebar{height:auto;position:static}.nav{grid-template-columns:1fr 1fr}.sidebar-note{display:none}.topbar{position:static}.topline{align-items:flex-start}.status-rail{grid-template-columns:1fr 1fr}.fields,.fields.three,.owner-grid{grid-template-columns:1fr}.metric-grid{grid-template-columns:1fr}.meter-row{grid-template-columns:75px minmax(0,1fr) 75px}.fault{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="app">
<aside class="sidebar">
  <div class="logo"><div class="eyebrow">BX1 / LEO</div><h1>ROBOT<br>CONTROL</h1><small>Robot client v10.39</small></div>
  <div class="lcars-bar"></div>
  <nav class="nav" aria-label="Diagnostic sections">
    <button data-page="overview" class="active">Overview</button>
    <button data-page="conversation">Conversation</button>
    <button data-page="speech">Speech Input</button>
    <button data-page="vision">Vision / Awareness</button>
    <button data-page="idle">Idle Life</button>
    <button data-page="mouth">Mouth / Lighting</button>
    <button data-page="hardware">Hardware</button>
    <button data-page="doctor">Hardware Doctor</button>
    <button data-page="logs">Logs</button>
    <button data-page="advanced">Advanced</button>
  </nav>
  <div class="sidebar-note">Talk to BX1 by keyboard or robot microphone here.<br><span class="owner-mark">The desktop Brain App still owns personality, LLM and memory.</span></div>
</aside>
<div class="workspace">
<header class="topbar">
  <div class="topline"><div><h2 id="headerTitle">Overview</h2><div class="muted" id="headerSubtitle">Body health and active faults</div></div><div class="meta"><div class="clock" id="clock">--:--:--</div><div id="lastRefresh">Waiting for status…</div></div></div>
  <div class="status-rail" id="statusRail"></div>
</header>
<main>
<section class="page active" id="page-overview">
  <div class="page-title"><div><h3>System Overview</h3><p>Clear health summary, ownership boundaries and the shortest path to each fault.</p></div><button class="primary" onclick="refreshAll(true)">Refresh now</button></div>
  <div class="grid">
    <article class="card span-8"><h4>Active Conditions</h4><div id="overviewFaults" class="fault-list"></div></article>
    <article class="card span-4"><h4>Quick Actions</h4><div class="buttons"><button class="good" onclick="runDoctor(this)">Run diagnosis</button><button onclick="go('speech')">Test speech input</button><button onclick="testSpeechMouth(this)">Test voice + mouth</button><button onclick="apiAction('/api/repeat_last_response',{},this)">Repeat last reply</button></div><div class="rule"></div><div id="overviewRuntime" class="metric-grid"></div></article>
    <article class="card span-12"><h4>Control Ownership — prevents duplicate settings</h4><div class="owner-grid"><div class="owner-card brain"><strong>Desktop Brain App owns</strong><ul id="brainOwns"></ul></div><div class="owner-card body"><strong>Robot Body Client owns</strong><ul id="bodyOwns"></ul></div></div><details><summary>Shared interface contract</summary><ul id="sharedContract"></ul></details></article>
  </div>
</section>

<section class="page" id="page-conversation">
  <div class="page-title"><div><h3>Conversation</h3><p>Use the keyboard or the microphone fitted to BX1. Both routes use the same Brain App personality and memory.</p></div><span class="badge good">LIVE CONTROL</span></div>
  <div class="grid">
    <article class="card span-8"><h4>BX1 Conversation</h4><div id="chatTranscript" class="chat-log"><div class="muted">No conversation yet.</div></div><div class="rule"></div><div class="chat-compose"><div><textarea id="chatText" placeholder="Type to BX1. Press Enter to send; Shift+Enter adds a new line."></textarea><div class="help">The microphone button uses BX1's physical microphone, not the browser microphone.</div></div><div class="buttons" style="display:grid"><button class="primary" onclick="sendChat(this)">Send</button><button class="good" onclick="listenChat(this)">Listen and send</button><button onclick="apiAction('/api/repeat_last_response',{},this)">Repeat reply</button></div></div></article>
    <article class="card span-4"><h4>Conversation State</h4><div id="conversationMetrics" class="metric-grid"></div><div class="rule"></div><div id="conversationStatus" class="result-box">Waiting for status…</div><div class="rule"></div><h5>What BX1 heard</h5><div id="conversationHeard" class="result-box">No speech recognised yet.</div><div class="buttons"><button onclick="go('speech')">Wake and microphone settings</button><button onclick="go('hardware')">Servo and LED settings</button></div></article>
  </div>
</section>

<section class="page" id="page-speech">
  <div class="page-title"><div><h3>Speech Input</h3><p>Microphone capture, endpointing and recognition. This is the exact path used by live voice.</p></div><span class="badge info">BODY OWNED</span></div>
  <div class="grid">
    <article class="card span-7"><h4>Live Input Level</h4><div class="meter-row"><span>Filtered RMS</span><div class="meter"><span id="rmsBar"></span></div><span class="value-right" id="rmsText">-- dBFS</span></div><div class="meter-row"><span>Peak</span><div class="meter"><span id="peakBar"></span></div><span class="value-right" id="peakText">-- dBFS</span></div><canvas class="wave" id="levelCanvas" width="900" height="120"></canvas><div id="micBadges" class="buttons"></div><div class="buttons"><button onclick="startMonitor(this)">Start level meter</button><button onclick="stopMonitor(this)">Stop level meter</button><button onclick="loadDevices(this)">Refresh devices</button></div></article>
    <article class="card span-5"><h4>Production STT Test</h4><div class="help">Waits for speech, keeps the first syllable, and closes after natural end silence. Each test has its own capture ID, so playback cannot silently reuse an older WAV.</div><div class="buttons"><button class="good" onclick="listenOnce(false,this)">Listen once</button><button class="primary" onclick="listenOnce(true,this)">Listen and send to Brain</button></div><div id="sttResult" class="result-box">No diagnostic utterance captured yet.</div><div class="buttons"><button id="playSttRaw" disabled onclick="playDiagnosticAudio('raw',this)">Play raw</button><button id="playSttFiltered" disabled onclick="playDiagnosticAudio('filtered',this)">Play filtered</button><button id="playSttSubmitted" disabled onclick="playDiagnosticAudio('submitted',this)">Play submitted</button></div><div class="help" id="sttCaptureState">No current capture.</div></article>
    <article class="card span-7"><h4>Microphone and Endpoint Settings</h4><div class="fields"><div class="field"><label>Capture device</label><select id="micDevice"></select></div><div class="field"><label>Sample rate</label><select id="sampleRate"><option>16000</option><option>24000</option><option>48000</option></select></div></div><div class="fields three"><div class="field"><label>Software gain (dB)</label><input id="micGain" type="number" step="0.5"></div><div class="field"><label>Noise gate (dBFS)</label><input id="noiseGate" type="number" step="1"></div><div class="field"><label>Adaptive margin (dB)</label><input id="adaptiveMargin" type="number" step="0.5"></div></div><div class="fields three"><div class="field"><label>Pre-roll (ms)</label><input id="preRoll" type="number"></div><div class="field"><label>End silence (ms)</label><input id="endSilence" type="number"></div><div class="field"><label>Post-roll (ms)</label><input id="postRoll" type="number"></div></div><div class="fields three"><div class="field"><label>Start timeout (s)</label><input id="startTimeout" type="number" step="0.5"></div><div class="field"><label>Max utterance (s)</label><input id="maxUtterance" type="number" step="0.5"></div><div class="field"><label>Start trigger (ms)</label><input id="startTrigger" type="number"></div></div><div class="field"><label><input id="endpointingEnabled" type="checkbox"> Natural endpointing enabled</label><label><input id="adaptiveEnabled" type="checkbox"> Adaptive threshold enabled</label></div><button class="good" onclick="saveMic(this)">Save speech input settings</button>
      <details><summary>Audio filters and acceptance gates</summary><div class="fields three"><div class="field"><label>High-pass (Hz)</label><input id="highpassHz" type="number"></div><div class="field"><label>Notch (Hz)</label><input id="notchHz" type="number"></div><div class="field"><label>Noise reduction 0–1</label><input id="noiseReduction" type="number" step="0.05"></div></div><div class="field"><label><input id="filterEnabled" type="checkbox"> Enable audio filter chain</label><label><input id="highpassEnabled" type="checkbox"> High-pass enabled</label><label><input id="notchEnabled" type="checkbox"> Mains notch enabled</label><label><input id="nrEnabled" type="checkbox"> Noise reduction enabled</label></div><div class="fields"><div class="field"><label>Minimum Vosk confidence</label><input id="minConfidence" type="number" step="0.05"></div><div class="field"><label>Minimum voiced audio (ms)</label><input id="minVoiced" type="number"></div></div></details>
    </article>
    <article class="card span-5"><h4>Wake / Session Status</h4><div id="voiceMetrics" class="metric-grid"></div><div class="field"><label>Wake words — one per line</label><textarea id="wakeWords" placeholder="hello&#10;hey&#10;robot"></textarea></div><div class="buttons"><button onclick="setNaturalWakeWords()">Use Hello / Hey / Robot</button></div><div class="field"><label><input id="voiceEnabled" type="checkbox"> Start listening automatically and keep the live wake-word listener enabled</label></div><button class="good" onclick="saveVoice(this)">Save and activate listening</button><div class="help" id="voiceSaveState">Changes are saved to the robot and survive restart.</div><div class="rule"></div><h5>Speech recognition</h5><div class="field"><label>Local Vosk fallback model</label><input id="voskModelPath" readonly></div><div id="speechModelHint" class="result-box"></div><div class="rule"></div><h5>Speaker output</h5><div class="field"><label>Playback device</label><select id="playbackDevice"></select></div><div class="field"><label>Robot playback volume</label><input id="ttsVolume" type="number" min="0" max="100"></div><button onclick="saveOutput(this)">Save speaker output</button><div class="help" id="voiceOwnerText"></div></article>
  </div>
</section>

<section class="page" id="page-vision">
  <div class="page-title"><div><h3>Vision and Awareness</h3><p>Live camera preview, natural visual questions, passive Brain frames and local face/motion awareness.</p></div><span class="badge info">BODY + BRAIN</span></div>
  <div class="grid">
    <article class="card span-7"><h4>Camera View</h4><img id="visionPreview" alt="BX1 camera snapshot" style="width:100%;max-height:520px;object-fit:contain;background:#03080c;border:1px solid var(--line);border-radius:10px" src="/api/camera_snapshot.jpg"><div class="buttons"><button onclick="refreshVisionPreview(this,false,true)">Refresh snapshot</button><button class="good" onclick="cameraProbe(this)">Probe camera</button><button onclick="sendCameraFrame(this)">Send frame to Brain</button></div><div class="field"><label><input id="visionLivePreview" type="checkbox" onchange="syncVisionPreviewTimer()"> Live preview while this page is open</label></div><div id="visionPreviewState" class="help">Waiting for first frame…</div><div class="help">The preview uses the body client's cached camera frame, avoiding repeated camera-open conflicts. Explicit visual questions invoke the desktop Brain vision model.</div></article>
    <article class="card span-5"><h4>Awareness Runtime</h4><div id="visionMetrics" class="metric-grid"></div><div class="rule"></div><div id="visionEvidence" class="result-box">Waiting for camera status…</div><div class="help" style="margin-top:9px">When OpenCV is unavailable, presence is shown as unknown rather than incorrectly reporting that the robot is alone. Named-person recognition still requires enrolment in the desktop Brain App.</div></article>
    <article class="card span-7"><h4>Natural Camera Commands</h4><div class="help">These phrases route the instruction and current frame to the Brain vision model. One phrase per line.</div><textarea id="visionTriggers" style="min-height:220px" placeholder="look at this&#10;what is this&#10;describe this"></textarea><div class="field"><label>Test visual instruction</label><textarea id="visionPrompt">Describe what you can see. Mention any person, object, movement or clear gesture.</textarea></div><button class="primary" onclick="askCamera(this)">Ask Brain using current camera frame</button><div class="help">A Brain-side HTTP 400 from Ollama normally means the desktop vision route is using a text-only model. Select a vision-capable model in the Brain App.</div></article>
    <article class="card span-5"><h4>Camera and Presence Settings</h4><div class="fields"><div class="field"><label>Camera device</label><input id="cameraDevice"></div><div class="field"><label>Camera index</label><input id="cameraIndex" type="number" min="0" max="20"></div></div><div class="fields"><div class="field"><label>JPEG quality</label><input id="cameraQuality" type="number" min="20" max="100"></div><div class="field"><label>Passive Brain frame interval (s)</label><input id="cameraFrameInterval" type="number" min="2" max="120" step="0.5"></div></div><div class="fields"><div class="field"><label>Live preview interval (s)</label><input id="visionPreviewInterval" type="number" min="1" max="30" step="0.5" onchange="syncVisionPreviewTimer()"></div><div class="field"><label>Awareness interval (s)</label><input id="awarenessInterval" type="number" min="0.75" max="30" step="0.25"></div></div><div class="fields"><div class="field"><label>Motion threshold</label><input id="motionThreshold" type="number" min="0.005" max="0.3" step="0.005"></div><div class="field"><label>Alone after (s)</label><input id="aloneTimeout" type="number" min="5" max="600"></div></div><div class="field"><label>Visual wake window (s)</label><input id="visualWakeWindow" type="number" min="5" max="120"></div><div class="field"><label><input id="cameraEnabled" type="checkbox"> Camera enabled</label><label><input id="autoVision" type="checkbox"> Automatically use camera for natural visual questions</label><label><input id="passiveFrames" type="checkbox"> Send passive frames to desktop Brain App</label><label><input id="awarenessEnabled" type="checkbox"> Enable local face/motion awareness</label><label><input id="visualWake" type="checkbox"> A person entering view opens a listening window</label><label><input id="eventFrames" type="checkbox"> Send a frame when a person enters or leaves</label></div><button class="good" onclick="saveVision(this)">Save vision settings</button><div class="help">The installer attempts to install OpenCV. Restart after changing background-loop enable/disable options.</div></article>
  </div>
</section>

<section class="page" id="page-idle">
  <div class="page-title"><div><h3>Idle Life</h3><p>Give BX1 natural phases when nobody is interacting: watch, glance, become curious, comment, then sleep.</p></div><span class="badge info">BODY TIMER + BRAIN PERSONALITY</span></div>
  <div class="grid">
    <article class="card span-5"><h4>Idle Runtime</h4><div id="idleMetrics" class="metric-grid"></div><div class="rule"></div><div id="idleEvidence" class="result-box">Waiting for idle-life status…</div><div class="buttons"><button onclick="testIdleAction(this)">Test head / eyes</button><button class="primary" onclick="testIdleResponse(this)">Test idle response</button><button onclick="resetIdleTimer(this)">Reset timer</button></div></article>
    <article class="card span-7"><h4>Idle Behaviour</h4><div class="fields three"><div class="field"><label>First micro movement after (s)</label><input id="idleMicroDelay" type="number" min="10"></div><div class="field"><label>Movement interval (s)</label><input id="idleMicroInterval" type="number" min="20"></div><div class="field"><label>First spoken response after (s)</label><input id="idleCommentDelay" type="number" min="30"></div></div><div class="fields three"><div class="field"><label>Minimum response interval (s)</label><input id="idleCommentInterval" type="number" min="60"></div><div class="field"><label>Sleep after (s)</label><input id="idleSleepAfter" type="number" min="60"></div><div class="field"><label>Maximum responses per hour</label><input id="idleMaxComments" type="number" min="0" max="12"></div></div><div class="fields"><div class="field"><label>Response source</label><select id="idleResponseMode"><option value="brain">Brain-generated personality response</option><option value="local">Local stored phrases</option><option value="off">No spoken idle responses</option></select></div><div class="field"><label>Eye colour</label><input id="idleEyeColour" placeholder="blue"></div></div><div class="fields three"><div class="field"><label>Head yaw range (degrees)</label><input id="idleYaw" type="number" min="0" max="30" step="0.5"></div><div class="field"><label>Head pitch range (degrees)</label><input id="idlePitch" type="number" min="0" max="20" step="0.5"></div><div class="field"><label>Eye brightness 0–1</label><input id="idleBrightness" type="number" min="0" max="1" step="0.01"></div></div><div class="field"><label><input id="idleEnabled" type="checkbox"> Enable idle-life routine</label><label><input id="idleMicroEnabled" type="checkbox"> Enable small head and eye movements</label><label><input id="idleRequireAlone" type="checkbox"> Only speak when camera awareness does not see a person</label><label><input id="idleCuriosity" type="checkbox"> Allow occasional Brain curiosity with web access</label></div><div class="field"><label>Optional Brain idle prompt override</label><textarea id="idleBrainPrompt" placeholder="Leave blank for the built-in natural BX1 idle prompt."></textarea></div><button class="good" onclick="saveIdle(this)">Save idle-life settings</button><div class="help">The body decides when an idle phase occurs. The desktop Brain still decides the personality and wording.</div></article>
  </div>
</section>

<section class="page" id="page-mouth">
  <div class="page-title"><div><h3>Mouth and Lighting</h3><p>Mouth intensity follows the generated TTS WAV envelope; LED safety limits remain in the body client.</p></div><span class="badge info">BODY OWNED</span></div>
  <div class="grid">
    <article class="card span-6"><h4>Mouth Audio Runtime</h4><div id="mouthMetrics" class="metric-grid"></div><div class="buttons"><button class="good" onclick="testSpeechMouth(this)">Test speech + mouth animation</button><button onclick="testMouth('#00ffff',0.45,this)">Mouth cyan</button><button onclick="testMouth('#ff9900',0.45,this)">Mouth amber</button><button class="danger" onclick="testMouth('#000000',0,this)">Mouth off</button></div><div class="field"><label>Test phrase</label><textarea id="mouthTestText">Leo mouth-light diagnostic. Brightness should follow every word in this sentence.</textarea></div></article>
    <article class="card span-6"><h4>LED State Tests</h4><div id="stateButtons" class="buttons"></div><div class="help">State colours are body indicators. Emotion and wording remain controlled by the Brain App; the body enforces actual zones and brightness.</div><details><summary>Current LED state configuration</summary><pre id="ledStateJson"></pre></details></article>
    <article class="card span-12"><h4>Transport Evidence</h4><div id="mouthEvidence" class="result-box">No mouth command evidence yet.</div></article>
  </div>
</section>

<section class="page" id="page-hardware">
  <div class="page-title"><div><h3>Hardware</h3><p>MCU bridge, IMU, servo and LED registry. Physical limits remain authoritative here.</p></div><span class="badge info">BODY OWNED</span></div>
  <div class="grid">
    <article class="card span-5"><h4>Live Hardware State</h4><div id="hardwareMetrics" class="metric-grid"></div><div id="hardwareBridgeDetail" class="result-box">Waiting for MCU bridge evidence…</div><div class="buttons"><button onclick="hardwareTest('centre',0,null,this)">Centre head</button><button onclick="hardwareTest('yaw',-10,null,this)">Yaw left</button><button onclick="hardwareTest('yaw',10,null,this)">Yaw right</button><button onclick="hardwareTest('pitch',7,null,this)">Pitch up</button><button onclick="hardwareTest('pitch',-7,null,this)">Pitch down</button></div></article>
    <article class="card span-7"><h4>Registry Summary</h4><div id="registrySummary" class="table-wrap"></div><div class="buttons"><button class="warn" onclick="applyHardware(this)">Apply registry to MCU</button></div></article>
    <article class="card span-12"><h4>Servo GPIO and LED Setup</h4><div class="help">BX1 head mapping from behind: D9 yaw, D10 left gimbal, D11 right gimbal. The LED chain uses one data GPIO and logical address ranges.</div><h5>Head servos</h5><div class="inline-fields"><div class="field"><label><input id="servoYawEnabled" type="checkbox"> Yaw enabled</label><input id="servoYawPin" type="number" min="-1" max="99" placeholder="GPIO"><input id="servoYawHome" type="number" step="0.5" placeholder="Home degrees"><label><input id="servoYawInvert" type="checkbox"> Reverse yaw</label></div><div class="field"><label><input id="servoLeftEnabled" type="checkbox"> Left gimbal enabled</label><input id="servoLeftPin" type="number" min="-1" max="99" placeholder="GPIO"><input id="servoLeftHome" type="number" step="0.5" placeholder="Home degrees"></div><div class="field"><label><input id="servoRightEnabled" type="checkbox"> Right gimbal enabled</label><input id="servoRightPin" type="number" min="-1" max="99" placeholder="GPIO"><input id="servoRightHome" type="number" step="0.5" placeholder="Home degrees"></div><div class="field"><label>Known BX1 mapping</label><div class="result-box">Yaw: D9<br>Left: D10<br>Right: D11</div></div></div><h5>Servo noise control</h5><div class="inline-fields"><div class="field"><label><input id="servoQuietRelease" type="checkbox"> Quiet release after movement</label><div class="help">Detaches PWM after the head settles to stop holding buzz. The servos reattach automatically on the next movement.</div></div><div class="field"><label>Release delay (ms)</label><input id="servoReleaseAfter" type="number" min="250" max="10000" step="50"></div><div class="field"><label>Pulse deadband (µs)</label><input id="servoDeadband" type="number" min="0" max="30" step="1"><div class="help">Ignores very small pulse changes that can cause hunting.</div></div><div class="field"><label>Important</label><div class="result-box">Disable quiet release only if the head drops or cannot hold its position without continuous servo torque.</div></div></div><h5>Addressable LED chain</h5><div class="inline-fields"><div class="field"><label><input id="ledBusEnabled" type="checkbox"> LED chain enabled</label></div><div class="field"><label>Data GPIO</label><input id="ledBusPin" type="number" min="-1" max="99"></div><div class="field"><label>Total LEDs on chain</label><input id="ledBusCount" type="number" min="1" max="500"></div><div class="field"><label>Brightness safety limit 0–1</label><input id="ledBrightnessLimit" type="number" min="0" max="1" step="0.05"></div></div><div id="ledZoneEditor" class="zone-editor"></div><div class="buttons"><button onclick="loadKnownBx1Mapping()">Load D9 / D10 / D11</button><button class="good" onclick="saveSimpleHardware(this,true)">Save and apply to MCU</button><button onclick="saveSimpleHardware(this,false)">Save only</button></div></article>
    <article class="card span-12"><h4>Advanced Hardware Registry</h4><div class="help">Edit only when changing physical pin assignments, LED addresses, servo trims or safety limits.</div><textarea id="hardwareRegistry" style="min-height:370px;font-family:Consolas,monospace"></textarea><div class="buttons"><button onclick="formatRegistry()">Format JSON</button><button class="good" onclick="saveHardware(this)">Save registry</button></div></article>
  </div>
</section>

<section class="page" id="page-doctor">
  <div class="page-title"><div><h3>Hardware Doctor</h3><p>One fault per row, clear evidence, and bounded recovery. Firmware is never flashed automatically.</p></div><button class="good" onclick="runDoctor(this)">Run fresh diagnosis</button></div>
  <div class="grid"><article class="card span-8"><h4>Diagnosis</h4><div id="doctorSummary" class="result-box"></div><div id="doctorEvidence" class="fault-list" style="margin-top:10px"></div><div class="buttons"><button class="warn" onclick="recoverBridge(this)">Restart Arduino Router</button></div></article><article class="card span-4"><h4>Recommendations</h4><div id="doctorRecommendations"></div><div class="rule"></div><span class="badge good">NO AUTOMATIC FLASHING</span></article><article class="card span-12"><details open><summary>Raw diagnosis</summary><pre id="doctorRaw"></pre></details></article></div>
</section>

<section class="page" id="page-logs">
  <div class="page-title"><div><h3>Logs</h3><p>Duplicate events are collapsed so a repeated fault does not bury the useful evidence.</p></div><button onclick="refreshAll(true)">Refresh</button></div>
  <article class="card"><div class="log-tools"><div class="field"><label>Severity / type</label><select id="logType" onchange="renderLogs()"><option value="">All</option><option value="error">Errors</option><option value="rejected_input">Rejected speech</option><option value="input">Voice/input</option><option value="system">System</option><option value="led_state">LED</option></select></div><div class="field" style="flex:1"><label>Search</label><input id="logSearch" oninput="renderLogs()" placeholder="Search messages and subsystem data"></div><label><input id="collapseLogs" type="checkbox" checked onchange="renderLogs()"> Collapse duplicates</label></div><div id="eventLog" class="log"></div></article>
</section>

<section class="page" id="page-advanced">
  <div class="page-title"><div><h3>Advanced / Integration</h3><p>Connections and body diagnostics. Brain-owned model, personality, memory and TTS voice controls are deliberately absent.</p></div></div>
  <div class="grid">
    <article class="card span-6"><h4>Brain Connection</h4><div class="field"><label>Brain API base URL</label><input id="brainUrl"></div><div class="buttons"><button onclick="saveBrain(false,this)">Save URL</button><button onclick="saveBrain(true,this)">Use this browser PC</button><button class="good" onclick="testBrain(this)">Test Brain</button></div><pre id="brainResult"></pre></article>
    <article class="card span-6"><h4>Manual Diagnostic Message</h4><div class="help">Sends text using the Brain App's existing web, memory, model and personality policy. No duplicate per-message switches.</div><textarea id="manualText" placeholder="Diagnostic message to Brain App"></textarea><button class="primary" onclick="sendManual(this)">Send using Brain defaults</button><pre id="manualResult"></pre></article>
    <article class="card span-12"><h4>Full Body Snapshot</h4><details><summary>Show raw status JSON</summary><pre id="rawSnapshot"></pre></details></article>
  </div>
</section>
</main>
</div>
</div>
<div id="toast" class="toast" hidden></div>
<script>
let SNAP={};let EVENTS=[];let levels=[];let refreshing=false;let page='overview';let visionPreviewTimer=null;let STT_AUDIO_URLS={};let STT_CAPTURE_ID='';let sttAudioPlayer=null;
const PAGE_INFO={overview:['Overview','Body health and active faults'],conversation:['Conversation','Keyboard and robot microphone control'],speech:['Speech Input','Microphone, endpointing and STT'],vision:['Vision / Awareness','Camera, face presence, movement and visual requests'],idle:['Idle Life','Autonomous phases, movement and personality responses'],mouth:['Mouth / Lighting','TTS waveform and LED evidence'],hardware:['Hardware','MCU, IMU, servos and LED registry'],doctor:['Hardware Doctor','Diagnosis and bounded recovery'],logs:['Logs','Filtered and collapsed event history'],advanced:['Advanced','Brain connection and raw integration evidence']};
const $=id=>document.getElementById(id);const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function isDirty(el){return !!el&&(el.dataset.dirty==='1'||document.activeElement===el)}function clearDirty(root=document){root.querySelectorAll('[data-dirty="1"]').forEach(el=>delete el.dataset.dirty)}document.addEventListener('input',e=>{if(e.target.matches('input,textarea,select'))e.target.dataset.dirty='1'});document.addEventListener('change',e=>{if(e.target.matches('input,textarea,select'))e.target.dataset.dirty='1'});
function toast(msg,kind=''){const el=$('toast');el.textContent=msg;el.className='toast '+kind;el.hidden=false;clearTimeout(window.__toast);window.__toast=setTimeout(()=>el.hidden=true,4200)}
async function req(path,body){const opt=body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)};const r=await fetch(path,opt);let d={};try{d=await r.json()}catch(e){d={ok:false,error:'Invalid server response'}}if(!r.ok)throw new Error(d.error||d.message||('HTTP '+r.status));return d}
function busy(btn,on,label){if(!btn)return;if(on){btn.dataset.old=btn.textContent;btn.textContent=label||'Working…';btn.disabled=true}else{btn.textContent=btn.dataset.old||btn.textContent;btn.disabled=false}}
function cls(ok,warning=false){return ok?'good':warning?'warn':'bad'}function yes(v){return v===true?'yes':v===false?'no':String(v??'--')}
function go(name){page=name;document.querySelectorAll('.page').forEach(x=>x.classList.toggle('active',x.id==='page-'+name));document.querySelectorAll('.nav button').forEach(x=>x.classList.toggle('active',x.dataset.page===name));$('headerTitle').textContent=PAGE_INFO[name][0];$('headerSubtitle').textContent=PAGE_INFO[name][1];history.replaceState(null,'','/'+(name==='overview'?'':name));if(name==='logs')renderLogs();if(name==='conversation')renderConversation(SNAP);if(name==='idle')renderIdle(SNAP);syncVisionPreviewTimer()}
document.querySelectorAll('.nav button').forEach(b=>b.onclick=()=>go(b.dataset.page));
function statusCard(name,value,state){return `<div class="status-card ${state}"><div class="name">${esc(name)}</div><div class="value">${esc(value)}</div></div>`}
function metric(k,v,s=''){return `<div class="metric"><div class="k">${esc(k)}</div><div class="v">${esc(v)}</div>${s?`<div class="s">${esc(s)}</div>`:''}</div>`}
function eventText(e){return String(e.message??e.text??e.body??e.event??'')}
function deriveHealth(d){const s=d.state||{},vr=d.voice_runtime||{},ml=((d.mic_level||{}).level)||{},mouth=d.mouth_audio||{},p=d.performance||{};const brainEvidence=(Number(p.chat_count||0)>0)||(p.last_brain_latency_ms!==null&&p.last_brain_latency_ms!==undefined);const brainFault=!!s.brain_error&&!brainEvidence;const brainDegraded=!!s.brain_error&&brainEvidence;const sttReady=(d.voice||{}).stt_ready;const liveMic=!!vr.loop_active&&!['disabled','error'].includes(String(vr.state||''));const micGood=ml.running||liveMic;const micState=ml.error?'bad':micGood?'good':'warn';const mcu=!!s.mcu_ok;const imu=!!(s.imu_ok??((s.sensors||{}).imu_ok));const mouthSuspended=!mcu||!!mouth.suspended;const mouthState=mouthSuspended?'bad':mouth.last_ok===false?'bad':mouth.commands>0?'good':'warn';const micLabel=liveMic?(['processing','speechgen'].includes(String(vr.state||''))?'PAUSED':vr.state==='speaking'?'MUTED':vr.state==='recording'?'VOICE':'LISTENING'):(ml.running?(ml.active?'VOICE':'MONITORING'):'STOPPED');const brainLabel=brainFault?'FAULT':brainDegraded?'DEGRADED':'CONNECTED';const brainState=brainFault?'bad':brainDegraded?'warn':'good';const mouthLabel=mouthSuspended?'SUSPENDED':mouth.active?'ANIMATING':mouth.commands>0?'READY':'NO EVIDENCE';return [statusCard('Brain',brainLabel,brainState),statusCard('STT',sttReady?'READY':((d.voice||{}).stt_error?'FAULT':'IDLE'),sttReady?'good':(d.voice||{}).stt_error?'bad':'warn'),statusCard('Microphone',micLabel,micState),statusCard('MCU Bridge',mcu?'ONLINE':'OFFLINE',mcu?'good':'bad'),statusCard('IMU',imu?'ONLINE':(mcu?'DEGRADED':'UNKNOWN'),imu?'good':mcu?'warn':'off'),statusCard('Mouth LED',mouthLabel,mouthState)].join('')}
function buildFaults(d){const s=d.state||{},v=d.voice||{},ml=((d.mic_level||{}).level)||{},doc=d.hardware_doctor||{},m=d.mouth_audio||{},p=d.performance||{};let f=[];const brainEvidence=(Number(p.chat_count||0)>0)||(p.last_brain_latency_ms!==null&&p.last_brain_latency_ms!==undefined);if(s.brain_error)f.push(['Brain',brainEvidence?'warning':'fault',s.brain_error,brainEvidence?'Chat works, but a telemetry or health request failed':'Open Advanced and test Brain connection']);if(v.stt_error)f.push(['Speech','fault',v.stt_error,'Open Speech Input']);if(ml.error)f.push(['Microphone','fault',ml.error,'Check selected ALSA device']);if(!s.mcu_ok)f.push(['MCU','fault',s.bridge_error||s.mcu_error||doc.summary||'MCU bridge not healthy','Run Hardware Doctor']);if(s.mcu_ok&&!(s.imu_ok??((s.sensors||{}).imu_ok)))f.push(['IMU','warning',s.imu_error||(s.sensors||{}).imu_error||'IMU is not reporting valid data','Check Qwiic Wire1 connection/address 0x6A']);if(s.mcu_ok&&m.last_ok===false)f.push(['Mouth LED','fault',m.last_error||'Last mouth command failed','Open Mouth / Lighting']);const rejected=(d.events||[]).slice().reverse().find(e=>e.kind==='rejected_input');if(rejected)f.push(['STT recent','warning',eventText(rejected),'Review endpoint result and debug WAVs']);if(!f.length)f.push(['System','ok','No active body faults detected.','']);return f}
function renderOverview(d){$('statusRail').innerHTML=deriveHealth(d);const faults=buildFaults(d);$('overviewFaults').innerHTML=faults.map(x=>`<div class="fault"><span class="badge ${x[1]==='ok'?'good':x[1]==='warning'?'warn':'bad'}">${esc(x[0])}</span><div><strong>${esc(x[2])}</strong><small>${esc(x[3])}</small></div><button onclick="${x[0].startsWith('STT')||x[0]==='Speech'||x[0]==='Microphone'?"go('speech')":x[0]==='Mouth LED'?"go('mouth')":x[0]==='MCU'||x[0]==='IMU'?"go('doctor')":"refreshAll(true)"}">Open</button></div>`).join('');const p=d.performance||{},vr=d.voice_runtime||{};$('overviewRuntime').innerHTML=metric('Voice state',vr.state||'--')+metric('Last chat',p.last_chat_ms!=null?p.last_chat_ms+' ms':'--')+metric('Brain latency',p.last_brain_latency_ms!=null?p.last_brain_latency_ms+' ms':'--')+metric('TTS queue',p.tts_queue_pending??'--');const o=d.ownership||{};$('brainOwns').innerHTML=(o.brain_app||[]).map(x=>`<li>${esc(x)}</li>`).join('');$('bodyOwns').innerHTML=(o.body_client||[]).map(x=>`<li>${esc(x)}</li>`).join('');$('sharedContract').innerHTML=(o.shared_contract||[]).map(x=>`<li>${esc(x)}</li>`).join('')}
function dbPct(db){return Math.max(0,Math.min(100,(Number(db)+70)/70*100))}function renderLevel(l){l=l||{};$('rmsBar').style.width=dbPct(l.rms_dbfs)+'%';$('peakBar').style.width=dbPct(l.peak_dbfs)+'%';$('rmsText').textContent=(Number(l.rms_dbfs??-120).toFixed(1))+' dBFS';$('peakText').textContent=(Number(l.peak_dbfs??-120).toFixed(1))+' dBFS';$('micBadges').innerHTML=`<span class="badge ${l.running?'good':'warn'}">monitor ${l.running?'running':'stopped'}</span><span class="badge ${l.active?'good':'info'}">${l.active?'voice active':'quiet'}</span><span class="badge ${l.clipped?'bad':'good'}">clip ${l.clipped?'yes':'no'}</span><span class="badge info">${esc(l.device||'--')}</span>`;levels.push(Number(l.rms_dbfs??-120));if(levels.length>120)levels.shift();drawLevels()}
function drawLevels(){const c=$('levelCanvas'),x=c.getContext('2d'),w=c.width,h=c.height;x.clearRect(0,0,w,h);x.strokeStyle='#1d3345';x.lineWidth=1;for(let i=1;i<5;i++){x.beginPath();x.moveTo(0,h*i/5);x.lineTo(w,h*i/5);x.stroke()}x.strokeStyle='#43e5ff';x.lineWidth=2;x.beginPath();levels.forEach((db,i)=>{const px=i/(Math.max(1,levels.length-1))*w,py=h-(Math.max(-70,Math.min(0,db))+70)/70*h;i?x.lineTo(px,py):x.moveTo(px,py)});x.stroke()}
function fillSelect(el,items,current,formatter){const vals=(items||[]).map(x=>formatter?formatter(x):{value:x.value||x.device||x.id||x,name:x.label||x.name||x.device||x});if(current&&!vals.some(v=>String(v.value)===String(current)))vals.unshift({value:current,name:current+' (current)'});el.innerHTML=vals.map(v=>`<option value="${esc(v.value)}" ${String(v.value)===String(current)?'selected':''}>${esc(v.name)}</option>`).join('')}
function renderConversation(d){const el=$('chatTranscript');if(!el)return;const vr=d.voice_runtime||{},p=d.performance||{},v=d.voice||{};const messages=(d.events||[]).filter(e=>['user','input','bx1','error'].includes(String(e.kind||''))&&eventText(e)).slice(-80);el.innerHTML=messages.length?messages.map(e=>{const k=String(e.kind||'');const c=k==='bx1'?'robot':(k==='error'?'error':'user');const who=k==='bx1'?'BX1':(k==='error'?'System':'You');return `<div class="chat-msg ${c}"><div class="who">${who} · ${esc(e.at||e.timestamp||'')}</div>${esc(eventText(e))}</div>`}).join(''):'<div class="muted">No conversation yet. Type a message or use Listen and send.</div>';$('conversationMetrics').innerHTML=metric('Voice',vr.state||'--')+metric('Listener',vr.loop_active?'active':'stopped')+metric('STT',v.stt_ready?'ready':(v.stt_error?'fault':'starting'))+metric('Brain link',p.last_brain_latency_ms!=null?p.last_brain_latency_ms+' ms':'--');$('conversationStatus').className='result-box '+(vr.state==='error'?'bad':vr.loop_active?'good':'');$('conversationStatus').textContent=vr.label||vr.message||(vr.loop_active?'Listening for Hello, Hey or Robot.':'Live listening is not active. Open Speech Input and activate it.');const metrics=vr.last_stt_metrics||{};const heard=String(vr.last_heard||'').trim();const accepted=String(vr.last_accepted||'').trim();const cue=String(vr.last_thinking_cue||'').trim();let heardLines=[];if(heard)heardLines.push('Heard: “'+heard+'”');if(accepted&&accepted!==heard)heardLines.push('Command: “'+accepted+'”');if(vr.last_wake_word)heardLines.push('Wake word: '+vr.last_wake_word+(vr.wake_match_source?' · '+vr.wake_match_source:'')+(vr.wake_match_score!==undefined&&vr.wake_match_score!==null?' · score '+Number(vr.wake_match_score).toFixed(2):''));if(metrics.transcription_backend)heardLines.push('STT: '+String(metrics.transcription_backend)+(metrics.stt_model?' · '+metrics.stt_model:'')+(metrics.stt_device?' · '+metrics.stt_device+'/'+(metrics.stt_compute_type||''):'') );if(metrics.local_vosk_text&&String(metrics.local_vosk_text).trim()&&String(metrics.local_vosk_text).trim().toLowerCase()!==heard.toLowerCase())heardLines.push('Local fallback heard: “'+String(metrics.local_vosk_text).trim()+'”');if(metrics.stt_latency_ms!==undefined&&metrics.stt_latency_ms!==null)heardLines.push('STT model: '+Number(metrics.stt_latency_ms).toFixed(0)+' ms');if(metrics.stt_pipeline_ms!==undefined&&metrics.stt_pipeline_ms!==null)heardLines.push('STT pipeline: '+Number(metrics.stt_pipeline_ms).toFixed(0)+' ms');if(metrics.confidence!==undefined&&metrics.confidence!==null&&metrics.confidence!=='')heardLines.push('Confidence: '+Number(metrics.confidence).toFixed(2));if(metrics.primary_stt_error)heardLines.push('Primary STT warning: '+String(metrics.primary_stt_error));if(['processing','speechgen'].includes(String(vr.state||'')))heardLines.push('Thinking phase: '+String(vr.thinking_phase||'processing')+(cue?' — '+cue:''));if(vr.last_feedback_kind)heardLines.push('Last feedback audio: '+vr.last_feedback_kind+' · '+(vr.last_feedback_ok===true?'played':vr.last_feedback_ok===false?'FAILED':'queued')+(vr.last_feedback_error?' · '+vr.last_feedback_error:''));if(p.last_live_tool_route&&p.last_live_tool_route!=='none')heardLines.push('Live lookup: '+p.last_live_tool_route+' · '+(p.last_live_tool_verified?'verified':'FAILED')+(p.last_live_tool_result_count?' · '+p.last_live_tool_result_count+' result(s)':'')+(Array.isArray(p.last_live_tool_sources)&&p.last_live_tool_sources.length?' · '+p.last_live_tool_sources.join(', '):''));const h=$('conversationHeard');h.className='result-box '+(vr.state==='error'?'bad':heard?'good':'');h.textContent=heardLines.length?heardLines.join('\n'):'No speech recognised yet.';if(page==='conversation'&&!isDirty($('chatText')))el.scrollTop=el.scrollHeight}
function setValueIfClean(id,value){const el=$(id);if(el&&!isDirty(el))el.value=String(value??'')}
function setCheckedIfClean(id,value){const el=$(id);if(el&&!isDirty(el))el.checked=!!value}
function renderSpeech(d){
  const m=d.mic||{},v=d.voice||{},vr=d.voice_runtime||{},a=d.audio||{};
  if(!STT_CAPTURE_ID&&m.stt_last_capture_id&&m.stt_debug_audio_urls)setSttDiagnosticAudio(m.stt_debug_audio_urls,m.stt_last_capture_id);
  const mic=$('micDevice');
  if(mic&&!isDirty(mic)){
    fillSelect(mic,m.devices,m.mic_device,x=>({value:x.device||x.id||x.name,name:(x.device||x.id||x.name)+' — '+(x.description||x.label||'ALSA input')}));
  }
  setValueIfClean('sampleRate',m.sample_rate||16000);
  setValueIfClean('micGain',m.mic_software_gain_db??0);
  setValueIfClean('noiseGate',m.mic_noise_gate_dbfs??-48);
  setValueIfClean('adaptiveMargin',m.stt_adaptive_margin_db??8);
  setValueIfClean('preRoll',m.stt_pre_roll_ms??700);
  setValueIfClean('endSilence',m.stt_end_silence_ms??1350);
  setValueIfClean('postRoll',m.stt_post_roll_ms??300);
  setValueIfClean('startTimeout',m.stt_start_timeout_s??8);
  setValueIfClean('maxUtterance',m.stt_max_utterance_s??20);
  setValueIfClean('startTrigger',m.stt_start_trigger_ms??80);
  setCheckedIfClean('endpointingEnabled',m.stt_endpointing_enabled!==false);
  setCheckedIfClean('adaptiveEnabled',m.stt_adaptive_threshold_enabled!==false);
  setValueIfClean('highpassHz',m.audio_highpass_hz??90);
  setValueIfClean('notchHz',m.audio_notch_hz??50);
  setValueIfClean('noiseReduction',m.audio_noise_reduction_strength??.2);
  setCheckedIfClean('filterEnabled',m.audio_filter_enabled!==false);
  setCheckedIfClean('highpassEnabled',m.audio_highpass_enabled!==false);
  setCheckedIfClean('notchEnabled',m.audio_notch_enabled!==false);
  setCheckedIfClean('nrEnabled',m.audio_noise_reduction_enabled!==false);
  setValueIfClean('minConfidence',m.stt_min_confidence??.4);
  setValueIfClean('minVoiced',m.stt_min_voiced_ms??280);
  setValueIfClean('wakeWords',(v.wake_words||[]).join('\n'));
  setCheckedIfClean('voiceEnabled',!!v.voice_enabled);
  $('voiceMetrics').innerHTML=metric('State',vr.state||'--')+metric('STT ready',yes(v.stt_ready),v.stt_error||'')+metric('Capture',m.manual_capture_requested?'manual handover':(m.capture_busy?'live listener':'free'))+metric('Endpointing',v.endpointing_enabled?'natural':'fixed');
  setValueIfClean('voskModelPath',v.vosk_model_path||'');
  const brainPrimary=!!v.brain_stt_enabled&&String(v.stt_transcription_backend||'').includes('brain');
  const fallbackReady=!!v.local_vosk_ready;
  const improved=v.vosk_model_tier==='improved'||String(v.vosk_model_path||'').includes('0.22-lgraph');
  $('speechModelHint').className='result-box '+(brainPrimary?'good':(fallbackReady?'':'bad'));
  $('speechModelHint').textContent=brainPrimary?'Primary STT: desktop Brain faster-whisper. BX1 sends the completed WAV to the Brain PC; local Vosk is retained only as an offline fallback'+(fallbackReady?'.':', but the local fallback model is not ready.'):(improved?'Desktop STT disabled; improved local Vosk fallback active.':'Desktop STT disabled; small local Vosk fallback active.');
  setValueIfClean('ttsVolume',a.tts_volume??80);
  $('voiceOwnerText').textContent='TTS engine and voice owner: '+(a.voice_owner||'desktop_brain_app')+'. This page controls only speaker output.';
  renderLevel(((d.mic_level||{}).level)||{});
}
function renderVision(d){const v=d.vision_awareness||{},rt=v.runtime||v;const set=(id,value,checked=false)=>{const el=$(id);if(!el||isDirty(el))return;if(checked)el.checked=!!value;else el.value=value??''};set('cameraDevice',v.camera_device||'/dev/video0');set('cameraIndex',v.camera_index??0);set('cameraQuality',v.jpeg_quality??85);set('cameraFrameInterval',v.periodic_camera_frame_interval_s??5);set('visionPreviewInterval',v.camera_live_preview_interval_s??rt.camera_live_preview_interval_s??2);set('awarenessInterval',v.visual_awareness_interval_s??rt.interval_s??2);set('motionThreshold',v.visual_motion_threshold??rt.motion_threshold??0.035);set('aloneTimeout',v.visual_alone_timeout_s??rt.alone_timeout_s??20);set('visualWakeWindow',v.visual_wake_window_s??rt.wake_window_s??20);set('cameraEnabled',v.camera_enabled??rt.camera_enabled,true);set('autoVision',v.auto_camera_on_vision_request??rt.auto_camera_on_vision_request,true);set('passiveFrames',v.send_periodic_camera_frames??rt.send_periodic_camera_frames,true);set('awarenessEnabled',v.visual_awareness_enabled??rt.enabled,true);set('visualWake',v.visual_wake_on_person??rt.wake_on_person,true);set('eventFrames',v.visual_send_event_frames??rt.send_event_frames,true);set('visionLivePreview',v.camera_live_preview_enabled??rt.camera_live_preview_enabled??true,true);if(!isDirty($('visionTriggers')))set('visionTriggers',(v.vision_trigger_phrases||((d.chat_bridge||{}).vision_trigger_phrases)||[]).join('\n'));const person=rt.person_present===true?'present':rt.person_present===false?(rt.alone?'alone':'not seen'):'unknown';$('visionMetrics').innerHTML=metric('State',rt.state||'--')+metric('Person',person)+metric('Faces',rt.face_count??'--')+metric('Motion',rt.motion_detected===true?'detected':rt.motion_detected===false?'quiet':'--')+metric('Camera',rt.camera_ok===true?'online':rt.camera_ok===false?'fault':'starting')+metric('OpenCV',rt.opencv_available?'yes':'no')+metric('Last frame',rt.last_frame_at||rt.latest_cached_frame_at||'--')+metric('Brain frame',rt.last_frame_sent_at||'--');$('visionEvidence').className='result-box '+(rt.last_error?'bad':rt.camera_ok===true?'good':'');$('visionEvidence').textContent=`State: ${rt.state||'--'}\nPerson present: ${yes(rt.person_present)} · alone: ${yes(rt.alone)}\nFace count: ${rt.face_count??'--'} · motion score: ${rt.motion_score??'--'}\nLast transition: ${rt.last_transition||'none'}\nLast person seen: ${rt.last_person_seen_at||'none'}\nLast motion: ${rt.last_motion_at||'none'}\nCached frame: ${rt.latest_cached_frame_at||'none'} (${rt.latest_cached_frame_source||'--'})\nCamera error: ${rt.last_error||'none'}\nIdentity: ${rt.identity_note||'Named-person recognition is not enrolled yet.'}\nGesture mode: ${rt.gesture_recognition_mode||rt.gesture_mode||'Brain vision on request'}`;const ps=$('visionPreviewState');if(ps)ps.textContent=`Live preview ${$('visionLivePreview').checked?'on':'off'} · latest cached frame ${rt.latest_cached_frame_at||rt.last_frame_at||'not received yet'}`}
function renderIdle(d){const v=d.idle_life||{},rt=v.runtime||{};const set=(id,value,checked=false)=>{const el=$(id);if(!el||isDirty(el))return;if(checked)el.checked=!!value;else el.value=value??''};set('idleEnabled',v.enabled,true);set('idleMicroEnabled',v.micro_actions_enabled,true);set('idleRequireAlone',v.require_alone,true);set('idleCuriosity',v.internet_curiosity_enabled,true);set('idleResponseMode',v.response_mode||'brain');set('idleMicroDelay',v.micro_action_delay_s??120);set('idleMicroInterval',v.micro_action_interval_s??90);set('idleCommentDelay',v.comment_delay_s??300);set('idleCommentInterval',v.min_comment_interval_s??600);set('idleSleepAfter',v.sleep_after_s??1800);set('idleMaxComments',v.max_comments_per_hour??3);set('idleYaw',v.head_yaw_deg??8);set('idlePitch',v.head_pitch_deg??4);set('idleEyeColour',v.eye_colour||'blue');set('idleBrightness',v.eye_brightness??.14);set('idleBrainPrompt',v.brain_prompt||'');$('idleMetrics').innerHTML=metric('State',rt.state||'--')+metric('User idle',rt.user_idle_s!=null?rt.user_idle_s+' s':'--')+metric('Responses / hour',rt.comments_this_hour??0)+metric('Sleeping',yes(rt.sleeping))+metric('Response mode',v.response_mode||'brain')+metric('Require alone',yes(v.require_alone))+metric('Last action',rt.last_action||'--')+metric('Updated',rt.updated_at||'--');$('idleEvidence').className='result-box '+(rt.last_error?'bad':v.enabled?'good':'');$('idleEvidence').textContent=`Routine: ${v.enabled?'enabled':'disabled'}\nTrigger owner: ${v.trigger_owner||'robot body'}\nDialogue owner: ${v.dialogue_owner||'desktop Brain App'}\nCurrent phase: ${rt.state||'--'}\nLast action: ${rt.last_action||'none'}\nLast activity reason: ${rt.last_activity_reason||'none'}\nLast error: ${rt.last_error||'none'}\n\nTypical phases: active → watching → micro movement → curious/bored response → sleeping.`}
function renderMouth(d){const m=d.mouth_audio||{},s=d.state||{};$('mouthMetrics').innerHTML=metric('Active',yes(m.active))+metric('Commands',m.commands??0)+metric('Last level',m.last_brightness??'--')+metric('Transport',m.transport||'--');$('mouthEvidence').className='result-box '+(m.last_ok===false?'bad':m.commands>0?'good':'');$('mouthEvidence').textContent=`Last command: ${m.last_command_at||'none'}\nColour: ${m.last_colour||'--'}  Brightness: ${m.last_brightness??'--'}\nTransport: ${m.transport||'--'}  Result: ${yes(m.last_ok)}\nError: ${m.last_error||'none'}\nMCU count: ${s.led_command_count??'--'}  MCU last zone: ${s.last_led_zone||'--'}  MCU effective brightness: ${s.last_led_effective_brightness??s.last_led_brightness??'--'}`;const states=Object.keys(((d.led_states||{}).profiles)||((d.led_states||{}).led_state_profiles)||{});const use=states.length?states:['idle','listening','awake','thinking','speaking','success','warning','error','vision','diagnostic'];$('stateButtons').innerHTML=use.map(x=>`<button onclick="applyLedState('${esc(x)}',this)">${esc(x)}</button>`).join('');$('ledStateJson').textContent=JSON.stringify(d.led_states||{},null,2)}
function renderSimpleHardware(reg){const servos=reg.servos||{},yaw=servos.head_yaw||{},left=servos.gimbal_left||{},right=servos.gimbal_right||{},behaviour=reg.servo_behaviour||{},bus=(reg.led_buses||{}).main||{},zones=reg.led_zones||{};const set=(id,value,checked=false)=>{const el=$(id);if(!el||isDirty(el))return;if(checked)el.checked=!!value;else el.value=value??''};set('servoYawEnabled',yaw.enabled,true);set('servoYawPin',yaw.pin);set('servoYawHome',yaw.home_deg);set('servoYawInvert',yaw.invert,true);set('servoLeftEnabled',left.enabled,true);set('servoLeftPin',left.pin);set('servoLeftHome',left.home_deg);set('servoRightEnabled',right.enabled,true);set('servoRightPin',right.pin);set('servoRightHome',right.home_deg);set('servoQuietRelease',behaviour.quiet_release_enabled??true,true);set('servoReleaseAfter',behaviour.release_after_ms??1200);set('servoDeadband',behaviour.pulse_deadband_us??4);set('ledBusEnabled',bus.enabled,true);set('ledBusPin',bus.data_pin);set('ledBusCount',bus.total_pixels);set('ledBrightnessLimit',bus.brightness_limit);const editor=$('ledZoneEditor');if(!editor.querySelector('[data-zone]')){const order=['mouth','left_eye','right_eye','chest','status'];editor.innerHTML='<div class="head">Zone</div><div class="head">Enabled</div><div class="head">First LED</div><div class="head">Last LED</div>'+order.map(k=>{const z=zones[k]||{};return `<div>${esc(z.label||k)}</div><label><input type="checkbox" data-zone="${k}" data-key="enabled"></label><input type="number" min="1" max="500" data-zone="${k}" data-key="start"><input type="number" min="1" max="500" data-zone="${k}" data-key="end">`}).join('')}editor.querySelectorAll('[data-zone]').forEach(el=>{if(isDirty(el))return;const z=zones[el.dataset.zone]||{};if(el.dataset.key==='enabled')el.checked=!!z.enabled;else el.value=z[el.dataset.key]??''})}
function renderHardware(d){const s=d.state||{},h=d.hardware||{},reg=h.hardware_registry||{},sensor=s.sensors||{},imu=!!(s.imu_ok??sensor.imu_ok),rt=s.control_runtime||{},wheel=(reg.drive_buses||{}).rs485_wheels||{};$('hardwareMetrics').innerHTML=metric('MCU',yes(s.mcu_ok),s.firmware_version||'')+metric('Mode',s.mode||s.bridge_mode||'--')+metric('Pitch',s.pitch_deg??s.pitch??'--')+metric('Roll',s.roll_deg??s.roll??'--')+metric('IMU',yes(imu),s.imu_bus||sensor.imu_bus||'Wire1/Qwiic')+metric('LED commands',s.led_command_count??'--');const detail=$('hardwareBridgeDetail');if(detail){const err=s.bridge_error||s.mcu_error||'';detail.className='result-box '+(s.mcu_ok?(imu?'good':'warn'):'bad');detail.textContent=`High-level owner: ${rt.high_level_owner||'Linux Python'}
MCU transport: ${rt.mcu_transport||s.bridge_mode||'Arduino Router RPC'}
Firmware: ${s.firmware_version||'not responding'}
IMU: ${imu?'online':'offline'} · ${s.imu_source||sensor.imu_source||'Modulino Movement'} · ${s.imu_bus||sensor.imu_bus||'Wire1/Qwiic'} · ${s.imu_address||sensor.imu_address||'0x6A'}
Wheel RS485: ${wheel.enabled?'configured':'staged'} · motor ${wheel.motor_armed?'ARMED':'DISARMED'} · protocol ${wheel.protocol_confirmed?'confirmed':'not confirmed'}
Servo quiet mode: ${(s.servo_quiet||{}).enabled?'enabled':'disabled'} · ${(s.servo_quiet||{}).released?'PWM released':'holding/moving'} · release ${(s.servo_quiet||{}).release_after_ms??'--'} ms · deadband ${(s.servo_quiet||{}).pulse_deadband_us??'--'} µs
Error: ${err||s.imu_error||sensor.imu_error||'none'}

Repair command:
cd /home/arduino/Arduino_Q_Client_V1 && ./APPLY_BX1_V10_39_AUDIO_SERVO_FIX.sh

Editable reference implementation: mcu_micropython/`;}const buses=reg.led_buses||{},zones=reg.led_zones||{},servos=reg.servos||{},drives=reg.drive_buses||{};$('registrySummary').innerHTML=`<table><thead><tr><th>Category</th><th>Configured</th><th>Enabled</th><th>Key detail</th></tr></thead><tbody><tr><td>LED buses</td><td>${Object.keys(buses).length}</td><td>${Object.values(buses).filter(x=>x.enabled).length}</td><td>${esc(Object.entries(buses).map(([k,x])=>k+': D'+x.data_pin+', '+x.total_pixels+' pixels, limit '+x.brightness_limit).join('; '))}</td></tr><tr><td>LED zones</td><td>${Object.keys(zones).length}</td><td>${Object.values(zones).filter(x=>x.enabled).length}</td><td>${esc(Object.entries(zones).map(([k,x])=>k+' '+x.start+'-'+x.end).join('; '))}</td></tr><tr><td>Servos</td><td>${Object.keys(servos).length}</td><td>${Object.values(servos).filter(x=>x.enabled).length}</td><td>${esc(Object.entries(servos).map(([k,x])=>k+': D'+x.pin+' home '+x.home_deg).join('; '))}</td></tr><tr><td>Drive buses</td><td>${Object.keys(drives).length}</td><td>${Object.values(drives).filter(x=>x.enabled).length}</td><td>${esc(Object.entries(drives).map(([k,x])=>k+': '+(x.motor_armed?'ARMED':'DISARMED')+', '+(x.diagnostics_interface||'interface pending')+', protocol '+(x.protocol_confirmed?'confirmed':'pending')).join('; '))}</td></tr></tbody></table>`;renderSimpleHardware(reg);if(!isDirty($('hardwareRegistry')))$('hardwareRegistry').value=JSON.stringify(reg,null,2)}
function doctorData(d){return (d.hardware_doctor||{}).snapshot||d.hardware_doctor||{}}function renderDoctor(d){const q=doctorData(d),sev=q.severity||'unknown';$('doctorSummary').className='result-box '+(sev==='ok'?'good':sev==='unknown'?'':'bad');$('doctorSummary').innerHTML=`<div class="result-big">${esc(sev.toUpperCase())}</div>${esc(q.summary||'No diagnosis yet')}<br><span class="muted">Last run: ${esc(q.last_run_at||'not run')}</span>`;const e=q.evidence||{};const age=x=>x==null?'age unknown':`${Math.round(Number(x))} ms`;const rows=[['Router transport',e.mcu_transport_connected,e.bridge_error||e.bridge_mode||''],['MCU heartbeat',e.mcu_heartbeat_fresh,e.mcu_health_reason||age(e.mcu_last_update_age_ms)],['IMU detection',e.imu_present,e.imu_address||'not detected'],['IMU initialisation',e.imu_initialised,e.imu_error||e.imu_source||''],['IMU sample',e.imu_sample_fresh,e.imu_health_reason||age(e.imu_sample_age_ms)],['IMU health',e.imu_healthy,e.imu_health_reason||''],['Automatic flashing',false,'disabled by design']];$('doctorEvidence').innerHTML=rows.map(r=>`<div class="fault"><span class="badge ${r[0]==='Automatic flashing'?'good':r[1]?'good':'bad'}">${esc(r[0])}</span><div><strong>${r[0]==='Automatic flashing'?'OFF':r[1]?'OK':'FAULT'}</strong><small>${esc(r[2])}</small></div></div>`).join('');$('doctorRecommendations').innerHTML=(q.recommendations||['Run a fresh diagnosis to generate recommendations.']).map(x=>`<div class="fault"><span class="badge warn">ACTION</span><div>${esc(x)}</div></div>`).join('');$('doctorRaw').textContent=JSON.stringify(q,null,2)}
function renderAdvanced(d){setValueIfClean('brainUrl',(d.brain||{}).base_url||'');$('rawSnapshot').textContent=JSON.stringify(d,null,2)}
function renderAll(d){SNAP=d;EVENTS=d.events||[];renderOverview(d);renderConversation(d);renderSpeech(d);renderVision(d);renderIdle(d);renderMouth(d);renderHardware(d);renderDoctor(d);renderAdvanced(d);renderLogs();$('lastRefresh').textContent='Updated '+new Date().toLocaleTimeString()}
async function refreshAll(manual=false){if(refreshing)return;refreshing=true;try{const d=await req('/api/status');renderAll(d);if(manual)toast('Status refreshed','good')}catch(e){toast('Status failed: '+e.message,'bad')}finally{refreshing=false}}
async function pollLevel(){try{const d=await req('/api/mic_level');renderLevel(d.level||{})}catch(e){}}
async function startMonitor(btn){busy(btn,true);try{await req('/api/mic_monitor_start',{});toast('Level meter started','good');await refreshAll()}catch(e){toast(e.message,'bad')}finally{busy(btn,false)}}
async function stopMonitor(btn){busy(btn,true);try{await req('/api/mic_monitor_stop',{});toast('Level meter stopped','good');await refreshAll()}catch(e){toast(e.message,'bad')}finally{busy(btn,false)}}
async function loadDevices(btn){busy(btn,true);try{const d=await req('/api/mic_devices');const m=SNAP.mic||{};const mic=$('micDevice');const selected=(mic&&isDirty(mic)&&mic.value)?mic.value:m.mic_device;fillSelect(mic,d.devices,selected,x=>({value:x.device||x.id||x.name,name:(x.device||x.id||x.name)+' — '+(x.description||x.label||'ALSA input')}));const p=await req('/api/mic_playback_devices');const out=$('playbackDevice');const outSelected=(out&&isDirty(out)&&out.value)?out.value:(SNAP.audio||{}).tts_playback_device;fillSelect(out,p.devices,outSelected,x=>({value:x.device||x.id||x.name,name:(x.device||x.id||x.name)+' — '+(x.description||x.label||'ALSA output')}));toast('Audio devices refreshed','good')}catch(e){toast(e.message,'bad')}finally{busy(btn,false)}}
function micPayload(){const m=SNAP.mic||{};return {...m,mic_device:$('micDevice').value,sample_rate:Number($('sampleRate').value),mic_software_gain_db:Number($('micGain').value),mic_noise_gate_dbfs:Number($('noiseGate').value),stt_adaptive_margin_db:Number($('adaptiveMargin').value),stt_pre_roll_ms:Number($('preRoll').value),stt_end_silence_ms:Number($('endSilence').value),stt_post_roll_ms:Number($('postRoll').value),stt_start_timeout_s:Number($('startTimeout').value),stt_max_utterance_s:Number($('maxUtterance').value),stt_start_trigger_ms:Number($('startTrigger').value),stt_endpointing_enabled:$('endpointingEnabled').checked,stt_adaptive_threshold_enabled:$('adaptiveEnabled').checked,audio_highpass_hz:Number($('highpassHz').value),audio_notch_hz:Number($('notchHz').value),audio_noise_reduction_strength:Number($('noiseReduction').value),audio_filter_enabled:$('filterEnabled').checked,audio_highpass_enabled:$('highpassEnabled').checked,audio_notch_enabled:$('notchEnabled').checked,audio_noise_reduction_enabled:$('nrEnabled').checked,stt_min_confidence:Number($('minConfidence').value),stt_min_voiced_ms:Number($('minVoiced').value),stt_capture_method:'alsa',stt_debug_keep_audio:true}}
async function saveMic(btn){busy(btn,true,'Saving…');try{const requested=$('micDevice').value;const d=await req('/api/mic_settings',micPayload());const saved=String(((d.mic||{}).mic_device)||'');if(saved!==requested)throw new Error('Microphone save verification failed: requested '+requested+', service reported '+(saved||'[blank]'));clearDirty($('page-speech'));toast('Microphone saved: '+saved,'good');await refreshAll(true)}catch(e){toast(e.message,'bad')}finally{busy(btn,false)}}
function setNaturalWakeWords(){$('wakeWords').value='Hello\nHey\nRobot';$('wakeWords').dataset.dirty='1';$('voiceEnabled').checked=true;$('voiceEnabled').dataset.dirty='1'}
async function saveVoice(btn){busy(btn,true,'Saving…');try{const v=SNAP.voice||{};await req('/api/voice_settings',{...v,voice_enabled:$('voiceEnabled').checked,input_mode:$('voiceEnabled').checked?'both':'keyboard',wake_words:$('wakeWords').value});clearDirty($('page-speech'));$('voiceSaveState').textContent='Saved. Live listener will remain enabled after restart.';toast('Wake words saved and listening activated','good');await refreshAll(true)}catch(e){toast(e.message,'bad')}finally{busy(btn,false)}}
function setSttDiagnosticAudio(urls,captureId){STT_AUDIO_URLS=urls||{};STT_CAPTURE_ID=String(captureId||'');[['playSttRaw','raw'],['playSttFiltered','filtered'],['playSttSubmitted','submitted']].forEach(([id,k])=>{const b=$(id);if(b)b.disabled=!STT_AUDIO_URLS[k]});const s=$('sttCaptureState');if(s)s.textContent=STT_CAPTURE_ID?'Current capture: '+STT_CAPTURE_ID:'No current capture. Record again before using playback.'}
async function playDiagnosticAudio(kind,btn){const base=STT_AUDIO_URLS[kind];if(!base){toast('No current '+kind+' WAV. Record again first.','bad');return}busy(btn,true,'Loading…');try{if(sttAudioPlayer){try{sttAudioPlayer.pause()}catch(_){}}const joiner=base.includes('?')?'&':'?';sttAudioPlayer=new Audio(base+joiner+'play='+Date.now());sttAudioPlayer.preload='auto';await sttAudioPlayer.play();toast('Playing '+kind+' from capture '+STT_CAPTURE_ID,'good')}catch(e){toast('Audio playback failed: '+e.message,'bad')}finally{busy(btn,false)}}
async function listenOnce(send,btn){busy(btn,true,'Listening…');setSttDiagnosticAudio({},'');$('sttResult').className='result-box';$('sttResult').textContent='Waiting for speech…';try{const d=await req('/api/stt_once',{send});const r=d.stt||{},c=r.capture||{},va=r.voice_activity||{};setSttDiagnosticAudio(r.debug_audio_urls||{},r.capture_id||'');$('sttResult').className='result-box '+(d.ok?'good':'bad');$('sttResult').innerHTML=`<div class="result-big">${esc(d.text||'[no accepted text]')}</div>Accepted: ${yes(r.accepted)} · reason: ${esc(r.reason||'accepted')}<br>STT: ${esc(r.transcription_backend||'local_vosk')}${r.stt_model?' · '+esc(r.stt_model):''}${r.stt_latency_ms!=null?' · model '+esc(r.stt_latency_ms)+' ms':''}${r.stt_pipeline_ms!=null?' · pipeline '+esc(r.stt_pipeline_ms)+' ms':''}<br>${r.local_vosk_text&&String(r.local_vosk_text).trim().toLowerCase()!==String(d.text||'').trim().toLowerCase()?'Local fallback: '+esc(r.local_vosk_text)+'<br>':''}Close: ${esc(c.close_reason||'--')} · duration: ${esc(c.duration_s??'--')} s · waited: ${esc(c.waited_for_speech_s??'--')} s${c.ignored_transients?' · ignored transients: '+esc(c.ignored_transients):''}<br>Threshold: ${esc(c.threshold_dbfs??va.threshold_dbfs??'--')} dBFS · stop: ${esc(c.continue_threshold_dbfs??'--')} dBFS · noise floor: ${esc(c.noise_floor_dbfs??va.noise_floor_dbfs??'--')} dBFS · confidence: ${esc(r.confidence??'--')}`;toast(d.ok?'Speech recognised':'Speech rejected: '+(d.error||r.reason),d.ok?'good':'bad');await refreshAll()}catch(e){setSttDiagnosticAudio({},'');$('sttResult').className='result-box bad';$('sttResult').textContent='STT test failed: '+e.message;toast(e.message,'bad')}finally{busy(btn,false)}}
async function saveOutput(btn){busy(btn,true);try{const a=SNAP.audio||{};await req('/api/audio_settings',{...a,tts_playback_device:$('playbackDevice').value||a.tts_playback_device,tts_volume:Number($('ttsVolume').value),brain_tts_use_brain_defaults:true});toast('Speaker output saved','good');await refreshAll()}catch(e){toast(e.message,'bad')}finally{busy(btn,false)}}
function visionPayload(){const v=SNAP.vision_awareness||{};return {...v,camera_enabled:$('cameraEnabled').checked,camera_device:$('cameraDevice').value,camera_index:Number($('cameraIndex').value),jpeg_quality:Number($('cameraQuality').value),auto_camera_on_vision_request:$('autoVision').checked,vision_trigger_phrases:$('visionTriggers').value,send_periodic_camera_frames:$('passiveFrames').checked,periodic_camera_frame_interval_s:Number($('cameraFrameInterval').value),camera_live_preview_enabled:$('visionLivePreview').checked,camera_live_preview_interval_s:Number($('visionPreviewInterval').value),visual_awareness_enabled:$('awarenessEnabled').checked,visual_awareness_interval_s:Number($('awarenessInterval').value),visual_motion_threshold:Number($('motionThreshold').value),visual_alone_timeout_s:Number($('aloneTimeout').value),visual_wake_on_person:$('visualWake').checked,visual_wake_window_s:Number($('visualWakeWindow').value),visual_send_event_frames:$('eventFrames').checked}}
async function saveVision(btn){busy(btn,true,'Saving…');try{const d=await req('/api/vision_settings',visionPayload());clearDirty($('page-vision'));toast('Vision settings saved','good');await refreshAll(true)}catch(e){toast(e.message,'bad')}finally{busy(btn,false)}}
async function cameraProbe(btn){busy(btn,true,'Probing…');try{const d=await req('/api/camera_probe',{});$('visionEvidence').textContent=JSON.stringify(d.probe||d,null,2);toast(d.ok?'Camera online':'Camera probe failed',d.ok?'good':'bad');refreshVisionPreview(null);await refreshAll()}catch(e){toast(e.message,'bad')}finally{busy(btn,false)}}
async function sendCameraFrame(btn){busy(btn,true,'Capturing…');try{const d=await req('/api/camera_frame',{});toast(d.ok?'Frame sent to Brain':'Camera frame failed',d.ok?'good':'bad');refreshVisionPreview(null);await refreshAll()}catch(e){toast(e.message,'bad')}finally{busy(btn,false)}}
async function askCamera(btn){busy(btn,true,'Looking…');try{const d=await req('/api/camera_vision',{prompt:$('visionPrompt').value});toast(d.ok?'Vision reply completed':'Vision request failed',d.ok?'good':'bad');refreshVisionPreview(null);await refreshAll(true)}catch(e){toast(e.message,'bad')}finally{busy(btn,false)}}
function refreshVisionPreview(btn,quiet=false,fresh=false){if(btn)busy(btn,true,'Refreshing…');const img=$('visionPreview');if(!img)return;img.onload=()=>{if(btn)busy(btn,false);const e=$('visionPreviewState');if(e)e.textContent='Live frame updated '+new Date().toLocaleTimeString()};img.onerror=()=>{if(btn)busy(btn,false);if(!quiet)toast('Camera snapshot failed','bad')};img.src='/api/camera_snapshot.jpg?'+(fresh?'fresh=1&':'')+'t='+Date.now()}
function syncVisionPreviewTimer(){if(visionPreviewTimer){clearInterval(visionPreviewTimer);visionPreviewTimer=null}const enabled=page==='vision'&&$('visionLivePreview')&&$('visionLivePreview').checked;if(!enabled)return;refreshVisionPreview(null,true,false);const seconds=Math.max(1,Number($('visionPreviewInterval')?.value||2));visionPreviewTimer=setInterval(()=>{if(page==='vision'&&$('visionLivePreview')?.checked)refreshVisionPreview(null,true,false)},seconds*1000)}
function idlePayload(){const v=SNAP.idle_life||{};return {...v,enabled:$('idleEnabled').checked,micro_actions_enabled:$('idleMicroEnabled').checked,response_mode:$('idleResponseMode').value,require_alone:$('idleRequireAlone').checked,internet_curiosity_enabled:$('idleCuriosity').checked,micro_action_delay_s:Number($('idleMicroDelay').value),micro_action_interval_s:Number($('idleMicroInterval').value),comment_delay_s:Number($('idleCommentDelay').value),min_comment_interval_s:Number($('idleCommentInterval').value),sleep_after_s:Number($('idleSleepAfter').value),max_comments_per_hour:Number($('idleMaxComments').value),head_yaw_deg:Number($('idleYaw').value),head_pitch_deg:Number($('idlePitch').value),eye_colour:$('idleEyeColour').value,eye_brightness:Number($('idleBrightness').value),brain_prompt:$('idleBrainPrompt').value}}
async function saveIdle(btn){busy(btn,true,'Saving…');try{await req('/api/idle_life_settings',idlePayload());clearDirty($('page-idle'));toast('Idle-life settings saved','good');await refreshAll(true)}catch(e){toast(e.message,'bad')}finally{busy(btn,false)}}
async function testIdleAction(btn){busy(btn,true,'Moving…');try{const d=await req('/api/test_idle_life_action',{});toast(d.ok?'Idle movement sent':'Idle movement failed',d.ok?'good':'bad');await refreshAll()}catch(e){toast(e.message,'bad')}finally{busy(btn,false)}}
async function testIdleResponse(btn){busy(btn,true,'Thinking…');try{const d=await req('/api/test_idle_life_phrase',{});toast(d.ok?'Idle response generated':(d.skipped||d.error||'Idle response failed'),d.ok?'good':'bad');await refreshAll(true)}catch(e){toast(e.message,'bad')}finally{busy(btn,false)}}
async function resetIdleTimer(btn){busy(btn,true);try{await req('/api/reset_idle_life_timer',{});toast('Idle timer reset','good');await refreshAll()}catch(e){toast(e.message,'bad')}finally{busy(btn,false)}}
async function testSpeechMouth(btn){busy(btn,true,'Speaking…');try{const d=await req('/api/test_speech',{text:$('mouthTestText')?.value||'Leo mouth light diagnostic.'});toast(d.ok?'Speech and mouth test completed':'Speech test failed',' '+(d.ok?'good':'bad'));await refreshAll()}catch(e){toast(e.message,'bad')}finally{busy(btn,false)}}
async function testMouth(colour,brightness,btn){busy(btn,true);try{const d=await req('/api/hardware_test',{role:'mouth',colour,brightness});toast(d.ok?'Mouth command executed':'Mouth command failed',d.ok?'good':'bad');await refreshAll()}catch(e){toast(e.message,'bad')}finally{busy(btn,false)}}
async function applyLedState(state,btn){busy(btn,true);try{const d=await req('/api/led_state_apply',{state});toast(d.ok?'LED state applied: '+state:'LED state failed',d.ok?'good':'bad');await refreshAll()}catch(e){toast(e.message,'bad')}finally{busy(btn,false)}}
async function hardwareTest(role,value,colour,btn){busy(btn,true);try{const d=await req('/api/hardware_test',{role,value,colour});toast(d.ok?'Hardware command executed':'Hardware command failed',d.ok?'good':'bad');await refreshAll()}catch(e){toast(e.message,'bad')}finally{busy(btn,false)}}
function formatRegistry(){try{$('hardwareRegistry').value=JSON.stringify(JSON.parse($('hardwareRegistry').value),null,2);$('hardwareRegistry').dataset.dirty='1'}catch(e){toast('Invalid registry JSON: '+e.message,'bad')}}
function loadKnownBx1Mapping(){[['servoYawPin',9],['servoLeftPin',10],['servoRightPin',11]].forEach(([id,v])=>{$(id).value=v;$(id).dataset.dirty='1'});['servoYawEnabled','servoLeftEnabled','servoRightEnabled'].forEach(id=>{$(id).checked=true;$(id).dataset.dirty='1'});$('servoYawInvert').checked=true;$('servoYawInvert').dataset.dirty='1';toast('Loaded BX1 servo mapping D9 / D10 / D11','good')}
function simpleHardwareRegistry(){const reg=JSON.parse(JSON.stringify(((SNAP.hardware||{}).hardware_registry)||{}));reg.schema=reg.schema||'bx1.hardware_registry.v1';reg.servos=reg.servos||{};const patchServo=(key,en,pin,home,invert)=>{const s=reg.servos[key]||{};s.enabled=$(en).checked;s.pin=Number($(pin).value);s.home_deg=Number($(home).value||0);if(invert)s.invert=$(invert).checked;reg.servos[key]=s};patchServo('head_yaw','servoYawEnabled','servoYawPin','servoYawHome','servoYawInvert');patchServo('gimbal_left','servoLeftEnabled','servoLeftPin','servoLeftHome');patchServo('gimbal_right','servoRightEnabled','servoRightPin','servoRightHome');reg.servo_behaviour=reg.servo_behaviour||{};reg.servo_behaviour.quiet_release_enabled=$('servoQuietRelease').checked;reg.servo_behaviour.release_after_ms=Math.max(250,Math.min(10000,Number($('servoReleaseAfter').value||1200)));reg.servo_behaviour.pulse_deadband_us=Math.max(0,Math.min(30,Number($('servoDeadband').value||4)));reg.led_buses=reg.led_buses||{};const bus=reg.led_buses.main||{};bus.enabled=$('ledBusEnabled').checked;bus.data_pin=Number($('ledBusPin').value);bus.total_pixels=Math.max(1,Math.min(500,Number($('ledBusCount').value||1)));bus.brightness_limit=Math.max(0,Math.min(1,Number($('ledBrightnessLimit').value||0)));reg.led_buses.main=bus;reg.led_zones=reg.led_zones||{};$('ledZoneEditor').querySelectorAll('[data-zone]').forEach(el=>{const k=el.dataset.zone,z=reg.led_zones[k]||{bus:'main'};z[el.dataset.key]=el.dataset.key==='enabled'?el.checked:Number(el.value);reg.led_zones[k]=z});return reg}
async function saveSimpleHardware(btn,apply){busy(btn,true,apply?'Saving + applying…':'Saving…');try{const registry=simpleHardwareRegistry();await req('/api/hardware_settings',{hardware_registry:registry});if(apply){const d=await req('/api/hardware_apply',{});if(!d.ok)throw new Error(d.bridge_error||'MCU rejected registry')}clearDirty($('page-hardware'));toast(apply?'Servo and LED setup saved and applied':'Servo and LED setup saved','good');await refreshAll(true)}catch(e){toast(e.message,'bad')}finally{busy(btn,false)}}
async function saveHardware(btn){busy(btn,true);try{const registry=JSON.parse($('hardwareRegistry').value);await req('/api/hardware_settings',{hardware_registry:registry});clearDirty($('page-hardware'));toast('Hardware registry saved','good');await refreshAll(true)}catch(e){toast(e.message,'bad')}finally{busy(btn,false)}}
async function applyHardware(btn){busy(btn,true,'Applying…');try{const d=await req('/api/hardware_apply',{});toast(d.ok?'Registry applied to MCU':'MCU rejected registry',d.ok?'good':'bad');await refreshAll()}catch(e){toast(e.message,'bad')}finally{busy(btn,false)}}
async function runDoctor(btn){busy(btn,true,'Diagnosing…');try{const d=await req('/api/hardware_doctor_diagnose',{});SNAP.hardware_doctor=d.diagnosis||d;renderDoctor(SNAP);toast('Diagnosis complete','good')}catch(e){toast(e.message,'bad')}finally{busy(btn,false)}}
async function recoverBridge(btn){if(!confirm('Restart the approved arduino-router service? Firmware will not be flashed.'))return;busy(btn,true,'Restarting…');try{const d=await req('/api/hardware_doctor_recover',{});toast(d.ok?'Router recovery complete':'Router recovery failed',d.ok?'good':'bad');await refreshAll()}catch(e){toast(e.message,'bad')}finally{busy(btn,false)}}
function groupedEvents(){const type=$('logType')?.value||'',q=($('logSearch')?.value||'').toLowerCase(),collapse=$('collapseLogs')?.checked!==false;let a=EVENTS.filter(e=>(!type||e.kind===type)&&(!q||JSON.stringify(e).toLowerCase().includes(q)));if(!collapse)return a.map(e=>({...e,_count:1}));let out=[];for(const e of a){const key=(e.kind||'')+'|'+eventText(e);const last=out[out.length-1];if(last&&last._key===key){last._count++;last.at=e.at||e.timestamp||last.at}else out.push({...e,_key:key,_count:1})}return out}
function renderLogs(){const el=$('eventLog');if(!el)return;const a=groupedEvents();el.innerHTML=a.length?a.slice().reverse().map(e=>`<div class="log-entry ${esc(e.kind||'system')}"><div class="log-meta"><span>${esc(e.at||e.timestamp||'')} · ${esc(e.kind||'system')}</span>${e._count>1?`<span class="count">×${e._count}</span>`:''}</div><div class="log-body">${esc(eventText(e))}</div>${e.data?`<details><summary>Evidence</summary><pre>${esc(JSON.stringify(e.data,null,2))}</pre></details>`:''}</div>`).join(''):'<div class="log-entry"><div class="log-body muted">No matching events.</div></div>'}
async function saveBrain(useIp,btn){busy(btn,true,'Saving…');const requested=$('brainUrl').value.trim();try{const d=await req('/api/brain_settings',{brain_base_url:requested,base_url:requested,use_browser_client_ip:useIp,sync_tts_to_brain_host:true});$('brainResult').textContent=JSON.stringify(d,null,2);const saved=((d.brain||{}).base_url)||'';if(saved)$('brainUrl').value=saved;delete $('brainUrl').dataset.dirty;toast('Brain connection saved: '+(saved||'updated'),'good');await refreshAll(true)}catch(e){$('brainResult').textContent=e.message;toast(e.message,'bad')}finally{busy(btn,false)}}
async function testBrain(btn){busy(btn,true,'Testing…');try{const d=await req('/api/test_brain',{});$('brainResult').textContent=JSON.stringify(d,null,2);toast(d.ok?'Brain reachable':'Brain test failed',d.ok?'good':'bad')}catch(e){$('brainResult').textContent=e.message;toast(e.message,'bad')}finally{busy(btn,false)}}
async function sendChat(btn){const text=$('chatText').value.trim();if(!text)return;busy(btn,true,'Waiting…');try{const d=await req('/api/send_text',{text});$('chatText').value='';delete $('chatText').dataset.dirty;toast(d.ok?'BX1 replied':'Brain request failed',d.ok?'good':'bad');await refreshAll(true)}catch(e){toast(e.message,'bad')}finally{busy(btn,false)}}
async function listenChat(btn){busy(btn,true,'Listening…');try{const d=await req('/api/stt_once',{send:true});toast(d.ok?'BX1 heard and replied':(d.error||'Speech was not accepted'),d.ok?'good':'bad');await refreshAll(true)}catch(e){toast(e.message,'bad')}finally{busy(btn,false)}}
async function sendManual(btn){const text=$('manualText').value.trim();if(!text)return;busy(btn,true,'Waiting…');try{const d=await req('/api/send_text',{text});$('manualResult').textContent=JSON.stringify(d,null,2);toast(d.ok?'Brain replied':'Brain request failed',d.ok?'good':'bad');await refreshAll()}catch(e){$('manualResult').textContent=e.message;toast(e.message,'bad')}finally{busy(btn,false)}}
async function apiAction(path,body,btn){busy(btn,true);try{const d=await req(path,body);toast(d.ok?'Action complete':'Action failed',d.ok?'good':'bad');await refreshAll()}catch(e){toast(e.message,'bad')}finally{busy(btn,false)}}
function initRoute(){const n=location.pathname.replace(/^\//,'');go(PAGE_INFO[n]?n:'overview')}function tickClock(){$('clock').textContent=new Date().toLocaleTimeString()}
$('chatText').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendChat(document.querySelector('#page-conversation button.primary'))}});initRoute();tickClock();setInterval(tickClock,1000);refreshAll();setInterval(()=>refreshAll(false),1250);setInterval(pollLevel,450);loadDevices(null);
</script>
</body>
</html>

'''

class WebControlServer:
    def __init__(self, service: Any, host: str = "0.0.0.0", port: int = 8088) -> None:
        self.service = service
        self.host = host
        self.port = int(port)
        self.httpd: Optional[ThreadingHTTPServer] = None
        self.thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        service = self.service

        class Handler(BaseHTTPRequestHandler):
            server_version = "RobotBodyClient/10.39"

            def log_message(self, fmt: str, *args: Any) -> None:
                if not bool(service.cfg.get("web_log_http", False)):
                    return
                super().log_message(fmt, *args)

            def _send(self, status: int, body: bytes, content_type: str = "application/json") -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
                self.send_header("Pragma", "no-cache")
                self.send_header("Expires", "0")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
                self.end_headers()
                self.wfile.write(body)

            def _json(self, status: int, data: Dict[str, Any]) -> None:
                self._send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

            def _camera_snapshot(self, frame: Dict[str, Any]) -> None:
                body = bytes(frame.get("jpeg", b""))
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(body)))
                self.send_header(
                    "Cache-Control",
                    "no-store, no-cache, must-revalidate",
                )
                self.send_header("Pragma", "no-cache")
                self.send_header(
                    "X-BX1-Frame-Sequence",
                    str(int(frame.get("sequence", 0))),
                )
                self.send_header(
                    "X-BX1-Frame-Timestamp",
                    str(frame.get("timestamp", "")),
                )
                self.send_header(
                    "X-BX1-Frame-Age-Ms",
                    str(frame.get("age_ms", "")),
                )
                self.send_header(
                    "X-BX1-Frame-Resolution",
                    "%sx%s"
                    % (
                        frame.get("width") or 0,
                        frame.get("height") or 0,
                    ),
                )
                self.end_headers()
                self.wfile.write(body)

            def _camera_stream(self, query: str) -> None:
                try:
                    first = service.get_cached_camera_frame()
                except Exception as exc:
                    self._json(
                        503,
                        {"ok": False, "error": str(exc)},
                    )
                    return
                values = parse_qs(query or "")
                try:
                    requested_fps = float(
                        (values.get("fps") or ["8"])[0]
                    )
                except (TypeError, ValueError):
                    requested_fps = 8.0
                fps = max(1.0, min(15.0, requested_fps))
                interval = 1.0 / fps
                opened = getattr(
                    service, "camera_preview_stream_opened", None
                )
                closed = getattr(
                    service, "camera_preview_stream_closed", None
                )
                registered = False
                if callable(opened):
                    registered = opened() is not False
                    if not registered:
                        self._json(
                            503,
                            {
                                "ok": False,
                                "error": "camera preview client limit reached",
                            },
                        )
                        return
                self.send_response(200)
                self.send_header(
                    "Content-Type",
                    "multipart/x-mixed-replace; boundary=frame",
                )
                self.send_header(
                    "Cache-Control",
                    "no-store, no-cache, must-revalidate",
                )
                self.send_header("Pragma", "no-cache")
                self.send_header("Connection", "close")
                self.send_header("X-Accel-Buffering", "no")
                self.send_header("X-BX1-Preview-FPS", str(round(fps, 2)))
                self.end_headers()
                pending = first
                try:
                    while True:
                        frame = pending
                        pending = None
                        if frame is None:
                            try:
                                frame = service.get_cached_camera_frame()
                            except Exception:
                                time.sleep(interval)
                                continue
                        sequence = int(frame.get("sequence", 0))
                        jpeg = bytes(frame.get("jpeg", b""))
                        if not jpeg:
                            time.sleep(interval)
                            continue
                        timestamp = (
                            str(frame.get("timestamp", ""))
                            .replace("\r", "")
                            .replace("\n", "")
                        )
                        part = (
                            b"--frame\r\n"
                            b"Content-Type: image/jpeg\r\n"
                            + (
                                "Content-Length: %s\r\n"
                                "X-BX1-Frame-Sequence: %s\r\n"
                                "X-BX1-Frame-Timestamp: %s\r\n\r\n"
                                % (len(jpeg), sequence, timestamp)
                            ).encode("ascii", errors="replace")
                            + jpeg
                            + b"\r\n"
                        )
                        self.wfile.write(part)
                        self.wfile.flush()
                        time.sleep(interval)
                except (
                    BrokenPipeError,
                    ConnectionResetError,
                    ConnectionAbortedError,
                    OSError,
                ):
                    return
                finally:
                    if registered and callable(closed):
                        closed()

            def _read_json(self) -> Dict[str, Any]:
                length = int(self.headers.get("Content-Length", "0") or "0")
                raw = self.rfile.read(length) if length else b"{}"
                if not raw:
                    return {}
                return json.loads(raw.decode("utf-8"))

            def do_OPTIONS(self) -> None:  # noqa: N802
                self._send(204, b"")

            def do_GET(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                path = parsed.path
                if path in {"/", "/index.html", "/overview", "/conversation", "/speech", "/vision", "/mouth", "/hardware", "/doctor", "/logs", "/advanced", "/chat", "/identity", "/connection", "/microphone", "/cues", "/idle", "/context", "/actions", "/lighting", "/performance", "/telemetry"}:
                    self._send(200, INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8")
                    return
                if path == "/api/status":
                    self._json(200, service.web_snapshot())
                    return
                if path == "/api/camera_snapshot.jpg":
                    try:
                        fresh = "fresh=1" in (parsed.query or "")
                        body = service.get_camera_snapshot_jpeg(max_age_s=0.0 if fresh else None)
                        self._send(200, body, "image/jpeg")
                    except Exception as exc:
                        self._json(503, {"ok": False, "error": str(exc)})
                    return
                if path == "/api/camera/snapshot":
                    try:
                        self._camera_snapshot(
                            service.get_cached_camera_frame()
                        )
                    except Exception as exc:
                        self._json(
                            503,
                            {"ok": False, "error": str(exc)},
                        )
                    return
                if path == "/api/camera/status":
                    self._json(
                        200, service.get_camera_endpoint_status()
                    )
                    return
                if path == "/api/camera/stream":
                    self._camera_stream(parsed.query)
                    return
                if path == "/api/mic_level":
                    self._json(200, service.web_mic_level())
                    return
                if path == "/api/mic_devices":
                    self._json(200, service.web_list_mic_devices())
                    return
                if path == "/api/mic_playback_devices":
                    self._json(200, service.web_list_playback_devices())
                    return
                if path == "/api/mic_sample_info":
                    self._json(200, service.web_mic_sample_info())
                    return
                if path in {"/api/stt_audio/raw.wav", "/api/stt_audio/filtered.wav", "/api/stt_audio/submitted.wav"}:
                    kind = {
                        "/api/stt_audio/raw.wav": "raw",
                        "/api/stt_audio/filtered.wav": "filtered",
                        "/api/stt_audio/submitted.wav": "submitted",
                    }[path]
                    requested = str((parse_qs(parsed.query or "").get("capture_id") or [""])[0]).strip()
                    if requested and re.fullmatch(r"[A-Za-z0-9_-]{8,80}", requested):
                        sample = Path("/tmp") / f"bx1_stt_{requested}_{kind}.wav"
                    else:
                        # Compatibility for old bookmarks/tools. The v10.36 UI
                        # always supplies a capture_id and never relies on this
                        # mutable latest file.
                        sample = Path("/tmp") / f"bx1_stt_last_{kind}.wav"
                    if sample.exists() and sample.is_file():
                        body = sample.read_bytes()
                        self.send_response(200)
                        self.send_header("Content-Type", "audio/wav")
                        self.send_header("Content-Length", str(len(body)))
                        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
                        self.send_header("Pragma", "no-cache")
                        self.send_header("Expires", "0")
                        self.send_header("X-BX1-Capture-ID", requested or "legacy-latest")
                        self.send_header("Access-Control-Allow-Origin", "*")
                        self.end_headers()
                        self.wfile.write(body)
                    else:
                        self._json(404, {"ok": False, "error": "No STT diagnostic audio exists yet. Run Listen once first."})
                    return
                if path == "/api/mic_sample.wav":
                    sample = Path(str(getattr(service, "last_mic_test_wav", "") or ""))
                    if sample.exists() and sample.is_file():
                        body = sample.read_bytes()
                        self.send_response(200)
                        self.send_header("Content-Type", "audio/wav")
                        self.send_header("Content-Length", str(len(body)))
                        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
                        self.send_header("Access-Control-Allow-Origin", "*")
                        if "download=1" in (parsed.query or ""):
                            self.send_header("Content-Disposition", 'attachment; filename="bx1_mic_test.wav"')
                        self.end_headers()
                        self.wfile.write(body)
                    else:
                        self._json(404, {"ok": False, "error": "No microphone WAV sample found yet."})
                    return
                self._json(404, {"ok": False, "error": "not found"})

            def do_POST(self) -> None:  # noqa: N802
                path = urlparse(self.path).path
                try:
                    data = self._read_json()
                    if path == "/api/brain_settings":
                        result = service.web_update_brain_settings(data, client_ip=self.client_address[0] if self.client_address else None)
                        self._json(200 if result.get("ok") else 400, result)
                        return
                    if path == "/api/test_brain":
                        result = service.web_test_brain_connection()
                        self._json(200, result)
                        return
                    if path == "/api/chat_settings":
                        result = service.web_update_chat_settings(data)
                        self._json(200 if result.get("ok") else 400, result)
                        return
                    if path == "/api/send_text":
                        result = service.web_send_text(
                            str(data.get("text", "")),
                            use_web=data.get("use_web"),
                            use_memory=data.get("use_memory"),
                            allow_vision=data.get("allow_vision"),
                        )
                        self._json(200, result)
                        return
                    if path == "/api/repeat_last_response":
                        result = service.web_repeat_last_response()
                        self._json(200 if result.get("ok") else 400, result)
                        return
                    if path == "/api/stt_once":
                        result = service.web_stt_once(data)
                        # Rejected speech is a diagnostic result, not an HTTP transport
                        # failure. Always return the endpointing/recognition evidence.
                        self._json(200, result)
                        return
                    if path == "/api/vision_settings":
                        result = service.web_update_visual_awareness_settings(data)
                        self._json(200 if result.get("ok") else 400, result)
                        return
                    if path == "/api/camera_probe":
                        result = service.web_camera_probe()
                        self._json(200 if result.get("ok") else 400, result)
                        return
                    if path == "/api/camera_frame":
                        result = service.web_camera_frame()
                        self._json(200 if result.get("ok") else 400, result)
                        return
                    if path == "/api/camera_vision":
                        result = service.web_camera_vision(str(data.get("prompt", "")))
                        self._json(200 if result.get("ok") else 400, result)
                        return
                    if path == "/api/identity_settings":
                        result = service.web_update_identity_settings(data)
                        self._json(200 if result.get("ok") else 400, result)
                        return
                    if path == "/api/theme_settings":
                        result = service.web_update_theme_settings(data)
                        self._json(200 if result.get("ok") else 400, result)
                        return
                    if path == "/api/voice_settings":
                        result = service.web_update_voice_settings(data)
                        self._json(200 if result.get("ok") else 400, result)
                        return
                    if path == "/api/mic_settings":
                        result = service.web_update_mic_settings(data)
                        self._json(200 if result.get("ok") else 400, result)
                        return
                    if path == "/api/mic_monitor_start":
                        result = service.web_start_mic_monitor()
                        self._json(200 if result.get("ok") else 400, result)
                        return
                    if path == "/api/mic_monitor_stop":
                        result = service.web_stop_mic_monitor()
                        self._json(200 if result.get("ok") else 400, result)
                        return
                    if path == "/api/mic_record_test":
                        result = service.web_record_mic_test(data)
                        self._json(200 if result.get("ok") else 400, result)
                        return
                    if path == "/api/mic_playback_test":
                        result = service.web_play_mic_test(data)
                        self._json(200 if result.get("ok") else 400, result)
                        return
                    if path == "/api/mic_sample_info":
                        result = service.web_mic_sample_info()
                        self._json(200 if result.get("ok") else 400, result)
                        return
                    if path == "/api/mic_stt_status":
                        result = service.web_mic_stt_status(data)
                        self._json(200 if result.get("ok") else 400, result)
                        return
                    if path == "/api/mic_stt_test":
                        result = service.web_stt_mic_test(data)
                        self._json(200 if result.get("ok") else 400, result)
                        return
                    if path == "/api/led_state_settings":
                        result = service.web_update_led_state_settings(data)
                        self._json(200 if result.get("ok") else 400, result)
                        return
                    if path == "/api/led_state_apply":
                        result = service.web_apply_led_state(str(data.get("state", "idle")))
                        self._json(200 if result.get("ok") else 400, result)
                        return
                    if path == "/api/hardware_doctor_diagnose":
                        result = service.web_run_hardware_diagnosis()
                        self._json(200 if result.get("ok") else 400, result)
                        return
                    if path == "/api/hardware_doctor_recover":
                        result = service.web_hardware_doctor_recover()
                        self._json(200 if result.get("ok") else 400, result)
                        return
                    if path == "/api/hardware_doctor_generate":
                        result = service.web_generate_diagnostic_sketch(str(data.get("template", "")), str(data.get("note", "")))
                        self._json(200 if result.get("ok") else 400, result)
                        return
                    if path == "/api/thinking_cue_settings":
                        result = service.web_update_thinking_cue_settings(data)
                        self._json(200 if result.get("ok") else 400, result)
                        return
                    if path == "/api/play_thinking_cue":
                        result = service.play_one_thinking_cue()
                        self._json(200 if result.get("ok") else 400, result)
                        return
                    if path == "/api/regenerate_local_voice_cues":
                        result = service.web_regenerate_local_voice_cues(data)
                        self._json(200 if result.get("ok") else 400, result)
                        return
                    if path == "/api/idle_life_settings":
                        result = service.web_update_idle_life_settings(data)
                        self._json(200 if result.get("ok") else 400, result)
                        return
                    if path == "/api/test_idle_life_phrase":
                        result = service.web_test_idle_life_phrase()
                        self._json(200 if result.get("ok") else 400, result)
                        return
                    if path == "/api/test_idle_life_action":
                        result = service.web_test_idle_life_action()
                        self._json(200 if result.get("ok") else 400, result)
                        return
                    if path == "/api/reset_idle_life_timer":
                        result = service.web_reset_idle_life_timer()
                        self._json(200, result)
                        return
                    if path == "/api/audio_settings":
                        result = service.web_update_audio_settings(data)
                        self._json(200 if result.get("ok") else 400, result)
                        return
                    if path == "/api/elevenlabs_voices":
                        result = service.web_list_elevenlabs_voices(str(data.get("api_key", "")))
                        self._json(200 if result.get("ok") else 400, result)
                        return
                    if path == "/api/tts_diagnostics":
                        result = service.web_tts_diagnostics()
                        self._json(200 if result.get("ok") else 400, result)
                        return
                    if path == "/api/robot_brain_tts_status":
                        result = service.web_robot_brain_tts_status()
                        self._json(200 if result.get("ok") else 400, result)
                        return
                    if path == "/api/test_speech":
                        result = service.web_test_speech(str(data.get("text", "")))
                        self._json(200 if result.get("ok") else 400, result)
                        return
                    if path == "/api/manual_state":
                        result = service.web_update_manual_state(data)
                        self._json(200, result)
                        return
                    if path == "/api/action":
                        action = data.get("action") or {}
                        result = service.web_manual_action(action)
                        self._json(200, result)
                        return
                    if path == "/api/hardware_settings":
                        result = service.web_update_hardware_settings(data)
                        self._json(200 if result.get("ok") else 400, result)
                        return
                    if path == "/api/hardware_apply":
                        result = service.web_apply_hardware_to_mcu()
                        self._json(200 if result.get("ok") else 400, result)
                        return
                    if path == "/api/hardware_test":
                        result = service.web_test_hardware_device(data)
                        self._json(200 if result.get("ok") else 400, result)
                        return
                    if path == "/api/command":
                        command = str(data.get("command", ""))
                        result = service.web_console_command(command)
                        self._json(200, result)
                        return
                    self._json(404, {"ok": False, "error": "not found"})
                except Exception as exc:
                    service.web_log("error", f"web request failed: {exc}", {"traceback": traceback.format_exc(limit=6)})
                    self._json(500, {"ok": False, "error": str(exc)})

        self.httpd = ReusableThreadingHTTPServer((self.host, self.port), Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, name="bx1-web-control", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        if self.httpd is not None:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None
