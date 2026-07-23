from __future__ import annotations

import json
import html
import threading
import traceback
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional
from urllib.parse import urlparse


class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    # Lets BX1 restart cleanly after a recent shutdown. This does not allow
    # two live servers to use the same port; the starter script handles that.
    allow_reuse_address = True


INDEX_HTML = r"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Robot Body Client v10.22.1</title>
  <style>
    :root { --bg:#07101a; --panel:#101b27; --panel-bg:rgba(16,27,39,.92); --card:#0b1722; --text:#dce8f4; --muted:#8fa5ba; --line:#26394d; --good:#31d07d; --warn:#ffca3a; --bad:#ff5c6c; --blue:#5fb3ff; --body-bg:radial-gradient(circle at top left, #183653 0, #0b1118 42%, #05080c 100%); --header-bg:rgba(9,16,24,.92); --button-bg:linear-gradient(#1d3c58,#13283b); --nav-bg:#09131e; }
    body[data-theme="graphite"] { --panel:#1b1d21; --panel-bg:rgba(27,29,33,.94); --card:#15171b; --text:#e8eaed; --muted:#a8adb5; --line:#3a3d44; --blue:#9fb3c8; --body-bg:radial-gradient(circle at top left, #343940 0, #17191d 45%, #0b0c0f 100%); --header-bg:rgba(22,24,28,.94); --button-bg:linear-gradient(#343940,#202329); --nav-bg:#15171b; }
    body[data-theme="green"] { --panel:#10251f; --panel-bg:rgba(16,37,31,.94); --card:#0b1c17; --text:#e4fff4; --muted:#9bc9b7; --line:#254d40; --blue:#45e0a0; --body-bg:radial-gradient(circle at top left, #1e5f48 0, #0d1a17 45%, #050a08 100%); --header-bg:rgba(7,22,18,.94); --button-bg:linear-gradient(#1f654b,#123728); --nav-bg:#0b1c17; }
    body[data-theme="amber"] { --panel:#2a2112; --panel-bg:rgba(42,33,18,.94); --card:#1d170c; --text:#fff3d6; --muted:#d0b477; --line:#5d4520; --blue:#ffb347; --body-bg:radial-gradient(circle at top left, #5a3b14 0, #20170b 45%, #090704 100%); --header-bg:rgba(28,20,9,.94); --button-bg:linear-gradient(#705022,#3c2a11); --nav-bg:#1d170c; }
    body[data-theme="purple"] { --panel:#20162f; --panel-bg:rgba(32,22,47,.94); --card:#171022; --text:#f1e9ff; --muted:#baa7d6; --line:#46315f; --blue:#c58cff; --body-bg:radial-gradient(circle at top left, #4b2f79 0, #171022 45%, #08050d 100%); --header-bg:rgba(21,13,33,.94); --button-bg:linear-gradient(#54337b,#2c1b42); --nav-bg:#171022; }
    body[data-theme="light"] { --panel:#ffffff; --panel-bg:rgba(255,255,255,.96); --card:#f3f6fa; --text:#162231; --muted:#5d6d7c; --line:#c8d2dc; --good:#168a55; --warn:#b57900; --bad:#b3263a; --blue:#1565c0; --body-bg:linear-gradient(135deg,#eef5ff 0,#f8fbff 52%,#e8edf3 100%); --header-bg:rgba(255,255,255,.94); --button-bg:linear-gradient(#e6f1ff,#cbdff4); --nav-bg:#eef5ff; }
    * { box-sizing: border-box; }
    body { margin:0; font-family: Segoe UI, Roboto, Arial, sans-serif; background:var(--body-bg); color:var(--text); }
    header { padding:14px 18px 10px; border-bottom:1px solid var(--line); background:var(--header-bg); position:sticky; top:0; z-index:5; backdrop-filter:blur(8px); }
    h1 { margin:0; font-size:22px; letter-spacing:.5px; }
    h2 { margin:0 0 10px; font-size:16px; color:#eef7ff; }
    .sub { color:var(--muted); margin-top:4px; font-size:13px; }
    .topline { display:flex; align-items:flex-end; justify-content:space-between; gap:12px; flex-wrap:wrap; }
    .nav { display:flex; flex-wrap:wrap; gap:8px; margin-top:12px; }
    .nav button { padding:8px 12px; border-radius:999px; border:1px solid var(--line); background:var(--nav-bg); color:var(--blue); cursor:pointer; font-weight:650; }
    .nav button.active { background:linear-gradient(#21506f,#143044); color:#fff; border-color:#62b8ff; }
    main { padding:18px; max-width:1800px; margin:0 auto; }
    .page { display:none; } .page.active { display:block; }
    .grid { display:grid; grid-template-columns:1fr 1fr; gap:16px; } .grid.wide-left { grid-template-columns:1.25fr .75fr; }
    section { background:var(--panel-bg); border:1px solid var(--line); border-radius:14px; padding:14px; box-shadow:0 12px 34px rgba(0,0,0,.24); margin-bottom:16px; }
    textarea,input,select { width:100%; border:1px solid var(--line); background:var(--nav-bg); color:var(--text); border-radius:10px; padding:10px; font:inherit; outline:none; }
    textarea { min-height:120px; resize:vertical; }
    input[type="checkbox"] { width:auto; } input[type="range"] { padding:0; accent-color:var(--blue); }
    button { border:1px solid var(--line); background:var(--button-bg); color:var(--text); border-radius:10px; padding:9px 12px; font-weight:650; cursor:pointer; }
    button:hover { filter:brightness(1.14); } button:disabled { opacity:.55; cursor:wait; }
    button.danger { border-color:#8c3440; background:linear-gradient(#722735,#3b141d); } button.good { border-color:#2b7b55; background:linear-gradient(#1e6947,#123727); }
    button.action-running { border-color:#b3842a !important; background:linear-gradient(#8a641b,#4b3209) !important; color:#fff8d7 !important; box-shadow:0 0 0 3px rgba(255,202,58,.16), 0 0 18px rgba(255,202,58,.25); animation:pulse 1.0s ease-in-out infinite; }
    button.action-ok { border-color:#27c779 !important; background:linear-gradient(#22895a,#115833) !important; color:#eafff4 !important; box-shadow:0 0 0 3px rgba(49,208,125,.18), 0 0 18px rgba(49,208,125,.25); }
    button.action-fail { border-color:#ff5c6c !important; background:linear-gradient(#842736,#461018) !important; color:#ffe8ec !important; box-shadow:0 0 0 3px rgba(255,92,108,.18), 0 0 18px rgba(255,92,108,.25); }
    .toast { position:fixed; right:18px; bottom:18px; z-index:20; max-width:560px; padding:12px 14px; border-radius:12px; background:var(--panel-bg); border:1px solid var(--line); color:var(--text); box-shadow:0 18px 50px rgba(0,0,0,.36); font-size:13px; }
    .toast.good { border-color:#246b49; color:#d9ffe9; } .toast.bad { border-color:#87323c; color:#ffccd3; } .toast.warn { border-color:#8a6a20; color:#fff0b8; }
    .bridge-banner { margin:10px 0; padding:10px 12px; border-radius:12px; border:1px solid #8a6a20; color:#fff0b8; background:rgba(255,202,58,.08); }
    .cmd-history { max-height:170px; overflow:auto; background:#07101a; border:1px solid #26394d; border-radius:12px; padding:8px; font-size:12px; color:#cfe6ff; margin-top:10px; }
    .movement-grid { display:grid; grid-template-columns:280px 1fr; gap:12px; align-items:stretch; margin-top:10px; }
    .imu-stage { position:relative; min-height:245px; border:1px solid var(--line); border-radius:14px; background:radial-gradient(circle at center,#13293a 0,#07101a 72%); perspective:850px; overflow:hidden; }
    .imu-axis { position:absolute; left:18px; bottom:18px; font-size:11px; color:var(--muted); line-height:1.35; }
    .imu-cube { position:absolute; left:50%; top:50%; width:130px; height:80px; transform-style:preserve-3d; transform:translate(-50%,-50%) rotateX(0deg) rotateY(0deg) rotateZ(0deg); transition:transform .18s linear; }
    .imu-face { position:absolute; left:0; top:0; width:130px; height:80px; border:1px solid rgba(95,179,255,.75); background:rgba(95,179,255,.12); display:flex; align-items:center; justify-content:center; color:#dff2ff; font-weight:800; letter-spacing:.5px; }
    .imu-front { transform:translateZ(45px); } .imu-back { transform:rotateY(180deg) translateZ(45px); opacity:.45; }
    .imu-left { width:90px; transform:rotateY(-90deg) translateZ(45px); transform-origin:left center; opacity:.70; }
    .imu-right { width:90px; transform:rotateY(90deg) translateZ(85px); transform-origin:left center; opacity:.70; }
    .imu-top { height:90px; transform:rotateX(90deg) translateZ(45px); transform-origin:top center; opacity:.60; }
    .imu-bottom { height:90px; transform:rotateX(-90deg) translateZ(35px); transform-origin:top center; opacity:.35; }
    .imu-readouts { display:grid; grid-template-columns:repeat(3,1fr); gap:8px; margin-bottom:10px; }
    .imu-readout { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:10px; min-height:64px; }
    .imu-readout strong { display:block; color:var(--blue); font-size:18px; margin-top:4px; }
    .row { display:grid; grid-template-columns:1fr 1fr; gap:10px; margin:10px 0; }
    .personality-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:10px; margin:10px 0; }
    .trait-card { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:10px; }
    .trait-card label { color:var(--text); font-size:12px; }
    @media (max-width:1200px) { .personality-grid { grid-template-columns:1fr 1fr; } }
    @media (max-width:760px) { .personality-grid { grid-template-columns:1fr; } }
    .buttons { display:flex; flex-wrap:wrap; gap:8px; margin-top:10px; }
    .pillbar { display:flex; flex-wrap:wrap; gap:8px; margin-top:8px; }
    .pill { padding:6px 9px; background:#09131e; border:1px solid #30485f; border-radius:999px; color:var(--muted); font-size:12px; }
    .pill.good { color:var(--good); border-color:#246b49; } .pill.warn { color:var(--warn); border-color:#8a6a20; } .pill.bad { color:var(--bad); border-color:#87323c; }
    pre { background:#07101a; border:1px solid #26394d; border-radius:12px; padding:10px; overflow:auto; max-height:660px; white-space:pre-wrap; word-break:break-word; color:#cfe6ff; }
    .chatlog { height:520px; overflow:auto; padding:10px; background:#07101a; border:1px solid #26394d; border-radius:12px; }
    .event { border-bottom:1px solid #172636; padding:8px 0; } .event:last-child { border-bottom:0; }
    .event .meta { color:var(--muted); font-size:12px; margin-bottom:3px; } .event.user .body { color:#b8dcff; } .event.bx1 .body { color:#d9ffe9; } .event.error .body { color:#ffb8c0; } .event.thinking .body { color:#fff0b8; } .event.rejected_input .body { color:#ffca3a; } .event.input .body { color:#b8dcff; }
    label { display:block; color:var(--muted); font-size:12px; margin-bottom:5px; }
    .small { color:var(--muted); font-size:12px; line-height:1.35; }
    code { color:#b8dcff; background:#07101a; border:1px solid #26394d; border-radius:6px; padding:1px 5px; }
    input[readonly] { opacity:.8; }
    .mini-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:10px; margin:12px 0; }
    @media (max-width:1000px) { .mini-grid { grid-template-columns:1fr; } }
    .mini-card { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:12px; }
    .theme-controls { min-width:260px; display:grid; grid-template-columns:1fr auto; gap:8px; align-items:end; }
    .status-line { margin-top:8px; color:var(--muted); font-size:13px; min-height:20px; }
    .voice-status-card { margin-top:12px; display:grid; grid-template-columns:auto 1fr; gap:12px; align-items:center; padding:12px; border:1px solid var(--line); border-radius:14px; background:var(--card); }
    .voice-orb { width:46px; height:46px; border-radius:50%; border:2px solid #334f67; background:#111b26; box-shadow:0 0 0 rgba(95,179,255,0); transition:all .2s ease; }
    .voice-orb.listening { border-color:var(--blue); background:radial-gradient(circle,#5fb3ff 0,#102d45 58%,#07101a 100%); box-shadow:0 0 16px rgba(95,179,255,.38); animation:pulse 1.7s ease-in-out infinite; }
    .voice-orb.heard, .voice-orb.ignored { border-color:var(--warn); background:radial-gradient(circle,#ffca3a 0,#3b2a0b 58%,#07101a 100%); box-shadow:0 0 16px rgba(255,202,58,.35); }
    .voice-orb.awake, .voice-orb.processing, .voice-orb.recording, .voice-orb.transcribing { border-color:var(--good); background:radial-gradient(circle,#31d07d 0,#0e3b27 58%,#07101a 100%); box-shadow:0 0 22px rgba(49,208,125,.48); animation:pulse 1.0s ease-in-out infinite; }
    .voice-orb.speaking { border-color:var(--warn); background:radial-gradient(circle,#ffca3a 0,#3b2a0b 58%,#07101a 100%); box-shadow:0 0 20px rgba(255,202,58,.42); animation:pulse 0.8s ease-in-out infinite; }
    .voice-orb.asleep, .voice-orb.paused { border-color:#334f67; background:radial-gradient(circle,#37506a 0,#111b26 58%,#07101a 100%); opacity:.8; }
    .voice-orb.error { border-color:var(--bad); background:radial-gradient(circle,#ff5c6c 0,#3b1218 58%,#07101a 100%); box-shadow:0 0 16px rgba(255,92,108,.35); }
    .voice-title { font-size:16px; font-weight:750; color:var(--text); }
    .voice-detail { margin-top:3px; color:var(--muted); font-size:12px; line-height:1.4; }
    .voice-mini-grid { display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-top:8px; }
    .voice-mini-grid div { background:#07101a; border:1px solid #26394d; border-radius:10px; padding:7px; font-size:12px; color:var(--muted); min-height:32px; }
    .inline-control-panel { margin-top:12px; padding:12px; background:var(--card); border:1px solid var(--line); border-radius:12px; }
    .quick-toggle-row { display:flex; flex-wrap:wrap; gap:12px; align-items:center; margin:8px 0; }
    .quick-toggle-row label { margin:0; font-size:13px; color:var(--text); }
    .spinner { display:inline-block; width:12px; height:12px; margin-right:6px; border:2px solid #35536d; border-top-color:var(--blue); border-radius:50%; animation:spin .9s linear infinite; vertical-align:-2px; }
    .meter { width:100%; height:24px; background:#050b11; border:1px solid #294158; border-radius:999px; overflow:hidden; box-shadow:inset 0 0 10px rgba(0,0,0,.35); }
    .meter span { display:block; height:100%; background:linear-gradient(90deg,#245a8a,#31d07d,#ffca3a,#ff5c6c); transition:width .2s linear; }
    .meter-fill { height:100%; width:0%; background:linear-gradient(90deg,#245a8a,#31d07d,#ffca3a,#ff5c6c); transition:width .12s linear; }
    .meter-row { display:grid; grid-template-columns:110px 1fr 85px; gap:10px; align-items:center; margin:10px 0; }
    .audio-chart-grid { display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-top:10px; }
    .chart-card { background:#07101a; border:1px solid #26394d; border-radius:12px; padding:10px; min-height:220px; }
    .chart-card h3 { margin:0 0 6px; font-size:13px; color:#dce8f4; }
    canvas.audio-chart { width:100%; height:180px; display:block; background:#050b11; border:1px solid #172636; border-radius:10px; }
    .download-link { display:inline-block; text-decoration:none; border:1px solid #37607e; background:linear-gradient(#1d3c58,#13283b); color:#ecf7ff; border-radius:10px; padding:9px 12px; font-weight:650; }
    .led-state-table { min-width:980px; }
    .led-state-table th,.led-state-table td { vertical-align:middle; }
    .led-zone-editor { display:grid; grid-template-columns:52px 72px; gap:6px; align-items:center; min-width:130px; }
    .led-zone-editor input[type=color] { width:50px; height:34px; padding:2px; border-radius:7px; }
    .led-zone-editor input[type=number] { width:72px; }
    .state-row-active { outline:2px solid var(--blue); outline-offset:-2px; background:rgba(48,155,255,.08); }
    .mixer-grid { display:grid; grid-template-columns:repeat(4,minmax(130px,1fr)); gap:10px; margin-top:10px; }
    .mixer-diagram { background:#07101a; border:1px solid #2b4358; border-radius:12px; padding:12px; line-height:1.6; }
    @media (max-width:1000px) { .mixer-grid { grid-template-columns:1fr 1fr; } }
    @media (max-width:1000px) { .audio-chart-grid { grid-template-columns:1fr; } }
    @keyframes spin { to { transform:rotate(360deg); } }
    @keyframes pulse { 0%,100% { transform:scale(1); opacity:.78; } 50% { transform:scale(1.08); opacity:1; } }
    @media (max-width:1000px) { .grid,.grid.wide-left { grid-template-columns:1fr; } }
  </style>
</head>
<body>
  <header>
    <div class="topline">
      <div>
        <h1><span id="robotNameTitle">Robot</span> Body Client <span style="color:var(--blue);font-size:14px;">v10.22.1</span></h1>
        <div class="sub">Reusable robot body client: hardware I/O, STT wake/listen, camera, LEDs/servos, telemetry and Brain App connection. Robot name/personality now live in the desktop Brain App instance.</div>
      </div>
      <div class="theme-controls">
        <div><label>Colour theme</label><select id="uiTheme" onchange="previewTheme(this.value)"><option value="dark-blue">Dark Blue / BX1</option><option value="graphite">Graphite</option><option value="green">Workshop Green</option><option value="amber">Amber Console</option><option value="purple">Purple Lab</option><option value="light">Light</option></select></div>
        <button onclick="saveThemeSettings()">Save Theme</button>
      </div>
    </div>
    <div id="statusPills" class="pillbar"></div>
    <nav class="nav" aria-label="BX1 web pages">
      <button type="button" data-page="chat" onclick="navigatePage('chat')">Chat / Debug</button>
      <button type="button" data-page="identity" onclick="navigatePage('identity')">Body Settings</button>
      <button type="button" data-page="connection" onclick="navigatePage('connection')">Brain Connection</button>
      <button type="button" data-page="speech" onclick="navigatePage('speech')">Speech / Voice</button>
      <button type="button" data-page="microphone" onclick="navigatePage('microphone')">Microphone Test</button>
      <button type="button" data-page="cues" onclick="navigatePage('cues')">Thinking Cues</button>
      <button type="button" data-page="idle" onclick="navigatePage('idle')">Idle Life</button>
      <button type="button" data-page="context" onclick="navigatePage('context')">Sensor Context</button>
      <button type="button" data-page="actions" onclick="navigatePage('actions')">Robot Actions</button>
      <button type="button" data-page="hardware" onclick="navigatePage('hardware')">Hardware / GPIO</button>
      <button type="button" data-page="lighting" onclick="navigatePage('lighting')">LED States</button>
      <button type="button" data-page="doctor" onclick="navigatePage('doctor')">Hardware Doctor</button>
      <button type="button" data-page="performance" onclick="navigatePage('performance')">Performance</button>
      <button type="button" data-page="telemetry" onclick="navigatePage('telemetry')">Telemetry / Logs</button>
    </nav>
  </header>

  <main>
    <div class="page" data-page="chat">
      <div class="grid wide-left">
        <section>
          <h2>Manual Chat / Debug Input</h2>
          <div class="small">The text is sent to the Brain App exactly like a spoken message, with current body telemetry attached. The box clears immediately when you press send.</div>
          <textarea id="message" placeholder="Type what you want to say to the robot or Brain App..."></textarea>
          <div class="quick-toggle-row">
            <label><input id="useWeb" type="checkbox"> Allow laptop Brain App internet/web for this message</label>
            <label><input id="useMemory" type="checkbox" checked> Use memory/context</label>
            <label><input id="autoCamera" type="checkbox" checked> Auto use camera when asked</label>
          </div>
          <div class="buttons">
            <button id="sendButton" class="good" onclick="sendText()">Send Text</button>
            <button onclick="repeatLastResponse()">Repeat Last Response</button>
            <button onclick="sendPreset('What is your current body state?')">Ask Status</button>
            <button onclick="sendPreset('Use your camera and tell me what you can see.')">Ask Camera</button>
            <button onclick="sendPreset('Look around carefully and tell me what you would check next.')">Debug Check</button>
            <button onclick="document.getElementById('message').value=''">Clear Text</button>
          </div>
          <div class="inline-control-panel">
            <h2 style="font-size:14px; margin-bottom:8px;">Main Window Speech Input</h2>
            <div class="small">Use this for quick tests without opening the Microphone page. “Listen Once + Send” records one short sample, runs Vosk STT, then sends the recognised text to the Brain App.</div>
            <div class="row">
              <label><input id="mainVoiceEnabled" type="checkbox"> Enable live microphone/STT loop</label>
              <div><label>Main input mode</label><select id="mainInputMode"><option value="keyboard">keyboard only</option><option value="voice">voice only</option><option value="voice_or_keyboard">voice or keyboard</option><option value="both">both</option></select></div>
            </div>
            <div class="buttons">
              <button onclick="saveMainVoiceSettings()">Save Main STT Settings</button>
              <button onclick="listenOnce(false)">Listen Once</button>
              <button class="good" onclick="listenOnce(true)">Listen Once + Send</button>
              <button onclick="saveChatBridgeSettings()">Save Web/Camera Defaults</button>
              <button onclick="navigatePage('microphone')">Mic Diagnostics</button>
            </div>
            <div id="mainVoiceStatus" class="status-line">Main STT controls ready.</div>
            <div class="voice-status-card" aria-live="polite">
              <div id="voiceWakeOrb" class="voice-orb"></div>
              <div>
                <div id="voiceWakeTitle" class="voice-title">Voice loop not started</div>
                <div id="voiceWakeDetail" class="voice-detail">Enable the live microphone/STT loop, save settings, then say the robot wake word.</div>
                <div class="voice-mini-grid">
                  <div><strong>Last heard</strong><br><span id="voiceLastHeard">-</span></div>
                  <div><strong>Last wake</strong><br><span id="voiceLastWake">-</span></div>
                  <div><strong>Accepted command</strong><br><span id="voiceLastAccepted">-</span></div>
                  <div><strong>Wake words</strong><br><span id="voiceWakeWords">-</span></div>
                </div>
              </div>
            </div>
          </div>
          <div id="chatSendStatus" class="status-line"></div>
        </section>
        <section>
          <h2>Quick Body Summary</h2>
          <div class="small">The live status pills above update every two seconds. Full JSON is on the Telemetry page.</div>
          <div class="buttons">
            <button onclick="serviceCommand('/status')">Refresh Status</button>
            <button onclick="navigatePage('identity')">Body Settings</button>
            <button onclick="navigatePage('cues')">Thinking Cues</button>
            <button onclick="navigatePage('performance')">Performance</button>
          </div>
        </section>
      </div>
      <section>
        <h2>Conversation / Event Log</h2>
        <div id="chatlog" class="chatlog"></div>
      </section>
    </div>

    <div class="page" data-page="identity">
      <section>
        <h2>Body Settings / Brain-Managed Identity</h2>
        <div class="small">Robot name, character and personality have moved to the desktop Robot Brain. This page only keeps the body ID, wake words for local STT routing, hardware capabilities and theme.</div>
        <div class="row">
          <div><label>Robot ID sent to Brain App</label><input id="robotId" placeholder="BX1"></div>
          <div><label>Robot name (set in Brain App)</label><input id="robotName" placeholder="Brain-managed" disabled></div>
        </div>
        <div class="row">
          <div><label>Display name (set in Brain App)</label><input id="robotDisplayName" placeholder="Brain-managed" disabled></div>
          <div><label>Robot type / body description</label><input id="robotType" placeholder="small two wheeled companion robot"></div>
        </div>
        <label>Wake word aliases, one per line</label>
        <textarea id="wakeWords" placeholder="bx1&#10;be ex one&#10;robot"></textarea>
        <div class="row">
          <div><label>Personality summary (set in Brain App)</label><textarea id="personalitySummary" placeholder="Brain-managed in the desktop Robot Brain" disabled></textarea></div>
          <div><label>Tone (set in Brain App)</label><textarea id="personalityTone" placeholder="Brain-managed in the desktop Robot Brain" disabled></textarea></div>
        </div>
        <div class="buttons">
          <button disabled title="Personality presets now live in the Robot Brain profile">TARS preset</button>
          <button disabled title="Personality presets now live in the Robot Brain profile">Engineering</button>
          <button disabled title="Personality presets now live in the Robot Brain profile">Friendly</button>
          <button disabled title="Personality presets now live in the Robot Brain profile">Quiet</button>
          <button disabled title="Personality presets now live in the Robot Brain profile">Debug</button>
        </div>
        <div class="small" style="margin-top:8px;">Personality sliders are now disabled here by design. Run a separate Robot Brain profile/port for each robot personality.</div>
        <div class="personality-grid">
          <div class="trait-card"><label>Humour: <span id="personalityHumourValue">35</span>%</label><input id="personalityHumour" data-pkey="humour" type="range" min="0" max="100" value="35" oninput="updatePersonalitySliderLabel(this)"></div>
          <div class="trait-card"><label>Honesty: <span id="personalityHonestyValue">80</span>%</label><input id="personalityHonesty" data-pkey="honesty" type="range" min="0" max="100" value="80" oninput="updatePersonalitySliderLabel(this)"></div>
          <div class="trait-card"><label>Dry humour / sarcasm: <span id="personalitySarcasmValue">20</span>%</label><input id="personalitySarcasm" data-pkey="sarcasm" type="range" min="0" max="100" value="20" oninput="updatePersonalitySliderLabel(this)"></div>
          <div class="trait-card"><label>Timidity: <span id="personalityTimidityValue">45</span>%</label><input id="personalityTimidity" data-pkey="timidity" type="range" min="0" max="100" value="45" oninput="updatePersonalitySliderLabel(this)"></div>
          <div class="trait-card"><label>Curiosity: <span id="personalityCuriosityValue">75</span>%</label><input id="personalityCuriosity" data-pkey="curiosity" type="range" min="0" max="100" value="75" oninput="updatePersonalitySliderLabel(this)"></div>
          <div class="trait-card"><label>Chattiness: <span id="personalityChattinessValue">45</span>%</label><input id="personalityChattiness" data-pkey="chattiness" type="range" min="0" max="100" value="45" oninput="updatePersonalitySliderLabel(this)"></div>
          <div class="trait-card"><label>Technical depth: <span id="personalityTechnicalValue">75</span>%</label><input id="personalityTechnical" data-pkey="technical" type="range" min="0" max="100" value="75" oninput="updatePersonalitySliderLabel(this)"></div>
          <div class="trait-card"><label>Obedience: <span id="personalityObedienceValue">55</span>%</label><input id="personalityObedience" data-pkey="obedience" type="range" min="0" max="100" value="55" oninput="updatePersonalitySliderLabel(this)"></div>
          <div class="trait-card"><label>Confidence: <span id="personalityConfidenceValue">65</span>%</label><input id="personalityConfidence" data-pkey="confidence" type="range" min="0" max="100" value="65" oninput="updatePersonalitySliderLabel(this)"></div>
          <div class="trait-card"><label>Energy: <span id="personalityEnergyValue">55</span>%</label><input id="personalityEnergy" data-pkey="energy" type="range" min="0" max="100" value="55" oninput="updatePersonalitySliderLabel(this)"></div>
          <div class="trait-card"><label>Empathy: <span id="personalityEmpathyValue">55</span>%</label><input id="personalityEmpathy" data-pkey="empathy" type="range" min="0" max="100" value="55" oninput="updatePersonalitySliderLabel(this)"></div>
          <div class="trait-card"><label>Safety caution: <span id="personalityCautionValue">70</span>%</label><input id="personalityCaution" data-pkey="caution" type="range" min="0" max="100" value="70" oninput="updatePersonalitySliderLabel(this)"></div>
        </div>
        <div class="row">
          <div><label>Verbosity</label><select id="personalityVerbosity"><option value="short">short</option><option value="medium">medium</option><option value="detailed">detailed</option></select></div>
          <div><label>Personality lock strength: <span id="personalityStyleStrengthValue">95</span>%</label><input id="personalityStyleStrength" type="range" min="0" max="100" value="95" oninput="personalityStyleStrengthValue.textContent=this.value"></div>
        </div>
        <div class="row">
          <div><label>Usual location/context</label><input id="robotLocation" placeholder="workshop or home test environment"></div>
          <div><label>Identity ownership</label><input readonly value="Robot name and personality are owned by the desktop Robot Brain profile."></div>
        </div>
        <label>Personality / safety rules</label>
        <textarea id="personalityRules" placeholder="Set these in the desktop Robot Brain profile" disabled></textarea>
      </section>
      <section>
        <h2>Robot Capabilities</h2>
        <div class="small">These generic capabilities are sent to the Brain App with chat, vision and telemetry so the LLM knows what hardware this body actually has fitted.</div>
        <div class="row">
          <label><input id="capMic" type="checkbox"> Microphone</label>
          <label><input id="capSpeaker" type="checkbox"> Speaker / TTS</label>
        </div>
        <div class="row">
          <label><input id="capCamera" type="checkbox"> Camera</label>
          <label><input id="capHeadServo" type="checkbox"> Head servo</label>
        </div>
        <div class="row">
          <label><input id="capDriveMotors" type="checkbox"> Drive motors</label>
          <label><input id="capLidar" type="checkbox"> LiDAR / range scanner</label>
        </div>
        <div class="buttons">
          <button class="good" onclick="saveIdentitySettings()">Save Body Settings</button>
          <button onclick="navigatePage('speech')">Open Voice Settings</button>
          <button onclick="navigatePage('connection')">Open Brain Connection</button>
        </div>
        <div id="identityStatus" class="status-line"></div>
      </section>
    </div>

    <div class="page" data-page="connection">
      <section>
        <h2>Brain App Connection</h2>
        <div class="small">Portable setup: open this page from the Windows PC running the correct Robot Brain instance, choose the matching Brain API/TTS ports, then press <b>Use This Browser PC for Brain + Voice</b>. The body client will save that Brain instance for chat/API and voice. If you move house, workshop, hotspot, or network, press it again.</div>
        <div class="row">
          <div><label>Brain App URL</label><input id="brainBaseUrl" placeholder="http://PC_IP:8765"></div>
          <div><label>API key, optional</label><input id="brainApiKey" placeholder="leave blank unless configured"></div>
        </div>
        <div class="row">
          <div><label>Brain API port</label><input id="brainPort" placeholder="8765" value="8765"></div>
          <div><label>Brain TTS port</label><input id="brainTtsPort" placeholder="8091" value="8091"></div>
        </div>
        <div class="row">
          <div><label>Current saved Brain URL</label><input id="currentBrainUrl" readonly placeholder="not configured"></div>
          <div><label>Current saved Brain TTS URL</label><input id="currentBrainTtsUrl" readonly placeholder="not configured"></div>
        </div>
        <div class="buttons">
          <button class="good" onclick="saveBrainSettings(true)">Use This Browser PC for Brain + Voice</button>
          <button onclick="saveBrainSettings(false)">Save Manual Brain URL + Same Host Voice</button>
          <button onclick="testBrainConnection()">Test Brain Connection</button>
          <button onclick="navigatePage('speech')">Open Voice Settings</button>
          <button onclick="navigatePage('chat')">Go To Chat</button>
        </div>
        <div id="brainConnectionResult" class="status-line">Tip: BX1.local is the robot. The Brain URL must be the Windows PC running Robot Brain, not the Arduino Q.</div>
      </section>
    </div>

    <div class="page" data-page="speech">
      <section>
        <h2>Speech / Volume Settings</h2>
        <div class="small">Natural cloud/offline replies are now split into queued chunks so long replies do not time out halfway and switch to the robotic fallback.</div>
        <div class="row">
          <label><input id="ttsEnabled" type="checkbox" checked> Enable spoken replies</label>
          <div><label>TTS backend</label><select id="ttsBackend" onchange="syncTtsBackendHelp()"><option value="brain-tts">Robot Brain / Chatterbox voice</option><option value="edge-tts">Edge TTS fallback</option><option value="piper">Piper offline voice</option><option value="espeak-ng">espeak-ng: emergency robotic fallback</option><option value="custom">Custom command</option></select></div>
        </div>
        <div class="row">
          <div><label>espeak voice</label><select id="ttsVoice"><option value="en-gb+f3">UK female 3 - softer</option><option value="en-gb">UK default</option><option value="en-gb+m3">UK male 3</option><option value="en-sc">Scottish</option><option value="en-us">US default</option><option value="en-us+f3">US female 3</option></select></div>
          <div><label>Edge voice dropdown</label><select id="ttsEdgeVoice"><optgroup label="British English"><option value="en-GB-SoniaNeural">Sonia - British female, warm</option><option value="en-GB-LibbyNeural">Libby - British female, clear</option><option value="en-GB-RyanNeural">Ryan - British male, natural</option><option value="en-GB-ThomasNeural">Thomas - British male</option><option value="en-GB-MaisieNeural">Maisie - British female</option></optgroup><optgroup label="Irish English"><option value="en-IE-ConnorNeural">Connor - Irish male</option><option value="en-IE-EmilyNeural">Emily - Irish female</option></optgroup><optgroup label="US English"><option value="en-US-AriaNeural">Aria - US female</option><option value="en-US-JennyNeural">Jenny - US female</option><option value="en-US-GuyNeural">Guy - US male</option><option value="en-US-ChristopherNeural">Christopher - US male</option><option value="en-US-EricNeural">Eric - US male</option></optgroup></select></div>
        </div>
        <div class="row">
          <div><label>Speech rate: <span id="ttsRateValue">155</span></label><input id="ttsRate" type="range" min="80" max="260" value="155" oninput="ttsRateValue.textContent=this.value"></div>
          <div><label>Pitch: <span id="ttsPitchValue">42</span></label><input id="ttsPitch" type="range" min="0" max="99" value="42" oninput="ttsPitchValue.textContent=this.value"></div>
        </div>
        <div class="row">
          <div><label>Volume: <span id="ttsVolumeValue">80</span>%</label><input id="ttsVolume" type="range" min="0" max="100" value="80" oninput="ttsVolumeValue.textContent=this.value"></div>
          <div><label>TTS output device</label><input id="ttsPlaybackDevice" placeholder="default or plughw:1,0"></div>
        </div>
        <div class="row">
          <div><label>Piper model path</label><input id="ttsPiperModel" placeholder="models/piper/en_GB-alan-medium.onnx"></div>
          <div><label>Voice identity note</label><input readonly value="All spoken output should use the same saved voice profile."></div>
        </div>
        <div class="row">
          <div><label>Brain App TTS URL</label><input id="brainTtsBaseUrl" placeholder="http://YOUR_PC_IP:8091"></div>
          <div><label>Brain voice key</label><input id="brainTtsVoice" placeholder="chatterbox_bx1"></div>
        </div>
        <div class="row">
          <div><label>Brain TTS engine</label><input id="brainTtsEngine" placeholder="chatterbox_turbo"></div>
          <div><label>Brain TTS timeout seconds</label><input id="brainTtsTimeout" type="number" min="20" max="600" value="240"></div>
        </div>
        <div class="row">
          <div><label>Robot speak endpoint</label><input id="brainTtsEndpoint" placeholder="/robot/speak"></div>
          <div><label>Robot TTS status endpoint</label><input id="brainTtsStatusEndpoint" placeholder="/robot/tts/status"></div>
        </div>
        <div class="row">
          <label><input id="ttsChunkingEnabled" type="checkbox" checked> Split long replies into speech chunks</label>
          <div><label>Chunk size chars</label><input id="ttsChunkMaxChars" type="number" min="120" max="1400" value="650"></div>
        </div>
        <label><input id="ttsFallbackToEspeak" type="checkbox"> Allow robotic espeak fallback if natural voice fails</label>
        <div class="small">Leave this unticked to prevent the half-natural / half-robotic behaviour. Use TTS Diagnostics if natural speech stops.</div>
        <div class="mini-card" style="margin-top:12px;">
          <h2 style="font-size:14px; margin-bottom:8px;">Robot Brain Voice Bridge</h2>
          <div class="small">The preferred voice path is now the PC Robot Brain TTS service. The UNO Q calls <b>/robot/speak</b>, downloads the generated Chatterbox WAV, animates the mouth from the WAV envelope, and plays it through the robot speaker.</div>
        </div>
        <label style="margin-top:10px;">Custom TTS command</label><input id="ttsCommand" placeholder="espeak-ng -ven-gb -s 155 -p 35">
        <label style="margin-top:10px;">Test phrase</label><input id="ttsTestText" placeholder="Speech test. Voice system online.">
        <div class="buttons"><button class="good" onclick="saveAudioSettings()">Save Speech Settings</button><button onclick="testSpeech()">Test Speech</button><button onclick="runTtsDiagnostics()">TTS Diagnostics</button><button onclick="checkRobotBrainTts()">Check Robot Brain TTS</button><button onclick="setSpeechPreset('brain')">Robot Brain Voice Preset</button><button onclick="setSpeechPreset('edge')">Edge Fallback Preset</button><button onclick="setSpeechPreset('soft')">Emergency Robotic Preset</button></div>
        <div id="ttsHelp" class="small" style="margin-top:8px;"></div><pre id="ttsDiagnostics" style="margin-top:8px; min-height:48px; max-height:240px; overflow:auto;">TTS diagnostics not run yet.</pre>
      </section>
      <section>
        <h2>Speech To Text / Wake Word</h2>
        <div class="small">This prepares the UNO Q for hands-free use. Wake word matching uses the robot name and aliases from the Identity page.</div>
        <div class="row"><label><input id="voiceEnabled" type="checkbox"> Enable microphone/STT loop</label><div><label>Input mode</label><select id="inputMode"><option value="keyboard">keyboard only</option><option value="voice">voice only</option><option value="voice_or_keyboard">voice or keyboard</option><option value="both">both</option></select></div></div>
        <div class="row"><div><label>STT backend</label><select id="voiceBackend"><option value="vosk">Vosk offline STT</option></select></div><div><label>Record window seconds</label><input id="recordSeconds" type="number" min="2" max="20" value="5"></div></div>
        <div class="row"><div><label>Sample rate</label><input id="sampleRate" type="number" min="8000" max="48000" value="16000"></div><div><label>Vosk model path</label><input id="voskModelPath" placeholder="models/vosk-model-small-en-us-0.15"></div></div>
        <div class="buttons"><button class="good" onclick="saveVoiceSettings()">Save STT / Wake Settings</button><button onclick="navigatePage('identity')">Edit Wake Words</button></div>
        <div id="voiceStatus" class="status-line"></div>
      </section>
    </div>


    <div class="page" data-page="microphone">
      <section>
        <h2>Microphone Test / Live Level Meter</h2>
        <div class="small">This page reads the microphone on the Arduino Q using ALSA. Use it to tune capture volume, software gain and the noise gate before enabling wake-word mode.</div>
        <div class="row">
          <div><label>Microphone device</label><select id="micDevice"><option value="default">default</option></select></div>
          <div><label>Manual device override</label><input id="micDeviceManual" placeholder="e.g. plughw:1,0"></div>
        </div>
        <div class="row">
          <div><label>Capture mixer volume: <span id="micCaptureVolumeValue">70</span>%</label><input id="micCaptureVolume" type="range" min="0" max="100" value="70" oninput="micCaptureVolumeValue.textContent=this.value"></div>
          <div><label>ALSA capture control</label><input id="micCaptureControl" placeholder="Capture"></div>
        </div>
        <div class="row">
          <div><label>Software gain: <span id="micSoftwareGainValue">0</span> dB</label><input id="micSoftwareGain" type="range" min="-12" max="24" step="1" value="0" oninput="micSoftwareGainValue.textContent=this.value"></div>
          <div><label>Noise gate: <span id="micNoiseGateValue">-45</span> dBFS</label><input id="micNoiseGate" type="range" min="-80" max="-10" step="1" value="-45" oninput="micNoiseGateValue.textContent=this.value"></div>
        </div>
        <div class="row">
          <div><label>Sample rate</label><input id="micSampleRate" type="number" min="8000" max="48000" value="16000"></div>
          <div><label>Record test seconds</label><input id="micRecordSeconds" type="number" min="1" max="30" value="5"></div>
        </div>
        <div class="inline-control-panel">
          <h2 style="font-size:14px;margin-bottom:8px;">Real-time speech cleanup</h2>
          <div class="small">The filtered stream is used by Vosk. The live FFT below shows raw input and the processed result.</div>
          <div class="row"><label><input id="audioFilterEnabled" type="checkbox"> Enable speech filters</label><label><input id="micHighpassEnabled" type="checkbox"> High-pass filter</label></div>
          <div class="row"><div><label>High-pass frequency (Hz)</label><input id="audioHighpassHz" type="number" min="20" max="300" value="90"></div><label><input id="audioNotchEnabled" type="checkbox"> 50 Hz mains notch</label></div>
          <div class="row"><div><label>Notch frequency (Hz)</label><input id="audioNotchHz" type="number" min="40" max="70" value="50"></div><div><label>Notch harmonics</label><input id="audioNotchHarmonics" type="number" min="1" max="4" value="2"></div></div>
          <div class="row"><label><input id="audioNoiseReductionEnabled" type="checkbox"> Noise reduction / soft gate</label><div><label>Reduction strength (0–1)</label><input id="audioNoiseReductionStrength" type="number" min="0" max="1" step="0.05" value="0.45"></div></div>
          <h2 style="font-size:14px;margin:12px 0 8px;">STT acceptance gates</h2>
          <div class="row"><label><input id="sttValidationEnabled" type="checkbox"> Reject weak/fragmented transcripts</label><div><label>Minimum Vosk confidence</label><input id="sttMinConfidence" type="number" min="0" max="1" step="0.05" value="0.45"></div></div>
          <div class="row"><div><label>Minimum voiced audio (ms)</label><input id="sttMinVoicedMs" type="number" min="80" max="3000" value="320"></div><div><label>Longest continuous voice (ms)</label><input id="sttMinLongestVoicedMs" type="number" min="40" max="1500" value="160"></div></div>
          <div class="row"><div><label>Duplicate window (s)</label><input id="sttDuplicateWindow" type="number" min="1" max="120" value="12"></div><div><label>Echo similarity (0–1)</label><input id="sttEchoSimilarity" type="number" min="0.55" max="0.98" step="0.01" value="0.78"></div></div>
        </div>
        <div class="buttons">
          <button class="good" onclick="saveMicSettings()">Save Mic Settings</button>
          <button onclick="refreshMicDevices()">Refresh Devices</button>
          <button onclick="startMicMonitor()">Start Level Meter</button>
          <button onclick="stopMicMonitor()">Stop Level Meter</button>
        </div>
        <div id="micStatus" class="status-line">Microphone meter not started.</div>
      </section>
      <section>
        <h2>Live Input Level</h2>
        <div class="meter-row"><div class="small">RMS</div><div class="meter"><div id="micRmsBar" class="meter-fill"></div></div><div id="micRmsText" class="small">- dBFS</div></div>
        <div class="meter-row"><div class="small">Peak</div><div class="meter"><div id="micPeakBar" class="meter-fill"></div></div><div id="micPeakText" class="small">- dBFS</div></div>
        <div class="pillbar">
          <span id="micRunningPill" class="pill">running: -</span>
          <span id="micActivePill" class="pill">voice: -</span>
          <span id="micClipPill" class="pill">clip: -</span>
          <span id="micDevicePill" class="pill">device: -</span>
        </div>
        <div class="chart-card" style="margin-top:12px;"><h3>Live FFT — raw versus filtered</h3><canvas id="micLiveFftCanvas" class="audio-chart" width="900" height="260"></canvas><div id="micLiveFftLegend" class="small">Raw input and processed speech spectrum will appear while the level meter runs.</div></div>
        <div class="small" style="margin-top:8px;">Target: normal speech should peak roughly between -18 and -6 dBFS. If it reaches 0 dBFS or clips, lower capture volume or software gain. The gate should sit above room noise but below normal speech.</div>
      </section>
      <section>
        <h2>Recorded Audio Diagnostics</h2>
        <div class="small">These graphs analyse the last recorded WAV. Use them to see whether the microphone captured speech, static, hum, or clipping.</div>
        <div class="buttons">
          <button onclick="refreshMicSampleInfo()">Refresh Audio Diagnostics</button>
          <a id="micDownloadLink" class="download-link" href="/api/mic_sample.wav?download=1" download="bx1_mic_test.wav">Download Recorded WAV</a>
        </div>
        <div id="micAudioSummary" class="status-line">No recorded audio analysed yet.</div>
        <div class="audio-chart-grid">
          <div class="chart-card"><h3>Waveform preview</h3><canvas id="micWaveCanvas" class="audio-chart" width="900" height="260"></canvas><div class="small">Shape of the captured sample. Flat means silence; square/flattened tops means clipping.</div></div>
          <div class="chart-card"><h3>Level over time</h3><canvas id="micLevelCanvas" class="audio-chart" width="900" height="260"></canvas><div class="small">RMS/peak level during the sample. Speech should make clear bursts above the noise floor.</div></div>
          <div class="chart-card"><h3>FFT spectrum</h3><canvas id="micFftCanvas" class="audio-chart" width="900" height="260"></canvas><div class="small">Frequency content. 50 Hz hum, hiss/static, and speech bands are easier to spot here.</div></div>
          <div class="chart-card"><h3>Diagnostic hints</h3><pre id="micAudioHints" style="max-height:180px; margin:0;">No hints yet.</pre></div>
        </div>
      </section>
      <section>
        <h2>Push-To-Test Recording / STT</h2>
        <div class="small">Record a short sample, play it back, then run Vosk STT on that saved WAV. If Vosk is not installed yet, recording/playback will still work and the STT result will say what is missing.</div>
        <div class="row">
          <div><label>Robot playback device <span class="small">(aplay output on BX1)</span></label><select id="micPlaybackDevice"><option value="default">default - ALSA default playback</option></select></div>
          <div><label>Manual playback override</label><input id="micPlaybackManual" placeholder="e.g. plughw:0,0"></div>
        </div>
        <div class="buttons">
          <button id="micRecordButton" class="good" onclick="recordMicSample()">1. Record Test Sample</button>
          <button id="micRobotPlaybackButton" onclick="playMicSample()">2A. Play On BX1 Speaker</button>
          <button onclick="loadMicSampleInBrowser(true)">2B. Play In Browser</button>
          <a id="micDownloadLink2" class="download-link" href="/api/mic_sample.wav?download=1" download="bx1_mic_test.wav">Download WAV</a>
          <button onclick="checkMicSttStatus()">Check STT Setup</button>
          <button id="micSttButton" onclick="runMicSttTest()">3. Run STT On Sample</button>
          <button class="good" onclick="recordAndRunMicStt()">Record + Run STT</button>
          <button onclick="sendMicSttToChat()">Send STT Text To Chat</button>
          <button onclick="refreshMicSampleInfo()">Debug Sample</button>
        </div>
        <div id="micRecordStatus" class="status-line">Recorder idle.</div>
        <div id="micPlaybackStatus" class="status-line">Browser playback lets you hear the recorded WAV through this PC/tablet. BX1 playback uses the robot audio output.</div>
        <audio id="micBrowserAudio" controls preload="none" style="width:100%; margin:8px 0 4px;"></audio>
        <div id="micSttStatus" class="status-line">STT not checked yet. Recording can work even when Vosk is not installed.</div>
        <label>Recognised text / STT error</label>
        <textarea id="micRecognisedText" placeholder="Recognised speech, no-speech result, or STT error will appear here..."></textarea>
        <pre id="micDiagnostics">No microphone diagnostics yet.</pre>
      </section>
    </div>

    <div class="page" data-page="cues">
      <section>
        <h2>Thinking Cues / Waiting Noises</h2>
        <div class="small">When the Brain App takes longer than the delay, the UNO Q can speak a short filler phrase so it feels alive instead of frozen.</div>
        <div class="row"><label><input id="thinkingCuesEnabled" type="checkbox" checked> Enable thinking cues</label><label><input id="thinkingCueSpeak" type="checkbox" checked> Speak cues</label><label><input id="voiceCommandImmediateCue" type="checkbox" checked> Immediate cue after command</label></div>
        <div class="row"><label><input id="localVoiceCueCacheEnabled" type="checkbox" checked> Use cached Chatterbox voice cues</label><label><input id="localCueFallbackEspeak" type="checkbox" checked> Emergency espeak if cue is missing</label><label><input id="sttPauseDuringTts" type="checkbox" checked> Mute STT while robot speaks</label></div>
        <div class="row"><div><label>First cue delay seconds</label><input id="thinkingCueDelay" type="number" min="0.5" max="30" step="0.5" value="2"></div><div><label>Repeat every seconds</label><input id="thinkingCueRepeat" type="number" min="1" max="60" step="0.5" value="8"></div></div>
        <div class="row"><div><label>Maximum cues per reply</label><input id="thinkingCueMax" type="number" min="0" max="10" value="1"></div><div><label>Follow-up conversation window seconds</label><input id="conversationFollowupWindow" type="number" min="5" max="600" step="1" value="45"></div></div>
        <div class="row"><div><label>Wake-only command window seconds</label><input id="wakeCommandWindow" type="number" min="3" max="60" step="1" value="12"></div><div><label>Post-speech STT guard seconds</label><input id="sttPostTtsGuard" type="number" min="0" max="10" step="0.25" value="1.25"></div></div>
        <div class="row"><label><input id="wakeVoiceAckEnabled" type="checkbox" checked> Speak immediate wake acknowledgement</label><div><label>Wake phrase</label><input id="wakeAckPhrase" value="Yes John?"></div><div><label>Sleep phrase</label><input id="sleepAckPhrase" value="Going quiet."></div></div>
        <div class="row"><label><input id="voiceFeedbackAudioEnabled" type="checkbox" checked> Short acknowledgement chime when BX1 hears a command</label><label><input id="voiceFeedbackLedEnabled" type="checkbox" checked> Strong LED acknowledgement when speech is accepted</label><div><label>Chime level</label><input id="voiceFeedbackToneLevel" type="number" min="0.02" max="0.35" step="0.01" value="0.16"></div></div>
        <label>Cue table, one per line</label><textarea id="thinkingCueList" placeholder="Hmm.&#10;Let me think.&#10;One moment.&#10;I am checking that."></textarea>
        <div class="buttons"><button class="good" onclick="saveThinkingCueSettings()">Save Thinking Cues</button><button onclick="playThinkingCue()">Play Random Cue</button><button onclick="regenerateLocalVoiceCues(this)">Regenerate Local Chatterbox Cues</button></div>
        <div class="small" style="margin-top:8px;">Regenerate cues after changing the Brain voice profile. BX1 stores the WAVs locally, so wake acknowledgements and waiting phrases use the same Chatterbox voice without live-generation delay.</div>
        <div id="thinkingCueStatus" class="status-line"></div>
        <pre id="localVoiceCueStatus" style="margin-top:8px; min-height:48px; max-height:180px; overflow:auto;">Local voice cue cache not checked yet.</pre>
      </section>
    </div>

    <div class="page" data-page="idle">
      <section>
        <h2>Idle Life / Bored Routine</h2>
        <div class="small">Controls what BX1 does when left unattended. The routine pauses during active conversation, microphone diagnostics, and robot speech, then eventually enters sleep mode.</div>
        <div class="row">
          <label><input id="idleLifeEnabled" type="checkbox" checked> Enable idle-life routine</label>
          <label><input id="idleMicroActions" type="checkbox" checked> Small head / LED actions</label>
          <label><input id="idleSelfChatter" type="checkbox" checked> Allow self chatter</label>
        </div>
        <div class="row">
          <label><input id="idleInternetCuriosity" type="checkbox"> Allow internet curiosity through Brain App</label>
          <label><input id="idleSleepAnnounce" type="checkbox"> Speak when entering sleep</label>
          <div><label>Maximum comments per hour</label><input id="idleMaxComments" type="number" min="0" max="12" step="1" value="3"></div>
        </div>
        <div class="row"><div><label>Micro action after seconds</label><input id="idleMicroDelay" type="number" min="10" max="3600" step="5" value="120"></div><div><label>Micro action interval seconds</label><input id="idleMicroInterval" type="number" min="20" max="7200" step="5" value="90"></div></div>
        <div class="row"><div><label>First bored comment after seconds</label><input id="idleCommentDelay" type="number" min="30" max="7200" step="10" value="300"></div><div><label>Minimum comment interval seconds</label><input id="idleCommentInterval" type="number" min="60" max="7200" step="10" value="600"></div></div>
        <div class="row"><div><label>Internet curiosity after seconds</label><input id="idleCuriosityDelay" type="number" min="60" max="10800" step="30" value="900"></div><div><label>Curiosity interval seconds</label><input id="idleCuriosityInterval" type="number" min="300" max="21600" step="30" value="1800"></div></div>
        <div class="row"><div><label>Sleep after seconds</label><input id="idleSleepAfter" type="number" min="60" max="43200" step="30" value="1800"></div><div><label>Eye colour</label><input id="idleEyeColour" value="blue"></div></div>
        <div class="row"><div><label>Head yaw range deg</label><input id="idleHeadYaw" type="number" min="0" max="30" step="1" value="8"></div><div><label>Head pitch range deg</label><input id="idleHeadPitch" type="number" min="0" max="20" step="1" value="4"></div><div><label>Eye brightness</label><input id="idleEyeBrightness" type="number" min="0" max="1" step="0.01" value="0.14"></div></div>
        <label>Bored phrases, one per line</label><textarea id="idlePhrases" placeholder="Still here.&#10;Tiny systems check complete."></textarea>
        <label>Optional Brain App curiosity prompt</label><textarea id="idleCuriosityPrompt" placeholder="Leave blank to use the default short autonomous fact prompt."></textarea>
        <div class="buttons"><button class="good" onclick="saveIdleLifeSettings()">Save Idle Life</button><button onclick="testIdleLifePhrase()">Test Bored Phrase</button><button onclick="regenerateLocalVoiceCues(this)">Regenerate Voice Cues</button></div>
        <div id="idleLifeStatus" class="status-line">Idle-life status not loaded yet.</div>
        <pre id="idleLifeRuntime" style="margin-top:8px; min-height:80px; max-height:220px; overflow:auto;">No idle-life runtime yet.</pre>
      </section>
    </div>

    <div class="page" data-page="context">
      <section>
        <h2>Manual Sensor / Camera Context</h2>
        <div class="small">These values are added to the body-state packet for testing before every real sensor is live.</div>
        <div class="row"><div><label>Pitch deg</label><input id="pitch" placeholder="0.0"></div><div><label>Roll deg</label><input id="roll" placeholder="0.0"></div></div>
        <div class="row"><div><label>Yaw deg</label><input id="yaw" placeholder="0.0"></div><div><label>Front distance mm</label><input id="frontDistance" placeholder="e.g. 800"></div></div>
        <div class="row"><div><label>Battery V</label><input id="battery" placeholder="e.g. 12.1"></div><div><label>Location label</label><input id="locationLabel" placeholder="workbench / office / lab"></div></div>
        <label>Manual visual observation</label><textarea id="visualContext" placeholder="Example: BX1 is on the desk. John is in front of the robot. No obstacle nearby."></textarea>
        <div class="buttons"><button onclick="saveManualState()">Save Manual Context</button><button onclick="clearManualState()">Clear Manual Context</button><button onclick="navigatePage('chat')">Go To Chat</button></div>
      </section>
    </div>

    <div class="page" data-page="actions"><div class="grid"><section><h2>Manual Robot Actions</h2><div class="small">These send logical yaw/pitch/roll actions through the same bounded path as Brain App actions. Pitch and roll are mixed into the two physical gimbal servos by the MCU.</div><div class="buttons"><button class="danger" onclick="manualAction({type:'stop_motion', args:{}})">Stop Motion</button><button onclick="manualAction({type:'set_head_pose', args:{pitch_deg:0, roll_deg:0, yaw_deg:0}})">Head Centre</button><button onclick="manualAction({type:'set_head_pose', args:{pitch_deg:0, roll_deg:0, yaw_deg:-20}})">Look Left</button><button onclick="manualAction({type:'set_head_pose', args:{pitch_deg:0, roll_deg:0, yaw_deg:20}})">Look Right</button><button onclick="manualAction({type:'set_head_pose', args:{pitch_deg:-3, roll_deg:0, yaw_deg:0}})">Look Up 3°</button><button onclick="manualAction({type:'set_head_pose', args:{pitch_deg:3, roll_deg:0, yaw_deg:0}})">Look Down 3°</button><button onclick="manualAction({type:'set_head_pose', args:{pitch_deg:0, roll_deg:-3, yaw_deg:0}})">Tilt Left 3°</button><button onclick="manualAction({type:'set_head_pose', args:{pitch_deg:0, roll_deg:3, yaw_deg:0}})">Tilt Right 3°</button><button onclick="manualAction({type:'set_led_zone', args:{zone:'left_eye', secondary_zone:'right_eye', colour:'#0088ff', mode:'solid'}})">Eyes Blue</button><button onclick="navigatePage('lighting')">LED State Colours</button><button onclick="manualAction({type:'play_tone', args:{tone:'confirm'}})">Play Tone</button></div></section><section><h2>Service Commands</h2><div class="buttons"><button onclick="serviceCommand('/status')">Refresh Status</button><button onclick="serviceCommand('/frame')">Send Camera Frame</button><button onclick="serviceCommand('/vision Describe what you can see.')">Vision Test</button><button class="danger" onclick="serviceCommand('/quit')">Stop Service</button></div></section></div></div>

    

    <div class="page" data-page="hardware">
      <div class="grid">
        <section>
          <h2>Hardware Registry / IO Map</h2>
          <div class="small">BX1 v10.22.1 models the real neck linkage: one yaw servo rotates the head, while two physical push-pull gimbal servos are mixed together to produce logical pitch and roll. LED zones share one addressable bus and can use any RGB colour.</div>
          <h2 style="font-size:14px;margin-top:12px;">Addressable LED bus</h2>
          <div class="row">
            <label><input id="hwLedBusEnabled" type="checkbox" checked> Enable main NeoPixel/WS2812 bus</label>
            <div><label>Data pin</label><select id="hwLedBusPin" class="pin-select"><option value="-1">Disabled / not assigned</option><option value="2">D2</option><option value="3">D3</option><option value="4">D4</option><option value="5">D5</option><option value="6">D6</option><option value="7">D7</option><option value="8">D8</option><option value="9">D9</option><option value="10">D10</option><option value="11">D11</option><option value="12">D12</option><option value="13">D13</option><option value="14">A0 / D14</option><option value="15">A1 / D15</option><option value="16">A2 / D16</option><option value="17">A3 / D17</option><option value="18">A4 / D18</option><option value="19">A5 / D19</option></select></div>
          </div>
          <div class="row">
            <div><label>Total pixels on chain</label><input id="hwLedBusCount" type="number" min="1" max="500" value="100"></div>
            <div><label>Global brightness limit</label><input id="hwLedBusBrightness" type="number" min="0" max="1" step="0.05" value="0.20"></div>
          </div>
          <div class="buttons"><button class="good" onclick="presetBx1LedPlan(this)">BX1 LED plan: D3, mouth=1, eyes=2/3</button><button onclick="navigatePage('lighting')">Edit state colours</button><button onclick="testHardware('all_leds',null,'off',this)">LEDs Off</button></div>

          <h2 style="font-size:14px;margin-top:16px;">Direct LED paint / diagnostics</h2>
          <div class="small">Set any individual LED or address range to any RGB colour. Human numbering is used: LED 1 is the first pixel.</div>
          <div class="row">
            <div><label>Start LED</label><input id="ledPaintStart" type="number" min="1" max="500" value="1"></div>
            <div><label>End LED</label><input id="ledPaintEnd" type="number" min="1" max="500" value="1"></div>
          </div>
          <div class="row">
            <div><label>Colour</label><input id="ledPaintColour" type="color" value="#00ffff"></div>
            <div><label>Brightness</label><input id="ledPaintBrightness" type="range" min="0" max="1" step="0.01" value="0.25" oninput="ledPaintBrightnessText.value=this.value"></div>
            <div><label>Brightness value</label><input id="ledPaintBrightnessText" type="number" min="0" max="1" step="0.01" value="0.25" oninput="ledPaintBrightness.value=this.value"></div>
          </div>
          <div class="buttons"><button class="good" onclick="paintLedRange(this)">Set LED/range colour</button><button onclick="paintLedPreset(1,1,'#ff0000',0.25,this)">LED 1 red</button><button onclick="paintLedPreset(1,1,'#00ff00',0.25,this)">LED 1 green</button><button onclick="paintLedPreset(1,1,'#0000ff',0.25,this)">LED 1 blue</button><button onclick="paintLedPreset(1,100,'#000000',0.0,this)">All off</button></div>

          <h2 style="font-size:14px;margin-top:16px;">LED zones, human LED addresses</h2>
          <div class="small">Choose the default colour for each zone with the colour picker. Runtime state colours are configured separately on the LED States page.</div>
          <div style="overflow:auto;"><table class="compact-table">
            <thead><tr><th>Use</th><th>Zone</th><th>Start LED</th><th>End LED</th><th>Default colour</th><th>Brightness</th></tr></thead>
            <tbody>
              <tr><td><input id="zoneMouthEnabled" type="checkbox"></td><td>Mouth</td><td><input id="zoneMouthStart" type="number" min="1" value="1"></td><td><input id="zoneMouthEnd" type="number" min="1" value="1"></td><td><input id="zoneMouthColour" type="color" value="#00ffff"></td><td><input id="zoneMouthBrightness" type="number" min="0" max="1" step="0.05" value="0.20"></td></tr>
              <tr><td><input id="zoneLeftEyeEnabled" type="checkbox"></td><td>Left eye</td><td><input id="zoneLeftEyeStart" type="number" min="1" value="2"></td><td><input id="zoneLeftEyeEnd" type="number" min="1" value="2"></td><td><input id="zoneLeftEyeColour" type="color" value="#0088ff"></td><td><input id="zoneLeftEyeBrightness" type="number" min="0" max="1" step="0.05" value="0.25"></td></tr>
              <tr><td><input id="zoneRightEyeEnabled" type="checkbox"></td><td>Right eye</td><td><input id="zoneRightEyeStart" type="number" min="1" value="3"></td><td><input id="zoneRightEyeEnd" type="number" min="1" value="3"></td><td><input id="zoneRightEyeColour" type="color" value="#0088ff"></td><td><input id="zoneRightEyeBrightness" type="number" min="0" max="1" step="0.05" value="0.25"></td></tr>
              <tr><td><input id="zoneChestEnabled" type="checkbox"></td><td>Chest/status ring</td><td><input id="zoneChestStart" type="number" min="1" value="4"></td><td><input id="zoneChestEnd" type="number" min="1" value="19"></td><td><input id="zoneChestColour" type="color" value="#00ffff"></td><td><input id="zoneChestBrightness" type="number" min="0" max="1" step="0.05" value="0.20"></td></tr>
              <tr><td><input id="zoneStatusEnabled" type="checkbox"></td><td>Status strip</td><td><input id="zoneStatusStart" type="number" min="1" value="20"></td><td><input id="zoneStatusEnd" type="number" min="1" value="29"></td><td><input id="zoneStatusColour" type="color" value="#ff9900"></td><td><input id="zoneStatusBrightness" type="number" min="0" max="1" step="0.05" value="0.20"></td></tr>
            </tbody>
          </table></div>

          <h2 style="font-size:14px;margin-top:16px;">Physical head servos</h2>
          <div class="small">Yaw is independent. The left and right gimbal servos are the two red horn/linkage servos and are mixed to create both up/down pitch and left/right roll. Servo degree values are offsets from the 1500 µs neutral position, so configured min/max values are real movement limits.</div>
          <div style="overflow:auto;"><table class="compact-table">
            <thead><tr><th>Use</th><th>Physical servo</th><th>Pin</th><th>Min °</th><th>Home °</th><th>Max °</th><th>Invert</th></tr></thead>
            <tbody>
              <tr><td><input id="hwHeadYawEnabled" type="checkbox"></td><td>Yaw / head rotation</td><td><select id="hwHeadYawPin" class="pin-select"><option value="-1">Disabled / not assigned</option><option value="2">D2</option><option value="3">D3</option><option value="4">D4</option><option value="5">D5</option><option value="6">D6</option><option value="7">D7</option><option value="8">D8</option><option value="9">D9</option><option value="10">D10</option><option value="11">D11</option><option value="12">D12</option><option value="13">D13</option><option value="14">A0 / D14</option><option value="15">A1 / D15</option><option value="16">A2 / D16</option><option value="17">A3 / D17</option><option value="18">A4 / D18</option><option value="19">A5 / D19</option></select></td><td><input id="hwHeadYawMin" type="number" value="-20"></td><td><input id="hwHeadYawHome" type="number" value="0"></td><td><input id="hwHeadYawMax" type="number" value="20"></td><td><input id="hwHeadYawInvert" type="checkbox"></td></tr>
              <tr><td><input id="hwHeadGimbalLeftEnabled" type="checkbox"></td><td>Left push-pull gimbal</td><td><select id="hwHeadGimbalLeftPin" class="pin-select"><option value="-1">Disabled / not assigned</option><option value="2">D2</option><option value="3">D3</option><option value="4">D4</option><option value="5">D5</option><option value="6">D6</option><option value="7">D7</option><option value="8">D8</option><option value="9">D9</option><option value="10">D10</option><option value="11">D11</option><option value="12">D12</option><option value="13">D13</option><option value="14">A0 / D14</option><option value="15">A1 / D15</option><option value="16">A2 / D16</option><option value="17">A3 / D17</option><option value="18">A4 / D18</option><option value="19">A5 / D19</option></select></td><td><input id="hwHeadGimbalLeftMin" type="number" value="-20"></td><td><input id="hwHeadGimbalLeftHome" type="number" value="0"></td><td><input id="hwHeadGimbalLeftMax" type="number" value="20"></td><td><input id="hwHeadGimbalLeftInvert" type="checkbox"></td></tr>
              <tr><td><input id="hwHeadGimbalRightEnabled" type="checkbox"></td><td>Right push-pull gimbal</td><td><select id="hwHeadGimbalRightPin" class="pin-select"><option value="-1">Disabled / not assigned</option><option value="2">D2</option><option value="3">D3</option><option value="4">D4</option><option value="5">D5</option><option value="6">D6</option><option value="7">D7</option><option value="8">D8</option><option value="9">D9</option><option value="10">D10</option><option value="11">D11</option><option value="12">D12</option><option value="13">D13</option><option value="14">A0 / D14</option><option value="15">A1 / D15</option><option value="16">A2 / D16</option><option value="17">A3 / D17</option><option value="18">A4 / D18</option><option value="19">A5 / D19</option></select></td><td><input id="hwHeadGimbalRightMin" type="number" value="-20"></td><td><input id="hwHeadGimbalRightHome" type="number" value="0"></td><td><input id="hwHeadGimbalRightMax" type="number" value="20"></td><td><input id="hwHeadGimbalRightInvert" type="checkbox"></td></tr>
            </tbody>
          </table></div>

          <h2 style="font-size:14px;margin-top:16px;">Logical pitch/roll gimbal mixer</h2>
          <div class="mixer-diagram"><b>Logical command → physical servos</b><br>Left target = left home + pitch × gain × sign + roll × gain × sign<br>Right target = right home + pitch × gain × sign + roll × gain × sign<br><span class="small">The sign controls are deliberately configurable because linkage geometry and servo mounting can reverse either contribution.</span></div>
          <div class="mixer-grid">
            <div><label>Pitch min / home / max °</label><div class="row"><input id="hwPitchMin" type="number" value="-10"><input id="hwPitchHome" type="number" value="0"><input id="hwPitchMax" type="number" value="10"></div></div>
            <div><label>Roll min / home / max °</label><div class="row"><input id="hwRollMin" type="number" value="-10"><input id="hwRollHome" type="number" value="0"><input id="hwRollMax" type="number" value="10"></div></div>
            <div><label>Pitch gain</label><input id="hwPitchGain" type="number" min="0.05" max="5" step="0.05" value="1.0"><label>Roll gain</label><input id="hwRollGain" type="number" min="0.05" max="5" step="0.05" value="1.0"></div>
            <div><label>Left pitch sign</label><select id="hwLeftPitchSign"><option value="1">+1</option><option value="-1">−1</option></select><label>Right pitch sign</label><select id="hwRightPitchSign"><option value="-1">−1</option><option value="1">+1</option></select></div>
            <div><label>Left roll sign</label><select id="hwLeftRollSign"><option value="1">+1</option><option value="-1">−1</option></select></div>
            <div><label>Right roll sign</label><select id="hwRightRollSign"><option value="1">+1</option><option value="-1">−1</option></select></div>
          </div>
          <div class="bridge-banner" style="margin-top:10px;">Calibration safety: begin with both gimbal servos detached from the rods or use very small ±3° logical commands. Verify each servo home and direction before increasing travel.</div>

          <h2 style="font-size:14px;margin-top:16px;">Sensors and future drive bus</h2>
          <div class="row"><label><input id="hwModulinoMovementEnabled" type="checkbox" checked> Modulino Movement IMU on Qwiic/I2C</label><div><label>IMU I2C address</label><input id="hwModulinoAddress" value="0x6A"></div></div>
          <div class="row"><label><input id="hwRs485Enabled" type="checkbox"> Future RS485 closed-loop wheel steppers</label><div><label>RS485 baud</label><input id="hwRs485Baud" type="number" value="115200"></div></div>
          <div class="row"><div><label>Left motor ID</label><input id="hwRs485LeftId" type="number" value="1"></div><div><label>Right motor ID</label><input id="hwRs485RightId" type="number" value="2"></div></div>
          <div class="buttons"><button class="good" onclick="saveHardwareSettings(this)">Save Hardware Registry</button><button onclick="applyHardwareToMcu(this)">Apply Registry to MCU</button><button onclick="refresh(this)">Refresh</button></div>
          <div id="hardwareStatus" class="status-line"></div>
          <div id="hardwareBridgeBanner" class="bridge-banner">Hardware commands have not been tested yet. Save the registry first, then use Apply or a bench-test button.</div>
          <div id="hardwareCommandHistory" class="cmd-history">Command feedback will appear here.</div>
        </section>
        <section>
          <h2>Safe Gimbal Bench Test / Pin Guide</h2>
          <div class="buttons"><button onclick="testHardware('center',null,null,this)">Centre Head</button><button onclick="testHardware('yaw',-10,null,this)">Yaw Left</button><button onclick="testHardware('yaw',10,null,this)">Yaw Right</button><button onclick="testHardware('pitch',-3,null,this)">Pitch Up 3°</button><button onclick="testHardware('pitch',3,null,this)">Pitch Down 3°</button><button onclick="testHardware('roll',-3,null,this)">Tilt Left 3°</button><button onclick="testHardware('roll',3,null,this)">Tilt Right 3°</button><button class="good" onclick="testHardware('mouth_speech_test',null,null,this)">Test Talking Mouth LED</button></div>
          <div id="headMixerLiveStatus" class="status-line">Waiting for MCU head mixer status...</div>
          <div class="pin-guide"><div class="uno-board"><h2>Arduino UNO Sensor Shield — v10.22.1 mapping</h2><div class="small">NeoPixel DIN → D3/S. Example servo allocation: D5 yaw, D6 left gimbal, D9 right gimbal. Use a suitable external servo supply and common ground.</div><div class="pin-row"><span>D2</span><span class="active">D3 LED BUS</span><span>D4</span><span>D5 YAW</span><span>D6 GIMBAL L</span><span>D7</span><span>D8</span><span>D9 GIMBAL R</span><span>D10</span><span>D11</span></div><div class="small" style="color:var(--warn);margin-top:10px;">Do not share D3 with a servo. For 100 LEDs use a separate 5 V supply with common ground.</div></div></div>
          <h2 style="margin-top:16px;">Modulino Movement live view</h2>
          <div class="small">The 3D view follows logical pitch/roll/yaw body telemetry. The gimbal mixer converts logical pitch and roll into the two physical side-servo positions.</div>
          <div class="movement-grid"><div class="imu-stage"><div id="imuCube" class="imu-cube"><div class="imu-face imu-front">BX1</div><div class="imu-face imu-back">BACK</div><div class="imu-face imu-left">L</div><div class="imu-face imu-right">R</div><div class="imu-face imu-top">TOP</div><div class="imu-face imu-bottom">BOT</div></div><div class="imu-axis">Pitch = nose up/down<br>Roll = tilt left/right<br>Yaw = rotation</div></div><div><div class="imu-readouts"><div class="imu-readout">Pitch<strong id="imuPitchVal">--°</strong></div><div class="imu-readout">Roll<strong id="imuRollVal">--°</strong></div><div class="imu-readout">Yaw<strong id="imuYawVal">--°</strong></div></div><div class="mini-card"><div id="imuStatusText" class="small">Waiting for body telemetry...</div></div><div class="buttons"><button onclick="refresh(this)">Refresh IMU View</button><button onclick="navigatePage('telemetry')">Open Raw Telemetry</button><button onclick="navigatePage('context')">Manual Test Values</button></div></div></div>
          <pre id="hardwareJson">Hardware registry not loaded yet.</pre>
        </section>
      </div>
    </div>

    <div class="page" data-page="lighting">
      <section>
        <h2>LED State Colours</h2>
        <div class="small">Set the colour and brightness of every LED zone for each robot state. Talking, listening, thinking, camera use, diagnostics, warnings and faults are applied automatically by the body client. The talking mouth still follows speech amplitude while using the selected talking colour.</div>
        <div class="buttons"><button class="good" onclick="saveLedStateSettings(this)">Save all state profiles</button><button onclick="applyLedState('idle',this)">Test Idle</button><button onclick="applyLedState('listening',this)">Test Listening</button><button onclick="applyLedState('thinking',this)">Test Thinking</button><button onclick="applyLedState('speaking',this)">Test Talking</button><button onclick="applyLedState('error',this)">Test Error</button><button onclick="refresh(this)">Reload</button></div>
        <div id="ledStateStatus" class="status-line">Loading LED state profiles...</div>
        <div style="overflow:auto;"><table class="compact-table led-state-table"><thead><tr><th>Enabled</th><th>State</th><th>Mouth<br><span class="small">colour / level</span></th><th>Left eye</th><th>Right eye</th><th>Chest</th><th>Status</th><th>Test</th></tr></thead><tbody id="ledStateTableBody"></tbody></table></div>
        <div class="bridge-banner" style="margin-top:12px;">Brightness is limited both by the value here and by the global LED bus brightness limit. Set a zone to black or brightness 0 to turn it off for that state.</div>
      </section>
    </div>

    <div class="page" data-page="doctor">
      <div class="grid wide-left">
        <section>
          <h2>BX1 Hardware Doctor</h2>
          <div class="small">Deterministic diagnostics for the MCU bridge, router service and firmware identity. Automatic repair is limited to restarting the approved <b>arduino-router</b> service. Firmware is never flashed automatically.</div>
          <div class="buttons"><button class="good" onclick="runHardwareDoctor(this)">Run Diagnosis</button><button onclick="recoverHardwareBridge(this)">Restart Bridge Safely</button><button onclick="generateDoctorSketch('bridge_probe',this)">Generate Bridge Probe</button><button onclick="generateDoctorSketch('heartbeat_probe',this)">Generate Heartbeat Probe</button><button onclick="generateDoctorSketch('imu_probe',this)">Generate IMU Probe</button></div>
          <div id="doctorSummary" class="status-line">Hardware Doctor has not reported yet.</div>
          <pre id="doctorView" style="max-height:520px;overflow:auto;">No diagnosis loaded.</pre>
        </section>
        <section>
          <h2>Safety Boundary</h2>
          <div class="bridge-banner">Allowed autonomously: observe status, classify faults, restart arduino-router after repeated failures, and generate fixed diagnostic sketches for review.</div>
          <div class="bridge-banner" style="margin-top:10px;border-color:#8a6a20;">Not allowed autonomously: compile generated code, flash firmware, energise drive motors, change servo limits, or run arbitrary shell commands.</div>
          <div class="small" style="margin-top:12px;">Generated sketches are saved under <code>runtime/doctor/generated_sketches</code> with a manifest showing approved=false, compiled=false and flashed=false.</div>
        </section>
      </div>
    </div>

<div class="page" data-page="performance"><section><h2>Performance / Latency / Hardware Load</h2><div class="small">Shows Brain API timings plus UNO Q Linux/process load. Use this to spot when the body controller is being overloaded by audio, camera, STT or web refresh.</div><div class="buttons"><button onclick="testBrainConnection()">Measure Brain Latency</button><button onclick="refresh()">Refresh</button></div><div id="systemLoadCards" class="mini-grid"></div><pre id="performanceView">Loading...</pre></section></div>

    <div class="page" data-page="telemetry"><section><h2>Live Body Telemetry JSON</h2><div class="buttons"><button onclick="serviceCommand('/status')">Refresh Status</button><button onclick="navigatePage('context')">Edit Manual Context</button></div><pre id="stateView">Loading...</pre></section></div>
  </main>
<script>
const BX1_WEB_UI_VERSION = "10.22.1-led-range-head-diagnostics";
const PAGES = ["connection","chat","identity","speech","microphone","cues","idle","context","actions","hardware","lighting","doctor","performance","telemetry"];
let brainSettingsLoaded=false, audioSettingsLoaded=false, identitySettingsLoaded=false, voiceSettingsLoaded=false, micSettingsLoaded=false, cueSettingsLoaded=false, idleLifeSettingsLoaded=false, themeSettingsLoaded=false, chatBridgeSettingsLoaded=false;
let hardwareFormDirty=false;
let ledStateFormDirty=false;
let lastMicSttText="";
function setActivePageFromPath(){ let page=window.location.pathname.replace(/^\//,"")||"chat"; if(!PAGES.includes(page)) page="chat"; document.querySelectorAll(".page").forEach(el=>el.classList.toggle("active", el.dataset.page===page)); document.querySelectorAll(".nav button").forEach(btn=>btn.classList.toggle("active", btn.dataset.page===page)); }
function navigatePage(page){ if(!PAGES.includes(page)) page="chat"; history.pushState(null,"","/"+page); setActivePageFromPath(); }
window.addEventListener("popstate", setActivePageFromPath);
async function api(path,payload=null){ const opts=payload===null?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}; const r=await fetch(path,opts); const text=await r.text(); let data; try{data=JSON.parse(text)}catch{data={ok:false,raw:text}} if(!r.ok) throw new Error(data.error||text||r.statusText); return data; }
function pill(label,value,cls=''){ return `<span class="pill ${cls}">${label}: ${htmlEscape(value)}</span>`; } function classifyBool(v){ return v===true?'good':(v===false?'bad':'warn'); } function safe(v){ return v===undefined||v===null||v===''?'-':String(v); }
function htmlEscape(s){ return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c])); }
function ensureSelectOption(selectEl,value,label){ if(!value) return; for(const opt of selectEl.options){ if(opt.value===value) return; } const opt=document.createElement('option'); opt.value=value; opt.textContent=label||value; selectEl.appendChild(opt); }
function percentValue(v,fallback){ if(v===undefined||v===null||v==='') return fallback; const n=Number(v); if(Number.isNaN(n)) return fallback; return n<=1?Math.round(n*100):Math.round(n); }
function deriveTtsUrlFromBrainUrl(brainUrl){ try{ const u=new URL((brainUrl||'').trim()); u.port='8091'; u.pathname=''; u.search=''; u.hash=''; return u.toString().replace(/\/$/,''); }catch{ return ''; } }
function brainTtsUrlLooksPlaceholder(v){ const s=String(v||'').trim().toLowerCase(); return !s || s.includes('your_pc') || s.includes('<brain_pc') || s==='http://' || s==='https://'; }

const PERSONALITY_SLIDERS = {
  humour:['personalityHumour','personalityHumourValue',35], honesty:['personalityHonesty','personalityHonestyValue',80], sarcasm:['personalitySarcasm','personalitySarcasmValue',20], timidity:['personalityTimidity','personalityTimidityValue',45], curiosity:['personalityCuriosity','personalityCuriosityValue',75], chattiness:['personalityChattiness','personalityChattinessValue',45], technical:['personalityTechnical','personalityTechnicalValue',75], obedience:['personalityObedience','personalityObedienceValue',55], confidence:['personalityConfidence','personalityConfidenceValue',65], energy:['personalityEnergy','personalityEnergyValue',55], empathy:['personalityEmpathy','personalityEmpathyValue',55], caution:['personalityCaution','personalityCautionValue',70]
};
const PERSONALITY_PRESETS = {
  tars:{humour:80,honesty:90,sarcasm:55,timidity:20,curiosity:75,chattiness:45,technical:80,obedience:35,confidence:85,energy:55,empathy:45,caution:65},
  engineering:{humour:25,honesty:90,sarcasm:10,timidity:20,curiosity:70,chattiness:30,technical:95,obedience:55,confidence:85,energy:45,empathy:40,caution:80},
  friendly:{humour:55,honesty:80,sarcasm:10,timidity:35,curiosity:80,chattiness:60,technical:65,obedience:60,confidence:70,energy:65,empathy:75,caution:70},
  quiet:{humour:15,honesty:85,sarcasm:5,timidity:45,curiosity:45,chattiness:15,technical:65,obedience:65,confidence:60,energy:25,empathy:55,caution:75},
  debug:{humour:5,honesty:95,sarcasm:0,timidity:10,curiosity:40,chattiness:20,technical:100,obedience:70,confidence:85,energy:40,empathy:30,caution:90}
};
function updatePersonalitySliderLabel(input){ const key=input.dataset.pkey; const item=PERSONALITY_SLIDERS[key]; if(item){ const label=document.getElementById(item[1]); if(label) label.textContent=input.value; } }
function setPersonalityControls(controls){ controls=controls||{}; for(const [key,item] of Object.entries(PERSONALITY_SLIDERS)){ const el=document.getElementById(item[0]); const label=document.getElementById(item[1]); const v=percentValue(controls[key], item[2]); if(el) el.value=v; if(label) label.textContent=v; } }
function getPersonalityControlsPayload(){ const out={}; for(const [key,item] of Object.entries(PERSONALITY_SLIDERS)){ const el=document.getElementById(item[0]); out[key]=Number(el?el.value:item[2]); } return out; }
function setPersonalityPreset(name){ const preset=PERSONALITY_PRESETS[name]; if(!preset) return; setPersonalityControls(preset); identityStatus.textContent='Personality presets now live in the desktop Robot Brain profile.'; }
function previewTheme(theme){ document.body.setAttribute('data-theme', theme||'dark-blue'); }
function setThemeFields(theme){ theme=theme||{}; const current=theme.ui_theme||'dark-blue'; previewTheme(current); if(!themeSettingsLoaded){ const sel=document.getElementById('uiTheme'); if(sel){ sel.innerHTML=''; for(const t of theme.themes||[{id:'dark-blue',label:'Dark Blue / BX1'}]){ const opt=document.createElement('option'); opt.value=t.id; opt.textContent=t.label||t.id; sel.appendChild(opt); } sel.value=current; } themeSettingsLoaded=true; } }
async function saveThemeSettings(){ try{ const data=await api('/api/theme_settings',{ui_theme:uiTheme.value}); themeSettingsLoaded=false; setThemeFields(data.theme||{}); addLocalNotice('Theme saved: '+uiTheme.value); }catch(e){ addLocalNotice('Theme save failed: '+e.message,'error'); } }
function setBrainFields(brain){ brain=brain||{}; const url=brain.base_url||''; const tts=brain.brain_tts_base_url||''; document.getElementById('currentBrainUrl').value=url||'not configured'; const ttsEl=document.getElementById('currentBrainTtsUrl'); if(ttsEl) ttsEl.value=tts||'not configured'; if(!brainSettingsLoaded){ document.getElementById('brainBaseUrl').value=url; document.getElementById('brainApiKey').value=''; try{ const parsed=new URL(url); document.getElementById('brainPort').value=parsed.port||'8765'; }catch{document.getElementById('brainPort').value='8765'} try{ const parsedTts=new URL(tts); document.getElementById('brainTtsPort').value=parsedTts.port||'8091'; }catch{ const p=document.getElementById('brainTtsPort'); if(p) p.value='8091'; } brainSettingsLoaded=true; } }
function setChatBridgeFields(chat){ chat=chat||{}; if(!chatBridgeSettingsLoaded){ if(document.getElementById('useWeb')) useWeb.checked=chat.use_web_for_robot_questions===true; if(document.getElementById('useMemory')) useMemory.checked=chat.use_memory!==false; if(document.getElementById('autoCamera')) autoCamera.checked=chat.auto_camera_on_vision_request!==false; chatBridgeSettingsLoaded=true; } }
async function saveChatBridgeSettings(){ const payload={use_web_for_robot_questions:useWeb.checked, use_memory:useMemory.checked, auto_camera_on_vision_request:autoCamera.checked}; mainVoiceStatus.textContent='Saving web/camera defaults...'; try{ const data=await api('/api/chat_settings',payload); chatBridgeSettingsLoaded=false; setChatBridgeFields(data.chat_bridge||{}); mainVoiceStatus.textContent='Saved. Internet requests will be routed through the laptop Brain App; camera prompts will auto-use vision.'; await refresh(); }catch(e){ mainVoiceStatus.textContent='Save failed: '+e.message; addLocalNotice('Chat bridge save failed: '+e.message,'error'); } }
function setBrainManagedIdentityControls(){
  const ids=['robotName','robotDisplayName','personalitySummary','personalityTone','personalityVerbosity','personalityStyleStrength','personalityRules'];
  ids.forEach(id=>{ const el=document.getElementById(id); if(el) el.disabled=true; });
  Object.values(PERSONALITY_SLIDERS).forEach(([sliderId])=>{ const el=document.getElementById(sliderId); if(el) el.disabled=true; });
}
function setIdentityFields(identity){ identity=identity||{}; const bodyName=identity.robot_id||identity.body_id||'Robot Body'; document.getElementById('robotNameTitle').textContent=bodyName; document.title=bodyName+' Body Client v10.22.1'; setBrainManagedIdentityControls(); if(!identitySettingsLoaded){ document.getElementById('robotId').value=identity.robot_id||identity.body_id||'BX1-BODY'; document.getElementById('robotName').value='Brain-managed'; document.getElementById('robotDisplayName').value='Brain-managed'; document.getElementById('wakeWords').value=(identity.wake_words||[]).join('\n'); document.getElementById('personalitySummary').value='Set per Robot Brain instance/profile.'; document.getElementById('personalityTone').value='Set per Robot Brain instance/profile.'; ensureSelectOption(document.getElementById('personalityVerbosity'), 'medium'); document.getElementById('personalityVerbosity').value='medium'; const controls={}; setPersonalityControls(controls); const strength=100; if(document.getElementById('personalityStyleStrength')) personalityStyleStrength.value=strength; if(document.getElementById('personalityStyleStrengthValue')) personalityStyleStrengthValue.textContent=strength; document.getElementById('personalityRules').value='Set in the desktop Robot Brain profile.'; document.getElementById('robotType').value=identity.robot_type||''; document.getElementById('robotLocation').value=identity.robot_location||''; const caps=identity.capabilities||{}; capMic.checked=!!caps.has_microphone; capSpeaker.checked=caps.has_speaker!==false; capCamera.checked=caps.has_camera!==false; capHeadServo.checked=caps.has_head_servo!==false; capDriveMotors.checked=!!caps.has_drive_motors; capLidar.checked=!!caps.has_lidar; identitySettingsLoaded=true; } }
function setVoiceFields(voice){ voice=voice||{}; if(!voiceSettingsLoaded){ document.getElementById('voiceEnabled').checked=voice.voice_enabled===true; document.getElementById('inputMode').value=voice.input_mode||'keyboard'; document.getElementById('voiceBackend').value=voice.voice_backend||'vosk'; document.getElementById('recordSeconds').value=voice.record_seconds??5; document.getElementById('sampleRate').value=voice.sample_rate??16000; document.getElementById('voskModelPath').value=voice.vosk_model_path||'models/vosk-model-small-en-us-0.15'; if(document.getElementById('mainVoiceEnabled')) mainVoiceEnabled.checked=voice.voice_enabled===true; if(document.getElementById('mainInputMode')){ ensureSelectOption(mainInputMode, voice.input_mode||'keyboard'); mainInputMode.value=voice.input_mode||'keyboard'; } voiceSettingsLoaded=true; } const status = voice.stt_ready ? 'STT ready.' : (voice.stt_error ? 'STT not ready: '+voice.stt_error : 'STT not started.'); document.getElementById('voiceStatus').textContent=status; if(document.getElementById('mainVoiceStatus') && mainVoiceStatus.textContent==='Main STT controls ready.') mainVoiceStatus.textContent=status; setVoiceIndicator(voice.runtime||{}); }
function populateMicDevices(devices,current){ const sel=document.getElementById('micDevice'); if(!sel) return; const existing=sel.value||current||'default'; sel.innerHTML=''; const base=document.createElement('option'); base.value='default'; base.textContent='default - ALSA default'; sel.appendChild(base); for(const d of devices||[]){ if(!d || !d.id) continue; if(d.id==='default' && sel.options.length>0) continue; const opt=document.createElement('option'); opt.value=d.id; opt.textContent=d.label||d.id; sel.appendChild(opt); } ensureSelectOption(sel,current,current); sel.value=current||existing||'default'; }
function populatePlaybackDevices(devices,current){ const sel=document.getElementById('micPlaybackDevice'); if(!sel) return; const existing=sel.value||current||'default'; sel.innerHTML=''; const base=document.createElement('option'); base.value='default'; base.textContent='default - ALSA default playback'; sel.appendChild(base); for(const d of devices||[]){ if(!d || !d.id) continue; if(d.id==='default' && sel.options.length>0) continue; const opt=document.createElement('option'); opt.value=d.id; opt.textContent=d.label||d.id; sel.appendChild(opt); } ensureSelectOption(sel,current,current); sel.value=current||existing||'default'; }
function setMicFields(mic){ mic=mic||{}; if(!micSettingsLoaded){ populateMicDevices(mic.devices||[], mic.mic_device||'default'); document.getElementById('micDeviceManual').value=mic.mic_device&&mic.mic_device!=='default'?mic.mic_device:''; document.getElementById('micCaptureVolume').value=mic.mic_capture_volume??70; micCaptureVolumeValue.textContent=document.getElementById('micCaptureVolume').value; document.getElementById('micCaptureControl').value=mic.mic_capture_control||'Capture'; document.getElementById('micSoftwareGain').value=mic.mic_software_gain_db??0; micSoftwareGainValue.textContent=document.getElementById('micSoftwareGain').value; document.getElementById('micNoiseGate').value=mic.mic_noise_gate_dbfs??-48; micNoiseGateValue.textContent=document.getElementById('micNoiseGate').value; document.getElementById('micSampleRate').value=mic.sample_rate??16000; document.getElementById('micRecordSeconds').value=mic.record_seconds??5; document.getElementById('audioFilterEnabled').checked=mic.audio_filter_enabled!==false; document.getElementById('micHighpassEnabled').checked=mic.audio_highpass_enabled!==false; document.getElementById('audioHighpassHz').value=mic.audio_highpass_hz??90; document.getElementById('audioNotchEnabled').checked=mic.audio_notch_enabled!==false; document.getElementById('audioNotchHz').value=mic.audio_notch_hz??50; document.getElementById('audioNotchHarmonics').value=mic.audio_notch_harmonics??2; document.getElementById('audioNoiseReductionEnabled').checked=mic.audio_noise_reduction_enabled!==false; document.getElementById('audioNoiseReductionStrength').value=mic.audio_noise_reduction_strength??0.45; document.getElementById('sttValidationEnabled').checked=mic.stt_validation_enabled!==false; document.getElementById('sttMinConfidence').value=mic.stt_min_confidence??0.45; document.getElementById('sttMinVoicedMs').value=mic.stt_min_voiced_ms??320; document.getElementById('sttMinLongestVoicedMs').value=mic.stt_min_longest_voiced_ms??160; document.getElementById('sttDuplicateWindow').value=mic.stt_duplicate_window_s??12; document.getElementById('sttEchoSimilarity').value=mic.stt_echo_similarity_threshold??0.78; if(document.getElementById('micPlaybackManual')) document.getElementById('micPlaybackManual').value=mic.mic_playback_device&&mic.mic_playback_device!=='default'?mic.mic_playback_device:''; micSettingsLoaded=true; } }
function getMicPayload(){ const manual=(micDeviceManual.value||'').trim(); return { mic_device: manual || micDevice.value || 'default', mic_capture_volume: micCaptureVolume.value, mic_capture_control: micCaptureControl.value.trim()||'Capture', mic_software_gain_db: micSoftwareGain.value, mic_noise_gate_dbfs: micNoiseGate.value, sample_rate: micSampleRate.value, record_seconds: micRecordSeconds.value, audio_filter_enabled:audioFilterEnabled.checked, audio_highpass_enabled:micHighpassEnabled.checked, mic_highpass_enabled:micHighpassEnabled.checked, audio_highpass_hz:audioHighpassHz.value, audio_notch_enabled:audioNotchEnabled.checked, audio_notch_hz:audioNotchHz.value, audio_notch_harmonics:audioNotchHarmonics.value, audio_noise_reduction_enabled:audioNoiseReductionEnabled.checked, audio_noise_reduction_strength:audioNoiseReductionStrength.value, stt_validation_enabled:sttValidationEnabled.checked, stt_min_confidence:sttMinConfidence.value, stt_min_voiced_ms:sttMinVoicedMs.value, stt_min_longest_voiced_ms:sttMinLongestVoicedMs.value, stt_duplicate_window_s:sttDuplicateWindow.value, stt_echo_similarity_threshold:sttEchoSimilarity.value }; }
function drawLiveSpectrum(level){ const canvas=document.getElementById('micLiveFftCanvas'); if(!canvas) return; const ctx=canvas.getContext('2d'), w=canvas.width, h=canvas.height; const raw=level.spectrum_raw||[], clean=level.spectrum_filtered||[]; ctx.clearRect(0,0,w,h); ctx.fillStyle='#06101a'; ctx.fillRect(0,0,w,h); ctx.strokeStyle='#24445d'; ctx.lineWidth=1; for(let i=0;i<=6;i++){ const y=i*h/6; ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(w,y);ctx.stroke(); } function line(arr,colour){ if(!arr.length) return; ctx.strokeStyle=colour;ctx.lineWidth=2;ctx.beginPath(); arr.forEach((pt,i)=>{ const x=i*w/Math.max(1,arr.length-1); const db=Math.max(-100,Math.min(0,Number(pt.db??-100))); const y=h-(db+100)/100*h; if(i===0)ctx.moveTo(x,y);else ctx.lineTo(x,y); });ctx.stroke(); } line(raw,'#7f8c98'); line(clean,'#45d4ff'); ctx.fillStyle='#a9c7d9';ctx.font='12px sans-serif';ctx.fillText('0 dB',6,14);ctx.fillText('-100 dB',6,h-6); if(raw.length||clean.length){ const max=(clean.length?clean:raw).slice(-1)[0]; ctx.fillText('40 Hz → '+(max?max.hz:'?')+' Hz',w-150,h-6); } const legend=document.getElementById('micLiveFftLegend'); if(legend) legend.textContent=`Raw RMS ${level.raw_rms_dbfs??'-'} dBFS · Filtered RMS ${level.rms_dbfs??'-'} dBFS · grey=raw · cyan=filtered`; }

function updateMicLevelView(level){ level=level||{}; const rms=Number(level.rms_pct||0), peak=Number(level.peak_pct||0); micRmsBar.style.width=Math.max(0,Math.min(100,rms))+'%'; micPeakBar.style.width=Math.max(0,Math.min(100,peak))+'%'; micRmsText.textContent=(level.rms_dbfs??'-')+' dBFS filtered'; micPeakText.textContent=(level.peak_dbfs??'-')+' dBFS'; micRunningPill.className='pill '+(level.running?'good':'warn'); micRunningPill.textContent='running: '+(level.running?'yes':'no'); micActivePill.className='pill '+(level.active?'good':'warn'); micActivePill.textContent='voice: '+(level.active?'active':'quiet'); micClipPill.className='pill '+(level.clipped?'bad':'good'); micClipPill.textContent='clip: '+(level.clipped?'yes':'no'); micDevicePill.textContent='device: '+safe(level.device); drawLiveSpectrum(level); if(level.error){ micStatus.textContent='Mic error: '+level.error; } }
async function refreshMicDevices(){ micStatus.textContent='Refreshing microphone devices...'; try{ const data=await api('/api/mic_devices'); populateMicDevices(data.devices||[], micDevice.value||'default'); micDiagnostics.textContent=JSON.stringify(data,null,2); micStatus.textContent='Device list refreshed.'; }catch(e){ micStatus.textContent='Device refresh failed: '+e.message; } }
async function saveMicSettings(){ micStatus.textContent='Saving microphone settings...'; try{ const data=await api('/api/mic_settings',getMicPayload()); micSettingsLoaded=false; setMicFields(data.mic||{}); micDiagnostics.textContent=JSON.stringify(data,null,2); micStatus.textContent='Microphone settings saved.'; await refreshMicLevel(); }catch(e){ micStatus.textContent='Mic settings save failed: '+e.message; } }
async function startMicMonitor(){ micStatus.innerHTML='<span class="spinner"></span>Starting microphone meter...'; try{ await saveMicSettings(); const data=await api('/api/mic_monitor_start',{}); updateMicLevelView((data.level)||{}); micStatus.textContent=data.message||'Microphone meter running.'; }catch(e){ micStatus.textContent='Start meter failed: '+e.message; } }
async function stopMicMonitor(){ try{ const data=await api('/api/mic_monitor_stop',{}); updateMicLevelView((data.level)||{}); micStatus.textContent=data.message||'Microphone meter stopped.'; }catch(e){ micStatus.textContent='Stop meter failed: '+e.message; } }
async function refreshMicLevel(){ try{ const data=await api('/api/mic_level'); updateMicLevelView((data.level)||{}); }catch(e){ if(document.querySelector('.page[data-page="microphone"]').classList.contains('active')) micStatus.textContent='Level refresh failed: '+e.message; } }
function currentVoskModelPath(){ return (document.getElementById('voskModelPath') ? voskModelPath.value.trim() : '') || 'models/vosk-model-small-en-us-0.15'; }
function selectedPlaybackDevice(){ const manual=(document.getElementById('micPlaybackManual')?.value||'').trim(); return manual || (document.getElementById('micPlaybackDevice')?.value||'default'); }
function sampleSummary(info){ const a=(info&&info.analysis)||{}; if(!info||!info.exists) return 'No recorded WAV sample found yet.'; let msg=`Sample: ${a.duration_s??'?'} s, ${info.size_bytes??0} bytes, RMS ${a.rms_dbfs??'?'} dBFS, peak ${a.peak_dbfs??'?'} dBFS`; if(Number(a.peak_dbfs)<-35) msg+=' — very quiet, STT may hear silence.'; else if(Number(a.peak_dbfs)<-25) msg+=' — quiet, speak closer/louder or increase gain.'; else if(Number(a.peak_dbfs)>-3 || a.clipped) msg+=' — too hot/clipping, reduce gain.'; else msg+=' — level looks usable.'; return msg; }
function summariseRecordedLevel(a){ const rms=Number(a.rms_dbfs??-120); const peak=Number(a.peak_dbfs??-120); if(peak < -35) return `Recorded, but very quiet. RMS ${rms} dBFS, peak ${peak} dBFS. Raise capture/software gain or move closer.`; if(peak < -25) return `Recorded, but quiet. RMS ${rms} dBFS, peak ${peak} dBFS. Try louder speech or more gain.`; if(peak > -3 || a.clipped) return `Recorded, but too hot/clipping. RMS ${rms} dBFS, peak ${peak} dBFS. Lower gain.`; return `Recorded OK. RMS ${rms} dBFS, peak ${peak} dBFS.`; }
let micCountdownTimer=null;
function stopMicCountdown(){ if(micCountdownTimer){ clearInterval(micCountdownTimer); micCountdownTimer=null; } }
function startMicCountdown(seconds,label){ stopMicCountdown(); const total=Math.max(1,Number(seconds)||5); const started=Date.now(); const update=()=>{ const elapsed=(Date.now()-started)/1000; const remain=Math.max(0,total-elapsed); const pct=Math.min(100,Math.round((elapsed/total)*100)); micRecordStatus.innerHTML=`<span class="spinner"></span>${label}: ${remain.toFixed(1)} s remaining (${pct}%)`; }; update(); micCountdownTimer=setInterval(update,200); }
function setMicBusy(busy){ for(const id of ['micRecordButton','micRobotPlaybackButton','micSttButton']){ const el=document.getElementById(id); if(el) el.disabled=!!busy; } }
function dbToY(db,h,pad){ const lo=-80, hi=0; const v=Math.max(lo,Math.min(hi,Number(db))); return h-pad-((v-lo)/(hi-lo))*(h-2*pad); }
function drawChartFrame(ctx,w,h,title,yLabel){ ctx.clearRect(0,0,w,h); ctx.fillStyle='#050b11'; ctx.fillRect(0,0,w,h); ctx.strokeStyle='#1d3347'; ctx.lineWidth=1; const pad=34; for(let i=0;i<=4;i++){ const y=pad+i*(h-2*pad)/4; ctx.beginPath(); ctx.moveTo(pad,y); ctx.lineTo(w-10,y); ctx.stroke(); } ctx.fillStyle='#8fa5ba'; ctx.font='12px Segoe UI, Arial'; ctx.fillText(title,8,16); if(yLabel) ctx.fillText(yLabel,8,h-10); return pad; }
function drawWaveform(diag){ const c=document.getElementById('micWaveCanvas'); if(!c) return; const ctx=c.getContext('2d'), w=c.width, h=c.height, pad=34; drawChartFrame(ctx,w,h,'Amplitude vs time','±1'); const wf=(diag&&diag.waveform)||[]; if(!wf.length){ ctx.fillStyle='#8fa5ba'; ctx.fillText('No waveform data. Record a sample first.',44,70); return; } const dur=Number(diag.duration_s||wf[wf.length-1].t||1)||1; ctx.strokeStyle='#5fb3ff'; ctx.lineWidth=1.5; ctx.beginPath(); for(let i=0;i<wf.length;i++){ const x=pad+(Number(wf[i].t||0)/dur)*(w-pad-12); const y1=h/2-Number(wf[i].max||0)*(h/2-pad); const y2=h/2-Number(wf[i].min||0)*(h/2-pad); ctx.moveTo(x,y1); ctx.lineTo(x,y2); } ctx.stroke(); ctx.strokeStyle='#8fa5ba'; ctx.beginPath(); ctx.moveTo(pad,h/2); ctx.lineTo(w-12,h/2); ctx.stroke(); }
function drawLevelTimeline(diag){ const c=document.getElementById('micLevelCanvas'); if(!c) return; const ctx=c.getContext('2d'), w=c.width, h=c.height, pad=drawChartFrame(ctx,c.width,c.height,'RMS and peak dBFS over time','dBFS'); const tl=(diag&&diag.level_timeline)||[]; if(!tl.length){ ctx.fillStyle='#8fa5ba'; ctx.fillText('No level timeline yet.',44,70); return; } const dur=Number(diag.duration_s||tl[tl.length-1].t||1)||1; function line(key,colour){ ctx.strokeStyle=colour; ctx.lineWidth=2; ctx.beginPath(); for(let i=0;i<tl.length;i++){ const x=pad+(Number(tl[i].t||0)/dur)*(w-pad-12); const y=dbToY(tl[i][key],h,pad); if(i===0) ctx.moveTo(x,y); else ctx.lineTo(x,y); } ctx.stroke(); } line('peak_dbfs','#ffca3a'); line('rms_dbfs','#5fb3ff'); ctx.fillStyle='#cfe6ff'; ctx.fillText('blue RMS   yellow peak',pad,24); }
function drawSpectrum(diag){ const c=document.getElementById('micFftCanvas'); if(!c) return; const ctx=c.getContext('2d'), w=c.width, h=c.height, pad=drawChartFrame(ctx,c.width,c.height,'FFT frequency spectrum','dB'); const sp=(diag&&diag.spectrum)||[]; if(!sp.length){ ctx.fillStyle='#8fa5ba'; ctx.fillText('No FFT data yet.',44,70); return; } const maxHz=Math.max(...sp.map(p=>Number(p.hz||0)),1); const barW=Math.max(2,(w-pad-12)/sp.length); for(let i=0;i<sp.length;i++){ const x=pad+i*barW; const y=dbToY(sp[i].db,h,pad); const bh=h-pad-y; ctx.fillStyle='#31d07d'; ctx.fillRect(x,y,Math.max(1,barW-1),bh); } ctx.fillStyle='#cfe6ff'; ctx.fillText('0 Hz',pad,h-12); ctx.fillText(Math.round(maxHz)+' Hz',w-70,h-12); }
function renderAudioDiagnostics(info){ const diag=(info&&info.diagnostics)||{}; const a=(diag.analysis)||(info&&info.analysis)||{}; const link=document.getElementById('micDownloadLink'); const link2=document.getElementById('micDownloadLink2'); const href='/api/mic_sample.wav?download=1&cache='+Date.now(); if(link) link.href=href; if(link2) link2.href=href; drawWaveform(diag); drawLevelTimeline(diag); drawSpectrum(diag); const summary=document.getElementById('micAudioSummary'); const hints=document.getElementById('micAudioHints'); if(summary){ summary.textContent=info&&info.exists?`WAV: ${a.duration_s??'?'} s, ${info.size_bytes??0} bytes, sample rate ${a.sample_rate??'?'} Hz, RMS ${a.rms_dbfs??'?'} dBFS, peak ${a.peak_dbfs??'?'} dBFS, clipped: ${a.clipped?'yes':'no'}`:'No WAV sample found. Record a sample first.'; } if(hints){ const warnings=(diag.warnings||[]).slice(); if(!warnings.length && info&&info.exists) warnings.push('No obvious level fault detected. Use browser playback to confirm the WAV contains clean speech.'); hints.textContent=warnings.join('\n') || 'No hints yet.'; } }
async function refreshMicSampleInfo(){ try{ const data=await api('/api/mic_sample_info'); if(data.playback_devices) populatePlaybackDevices((data.playback_devices.devices||[]), selectedPlaybackDevice()); renderAudioDiagnostics(data); micDiagnostics.textContent=JSON.stringify(data,null,2); micRecordStatus.textContent=sampleSummary(data); return data; }catch(e){ micDiagnostics.textContent='Sample debug failed: '+e.message; micRecordStatus.textContent='Sample debug failed.'; return null; } }
async function recordMicSample(){ micDiagnostics.textContent='Preparing recording...'; micRecognisedText.value=''; setMicBusy(true); const seconds=Number(micRecordSeconds.value||5); try{ await saveMicSettings(); micRecordStatus.textContent='Stopping live meter while recording so the capture device is not shared...'; try{ await api('/api/mic_monitor_stop',{}); }catch{} startMicCountdown(seconds,'Recording now — speak clearly into the microphone'); const data=await api('/api/mic_record_test',{seconds:micRecordSeconds.value, mic_device:(micDeviceManual.value||micDevice.value||'default'), sample_rate:micSampleRate.value}); stopMicCountdown(); micDiagnostics.textContent=JSON.stringify(data,null,2); const a=(data.recording&&data.recording.analysis_gain_adjusted)||(data.recording&&data.recording.analysis)||{}; micRecordStatus.textContent=data.ok?('Recording complete. '+summariseRecordedLevel(a)):'Recording failed.'; micStatus.textContent=data.ok?'Recording complete.':'Recording failed.'; await loadMicSampleInBrowser(false); await refreshMicSampleInfo(); try{ await api('/api/mic_monitor_start',{}); }catch{} return !!data.ok; }catch(e){ stopMicCountdown(); micDiagnostics.textContent='Recording failed: '+e.message; micRecordStatus.textContent='Recording failed: '+e.message; micStatus.textContent='Recording failed.'; return false; }finally{ setMicBusy(false); } }
async function loadMicSampleInBrowser(playNow=false){ const audio=document.getElementById('micBrowserAudio'); if(!audio) return; const url='/api/mic_sample.wav?cache='+Date.now(); audio.src=url; audio.load(); micPlaybackStatus.textContent='Browser sample loaded from BX1. This plays through the browser device, not the robot speaker.'; try{ await refreshMicSampleInfo(); }catch{} if(playNow){ try{ await audio.play(); micPlaybackStatus.textContent='Playing recorded sample in browser.'; }catch(e){ micPlaybackStatus.textContent='Browser playback blocked or failed: '+e.message+' Press the audio play button manually.'; } } }
async function playMicSample(){ const dev=selectedPlaybackDevice(); const cap=(micDeviceManual.value||micDevice.value||'default').trim(); if(dev && cap && dev===cap && dev!=='default'){ micPlaybackStatus.textContent='That device is currently selected as the microphone/capture device, not a speaker output. Use 2B Play In Browser, or choose a real playback device.'; return; } micPlaybackStatus.innerHTML='<span class="spinner"></span>Playing sample on BX1 audio output...'; try{ const data=await api('/api/mic_playback_test',{playback_device:dev}); micDiagnostics.textContent=JSON.stringify(data,null,2); if(data.sample_info&&data.sample_info.playback_devices) populatePlaybackDevices((data.sample_info.playback_devices.devices||[]), selectedPlaybackDevice()); renderAudioDiagnostics((data.sample_info)||{}); micPlaybackStatus.textContent=data.ok?'BX1 playback command completed. If you heard nothing, try browser playback or select another ALSA playback device.':'BX1 playback failed. Use Play In Browser to confirm the WAV, then select a real speaker output.'; }catch(e){ micDiagnostics.textContent='Playback failed: '+e.message; micPlaybackStatus.textContent='Playback failed: '+e.message; } }
async function checkMicSttStatus(){ micSttStatus.innerHTML='<span class="spinner"></span>Checking Vosk/module/model/sample...'; try{ const data=await api('/api/mic_stt_status',{vosk_model_path:currentVoskModelPath()}); micDiagnostics.textContent=JSON.stringify(data,null,2); const s=data.status||{}; const bits=[]; bits.push(s.vosk_import_ok?'Vosk module: OK':'Vosk module: missing'); bits.push(s.model_exists?'model: OK':'model: missing'); bits.push(s.wav_exists?'sample: OK':'sample: missing'); if(s.wav_analysis&&s.wav_analysis.ok) bits.push(`sample peak: ${s.wav_analysis.peak_dbfs} dBFS`); micSttStatus.textContent=bits.join(' | ')+(s.error?(' | '+s.error):''); return !!(s.vosk_import_ok && s.model_exists && s.wav_exists); }catch(e){ micSttStatus.textContent='STT setup check failed: '+e.message; micDiagnostics.textContent='STT setup check failed: '+e.message; return false; } }
function noSpeechMessage(data){ const a=(data.sample_info&&data.sample_info.analysis)||(data.stt&&data.stt.analysis)||(data.status&&data.status.wav_analysis)||{}; let msg='[Vosk ran, but no speech was recognised.]\n'; if(a.ok){ msg+=`Recorded WAV: ${a.duration_s}s, RMS ${a.rms_dbfs} dBFS, peak ${a.peak_dbfs} dBFS.\n`; if(Number(a.peak_dbfs)<-30) msg+='The sample is still very quiet. Increase gain or speak closer.\n'; } msg+='Use “2B. Play In Browser” to verify the actual recorded WAV contains your voice. If the browser sample is silent, the wrong capture device is selected.'; return msg; }
async function runMicSttTest(){ micStatus.innerHTML='<span class="spinner"></span>Running Vosk STT on saved sample. Loading the model can take a few seconds...'; micRecognisedText.value=''; setMicBusy(true); try{ const ready=await checkMicSttStatus(); if(!ready){ micStatus.textContent='STT is not ready. See the setup status line.'; micRecognisedText.value=micSttStatus.textContent; return false; } const data=await api('/api/mic_stt_test',{vosk_model_path:currentVoskModelPath()}); micDiagnostics.textContent=JSON.stringify(data,null,2); lastMicSttText=((data.stt&&data.stt.text)||'').trim(); if(data.ok){ micRecognisedText.value=lastMicSttText || noSpeechMessage(data); micStatus.textContent=lastMicSttText?'STT complete.':'STT complete, but no speech recognised.'; return true; } const err=(data.stt&&data.stt.error)||'unknown error'; micRecognisedText.value='STT failed: '+err; micStatus.textContent='STT failed: '+err; return false; }catch(e){ micDiagnostics.textContent='STT failed: '+e.message; micRecognisedText.value='STT failed: '+e.message; micStatus.textContent='STT failed.'; return false; }finally{ setMicBusy(false); } }
async function recordAndRunMicStt(){ const ok=await recordMicSample(); if(!ok) return; await runMicSttTest(); }
function sendMicSttToChat(){ const text=(micRecognisedText.value||lastMicSttText||'').trim(); if(!text || text.startsWith('[') || text.startsWith('STT failed')){ micStatus.textContent='No valid recognised text to send.'; return; } message.value=text; navigatePage('chat'); sendText(); }
function setCueFields(cues){ cues=cues||{}; if(!cueSettingsLoaded){
  document.getElementById('thinkingCuesEnabled').checked=cues.thinking_cues_enabled!==false;
  document.getElementById('thinkingCueSpeak').checked=cues.thinking_cue_speak!==false;
  const vc=document.getElementById('voiceCommandImmediateCue'); if(vc) vc.checked=cues.voice_command_immediate_cue_enabled!==false;
  const lc=document.getElementById('localVoiceCueCacheEnabled'); if(lc) lc.checked=cues.local_voice_cue_cache_enabled!==false;
  const ef=document.getElementById('localCueFallbackEspeak'); if(ef) ef.checked=cues.local_cue_fallback_espeak_enabled!==false;
  const st=document.getElementById('sttPauseDuringTts'); if(st) st.checked=cues.stt_pause_during_tts!==false;
  const wake=document.getElementById('wakeVoiceAckEnabled'); if(wake) wake.checked=cues.wake_voice_ack_enabled!==false;
  const vfa=document.getElementById('voiceFeedbackAudioEnabled'); if(vfa) vfa.checked=cues.voice_feedback_audio_enabled!==false;
  const vfl=document.getElementById('voiceFeedbackLedEnabled'); if(vfl) vfl.checked=cues.voice_feedback_led_enabled!==false;
  const vft=document.getElementById('voiceFeedbackToneLevel'); if(vft) vft.value=cues.voice_feedback_tone_level??0.16;
  document.getElementById('thinkingCueDelay').value=cues.thinking_cue_delay_s??2;
  document.getElementById('thinkingCueRepeat').value=cues.thinking_cue_repeat_s??8;
  document.getElementById('thinkingCueMax').value=cues.thinking_cue_max_per_reply??1;
  const conv=document.getElementById('conversationFollowupWindow'); if(conv) conv.value=cues.conversation_followup_window_s??45;
  const wakeWin=document.getElementById('wakeCommandWindow'); if(wakeWin) wakeWin.value=cues.wake_command_window_s??12;
  const guard=document.getElementById('sttPostTtsGuard'); if(guard) guard.value=cues.stt_post_tts_guard_s??1.25;
  const wp=document.getElementById('wakeAckPhrase'); if(wp) wp.value=cues.wake_ack_phrase??'Yes John?';
  const sp=document.getElementById('sleepAckPhrase'); if(sp) sp.value=cues.sleep_ack_phrase??'Going quiet.';
  document.getElementById('thinkingCueList').value=(cues.thinking_cues||[]).join('\n');
  cueSettingsLoaded=true;
}
  const cache=document.getElementById('localVoiceCueStatus'); if(cache){ const lv=cues.local_voice_cues||{}; cache.textContent=JSON.stringify({enabled:lv.enabled, count:lv.count, expected_count:lv.expected_count, cache_dir:lv.cache_dir, generated_at:lv.generated_at, files:(lv.files||[]).map(f=>({key:f.key, exists:f.exists, size_bytes:f.size_bytes, text:f.text}))}, null, 2); }
}
function setIdleLifeFields(idle){ idle=idle||{}; const rt=idle.runtime||{}; if(!idleLifeSettingsLoaded){
  const setChecked=(id,val)=>{ const el=document.getElementById(id); if(el) el.checked=!!val; };
  const setVal=(id,val)=>{ const el=document.getElementById(id); if(el) el.value=val; };
  setChecked('idleLifeEnabled', idle.enabled!==false);
  setChecked('idleMicroActions', idle.micro_actions_enabled!==false);
  setChecked('idleSelfChatter', idle.self_chatter_enabled!==false);
  setChecked('idleInternetCuriosity', idle.internet_curiosity_enabled===true);
  setChecked('idleSleepAnnounce', idle.sleep_announce_enabled===true);
  setVal('idleMaxComments', idle.max_comments_per_hour??3);
  setVal('idleMicroDelay', idle.micro_action_delay_s??120);
  setVal('idleMicroInterval', idle.micro_action_interval_s??90);
  setVal('idleCommentDelay', idle.comment_delay_s??300);
  setVal('idleCommentInterval', idle.min_comment_interval_s??600);
  setVal('idleCuriosityDelay', idle.curiosity_delay_s??900);
  setVal('idleCuriosityInterval', idle.curiosity_interval_s??1800);
  setVal('idleSleepAfter', idle.sleep_after_s??1800);
  setVal('idleHeadYaw', idle.head_yaw_deg??8);
  setVal('idleHeadPitch', idle.head_pitch_deg??4);
  setVal('idleEyeColour', idle.eye_colour||'blue');
  setVal('idleEyeBrightness', idle.eye_brightness??0.14);
  setVal('idlePhrases', (idle.phrases||[]).join('\n'));
  setVal('idleCuriosityPrompt', idle.curiosity_prompt||'');
  idleLifeSettingsLoaded=true;
}
  const status=document.getElementById('idleLifeStatus');
  if(status){ status.textContent = `State: ${rt.state||'idle'} · idle ${rt.idle_seconds??0}s · comments/hour ${rt.comments_this_hour??0}` + (rt.conversation_active?` · conversation ${rt.conversation_remaining_s}s`: '') + (rt.sleeping?' · sleeping':''); }
  const out=document.getElementById('idleLifeRuntime'); if(out) out.textContent=JSON.stringify(rt,null,2);
}
function idleLifePayload(){ return {
  enabled:document.getElementById('idleLifeEnabled')?.checked,
  micro_actions_enabled:document.getElementById('idleMicroActions')?.checked,
  self_chatter_enabled:document.getElementById('idleSelfChatter')?.checked,
  internet_curiosity_enabled:document.getElementById('idleInternetCuriosity')?.checked,
  sleep_announce_enabled:document.getElementById('idleSleepAnnounce')?.checked,
  max_comments_per_hour:document.getElementById('idleMaxComments')?.value,
  micro_action_delay_s:document.getElementById('idleMicroDelay')?.value,
  micro_action_interval_s:document.getElementById('idleMicroInterval')?.value,
  comment_delay_s:document.getElementById('idleCommentDelay')?.value,
  min_comment_interval_s:document.getElementById('idleCommentInterval')?.value,
  curiosity_delay_s:document.getElementById('idleCuriosityDelay')?.value,
  curiosity_interval_s:document.getElementById('idleCuriosityInterval')?.value,
  sleep_after_s:document.getElementById('idleSleepAfter')?.value,
  head_yaw_deg:document.getElementById('idleHeadYaw')?.value,
  head_pitch_deg:document.getElementById('idleHeadPitch')?.value,
  eye_colour:document.getElementById('idleEyeColour')?.value,
  eye_brightness:document.getElementById('idleEyeBrightness')?.value,
  phrases:document.getElementById('idlePhrases')?.value,
  curiosity_prompt:document.getElementById('idleCuriosityPrompt')?.value
}; }
async function saveIdleLifeSettings(){ const status=document.getElementById('idleLifeStatus'); if(status) status.textContent='Saving idle-life settings...'; try{ const data=await api('/api/idle_life_settings', idleLifePayload()); idleLifeSettingsLoaded=false; setIdleLifeFields(data.idle_life||{}); if(status) status.textContent='Idle-life settings saved.'; await refresh(); }catch(e){ if(status) status.textContent='Idle-life save failed: '+e.message; } }
async function testIdleLifePhrase(){ const status=document.getElementById('idleLifeStatus'); if(status) status.textContent='Testing bored phrase...'; try{ const data=await api('/api/test_idle_life_phrase',{}); if(status) status.textContent='Played: '+(data.phrase||'idle phrase'); await refresh(); }catch(e){ if(status) status.textContent='Idle phrase test failed: '+e.message; } }
function setAudioFields(audio){ audio=audio||{}; document.getElementById('ttsEnabled').checked=audio.tts_enabled!==false; let backend=audio.tts_backend||'brain-tts'; if(backend==='elevenlabs') backend='brain-tts'; document.getElementById('ttsBackend').value=backend; ensureSelectOption(document.getElementById('ttsVoice'), audio.tts_voice||'en-gb+f3'); document.getElementById('ttsVoice').value=audio.tts_voice||'en-gb+f3'; ensureSelectOption(document.getElementById('ttsEdgeVoice'), audio.tts_edge_voice||'en-GB-SoniaNeural'); document.getElementById('ttsEdgeVoice').value=audio.tts_edge_voice||'en-GB-SoniaNeural'; document.getElementById('ttsRate').value=audio.tts_rate??155; ttsRateValue.textContent=document.getElementById('ttsRate').value; document.getElementById('ttsPitch').value=audio.tts_pitch??42; ttsPitchValue.textContent=document.getElementById('ttsPitch').value; document.getElementById('ttsVolume').value=audio.tts_volume??80; ttsVolumeValue.textContent=document.getElementById('ttsVolume').value; document.getElementById('ttsPlaybackDevice').value=audio.tts_playback_device||'default'; document.getElementById('brainTtsBaseUrl').value=audio.brain_tts_base_url||deriveTtsUrlFromBrainUrl((document.getElementById('brainBaseUrl')&&brainBaseUrl.value)||''); document.getElementById('brainTtsEngine').value=audio.brain_tts_engine||'chatterbox_turbo'; document.getElementById('brainTtsVoice').value=audio.brain_tts_voice||'chatterbox_bx1'; document.getElementById('brainTtsTimeout').value=audio.brain_tts_timeout_s??240; if(document.getElementById('brainTtsEndpoint')) brainTtsEndpoint.value=audio.brain_tts_endpoint||'/robot/speak'; if(document.getElementById('brainTtsStatusEndpoint')) brainTtsStatusEndpoint.value=audio.brain_tts_status_endpoint||'/robot/tts/status'; document.getElementById('ttsCommand').value=audio.tts_command||''; document.getElementById('ttsPiperModel').value=audio.tts_piper_model||'models/piper/en_GB-alan-medium.onnx'; document.getElementById('ttsChunkingEnabled').checked=audio.tts_chunking_enabled!==false; document.getElementById('ttsChunkMaxChars').value=audio.tts_chunk_max_chars??650; document.getElementById('ttsFallbackToEspeak').checked=audio.tts_fallback_to_espeak===true; syncTtsBackendHelp(); }
function syncTtsBackendHelp(){ const backend=document.getElementById('ttsBackend').value; const help=document.getElementById('ttsHelp'); if(backend==='piper') help.textContent='Piper is an offline natural voice option. It needs the piper binary and a local model on the UNO Q.'; else if(backend==='edge-tts') help.textContent='Edge TTS is now only a fallback/test option. The preferred production voice is Robot Brain / Chatterbox.'; else if(backend==='brain-tts') help.textContent='Robot Brain TTS uses the PC voice service, so BX1 speaks with the same Chatterbox voice as the Brain App. The TTS URL now follows the saved Brain App host automatically on port 8091; you should not need to type it separately.'; else if(backend==='custom') help.textContent='Custom command runs your command. Use {text} where the spoken text should be inserted.'; else help.textContent='espeak-ng is reliable and lightweight, but robotic. Use only as an emergency fallback.'; }
function getAudioPayload(){ const derived=deriveTtsUrlFromBrainUrl((document.getElementById('brainBaseUrl')&&brainBaseUrl.value)||''); const ttsUrl=brainTtsUrlLooksPlaceholder(brainTtsBaseUrl.value)?derived:brainTtsBaseUrl.value.trim(); return {tts_enabled:ttsEnabled.checked, tts_backend:ttsBackend.value, tts_voice:ttsVoice.value.trim(), tts_edge_voice:ttsEdgeVoice.value.trim(), tts_rate:ttsRate.value, tts_pitch:ttsPitch.value, tts_volume:ttsVolume.value, tts_playback_device:ttsPlaybackDevice.value.trim()||'default', brain_tts_base_url:ttsUrl, brain_tts_follow_brain_host:true, brain_tts_engine:brainTtsEngine.value.trim()||'chatterbox_turbo', brain_tts_voice:brainTtsVoice.value.trim()||'chatterbox_bx1', brain_tts_timeout_s:brainTtsTimeout.value, brain_tts_endpoint:(document.getElementById('brainTtsEndpoint')?brainTtsEndpoint.value.trim():'/robot/speak')||'/robot/speak', brain_tts_status_endpoint:(document.getElementById('brainTtsStatusEndpoint')?brainTtsStatusEndpoint.value.trim():'/robot/tts/status')||'/robot/tts/status', tts_command:ttsCommand.value.trim(), tts_piper_model:ttsPiperModel.value.trim(), tts_chunking_enabled:ttsChunkingEnabled.checked, tts_chunk_max_chars:ttsChunkMaxChars.value, tts_fallback_to_espeak:ttsFallbackToEspeak.checked}; }
async function saveAudioSettings(){ try{ const data=await api('/api/audio_settings',getAudioPayload()); audioSettingsLoaded=false; addLocalNotice('Speech settings saved.'); await refresh(); }catch(e){ addLocalNotice('Speech settings save failed: '+e.message,'error'); } }
async function testSpeech(){ ttsDiagnostics.textContent='Running speech test on the UNO Q...'; try{ const data=await api('/api/test_speech',{text:ttsTestText.value}); ttsDiagnostics.textContent=JSON.stringify(data.report||data,null,2); addLocalNotice(data.ok?'Speech test OK.':'Speech test problem. ', data.ok?'system':'error'); await refresh(); }catch(e){ ttsDiagnostics.textContent='Speech test failed: '+e.message; addLocalNotice('Speech test failed: '+e.message,'error'); } }
async function runTtsDiagnostics(){ ttsDiagnostics.textContent='Checking TTS setup...'; try{ const data=await api('/api/tts_diagnostics',{}); ttsDiagnostics.textContent=JSON.stringify(data.diagnostics||data,null,2); const problems=(data.diagnostics&&data.diagnostics.problems)||[]; addLocalNotice(problems.length?'TTS diagnostics found: '+problems.join('; '):'TTS diagnostics OK.', problems.length?'error':'system'); await refresh(); }catch(e){ ttsDiagnostics.textContent='Diagnostics failed: '+e.message; addLocalNotice('Diagnostics failed: '+e.message,'error'); } }
async function checkRobotBrainTts(){ ttsDiagnostics.textContent='Checking Robot Brain TTS bridge...'; try{ await api('/api/audio_settings',getAudioPayload()); const data=await api('/api/robot_brain_tts_status',{}); ttsDiagnostics.textContent=JSON.stringify(data,null,2); addLocalNotice(data.ok?'Robot Brain TTS bridge reachable.':'Robot Brain TTS bridge problem: '+(data.error||'not OK'), data.ok?'good':'bad'); await refresh(); }catch(e){ ttsDiagnostics.textContent='Robot Brain TTS check failed: '+e.message; addLocalNotice('Robot Brain TTS check failed: '+e.message,'error'); } }
function setSpeechPreset(mode){ if(mode==='brain'){ ttsBackend.value='brain-tts'; const derived=deriveTtsUrlFromBrainUrl((document.getElementById('brainBaseUrl')&&brainBaseUrl.value)||''); if(derived) brainTtsBaseUrl.value=derived; brainTtsEngine.value=brainTtsEngine.value||'chatterbox_turbo'; brainTtsVoice.value=brainTtsVoice.value||'chatterbox_bx1'; if(document.getElementById('brainTtsEndpoint')) brainTtsEndpoint.value='/robot/speak'; if(document.getElementById('brainTtsStatusEndpoint')) brainTtsStatusEndpoint.value='/robot/tts/status'; ttsVolume.value=80; ttsChunkingEnabled.checked=true; ttsChunkMaxChars.value=650; ttsFallbackToEspeak.checked=false; } else if(mode==='edge'){ ttsBackend.value='edge-tts'; ttsEdgeVoice.value='en-GB-SoniaNeural'; ttsVolume.value=75; ttsChunkingEnabled.checked=true; ttsChunkMaxChars.value=650; ttsFallbackToEspeak.checked=false; } else { ttsBackend.value='espeak-ng'; ttsVoice.value= mode==='soft'?'en-gb+f3':'en-gb'; ttsRate.value=mode==='soft'?145:165; ttsPitch.value=mode==='soft'?48:38; ttsVolume.value=mode==='soft'?65:85; } ttsRateValue.textContent=ttsRate.value; ttsPitchValue.textContent=ttsPitch.value; ttsVolumeValue.textContent=ttsVolume.value; syncTtsBackendHelp(); }
function getCapabilityPayload(){ return {has_microphone:capMic.checked, has_speaker:capSpeaker.checked, has_camera:capCamera.checked, has_head_servo:capHeadServo.checked, has_drive_motors:capDriveMotors.checked, has_lidar:capLidar.checked}; }
async function saveIdentitySettings(){ identityStatus.textContent='Saving generic body settings...'; try{ const data=await api('/api/identity_settings',{robot_id:robotId.value.trim(), wake_words:wakeWords.value, robot_type:robotType.value.trim(), robot_location:robotLocation.value.trim(), capabilities:getCapabilityPayload()}); identitySettingsLoaded=false; await refresh(); identityStatus.textContent='Saved body settings. Personality is managed by the Robot Brain.'; }catch(e){ identityStatus.textContent='Save failed: '+e.message; } }
async function saveVoiceSettings(){ voiceStatus.textContent='Saving STT settings...'; try{ const data=await api('/api/voice_settings',{voice_enabled:voiceEnabled.checked, input_mode:inputMode.value, voice_backend:voiceBackend.value, record_seconds:recordSeconds.value, sample_rate:sampleRate.value, vosk_model_path:voskModelPath.value.trim(), wake_words:wakeWords.value}); voiceSettingsLoaded=false; await refresh(); voiceStatus.textContent='Saved. '+((data.voice&&data.voice.stt_ready)?'STT ready.':'STT may need model/install check.'); }catch(e){ voiceStatus.textContent='Save failed: '+e.message; } }
async function saveMainVoiceSettings(){ mainVoiceStatus.textContent='Saving live STT settings...'; try{ const data=await api('/api/voice_settings',{voice_enabled:mainVoiceEnabled.checked, input_mode:mainInputMode.value, voice_backend:(document.getElementById('voiceBackend')?.value||'vosk'), record_seconds:(document.getElementById('recordSeconds')?.value||5), sample_rate:(document.getElementById('sampleRate')?.value||16000), vosk_model_path:(document.getElementById('voskModelPath')?.value||'models/vosk-model-small-en-us-0.15').trim(), wake_words:(document.getElementById('wakeWords')?.value||'')}); voiceSettingsLoaded=false; await refresh(); mainVoiceStatus.textContent='Saved. '+((data.voice&&data.voice.stt_ready)?'Live STT ready.':'STT may need model/install check.'); }catch(e){ mainVoiceStatus.textContent='Save failed: '+e.message; addLocalNotice('Main STT save failed: '+e.message,'error'); } }
async function listenOnce(send){ const status=mainVoiceStatus; status.innerHTML='<span class="spinner"></span>Recording and transcribing...'; try{ const data=await api('/api/stt_once',{send:!!send, use_web:useWeb.checked, use_memory:useMemory.checked, allow_vision:autoCamera.checked, seconds:(document.getElementById('recordSeconds')?.value||5), mic_device:(document.getElementById('micDeviceManual')?.value||document.getElementById('micDevice')?.value||'default'), sample_rate:(document.getElementById('sampleRate')?.value||16000), vosk_model_path:(document.getElementById('voskModelPath')?.value||'models/vosk-model-small-en-us-0.15')}); const text=data.text||''; if(!send && text){ message.value=text; status.textContent='Heard: '+text; } else if(send){ status.textContent=text?'Sent recognised speech: '+text:'No speech recognised.'; } else { status.textContent='No speech recognised.'; } await refresh(); }catch(e){ status.textContent='Listen failed: '+e.message; addLocalNotice('Listen failed: '+e.message,'error'); } }
async function saveThinkingCueSettings(){ thinkingCueStatus.textContent='Saving thinking cues...'; try{ await api('/api/thinking_cue_settings',{
  thinking_cues_enabled:thinkingCuesEnabled.checked, thinking_cue_speak:thinkingCueSpeak.checked,
  voice_command_immediate_cue_enabled:document.getElementById('voiceCommandImmediateCue')?.checked,
  local_voice_cue_cache_enabled:document.getElementById('localVoiceCueCacheEnabled')?.checked,
  local_cue_fallback_espeak_enabled:document.getElementById('localCueFallbackEspeak')?.checked,
  stt_pause_during_tts:document.getElementById('sttPauseDuringTts')?.checked,
  wake_voice_ack_enabled:document.getElementById('wakeVoiceAckEnabled')?.checked,
  voice_feedback_audio_enabled:document.getElementById('voiceFeedbackAudioEnabled')?.checked,
  voice_feedback_led_enabled:document.getElementById('voiceFeedbackLedEnabled')?.checked,
  voice_feedback_tone_level:document.getElementById('voiceFeedbackToneLevel')?.value,
  thinking_cue_delay_s:thinkingCueDelay.value, thinking_cue_repeat_s:thinkingCueRepeat.value, thinking_cue_max_per_reply:thinkingCueMax.value,
  conversation_followup_window_s:document.getElementById('conversationFollowupWindow')?.value,
  wake_command_window_s:document.getElementById('wakeCommandWindow')?.value,
  stt_post_tts_guard_s:document.getElementById('sttPostTtsGuard')?.value,
  wake_ack_phrase:document.getElementById('wakeAckPhrase')?.value, sleep_ack_phrase:document.getElementById('sleepAckPhrase')?.value,
  thinking_cues:thinkingCueList.value
}); cueSettingsLoaded=false; await refresh(); thinkingCueStatus.textContent='Thinking cues saved.'; }catch(e){ thinkingCueStatus.textContent='Save failed: '+e.message; } }
async function playThinkingCue(){ thinkingCueStatus.textContent='Playing a random cue...'; try{ const data=await api('/api/play_thinking_cue',{}); thinkingCueStatus.textContent='Played: '+data.cue+(data.spoken?'':' (cache missing or speech disabled)'); await refresh(); }catch(e){ thinkingCueStatus.textContent='Cue test failed: '+e.message; } }
async function regenerateLocalVoiceCues(btn){ if(btn) markButton(btn,'running','Generating...'); thinkingCueStatus.textContent='Generating Chatterbox cue WAVs on the Brain PC. This can take a while...'; try{ const data=await api('/api/regenerate_local_voice_cues',{max_items:25}); const ok=data.generated||0; const req=data.requested||0; thinkingCueStatus.textContent=`Generated ${ok}/${req} local voice cues.`; const cache=document.getElementById('localVoiceCueStatus'); if(cache) cache.textContent=JSON.stringify(data.status||data,null,2); cueSettingsLoaded=false; await refresh(); if(btn) markButton(btn, ok?'ok':'fail', ok?'Generated':'Failed'); }catch(e){ thinkingCueStatus.textContent='Cue generation failed: '+e.message; if(btn) markButton(btn,'fail','Failed'); } }
function addLocalNotice(message,kind='system'){ const el=chatlog; const div=document.createElement('div'); div.className='event '+kind; div.innerHTML=`<div class="meta">local · ${kind}</div><div class="body">${htmlEscape(message)}</div>`; el.prepend(div); }
async function saveBrainSettings(useBrowserPc){ brainConnectionResult.textContent=useBrowserPc?'Saving this browser PC as Brain + Voice host...':'Saving Brain App URL and matching voice host...'; try{ const data=await api('/api/brain_settings',{brain_base_url:brainBaseUrl.value.trim(), api_key:brainApiKey.value, brain_port:brainPort.value.trim()||'8765', brain_tts_port:(document.getElementById('brainTtsPort')?brainTtsPort.value.trim():'8091')||'8091', use_browser_client_ip:!!useBrowserPc, sync_tts_to_brain_host:true}); brainSettingsLoaded=false; audioSettingsLoaded=false; await refresh(); const apiUrl=data.brain&&data.brain.base_url?data.brain.base_url:'Brain URL updated'; const ttsUrl=(data.audio&&data.audio.brain_tts_base_url)||(data.brain&&data.brain.brain_tts_base_url)||''; brainConnectionResult.textContent='Saved API: '+apiUrl+(ttsUrl?' | Saved TTS: '+ttsUrl:''); }catch(e){ brainConnectionResult.textContent='Save failed: '+e.message; } }
async function testBrainConnection(){ brainConnectionResult.textContent='Testing Brain App connection...'; try{ const data=await api('/api/test_brain',{}); brainConnectionResult.textContent=data.ok?`Brain connection OK: ${data.base_url} (${data.latency_ms} ms)`:'Brain connection failed: '+data.error; await refresh(); }catch(e){ brainConnectionResult.textContent='Brain connection test failed: '+e.message; } }
function voiceStateText(state){ const map={disabled:'Voice disabled', idle:'Voice idle', starting:'Starting voice loop', listening:'Listening for wake word', recording:'Recording', transcribing:'Transcribing speech', heard:'Speech heard', ignored:'Heard but not woken', awake:'Robot awake', processing:'Awake and processing', speaking:'Robot speaking', asleep:'Sleep mode', paused:'Voice paused', rejected:'Input rejected by speech gate', error:'Voice error'}; return map[state]||String(state||'Voice state'); }
function setVoiceIndicator(runtime){ runtime=runtime||{}; const state=String(runtime.state||'idle'); const orb=document.getElementById('voiceWakeOrb'); const title=document.getElementById('voiceWakeTitle'); const detail=document.getElementById('voiceWakeDetail'); if(orb){ orb.className='voice-orb '+state; } if(title){ title.textContent=voiceStateText(state); } if(detail){ let bits=[]; if(runtime.label) bits.push(runtime.label); if(runtime.loop_active) bits.push('Loop active'); if(runtime.stt_ready===false && runtime.enabled) bits.push('STT not ready'+(runtime.stt_error?': '+runtime.stt_error:'')); if(runtime.updated_at) bits.push('Updated '+runtime.updated_at); detail.textContent=bits.join(' · ')||'No live voice status yet.'; } const heard=document.getElementById('voiceLastHeard'); const wake=document.getElementById('voiceLastWake'); const accepted=document.getElementById('voiceLastAccepted'); const words=document.getElementById('voiceWakeWords'); if(heard) heard.textContent=runtime.last_heard||'-'; if(wake) wake.textContent=(runtime.last_wake_word||'-')+(runtime.last_wake_at?' at '+runtime.last_wake_at:''); if(accepted) accepted.textContent=runtime.last_accepted||'-'; if(words) words.textContent=(runtime.wake_words||[]).slice(0,6).join(', ')||'-'; }
function renderLog(events){ chatlog.innerHTML=events.slice().reverse().map(ev=>`<div class="event ${htmlEscape(ev.kind||'event')}"><div class="meta">${htmlEscape(ev.timestamp||'')} · ${htmlEscape(ev.kind||'event')}</div><div class="body">${htmlEscape(ev.message||'')}</div></div>`).join(''); }
function loadCard(label,value,sub='',pct=null){ const p=Number(pct); const bar=Number.isFinite(p)?`<div class="meter"><span style="width:${Math.max(0,Math.min(100,p))}%"></span></div>`:''; return `<div class="mini-card"><strong>${htmlEscape(label)}</strong><br><span>${htmlEscape(value)}</span>${sub?`<div class="small">${htmlEscape(sub)}</div>`:''}${bar}</div>`; }
function renderPerformance(perf){ perf=perf||{}; const stateText=stateView&&stateView.textContent?stateView.textContent:''; let state={}; try{ state=JSON.parse(stateText)||{}; }catch{} const load=(state.system_load)||perf.system_load||{}; const cards=[]; if(load&&Object.keys(load).length){ cards.push(loadCard('CPU load', (load.cpu_percent_est??'-')+' %', '1m load '+(load.loadavg_1m??'-')+' on '+(load.cpu_cores??'?')+' core(s)', load.cpu_percent_est)); cards.push(loadCard('Memory', (load.memory_percent??'-')+' %', (load.memory_used_mb??'-')+' / '+(load.memory_total_mb??'-')+' MB', load.memory_percent)); cards.push(loadCard('Process RSS', (load.process_rss_mb??'-')+' MB', (load.process_threads??'-')+' thread(s)')); cards.push(loadCard('Temperature', (load.temperature_c??'-')+' °C')); cards.push(loadCard('Disk used', (load.disk_percent??'-')+' %', (load.disk_free_gb??'-')+' GB free', load.disk_percent)); cards.push(loadCard('Speech/STT gate', load.speech_output_active?'muted while speaking':'open', 'guard '+(load.stt_guard_remaining_s??0)+' s')); } const el=document.getElementById('systemLoadCards'); if(el) el.innerHTML=cards.join('')||'<div class="mini-card">No system load data yet. Refresh after telemetry updates.</div>'; performanceView.textContent=JSON.stringify(perf||{},null,2); }


function hwVal(id,def){ const el=document.getElementById(id); if(!el) return def; const v=String(el.value??'').trim(); return v===''?def:v; }
function hwNum(id,def){ const v=Number(hwVal(id,def)); return Number.isFinite(v)?v:def; }
function hwText(id,def){ return String(hwVal(id,def)).trim() || def; }
function hwChecked(id){ const el=document.getElementById(id); return !!(el&&el.checked); }
function setPinValue(id,value){ const el=document.getElementById(id); if(!el) return; const v=String(value??-1); if(el.tagName==='SELECT'){ let found=false; for(const opt of el.options){ if(opt.value===v){ found=true; break; } } if(!found){ const opt=document.createElement('option'); opt.value=v; opt.textContent='Custom pin '+v; el.appendChild(opt); } } el.value=v; }
function markHardwareDirty(){ hardwareFormDirty=true; const s=document.getElementById('hardwareStatus'); if(s && !s.textContent.includes('unsaved')) s.textContent='Hardware changes are unsaved. Press Save Hardware Registry, then Apply Registry to MCU.'; }
function setHardwareClean(){ hardwareFormDirty=false; }
function hardwareInputIds(){ return ['hwLedBusEnabled','hwLedBusPin','hwLedBusCount','hwLedBusBrightness','zoneMouthEnabled','zoneMouthStart','zoneMouthEnd','zoneMouthColour','zoneMouthBrightness','zoneLeftEyeEnabled','zoneLeftEyeStart','zoneLeftEyeEnd','zoneLeftEyeColour','zoneLeftEyeBrightness','zoneRightEyeEnabled','zoneRightEyeStart','zoneRightEyeEnd','zoneRightEyeColour','zoneRightEyeBrightness','zoneChestEnabled','zoneChestStart','zoneChestEnd','zoneChestColour','zoneChestBrightness','zoneStatusEnabled','zoneStatusStart','zoneStatusEnd','zoneStatusColour','zoneStatusBrightness','hwHeadYawEnabled','hwHeadYawPin','hwHeadYawMin','hwHeadYawHome','hwHeadYawMax','hwHeadYawInvert','hwHeadGimbalLeftEnabled','hwHeadGimbalLeftPin','hwHeadGimbalLeftMin','hwHeadGimbalLeftHome','hwHeadGimbalLeftMax','hwHeadGimbalLeftInvert','hwHeadGimbalRightEnabled','hwHeadGimbalRightPin','hwHeadGimbalRightMin','hwHeadGimbalRightHome','hwHeadGimbalRightMax','hwHeadGimbalRightInvert','hwPitchMin','hwPitchHome','hwPitchMax','hwRollMin','hwRollHome','hwRollMax','hwPitchGain','hwRollGain','hwLeftPitchSign','hwRightPitchSign','hwLeftRollSign','hwRightRollSign','hwModulinoMovementEnabled','hwModulinoAddress','hwRs485Enabled','hwRs485Baud','hwRs485LeftId','hwRs485RightId']; }
function attachHardwareDirtyHandlers(){ for(const id of hardwareInputIds()){ const el=document.getElementById(id); if(el && !el.dataset.hwDirtyHooked){ el.dataset.hwDirtyHooked='1'; el.addEventListener('input',markHardwareDirty); el.addEventListener('change',markHardwareDirty); } } }

function presetBx1LedPlan(btn){
  markButton(btn,'running','Setting plan...');
  if(!document.getElementById('hwLedBusPin')) return;
  hwLedBusEnabled.checked=true; setPinValue('hwLedBusPin',3); hwLedBusCount.value=100; hwLedBusBrightness.value=0.20;
  zoneMouthEnabled.checked=true; zoneMouthStart.value=1; zoneMouthEnd.value=1; zoneMouthColour.value='#00ffff'; zoneMouthBrightness.value=0.20;
  zoneLeftEyeEnabled.checked=true; zoneLeftEyeStart.value=2; zoneLeftEyeEnd.value=2; zoneLeftEyeColour.value='#0088ff'; zoneLeftEyeBrightness.value=0.25;
  zoneRightEyeEnabled.checked=true; zoneRightEyeStart.value=3; zoneRightEyeEnd.value=3; zoneRightEyeColour.value='#0088ff'; zoneRightEyeBrightness.value=0.25;
  zoneChestEnabled.checked=false; zoneChestStart.value=4; zoneChestEnd.value=19; zoneStatusEnabled.checked=false; zoneStatusStart.value=20; zoneStatusEnd.value=29;
  hardwareStatus.textContent='BX1 LED plan set locally: D3 bus, mouth LED 1, eyes LEDs 2 and 3. Press Save Hardware Registry.';
  pushHardwareHistory('Local preset selected: D3 bus, mouth=1, eyes=2/3. Not sent to MCU yet.');
  markButton(btn,'ok','Plan set');
}
function zonePayload(enabledId,startId,endId,colourId,brightnessId,label){ let st=Math.max(1,hwNum(startId,1)); let en=Math.max(st,hwNum(endId,st)); return {label:label,bus:'main',enabled:hwChecked(enabledId),start:st,end:en,default_colour:hwText(colourId,'#000000'),brightness:Math.max(0,Math.min(1,hwNum(brightnessId,0.2)))}; }
function servoPayloadV10(label,enabledId,pinId,minId,homeId,maxId,invertId){ let mn=hwNum(minId,-10), hm=hwNum(homeId,0), mx=hwNum(maxId,10); if(mx<mn){ const t=mn; mn=mx; mx=t; } hm=Math.max(mn,Math.min(mx,hm)); const pin=hwNum(pinId,-1); return {label:label,enabled:hwChecked(enabledId)&&pin>=0,pin:pin,min_deg:mn,home_deg:hm,max_deg:mx,invert:hwChecked(invertId),speed_deg_s:90}; }
function getHardwarePayload(){ return {hardware_registry:{schema:'bx1.hardware_registry.v1',led_buses:{main:{label:'Main addressable LED chain',type:'neopixel',enabled:hwChecked('hwLedBusEnabled')&&hwNum('hwLedBusPin',-1)>=0,data_pin:hwNum('hwLedBusPin',3),total_pixels:Math.max(1,hwNum('hwLedBusCount',100)),brightness_limit:Math.max(0,Math.min(1,hwNum('hwLedBusBrightness',0.2))),colour_order:'GRB',human_addressing:true}},led_zones:{mouth:zonePayload('zoneMouthEnabled','zoneMouthStart','zoneMouthEnd','zoneMouthColour','zoneMouthBrightness','Mouth'),left_eye:zonePayload('zoneLeftEyeEnabled','zoneLeftEyeStart','zoneLeftEyeEnd','zoneLeftEyeColour','zoneLeftEyeBrightness','Left eye'),right_eye:zonePayload('zoneRightEyeEnabled','zoneRightEyeStart','zoneRightEyeEnd','zoneRightEyeColour','zoneRightEyeBrightness','Right eye'),chest:zonePayload('zoneChestEnabled','zoneChestStart','zoneChestEnd','zoneChestColour','zoneChestBrightness','Chest / status'),status:zonePayload('zoneStatusEnabled','zoneStatusStart','zoneStatusEnd','zoneStatusColour','zoneStatusBrightness','Status strip')},servos:{head_yaw:servoPayloadV10('Head rotation / yaw','hwHeadYawEnabled','hwHeadYawPin','hwHeadYawMin','hwHeadYawHome','hwHeadYawMax','hwHeadYawInvert'),gimbal_left:servoPayloadV10('Left push-pull gimbal servo','hwHeadGimbalLeftEnabled','hwHeadGimbalLeftPin','hwHeadGimbalLeftMin','hwHeadGimbalLeftHome','hwHeadGimbalLeftMax','hwHeadGimbalLeftInvert'),gimbal_right:servoPayloadV10('Right push-pull gimbal servo','hwHeadGimbalRightEnabled','hwHeadGimbalRightPin','hwHeadGimbalRightMin','hwHeadGimbalRightHome','hwHeadGimbalRightMax','hwHeadGimbalRightInvert')},head_kinematics:{type:'dual_servo_push_pull',pitch_min_deg:hwNum('hwPitchMin',-10),pitch_home_deg:hwNum('hwPitchHome',0),pitch_max_deg:hwNum('hwPitchMax',10),roll_min_deg:hwNum('hwRollMin',-10),roll_home_deg:hwNum('hwRollHome',0),roll_max_deg:hwNum('hwRollMax',10),pitch_gain:Math.max(0.05,Math.min(5,hwNum('hwPitchGain',1))),roll_gain:Math.max(0.05,Math.min(5,hwNum('hwRollGain',1))),left_pitch_sign:hwNum('hwLeftPitchSign',1)>=0?1:-1,right_pitch_sign:hwNum('hwRightPitchSign',-1)>=0?1:-1,left_roll_sign:hwNum('hwLeftRollSign',1)>=0?1:-1,right_roll_sign:hwNum('hwRightRollSign',1)>=0?1:-1},sensors:{modulino_movement:{label:'Arduino Modulino Movement IMU',enabled:hwChecked('hwModulinoMovementEnabled'),bus:'i2c_qwiic',i2c_address:hwText('hwModulinoAddress','0x6A'),use_for:['pitch','roll','gyro','motion_awareness']}},drive_buses:{rs485_wheels:{label:'Future RS485 closed-loop wheel steppers',enabled:hwChecked('hwRs485Enabled'),adapter:'usb_rs485_or_uart_rs485',port:'',baud:hwNum('hwRs485Baud',115200),left_motor_id:hwNum('hwRs485LeftId',1),right_motor_id:hwNum('hwRs485RightId',2),max_linear_mps:0.25,max_angular_dps:60,safety_timeout_ms:500}}}}; }

function toast(msg,kind=''){ let t=document.getElementById('bx1Toast'); if(!t){ t=document.createElement('div'); t.id='bx1Toast'; t.className='toast'; document.body.appendChild(t); } t.className='toast '+kind; t.textContent=msg; clearTimeout(window._bx1ToastTimer); window._bx1ToastTimer=setTimeout(()=>{ if(t) t.remove(); },4200); }
function markButton(btn,state,label){ if(!btn) return; if(!btn.dataset.originalText) btn.dataset.originalText=btn.textContent; btn.classList.remove('action-running','action-ok','action-fail'); if(state==='running'){ btn.classList.add('action-running'); btn.disabled=true; btn.textContent=label||'Working...'; return; } if(state==='ok'){ btn.classList.add('action-ok'); btn.disabled=false; btn.textContent=label||'Done'; setTimeout(()=>{ btn.classList.remove('action-ok'); btn.textContent=btn.dataset.originalText; },1800); return; } if(state==='fail'){ btn.classList.add('action-fail'); btn.disabled=false; btn.textContent=label||'Failed'; setTimeout(()=>{ btn.classList.remove('action-fail'); btn.textContent=btn.dataset.originalText; },2600); return; } btn.disabled=false; btn.textContent=btn.dataset.originalText||btn.textContent; }
function pushHardwareHistory(msg,obj=null){ const el=document.getElementById('hardwareCommandHistory'); if(!el) return; const ts=new Date().toLocaleTimeString(); const line='['+ts+'] '+msg+(obj?'\n'+JSON.stringify(obj,null,2):''); el.textContent=line+'\n\n'+(el.textContent||''); }
function updateBridgeBanner(data){ const el=document.getElementById('hardwareBridgeBanner'); if(!el) return; const ok=!!(data && (data.bridge_ok||data.ok)); const err=(data && (data.bridge_error||data.error))||''; if(ok){ el.style.borderColor='#246b49'; el.style.color='#d9ffe9'; el.textContent='MCU command accepted. If the device did not move/light, check wiring, power, and the uploaded MCU sketch.'; } else { el.style.borderColor='#8a6a20'; el.style.color='#fff0b8'; el.textContent='MCU bridge not active yet. The registry is saved, but D3/servos will not physically respond until the MCU sketch/RouterBridge path is working. '+(err?('Error: '+err):''); } }
function fillZone(prefix,z){ if(!document.getElementById('zone'+prefix+'Enabled')) return; document.getElementById('zone'+prefix+'Enabled').checked=!!z.enabled; document.getElementById('zone'+prefix+'Start').value=z.start??1; document.getElementById('zone'+prefix+'End').value=z.end??z.start??1; document.getElementById('zone'+prefix+'Colour').value=normaliseHex(z.default_colour||'#000000'); document.getElementById('zone'+prefix+'Brightness').value=z.brightness??0.2; }
function fillServo(prefix,s){ const en=document.getElementById('hwHead'+prefix+'Enabled'); if(!en) return; en.checked=!!s.enabled; setPinValue('hwHead'+prefix+'Pin',s.pin??-1); document.getElementById('hwHead'+prefix+'Min').value=s.min_deg??-10; document.getElementById('hwHead'+prefix+'Home').value=s.home_deg??0; document.getElementById('hwHead'+prefix+'Max').value=s.max_deg??10; document.getElementById('hwHead'+prefix+'Invert').checked=!!s.invert; }
function setHardwareFields(hardware){ hardware=hardware||{}; const r=hardware.hardware_registry||{}; const bus=((r.led_buses||{}).main)||{}; if(document.getElementById('hwLedBusPin')){ hardwareJson.textContent=JSON.stringify(hardware,null,2); attachHardwareDirtyHandlers(); if(hardwareFormDirty){ const st=document.getElementById('hardwareStatus'); if(st && !st.textContent.includes('unsaved')) st.textContent='Hardware changes are unsaved. Auto-refresh will not overwrite them.'; return; } hwLedBusEnabled.checked=bus.enabled!==false; setPinValue('hwLedBusPin',bus.data_pin??3); hwLedBusCount.value=bus.total_pixels??100; hwLedBusBrightness.value=bus.brightness_limit??0.2; const z=r.led_zones||{}; fillZone('Mouth',z.mouth||{}); fillZone('LeftEye',z.left_eye||{}); fillZone('RightEye',z.right_eye||{}); fillZone('Chest',z.chest||{}); fillZone('Status',z.status||{}); const sv=r.servos||{}; fillServo('Yaw',sv.head_yaw||{}); fillServo('GimbalLeft',sv.gimbal_left||sv.head_pitch||{}); fillServo('GimbalRight',sv.gimbal_right||sv.head_roll||{}); const k=r.head_kinematics||{}; hwPitchMin.value=k.pitch_min_deg??-10; hwPitchHome.value=k.pitch_home_deg??0; hwPitchMax.value=k.pitch_max_deg??10; hwRollMin.value=k.roll_min_deg??-10; hwRollHome.value=k.roll_home_deg??0; hwRollMax.value=k.roll_max_deg??10; hwPitchGain.value=k.pitch_gain??1; hwRollGain.value=k.roll_gain??1; hwLeftPitchSign.value=String(k.left_pitch_sign??1); hwRightPitchSign.value=String(k.right_pitch_sign??-1); hwLeftRollSign.value=String(k.left_roll_sign??1); hwRightRollSign.value=String(k.right_roll_sign??1); const sens=(r.sensors||{}).modulino_movement||{}; hwModulinoMovementEnabled.checked=sens.enabled!==false; hwModulinoAddress.value=sens.i2c_address||'0x6A'; const drv=(r.drive_buses||{}).rs485_wheels||{}; hwRs485Enabled.checked=!!drv.enabled; hwRs485Baud.value=drv.baud??115200; hwRs485LeftId.value=drv.left_motor_id??1; hwRs485RightId.value=drv.right_motor_id??2; } }

const LED_STATE_FALLBACK_ORDER=['idle','listening','heard','awake','processing','thinking','speaking','success','warning','error','sleep','vision','diagnostic'];
const LED_ZONE_FALLBACK_ORDER=['mouth','left_eye','right_eye','chest','status'];
let ledStateModel={profiles:{},state_order:LED_STATE_FALLBACK_ORDER,zone_order:LED_ZONE_FALLBACK_ORDER,current_state:''};
function normaliseHex(value){ const names={off:'#000000',black:'#000000',red:'#ff0000',green:'#00ff00',blue:'#0000ff',cyan:'#00ffff',amber:'#ff9900',orange:'#ff6600',yellow:'#ffff00',purple:'#8000ff',pink:'#ff0080',magenta:'#ff00ff',white:'#ffffff'}; const t=String(value||'').trim().toLowerCase(); if(names[t]) return names[t]; if(/^#[0-9a-f]{6}$/.test(t)) return t; if(/^[0-9a-f]{6}$/.test(t)) return '#'+t; return '#000000'; }
function stateZoneEditor(state,zone,z){ const id=(state+'_'+zone).replace(/[^a-z0-9_]/gi,'_'); const col=normaliseHex(z.colour||z.color||'#000000'); const br=Math.max(0,Math.min(1,Number(z.brightness??0))); return `<div class="led-zone-editor"><input id="ledcol_${id}" type="color" value="${col}" title="${zone} colour"><input id="ledbr_${id}" type="number" min="0" max="1" step="0.01" value="${br.toFixed(2)}" title="brightness 0 to 1"></div>`; }
function renderLedStateSettings(data,force=false){ data=data||{}; if(data.profiles && (!ledStateFormDirty||force)) ledStateModel=data; const body=document.getElementById('ledStateTableBody'); if(!body) return; if(ledStateFormDirty&&!force){ const status=document.getElementById('ledStateStatus'); if(status&&!status.textContent.includes('unsaved')) status.textContent='LED state changes are unsaved. Auto-refresh will not overwrite them.'; return; } const order=ledStateModel.state_order||LED_STATE_FALLBACK_ORDER; const zones=ledStateModel.zone_order||LED_ZONE_FALLBACK_ORDER; const profiles=ledStateModel.profiles||{}; body.innerHTML=order.map(state=>{ const p=profiles[state]||{label:state,zones:{}}; const cls=state===ledStateModel.current_state?' class="state-row-active"':''; const cells=zones.map(zone=>`<td>${stateZoneEditor(state,zone,(p.zones||{})[zone]||{})}</td>`).join(''); return `<tr${cls}><td><input id="ledstate_enabled_${state}" type="checkbox" ${p.enabled!==false?'checked':''}></td><td><b>${htmlEscape(p.label||state)}</b><div class="small">${htmlEscape(state)}</div></td>${cells}<td><button onclick="applyLedState('${state}',this)">Test</button></td></tr>`; }).join(''); body.querySelectorAll('input').forEach(el=>{ el.addEventListener('input',()=>{ledStateFormDirty=true; const status=document.getElementById('ledStateStatus'); if(status) status.textContent='LED state changes are unsaved. Press Save all state profiles.';}); el.addEventListener('change',()=>{ledStateFormDirty=true;}); }); const status=document.getElementById('ledStateStatus'); if(status) status.textContent='Current LED state: '+(ledStateModel.current_state||'not yet applied')+'. Edit colours/brightness then save.'; }
function collectLedStateSettings(){ const order=ledStateModel.state_order||LED_STATE_FALLBACK_ORDER; const zones=ledStateModel.zone_order||LED_ZONE_FALLBACK_ORDER; const current=ledStateModel.profiles||{}; const profiles={}; for(const state of order){ const old=current[state]||{}; const p={label:old.label||state,enabled:!!document.getElementById('ledstate_enabled_'+state)?.checked,zones:{}}; for(const zone of zones){ const id=(state+'_'+zone).replace(/[^a-z0-9_]/gi,'_'); p.zones[zone]={enabled:true,colour:normaliseHex(document.getElementById('ledcol_'+id)?.value||'#000000'),brightness:Math.max(0,Math.min(1,Number(document.getElementById('ledbr_'+id)?.value||0)))}; } profiles[state]=p; } return {profiles}; }
async function saveLedStateSettings(btn=null){ markButton(btn,'running','Saving...'); const st=document.getElementById('ledStateStatus'); if(st) st.textContent='Saving LED state profiles...'; try{ const data=await api('/api/led_state_settings',collectLedStateSettings()); ledStateModel=data.led_states||ledStateModel; ledStateFormDirty=false; renderLedStateSettings(ledStateModel,true); if(st) st.textContent='LED state profiles saved.'; toast('LED state colours saved.','good'); markButton(btn,'ok','Saved'); }catch(e){ if(st) st.textContent='Save failed: '+e.message; toast('LED state save failed: '+e.message,'bad'); markButton(btn,'fail','Failed'); } }
async function applyLedState(state,btn=null){ if(ledStateFormDirty){ const st=document.getElementById('ledStateStatus'); if(st) st.textContent='Save the LED state profiles before testing them.'; toast('Save LED state changes before testing.','warn'); return; } markButton(btn,'running','Applying...'); const st=document.getElementById('ledStateStatus'); if(st) st.textContent='Applying '+state+' LED state...'; try{ const data=await api('/api/led_state_apply',{state}); if(!data.ok) throw new Error(data.error||'one or more LED zones failed'); ledStateModel.current_state=state; renderLedStateSettings(ledStateModel); if(st) st.textContent='Applied '+state+' LED state.'; toast('Applied '+state+' LED state.','good'); markButton(btn,'ok','Applied'); }catch(e){ if(st) st.textContent='Apply failed: '+e.message; toast('LED state test failed: '+e.message,'bad'); markButton(btn,'fail','Failed'); } }

async function saveHardwareSettings(btn=null){ markButton(btn,'running','Saving...'); hardwareStatus.textContent='Saving hardware registry...'; try{ const payload=getHardwarePayload(); hardwareJson.textContent=JSON.stringify(payload,null,2); const data=await api('/api/hardware_settings',payload); setHardwareClean(); setHardwareFields(data.hardware||{}); hardwareStatus.textContent='Saved hardware registry. Servo pin selections are locked until you change them again. Press Apply Registry to MCU to move enabled servos to Home.'; pushHardwareHistory('Saved hardware registry.', data.hardware?data.hardware.mcu_config_packet:null); toast('Hardware registry saved. Not necessarily applied to MCU yet.','good'); markButton(btn,'ok','Saved'); await refresh(); return data; }catch(e){ hardwareStatus.textContent='Save failed: '+e.message; pushHardwareHistory('Save failed: '+e.message); toast('Save failed: '+e.message,'bad'); markButton(btn,'fail','Save failed'); throw e; } }
async function applyHardwareToMcu(btn=null){ markButton(btn,'running','Applying...'); hardwareStatus.textContent='Applying hardware registry to MCU...'; try{ await saveHardwareSettings(); const data=await api('/api/hardware_apply',{}); hardwareJson.textContent=JSON.stringify(data,null,2); const msg=data.ok?'Applied to MCU. Enabled servos have been moved to Home.':'Apply failed: '+(data.bridge_error||data.error||'unknown'); hardwareStatus.textContent=msg; updateBridgeBanner(data); pushHardwareHistory(msg,data); toast(msg,data.ok?'good':'warn'); markButton(btn,data.ok?'ok':'fail',data.ok?'Applied':'Bridge fail'); await refresh(); }catch(e){ hardwareStatus.textContent='Apply failed: '+e.message; updateBridgeBanner({ok:false,error:e.message}); pushHardwareHistory('Apply failed: '+e.message); toast('Apply failed: '+e.message,'bad'); markButton(btn,'fail','Failed'); } }

async function paintLedRange(btn=null){
  markButton(btn,'running','Painting...');
  const start=parseInt(document.getElementById('ledPaintStart')?.value||'1',10);
  const end=parseInt(document.getElementById('ledPaintEnd')?.value||String(start),10);
  const colour=document.getElementById('ledPaintColour')?.value||'#00ffff';
  const brightness=parseFloat(document.getElementById('ledPaintBrightness')?.value||'0.25');
  hardwareStatus.textContent='Painting LED '+start+' to '+end+' '+colour+'...';
  try{
    const data=await api('/api/hardware_test',{role:'led_range', start_led:start, end_led:end, colour_hex:colour, brightness});
    hardwareJson.textContent=JSON.stringify(data,null,2);
    const ack=data.ack||{};
    const ok=!!(data.ok && (!ack.errors || ack.errors.length===0));
    const err=(ack.errors&&ack.errors.length)?ack.errors.join('; '):(data.error||'unknown');
    const msg=ok?'Paint command sent: LED '+start+' to '+end+' '+colour:'Paint failed: '+err;
    hardwareStatus.textContent=msg;
    updateBridgeBanner({ok,error:err,bridge_error:err});
    pushHardwareHistory(msg,data);
    toast(msg,ok?'good':'bad');
    markButton(btn,ok?'ok':'fail',ok?'Painted':'Failed');
    await refresh();
  }catch(e){
    hardwareStatus.textContent='Paint failed: '+e.message;
    updateBridgeBanner({ok:false,error:e.message});
    pushHardwareHistory('Paint failed: '+e.message);
    toast('Paint failed: '+e.message,'bad');
    markButton(btn,'fail','Failed');
  }
}
function paintLedPreset(start,end,colour,brightness,btn=null){
  const a=document.getElementById('ledPaintStart'); if(a) a.value=start;
  const b=document.getElementById('ledPaintEnd'); if(b) b.value=end;
  const c=document.getElementById('ledPaintColour'); if(c) c.value=colour;
  const d=document.getElementById('ledPaintBrightness'); if(d) d.value=brightness;
  const e=document.getElementById('ledPaintBrightnessText'); if(e) e.value=brightness;
  return paintLedRange(btn);
}


async function testHardware(role,value,colour,btn=null){ markButton(btn,'running','Testing...'); hardwareStatus.textContent='Testing '+role+'...'; try{ const data=await api('/api/hardware_test',{role,value,colour}); hardwareJson.textContent=JSON.stringify(data,null,2); const ack=data.ack||{}; const failed=(ack.items||[]).filter(item=>!(item&&item.ok&&item.executed)); const errors=[...(data.errors||[]),...failed.map(item=>item.bridge_error||item.reason||'command not executed')].filter(Boolean); const ok=!!data.ok && errors.length===0; const err=errors.length?errors.join('; '):(data.error||'unknown'); const msg=ok?'Test command executed: '+role:'Test failed: '+err; hardwareStatus.textContent=msg; updateBridgeBanner({ok, error:err, bridge_error:err}); pushHardwareHistory(msg,data); toast(msg,ok?'good':'bad'); markButton(btn,ok?'ok':'fail',ok?'Executed':'Failed'); await refresh(); }catch(e){ hardwareStatus.textContent='Test failed: '+e.message; updateBridgeBanner({ok:false,error:e.message}); pushHardwareHistory('Test failed: '+role+' - '+e.message); toast('Test failed: '+e.message,'bad'); markButton(btn,'fail','Failed'); } }
function asNum(v, fallback=0){ const n=Number(v); return Number.isFinite(n)?n:fallback; }
function renderMovementModule(data){ const state=(data&&data.state)||{}; const sensors=state.sensors||{}; const pitch=asNum(sensors.pitch_deg ?? state.pitch_deg ?? state.pitch, 0); const roll=asNum(sensors.roll_deg ?? state.roll_deg ?? state.roll, 0); const yaw=asNum(sensors.yaw_deg ?? state.yaw_deg ?? state.yaw, 0); const cube=document.getElementById('imuCube'); if(cube){ cube.style.transform='translate(-50%,-50%) rotateX('+(-pitch).toFixed(1)+'deg) rotateY('+(yaw).toFixed(1)+'deg) rotateZ('+(roll).toFixed(1)+'deg)'; } if(document.getElementById('imuPitchVal')) imuPitchVal.textContent=pitch.toFixed(1)+'°'; if(document.getElementById('imuRollVal')) imuRollVal.textContent=roll.toFixed(1)+'°'; if(document.getElementById('imuYawVal')) imuYawVal.textContent=yaw.toFixed(1)+'°'; const text=document.getElementById('imuStatusText'); if(text){ const mcu=!!state.mcu_ok; const imu=!!sensors.imu_ok; const src=mcu?'MCU/bridge telemetry':(imu?'IMU telemetry':'manual/default telemetry'); text.innerHTML='<strong>Source:</strong> '+src+'<br><strong>MCU:</strong> '+safe(state.mcu_ok)+' &nbsp; <strong>IMU:</strong> '+safe(sensors.imu_ok)+'<br><strong>Note:</strong> If this stays at 0.0°, the Modulino data is not reaching Linux yet. Open Telemetry / Logs to inspect the raw packet.'; } const hs=document.getElementById('headMixerLiveStatus'); if(hs){ const pins=state.head_servo_pins||{}; const targets=state.head_gimbal_targets_deg||{}; const left=Number(pins.gimbal_left??pins.pitch??-1), right=Number(pins.gimbal_right??pins.roll??-1), yp=Number(pins.yaw??-1); const ready=left>=0&&right>=0; hs.innerHTML='<strong>MCU head mixer:</strong> '+(ready?'READY':'NOT ATTACHED')+' &nbsp; <strong>Pins:</strong> yaw '+(yp>=0?'D'+yp:'disabled')+', left '+(left>=0?'D'+left:'disabled')+', right '+(right>=0?'D'+right:'disabled')+'<br><strong>Logical command:</strong> pitch '+safe(state.head_pitch_deg??'--')+'°, roll '+safe(state.head_roll_deg??'--')+'°, yaw '+safe(state.head_yaw_deg??'--')+'°<br><strong>Physical targets:</strong> left '+safe(targets.left??'--')+'°, right '+safe(targets.right??'--')+'° &nbsp; <strong>Mode:</strong> '+safe(state.mode||'--')+(ready?'':'<br><b>Enable both gimbal servos, choose their pins, Save, then Apply Registry to MCU.</b>'); } }
function renderHardwareDoctor(doctor){ doctor=doctor||{}; const snap=doctor.snapshot||doctor; const sum=document.getElementById('doctorSummary'), view=document.getElementById('doctorView'); if(sum){ sum.textContent=(snap.severity||'unknown').toUpperCase()+': '+(snap.summary||'No diagnosis'); sum.className='status-line '+(snap.severity==='ok'?'good':(['critical','fault'].includes(snap.severity)?'bad':'warn')); } if(view) view.textContent=JSON.stringify(doctor,null,2); }
async function runHardwareDoctor(btn=null){ markButton(btn,'running','Diagnosing...'); try{ const data=await api('/api/hardware_doctor_diagnose',{}); renderHardwareDoctor(data.diagnosis||data); markButton(btn,'ok','Diagnosed'); await refresh(); }catch(e){ doctorSummary.textContent='Diagnosis failed: '+e.message; markButton(btn,'fail','Failed'); } }
async function recoverHardwareBridge(btn=null){ if(!confirm('Restart the approved arduino-router service now? No firmware will be flashed.')) return; markButton(btn,'running','Restarting...'); try{ const data=await api('/api/hardware_doctor_recover',{}); renderHardwareDoctor((data.after)||data); doctorView.textContent=JSON.stringify(data,null,2); markButton(btn,data.ok?'ok':'fail',data.ok?'Recovered':'Failed'); await refresh(); }catch(e){ doctorSummary.textContent='Recovery failed: '+e.message; markButton(btn,'fail','Failed'); } }
async function generateDoctorSketch(template,btn=null){ markButton(btn,'running','Generating...'); try{ const data=await api('/api/hardware_doctor_generate',{template:template,note:'Generated from BX1 Hardware Doctor web page'}); doctorView.textContent=JSON.stringify(data,null,2); doctorSummary.textContent=data.ok?'Review-only sketch generated: '+data.sketch:'Generation failed: '+data.error; markButton(btn,data.ok?'ok':'fail',data.ok?'Generated':'Failed'); }catch(e){ doctorSummary.textContent='Generation failed: '+e.message; markButton(btn,'fail','Failed'); } }
async function refresh(btn=null){ if(btn) markButton(btn,'running','Refreshing...'); try{ const data=await api('/api/status'); setThemeFields(data.theme||{}); setBrainFields(data.brain||{}); setChatBridgeFields(data.chat_bridge||{}); setIdentityFields(data.identity||{}); setVoiceFields(data.voice||{}); setVoiceIndicator(data.voice_runtime || (data.voice&&data.voice.runtime) || {}); setMicFields(data.mic||{}); setCueFields(data.thinking_cues||{}); setIdleLifeFields(data.idle_life||{}); setHardwareFields(data.hardware||{}); renderLedStateSettings(data.led_states||{}); renderHardwareDoctor(data.hardware_doctor||{}); renderMovementModule(data); if(data.mic_level&&data.mic_level.level){ updateMicLevelView(data.mic_level.level); } if(!audioSettingsLoaded){ setAudioFields(data.audio||{}); audioSettingsLoaded=true; } const s=data.state||{}; stateView.textContent=JSON.stringify(s,null,2); renderPerformance(data.performance||{}); const pills=[]; pills.push(pill('robot', safe(s.robot_name||s.robot_id))); pills.push(pill('mcu', safe(s.mcu_ok), classifyBool(s.mcu_ok))); pills.push(pill('safe', safe(s.safety_ok), classifyBool(s.safety_ok))); pills.push(pill('fallen', safe(s.fallen), s.fallen?'bad':'good')); pills.push(pill('pitch', safe(s.pitch_deg??s.pitch))); pills.push(pill('roll', safe(s.roll_deg??s.roll))); const p=data.performance||{}; if(p.last_chat_ms!==null&&p.last_chat_ms!==undefined) pills.push(pill('last chat', p.last_chat_ms+' ms')); if(p.last_brain_latency_ms!==null&&p.last_brain_latency_ms!==undefined) pills.push(pill('latency', p.last_brain_latency_ms+' ms')); const vr=data.voice_runtime || (data.voice&&data.voice.runtime) || {}; if(vr.state){ const cls=['listening','awake','processing','recording','transcribing'].includes(vr.state)?'good':(vr.state==='error'?'bad':(['heard','ignored','starting','rejected'].includes(vr.state)?'warn':'')); pills.push(pill('voice', voiceStateText(vr.state).replace('Voice ',''), cls)); } if(data.mic_level&&data.mic_level.level&&data.mic_level.level.running) pills.push(pill('mic', data.mic_level.level.active?'voice':'quiet', data.mic_level.level.active?'good':'warn')); const idle=data.idle_life||{}; const ir=idle.runtime||{}; if(idle.enabled!==false && ir.state) pills.push(pill('idle', ir.sleeping?'sleep':ir.state, ir.sleeping?'warn':'')); const doc=(data.hardware_doctor||{}).snapshot||data.hardware_doctor||{}; if(doc.severity) pills.push(pill('doctor',doc.severity,doc.severity==='ok'?'good':(['fault','critical'].includes(doc.severity)?'bad':'warn'))); if(s.brain_error) pills.push(pill('brain','error','bad')); const lr=data.last_reply||{}; if(lr.available) pills.push(pill('repeat','ready '+(lr.chars||0)+' chars','good')); statusPills.innerHTML=pills.join(''); renderLog(data.events||[]); if(btn) markButton(btn,'ok','Refreshed'); }catch(e){ if(btn) markButton(btn,'fail','Failed'); stateView.textContent='Status failed: '+e.message; performanceView.textContent='Status failed: '+e.message; } }
async function sendText(){ const box=message; const text=box.value.trim(); if(!text) return; box.value=''; sendButton.disabled=true; const started=Date.now(); chatSendStatus.innerHTML='<span class="spinner"></span>Waiting for Brain App reply...'; const timer=setInterval(()=>{ const sec=Math.round((Date.now()-started)/1000); chatSendStatus.innerHTML='<span class="spinner"></span>Still thinking... '+sec+' s'; },1000); try{ await api('/api/send_text',{text, use_web:useWeb.checked, use_memory:useMemory.checked, allow_vision:autoCamera.checked}); chatSendStatus.textContent='Reply received.'; await refresh(); }catch(e){ chatSendStatus.textContent='Send failed: '+e.message; addLocalNotice('Send failed: '+e.message,'error'); }finally{ clearInterval(timer); sendButton.disabled=false; setTimeout(()=>{ if(chatSendStatus.textContent==='Reply received.') chatSendStatus.textContent=''; },4000); } }
async function repeatLastResponse(){ chatSendStatus.innerHTML='<span class="spinner"></span>Repeating last response...'; try{ const data=await api('/api/repeat_last_response',{}); chatSendStatus.textContent=data.ok?'Repeating last response.':'Repeat failed: '+(data.error||'no previous response'); if(data.ok) addLocalNotice('Repeating last response.','system'); await refresh(); }catch(e){ chatSendStatus.textContent='Repeat failed: '+e.message; addLocalNotice('Repeat failed: '+e.message,'error'); } }
function sendPreset(text){ message.value=text; sendText(); }
async function saveManualState(){ await api('/api/manual_state',{enabled:true,pitch_deg:pitch.value,roll_deg:roll.value,yaw_deg:yaw.value,front_distance_mm:frontDistance.value,battery_v:battery.value,location_label:locationLabel.value,visual_context:visualContext.value}); await refresh(); }
async function clearManualState(){ await api('/api/manual_state',{enabled:false,clear:true}); ['pitch','roll','yaw','frontDistance','battery','locationLabel','visualContext'].forEach(id=>document.getElementById(id).value=''); await refresh(); }
async function manualAction(action){ await api('/api/action',{action}); await refresh(); }
async function serviceCommand(command){ await api('/api/command',{command}); await refresh(); }
window.addEventListener('load',()=>{ setActivePageFromPath(); attachHardwareDirtyHandlers(); refresh(); setInterval(refresh,2000); setInterval(refreshMicLevel,250); message.addEventListener('keydown',e=>{ if(e.ctrlKey&&e.key==='Enter') sendText(); }); ['hwLedBusPin','hwHeadYawPin','hwHeadGimbalLeftPin','hwHeadGimbalRightPin'].forEach(id=>{ const el=document.getElementById(id); if(el){ el.addEventListener('input',enforceHardwareAutoEnable); el.addEventListener('change',enforceHardwareAutoEnable); } }); });
</script>
</body>
</html>
"""

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
            server_version = "RobotBodyClient/10.22.1"

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
                if path in {"/", "/index.html", "/chat", "/identity", "/connection", "/speech", "/microphone", "/cues", "/idle", "/context", "/actions", "/hardware", "/lighting", "/doctor", "/performance", "/telemetry"}:
                    self._send(200, INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8")
                    return
                if path == "/api/status":
                    self._json(200, service.web_snapshot())
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
