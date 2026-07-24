from __future__ import annotations

import argparse
import html
import inspect
import json
import statistics
import os
import re
import threading
import time
import uuid
import wave
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict
from urllib.parse import parse_qs, unquote, urlparse

ROOT = Path(__file__).resolve().parents[2]
SHARED_RUNTIME = ROOT / "runtime" / "dottts_shared"
OUTPUT = SHARED_RUNTIME / "output_audio"


def configure_storage(profile: str) -> str:
    """Prepare shared model output while voice references remain profile-owned."""
    OUTPUT.mkdir(parents=True, exist_ok=True)
    return "shared"


configure_storage("shared")


def _safe_profile(value: Any) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", str(value or "bx1")).strip("_").lower() or "bx1"


def _profile_voice_dir(profile: Any) -> Path:
    path = ROOT / "runtime" / _safe_profile(profile) / "dottts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _read_active_reference(profile: Any = "bx1") -> Dict[str, str]:
    try:
        data = json.loads((_profile_voice_dir(profile) / "active_reference.json").read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_active_reference(audio_path: str, prompt_text: str, profile: Any = "bx1") -> None:
    target = _profile_voice_dir(profile) / "active_reference.json"
    target.write_text(json.dumps({"audio_path": audio_path, "prompt_text": prompt_text, "updated_at": datetime.now().isoformat(timespec="seconds")}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _wsl_audio_path(value: str) -> str:
    """Accept native Linux paths or translate an existing Windows drive path."""
    raw = str(value or "").strip().strip('"')
    if not raw:
        return ""
    direct = Path(raw).expanduser()
    if direct.exists():
        return str(direct.resolve())
    if not direct.is_absolute():
        project_relative = (ROOT / direct).resolve()
        if project_relative.exists():
            return str(project_relative)
    match = re.match(r"^([A-Za-z]):[\\/](.*)$", raw)
    if match:
        candidate = Path("/mnt") / match.group(1).lower() / match.group(2).replace("\\", "/")
        if candidate.exists():
            return str(candidate.resolve())
    return ""



def protect_audio_edges(
    audio: Any,
    sample_rate: int,
    *,
    leading_silence_ms: int = 250,
    trailing_silence_ms: int = 400,
    edge_fade_ms: int = 4,
) -> tuple[Any, Dict[str, Any]]:
    """Add device wake/release protection without trimming generated speech.

    USB/HDMI audio devices and amplifier enable lines can lose the first few
    milliseconds when playback starts and release slightly before the last
    sample is heard.  Padding is written into the WAV itself so the protection
    follows the file whether it is played on the Brain PC or downloaded by the
    robot body.
    """
    import numpy as np

    rate = max(1, int(sample_rate or 1))
    lead_ms = max(0, min(2000, int(leading_silence_ms or 0)))
    tail_ms = max(0, min(3000, int(trailing_silence_ms or 0)))
    fade_ms = max(0, min(50, int(edge_fade_ms or 0)))

    data = np.asarray(audio, dtype=np.float32)
    if data.ndim == 0:
        data = data.reshape(1)
    data = np.squeeze(data)
    if data.ndim == 0:
        data = data.reshape(1)
    if data.ndim > 2:
        raise ValueError(f"Unexpected Dot.TTS audio shape: {data.shape}")
    # soundfile expects frames x channels. Some runtimes return channels x
    # frames, so normalise that uncommon case before applying frame padding.
    if data.ndim == 2 and data.shape[0] <= 8 and data.shape[1] > data.shape[0]:
        data = data.T

    raw_frames = int(data.shape[0])
    fade_frames = min(raw_frames // 2, int(round(rate * fade_ms / 1000.0)))
    if fade_frames > 0:
        ramp = np.linspace(0.0, 1.0, fade_frames, endpoint=True, dtype=np.float32)
        if data.ndim == 2:
            ramp = ramp[:, None]
        data = data.copy()
        data[:fade_frames] *= ramp
        data[-fade_frames:] *= ramp[::-1]

    lead_frames = int(round(rate * lead_ms / 1000.0))
    tail_frames = int(round(rate * tail_ms / 1000.0))
    silence_shape = lambda frames: (frames,) + tuple(data.shape[1:])
    parts = []
    if lead_frames:
        parts.append(np.zeros(silence_shape(lead_frames), dtype=np.float32))
    parts.append(data)
    if tail_frames:
        parts.append(np.zeros(silence_shape(tail_frames), dtype=np.float32))
    protected = np.concatenate(parts, axis=0)

    return protected, {
        "raw_audio_duration_sec": round(raw_frames / rate, 3),
        "audio_duration_sec": round(int(protected.shape[0]) / rate, 3),
        "leading_silence_ms": lead_ms,
        "trailing_silence_ms": tail_ms,
        "edge_fade_ms": fade_ms,
        "audio_edge_protection": bool(lead_frames or tail_frames or fade_frames),
    }


class DotEngine:
    def __init__(self, model: str, precision: str, optimize: bool) -> None:
        self.model_name = model
        self.precision = precision
        self.optimize = optimize
        self.runtime = None
        self.lock = threading.Lock()
        self.loaded_at = ""
        self.last_load_sec = 0.0
        self.last_error = ""

    def status(self) -> Dict[str, Any]:
        cuda_available = False
        gpu_name = ""
        torch_version = ""
        try:
            import dots_tts  # noqa: F401
            installed = True
        except Exception as exc:
            installed = False
            self.last_error = str(exc)
        try:
            import torch
            torch_version = str(torch.__version__)
            cuda_available = bool(torch.cuda.is_available())
            if cuda_available:
                gpu_name = str(torch.cuda.get_device_name(0))
        except Exception:
            pass
        return {"installed": installed, "loaded": self.runtime is not None, "model": self.model_name, "precision": self.precision, "optimize": self.optimize, "loaded_at": self.loaded_at, "model_load_sec": round(self.last_load_sec, 3), "torch_version": torch_version, "cuda_available": cuda_available, "gpu_name": gpu_name, "environment": "WSL2/Linux recommended", "last_error": self.last_error}

    def load(self) -> None:
        if self.runtime is not None:
            return
        from dots_tts.runtime import DotsTtsRuntime
        started = time.perf_counter()
        self.runtime = DotsTtsRuntime.from_pretrained(self.model_name, precision=self.precision, optimize=self.optimize)
        self.last_load_sec = time.perf_counter() - started
        self.loaded_at = datetime.now().isoformat(timespec="seconds")

    def generate(self, body: Dict[str, Any], out_path: Path) -> Dict[str, Any]:
        import soundfile as sf
        with self.lock:
            self.load()
            seed = int(body.get("seed") or 42)
            torch_module = None
            try:
                import torch
                torch_module = torch
                torch.manual_seed(seed)
                if torch.cuda.is_available():
                    torch.cuda.manual_seed_all(seed)
                    torch.cuda.reset_peak_memory_stats()
            except Exception:
                pass
            kwargs: Dict[str, Any] = {
                "text": str(body.get("text") or "").strip(),
                "num_steps": int(body.get("num_steps") or (4 if self.model_name.endswith("-mf") else 10)),
                "guidance_scale": float(body.get("guidance_scale") or 1.2),
            }
            requested_prompt_audio = str(body.get("prompt_audio_path") or body.get("reference_audio_path") or body.get("audio_prompt_path") or "").strip()
            prompt_audio = _wsl_audio_path(requested_prompt_audio)
            prompt_text = str(body.get("prompt_text") or body.get("reference_text") or body.get("reference_transcript") or "").strip()
            profile = _safe_profile(body.get("profile") or "bx1")
            active_reference_used = False
            # The Lab stores a complete, known-good audio/transcript pair. Use
            # that pair when the Windows Brain sends no usable reference, or
            # sends an audio path without its exact transcript.
            if not prompt_audio or not prompt_text:
                active = _read_active_reference(profile)
                active_audio = _wsl_audio_path(str(active.get("audio_path") or ""))
                active_text = str(active.get("prompt_text") or "").strip()
                if active_audio and active_text:
                    prompt_audio = active_audio
                    prompt_text = active_text
                    active_reference_used = True
            if prompt_audio and prompt_text and not active_reference_used:
                _save_active_reference(prompt_audio, prompt_text, profile)
            language = str(body.get("language") or "EN").strip()
            if prompt_audio: kwargs["prompt_audio_path"] = prompt_audio
            if prompt_text: kwargs["prompt_text"] = prompt_text
            if language and language.lower() not in {"none", "english"}: kwargs["language"] = language
            # dots.tts has changed its Python signature between releases. Keep
            # this service compatible by sending only arguments supported by
            # the installed runtime instead of failing on a removed option.
            signature = inspect.signature(self.runtime.generate)
            accepts_extra = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in signature.parameters.values())
            supported = kwargs if accepts_extra else {key: value for key, value in kwargs.items() if key in signature.parameters}
            ignored = sorted(set(kwargs) - set(supported))
            result = self.runtime.generate(**supported)
            audio = result["audio"].float().cpu().squeeze().numpy()
            sample_rate = int(result["sample_rate"])
            audio, edge_meta = protect_audio_edges(
                audio,
                sample_rate,
                leading_silence_ms=int(body.get("leading_silence_ms", 250) or 0),
                trailing_silence_ms=int(body.get("trailing_silence_ms", 400) or 0),
                edge_fade_ms=int(body.get("edge_fade_ms", 4) or 0),
            )
            sf.write(str(out_path), audio, sample_rate, subtype="PCM_16")
            samples = int(audio.shape[0])
            gpu_peak_allocated_mb = 0.0
            gpu_peak_reserved_mb = 0.0
            if torch_module is not None and torch_module.cuda.is_available():
                gpu_peak_allocated_mb = torch_module.cuda.max_memory_allocated() / (1024 * 1024)
                gpu_peak_reserved_mb = torch_module.cuda.max_memory_reserved() / (1024 * 1024)
            return {"sample_rate": sample_rate, **edge_meta, "num_steps": kwargs["num_steps"], "guidance_scale": kwargs["guidance_scale"], "seed": seed, "gpu_peak_allocated_mb": round(gpu_peak_allocated_mb, 1), "gpu_peak_reserved_mb": round(gpu_peak_reserved_mb, 1), "ignored_unsupported_options": ignored, "voice_clone": bool(prompt_audio), "continuation_clone": bool(prompt_audio and prompt_text), "reference_audio_path": prompt_audio, "active_reference_used": active_reference_used, "profile": profile}


LAB_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dot.TTS English Voice Lab</title>
<style>
:root{color-scheme:dark;--bg:#0c1420;--card:#111d2d;--field:#172840;--line:#466482;--accent:#2c83c9;--text:#edf5fc;--muted:#a9bfd4;--good:#54d6a0}
*{box-sizing:border-box}body{font:16px Segoe UI,Arial,sans-serif;background:var(--bg);color:var(--text);max-width:1040px;margin:32px auto;padding:0 20px}h1{margin-bottom:8px}fieldset{background:var(--card);border:1px solid #38516c;border-radius:12px;padding:18px;margin:16px 0}legend{padding:0 8px;font-size:18px;font-weight:700}label{display:block;margin:13px 0 5px;font-weight:600}input,textarea,select,button{font:inherit;border-radius:7px;padding:10px}input,textarea,select{background:var(--field);color:#fff;border:1px solid var(--line);width:100%}button{cursor:pointer;color:#fff;background:var(--accent);border:1px solid #4595d3;font-weight:600}button.secondary{background:#253a52;border-color:#526d89}button:disabled{opacity:.55;cursor:wait}.hint{color:var(--muted);line-height:1.45}.drop-zone{border:2px dashed #597b9d;border-radius:11px;padding:24px;text-align:center;background:#0e1928;transition:.15s}.drop-zone.drag{border-color:#69bfff;background:#142a41;transform:translateY(-1px)}.drop-zone.ready{border-color:var(--good)}.file-name{margin:9px 0 0;color:var(--muted);font-size:14px;word-break:break-all}.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.row button{flex:0 0 auto}.path{margin-top:10px;font:13px Consolas,monospace;color:#9fc1dc;word-break:break-all}pre{white-space:pre-wrap;background:#07101b;padding:13px;border-radius:9px;min-height:46px}audio{width:min(100%,420px);margin:8px 0}.table-wrap{overflow:auto;margin-top:14px}table{width:100%;border-collapse:collapse;font-size:14px}th,td{padding:9px;border-bottom:1px solid #314860;text-align:left;white-space:nowrap}th{color:#a8c9e2;background:#0d1827}td audio{width:150px;height:32px;margin:0}.summary{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px;margin:12px 0}.metric{background:#0c1725;border:1px solid #314a64;border-radius:8px;padding:10px}.metric strong{display:block;color:#7fcaff;font-size:20px}
</style></head><body>
<h1>Dot.TTS English Voice Lab</h1>
<p class="hint">The first generation downloads and loads the selected 2B model and can take several minutes. Upload a clean reference clip for voice cloning.</p>
<fieldset><legend>Voice generation</legend>
<label for="text">Text to speak</label><textarea id="text" rows="5">Hello. This is the Robot Brain speaking with Dot TTS.</textarea>
<label>Reference audio (optional)</label>
<div id="dropZone" class="drop-zone" tabindex="0" role="button" aria-label="Drop or select a reference audio file">
  <strong>Drop a reference audio file here</strong>
  <p class="hint">WAV is recommended. MP3, FLAC, M4A and OGG are also accepted.</p>
  <button id="openButton" type="button">Open audio file</button>
  <input id="filePicker" type="file" accept="audio/*,.wav,.mp3,.flac,.m4a,.ogg" hidden>
  <div id="fileName" class="file-name">No reference file selected</div>
</div>
<input id="audio" type="hidden"><div id="uploadedPath" class="path"></div>
<audio id="referencePlayer" controls hidden></audio>
<label for="prompt">Exact reference transcript (strongly recommended)</label><textarea id="prompt" rows="3" placeholder="Type exactly what is spoken in the reference recording"></textarea>
<div class="row"><div style="flex:1"><label for="steps">Sampling steps</label><input id="steps" type="number" value="4" min="1" max="32"></div><div style="flex:1"><label for="guidance">Guidance scale</label><input id="guidance" type="number" value="1.2" step="0.1"></div></div>
<div class="row" style="margin-top:16px"><button id="generateButton" type="button">Generate speech</button><button id="healthButton" type="button" class="secondary">Refresh health</button></div>
</fieldset>
<pre id="status">Ready.</pre><audio id="player" controls></audio>
<fieldset><legend>Performance benchmark</legend>
<p class="hint">Use the same reference recording, transcript and test suite when comparing Dot.TTS with another engine. Close other GPU-heavy programs for cleaner results.</p>
<div class="row"><div style="flex:1"><label for="benchmarkRuns">Repeats per phrase</label><input id="benchmarkRuns" type="number" min="1" max="3" value="1"></div><div style="flex:2"><label>Test selection</label><div class="row"><button id="benchmarkCurrent" type="button">Benchmark current text</button><button id="benchmarkSuite" type="button" class="secondary">Run short / medium / long suite</button><button id="exportBenchmark" type="button" class="secondary" disabled>Export JSON</button></div></div></div>
<div id="benchmarkSummary" class="summary"></div>
<div class="table-wrap"><table id="benchmarkTable" hidden><thead><tr><th>Case</th><th>Run</th><th>Characters</th><th>Generate</th><th>Audio</th><th>RTF</th><th>Chars/s</th><th>GPU peak</th><th>Listen</th></tr></thead><tbody></tbody></table></div>
</fieldset>
<script>
const $=id=>document.getElementById(id), status=$('status'), drop=$('dropZone'), picker=$('filePicker');
const profile=new URLSearchParams(location.search).get('profile')||'bx1';
let benchmarkData=null;
async function health(){const r=await fetch(`/health?profile=${encodeURIComponent(profile)}`);status.textContent=JSON.stringify(await r.json(),null,2)}
async function uploadReference(file){
  if(!file)return;
  const allowed=['.wav','.mp3','.flac','.m4a','.ogg'];
  const ext=file.name.slice(file.name.lastIndexOf('.')).toLowerCase();
  if(!allowed.includes(ext)){status.textContent='Please choose WAV, MP3, FLAC, M4A or OGG audio.';return}
  if(file.size>50*1024*1024){status.textContent='Reference audio must be smaller than 50 MB.';return}
  $('openButton').disabled=true;$('fileName').textContent=`Uploading ${file.name}…`;status.textContent='Uploading reference audio…';
  try{
    const r=await fetch('/upload-reference',{method:'POST',headers:{'Content-Type':file.type||'application/octet-stream','X-Filename':encodeURIComponent(file.name),'X-Robot-Profile':profile},body:file});
    const j=await r.json();if(!r.ok||!j.ok)throw new Error(j.error||`Upload failed (${r.status})`);
    $('audio').value=j.audio_path;$('fileName').textContent=`Selected: ${j.original_filename}`;$('uploadedPath').textContent=`Service path: ${j.audio_path}`;
    drop.classList.add('ready');$('referencePlayer').src=URL.createObjectURL(file);$('referencePlayer').hidden=false;status.textContent='Reference audio uploaded and ready.';
  }catch(e){$('fileName').textContent='Upload failed';status.textContent=String(e)}finally{$('openButton').disabled=false}
}
async function speak(){
  $('generateButton').disabled=true;status.textContent='Generating speech. The first model load can take several minutes…';
  try{const body={profile,text:$('text').value,prompt_audio_path:$('audio').value,prompt_text:$('prompt').value,num_steps:+$('steps').value,guidance_scale:+$('guidance').value,language:'EN'};
    const r=await fetch('/speak',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const j=await r.json();status.textContent=JSON.stringify(j,null,2);if(j.audio_url){$('player').src=j.audio_url;$('player').play()}
  }catch(e){status.textContent=String(e)}finally{$('generateButton').disabled=false}
}
async function runBenchmark(mode){
  const buttons=[$('benchmarkCurrent'),$('benchmarkSuite')];buttons.forEach(b=>b.disabled=true);$('benchmarkSummary').innerHTML='';$('benchmarkTable').hidden=true;status.textContent='Running benchmark. Keep this page open…';
  try{const body={profile,mode,text:$('text').value,prompt_audio_path:$('audio').value,prompt_text:$('prompt').value,num_steps:+$('steps').value,guidance_scale:+$('guidance').value,repeats:+$('benchmarkRuns').value,language:'EN'};
    const r=await fetch('/benchmark',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const j=await r.json();if(!r.ok||!j.ok)throw new Error(j.error||`Benchmark failed (${r.status})`);benchmarkData=j;renderBenchmark(j);$('exportBenchmark').disabled=false;status.textContent='Benchmark complete.';
  }catch(e){status.textContent=String(e)}finally{buttons.forEach(b=>b.disabled=false)}
}
function renderBenchmark(j){
  const a=j.aggregate;$('benchmarkSummary').innerHTML=`<div class="metric"><strong>${a.mean_elapsed_sec.toFixed(2)} s</strong>Mean generation</div><div class="metric"><strong>${a.mean_rtf.toFixed(3)}</strong>Mean real-time factor</div><div class="metric"><strong>${a.mean_chars_per_sec.toFixed(1)}</strong>Mean characters/s</div><div class="metric"><strong>${a.max_gpu_peak_allocated_mb.toFixed(0)} MB</strong>Peak GPU allocated</div>`;
  const tbody=$('benchmarkTable').querySelector('tbody');tbody.innerHTML='';for(const x of j.results){const tr=document.createElement('tr');tr.innerHTML=`<td>${x.case}</td><td>${x.run}</td><td>${x.chars}</td><td>${x.elapsed_sec.toFixed(3)} s</td><td>${x.audio_duration_sec.toFixed(3)} s</td><td>${x.rtf.toFixed(3)}</td><td>${x.chars_per_sec.toFixed(1)}</td><td>${x.gpu_peak_allocated_mb.toFixed(0)} MB</td><td><audio controls src="${x.audio_url}"></audio></td>`;tbody.appendChild(tr)}$('benchmarkTable').hidden=false;
}
function exportBenchmark(){if(!benchmarkData)return;const blob=new Blob([JSON.stringify(benchmarkData,null,2)],{type:'application/json'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=`dottts_benchmark_${new Date().toISOString().replace(/[:.]/g,'-')}.json`;a.click();URL.revokeObjectURL(a.href)}
$('openButton').onclick=e=>{e.stopPropagation();picker.click()};picker.onchange=()=>uploadReference(picker.files[0]);
drop.onclick=e=>{if(e.target.id!=='openButton')picker.click()};drop.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();picker.click()}};
for(const name of ['dragenter','dragover'])drop.addEventListener(name,e=>{e.preventDefault();drop.classList.add('drag')});
for(const name of ['dragleave','drop'])drop.addEventListener(name,e=>{e.preventDefault();drop.classList.remove('drag')});
drop.addEventListener('drop',e=>uploadReference(e.dataTransfer.files[0]));$('generateButton').onclick=speak;$('healthButton').onclick=health;$('benchmarkCurrent').onclick=()=>runBenchmark('current');$('benchmarkSuite').onclick=()=>runBenchmark('suite');$('exportBenchmark').onclick=exportBenchmark;health();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    engine: DotEngine
    profile = "shared"
    server_version = "RobotBrain-DotTTS/2.1"

    def _json(self, data: Dict[str, Any], status: int = 200) -> None:
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        try:
            self.send_response(status); self.send_header("Content-Type", "application/json; charset=utf-8"); self.send_header("Content-Length", str(len(raw))); self.send_header("Access-Control-Allow-Origin", "*"); self.end_headers(); self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError):
            print("[Dot.TTS] Client disconnected before the response completed.")

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in {"/", "/lab"}:
            raw = LAB_HTML.encode("utf-8"); self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw); return
        if path == "/health":
            query = parse_qs(urlparse(self.path).query)
            profile = _safe_profile((query.get("profile") or ["bx1"])[0])
            active = _read_active_reference(profile)
            active_ready = bool(_wsl_audio_path(str(active.get("audio_path") or "")) and str(active.get("prompt_text") or "").strip())
            self._json({"ok": True, "service": "Shared Dot.TTS English Service", "shared_host": True, "protocol_version": 2, "service_profile": self.profile, "reference_profile": profile, **self.engine.status(), "active_reference_configured": active_ready, "active_reference_path": str(active.get("audio_path") or "")}); return
        if path.startswith("/audio/"):
            target = OUTPUT / Path(path).name
            if not target.exists(): self._json({"ok": False, "error": "Audio file not found"}, 404); return
            raw = target.read_bytes(); self.send_response(200); self.send_header("Content-Type", "audio/wav"); self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw); return
        self._json({"ok": False, "error": "Not found"}, 404)

    def do_POST(self) -> None:
        request_path = urlparse(self.path).path
        if request_path == "/shutdown":
            if self.headers.get("X-Robot-Brain-Shutdown") != "1":
                self._json({"ok": False, "error": "Missing shutdown confirmation header."}, 403)
                return
            # The Windows Brain uses this only for a service instance it started.
            # Reply first, then stop serve_forever from a different thread.
            self._json({"ok": True, "message": "Dot.TTS service is shutting down."})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        if request_path == "/upload-reference":
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if size <= 0:
                    self._json({"ok": False, "error": "The selected file is empty."}, 400); return
                if size > 50 * 1024 * 1024:
                    self._json({"ok": False, "error": "Reference audio must be smaller than 50 MB."}, 413); return
                original = Path(unquote(str(self.headers.get("X-Filename") or "reference.wav"))).name
                suffix = Path(original).suffix.lower()
                if suffix not in {".wav", ".mp3", ".flac", ".m4a", ".ogg"}:
                    self._json({"ok": False, "error": "Supported formats: WAV, MP3, FLAC, M4A and OGG."}, 415); return
                filename = f"reference_{uuid.uuid4().hex}{suffix}"
                profile = _safe_profile(self.headers.get("X-Robot-Profile") or "bx1")
                references = _profile_voice_dir(profile) / "reference_audio"
                references.mkdir(parents=True, exist_ok=True)
                target = references / filename
                target.write_bytes(self.rfile.read(size))
                self._json({"ok": True, "profile": profile, "original_filename": original, "filename": filename, "audio_path": str(target), "size_bytes": size})
            except Exception as exc:
                self._json({"ok": False, "error": f"Reference upload failed: {exc}"}, 500)
            return
        if request_path == "/benchmark":
            try:
                size = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(size) or b"{}")
                mode = str(body.get("mode") or "current").lower()
                repeats = max(1, min(3, int(body.get("repeats") or 1)))
                current_text = str(body.get("text") or "").strip()
                if mode == "suite":
                    cases = [
                        ("short", "Hello. This is a short Robot Brain voice benchmark."),
                        ("medium", "Robot Brain is measuring speech quality, voice similarity, timing and clarity using the same repeatable sentence on every voice engine."),
                        ("long", "This longer benchmark checks whether the voice remains natural, consistent and easy to understand across a complete response. It includes short pauses, technical language, and changing sentence length so we can compare real-time performance without judging only a single phrase."),
                    ]
                else:
                    if not current_text:
                        self._json({"ok": False, "error": "Enter text before running the current-text benchmark."}, 400); return
                    cases = [("current", current_text)]
                request_base = dict(body)
                request_base.pop("mode", None); request_base.pop("repeats", None)
                results = []
                host = self.headers.get("Host") or "127.0.0.1:8092"
                loaded_before = self.engine.runtime is not None
                benchmark_started = time.perf_counter()
                for case_name, case_text in cases:
                    for run_number in range(1, repeats + 1):
                        payload = dict(request_base); payload["text"] = case_text
                        filename = f"dottts_benchmark_{case_name}_{uuid.uuid4().hex}.wav"
                        started = time.perf_counter()
                        meta = self.engine.generate(payload, OUTPUT / filename)
                        elapsed = time.perf_counter() - started
                        duration = float(meta.get("audio_duration_sec") or 0.0)
                        results.append({
                            "case": case_name,
                            "run": run_number,
                            "chars": len(case_text),
                            "elapsed_sec": round(elapsed, 3),
                            "audio_duration_sec": round(duration, 3),
                            "rtf": round(elapsed / duration, 4) if duration > 0 else 0.0,
                            "chars_per_sec": round(len(case_text) / elapsed, 3) if elapsed > 0 else 0.0,
                            "gpu_peak_allocated_mb": float(meta.get("gpu_peak_allocated_mb") or 0.0),
                            "gpu_peak_reserved_mb": float(meta.get("gpu_peak_reserved_mb") or 0.0),
                            "audio_url": f"http://{host}/audio/{filename}",
                            "filename": filename,
                        })
                elapsed_values = [float(x["elapsed_sec"]) for x in results]
                rtf_values = [float(x["rtf"]) for x in results]
                cps_values = [float(x["chars_per_sec"]) for x in results]
                self._json({
                    "ok": True,
                    "benchmark_version": 1,
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                    "model": self.engine.model_name,
                    "precision": self.engine.precision,
                    "optimize": self.engine.optimize,
                    "model_was_loaded_before_benchmark": loaded_before,
                    "model_load_sec": round(self.engine.last_load_sec, 3),
                    "suite": mode,
                    "repeats": repeats,
                    "voice_clone": bool(request_base.get("prompt_audio_path")),
                    "num_steps": int(request_base.get("num_steps") or 4),
                    "guidance_scale": float(request_base.get("guidance_scale") or 1.2),
                    "total_benchmark_sec": round(time.perf_counter() - benchmark_started, 3),
                    "aggregate": {
                        "runs": len(results),
                        "mean_elapsed_sec": statistics.fmean(elapsed_values),
                        "median_elapsed_sec": statistics.median(elapsed_values),
                        "mean_rtf": statistics.fmean(rtf_values),
                        "median_rtf": statistics.median(rtf_values),
                        "mean_chars_per_sec": statistics.fmean(cps_values),
                        "max_gpu_peak_allocated_mb": max(float(x["gpu_peak_allocated_mb"]) for x in results),
                        "max_gpu_peak_reserved_mb": max(float(x["gpu_peak_reserved_mb"]) for x in results),
                    },
                    "results": results,
                })
            except Exception as exc:
                self.engine.last_error = str(exc)
                self._json({"ok": False, "error": f"Benchmark failed: {exc}"}, 500)
            return
        if request_path != "/speak": self._json({"ok": False, "error": "Not found"}, 404); return
        try:
            size = int(self.headers.get("Content-Length", "0")); body = json.loads(self.rfile.read(size) or b"{}")
            if not str(body.get("text") or "").strip(): self._json({"ok": False, "error": "Text is required"}, 400); return
            started = time.perf_counter(); filename = f"dottts_{uuid.uuid4().hex}.wav"; meta = self.engine.generate(body, OUTPUT / filename)
            host = self.headers.get("Host") or "127.0.0.1:8092"
            self._json({"ok": True, "engine": "dottts", "model": self.engine.model_name, "audio_url": f"http://{host}/audio/{filename}", "relative_audio_url": f"/audio/{filename}", "audio_path": str(OUTPUT / filename), "filename": filename, "format": "wav", "elapsed_sec": round(time.perf_counter()-started, 3), **meta})
        except Exception as exc:
            self.engine.last_error = str(exc); self._json({"ok": False, "engine": "dottts", "error": str(exc), "hint": "Check the service window for the full runtime error, then restart the service after applying an update."}, 500)

    def log_message(self, fmt: str, *args: Any) -> None:
        print("[Dot.TTS] " + fmt % args)


def main() -> None:
    parser = argparse.ArgumentParser(description="Robot Brain isolated Dot.TTS service")
    parser.add_argument("--host", default="0.0.0.0"); parser.add_argument("--port", type=int, default=8092)
    parser.add_argument("--model", choices=["mf", "soar"], default="mf"); parser.add_argument("--precision", default="bfloat16"); parser.add_argument("--no-optimize", action="store_true")
    parser.add_argument("--profile", default="shared")
    args = parser.parse_args(); model = f"rednote-hilab/dots.tts-{args.model}"
    Handler.profile = configure_storage(args.profile)
    Handler.engine = DotEngine(model, args.precision, not args.no_optimize)
    print(f"Dot.TTS English Lab: http://127.0.0.1:{args.port}/lab\nService: shared GPU host\nModel: {model}")
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__": main()
