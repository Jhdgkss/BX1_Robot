"""Small browser dashboard for BX1 Brain.

The desktop Tk app remains the main operator console.  This page gives phones,
tablets, or the Arduino Q browser a read-only live status view without adding a
full web framework dependency.
"""
from __future__ import annotations

from html import escape
from typing import Any, Dict


def render_dashboard_html(title: str = "BX1 Brain Web Deck") -> str:
    title = escape(title)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    :root {{
      --bg: #07111f; --panel: rgba(14,28,47,.86); --panel2: rgba(22,40,62,.82);
      --text: #e8f3ff; --muted: #8aa6c1; --accent: #28d7ff; --accent2: #7cffd4;
      --warn: #ffc857; --danger: #ff5570; --grid: rgba(91, 160, 203, .24);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0; min-height: 100vh; color: var(--text);
      font-family: Segoe UI, Roboto, Arial, sans-serif;
      background:
        radial-gradient(circle at 20% 10%, rgba(40,215,255,.16), transparent 25%),
        radial-gradient(circle at 80% 20%, rgba(124,255,212,.10), transparent 22%),
        linear-gradient(135deg, #050b12, var(--bg));
    }}
    header {{ padding: 22px 26px 12px; }}
    h1 {{ margin: 0; font-size: 28px; letter-spacing: .02em; }}
    .sub {{ color: var(--muted); margin-top: 6px; }}
    .grid {{ display: grid; grid-template-columns: repeat(12, 1fr); gap: 14px; padding: 14px 24px 24px; }}
    .card {{
      grid-column: span 4; min-height: 116px; padding: 16px; border: 1px solid var(--grid);
      border-radius: 22px; background: var(--panel); box-shadow: 0 0 24px rgba(40,215,255,.08), inset 0 0 18px rgba(255,255,255,.025);
      backdrop-filter: blur(8px);
    }}
    .card.wide {{ grid-column: span 8; }} .card.full {{ grid-column: 1 / -1; }}
    .label {{ color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .12em; }}
    .value {{ font-size: 22px; font-weight: 700; margin-top: 8px; white-space: pre-wrap; }}
    .small {{ color: var(--muted); font-size: 13px; margin-top: 8px; white-space: pre-wrap; }}
    canvas {{ width: 100%; height: 180px; display: block; }}
    .pill {{ display: inline-block; padding: 6px 10px; border-radius: 999px; border: 1px solid var(--grid); color: var(--accent2); }}
    pre {{ margin: 0; white-space: pre-wrap; color: #d8f7ff; max-height: 260px; overflow: auto; }}
    @media (max-width: 920px) {{ .card, .card.wide {{ grid-column: 1 / -1; }} }}
  </style>
</head>
<body>
<header>
  <h1>BX1 Brain Web Deck</h1>
  <div class="sub">Read-only browser dashboard from the Robot API. Main control stays in the desktop app.</div>
</header>
<section class="grid">
  <div class="card"><div class="label">API</div><div id="api" class="value">Waiting...</div><div class="small">/dashboard/data refreshes every 2 seconds.</div></div>
  <div class="card"><div class="label">Model</div><div id="model" class="value">Waiting...</div></div>
  <div class="card"><div class="label">Route</div><div id="route" class="value">Waiting...</div></div>
  <div class="card"><div class="label">GPU</div><canvas id="gpuGauge" width="420" height="180"></canvas></div>
  <div class="card"><div class="label">VRAM</div><canvas id="vramGauge" width="420" height="180"></canvas></div>
  <div class="card"><div class="label">Token speed</div><canvas id="tokGauge" width="420" height="180"></canvas></div>
  <div class="card wide"><div class="label">Performance trend</div><canvas id="trend" width="850" height="210"></canvas></div>
  <div class="card"><div class="label">YOLO perception</div><div id="yolo" class="value">Waiting...</div><div id="yoloSmall" class="small"></div></div>
  <div class="card full"><div class="label">Robot body state / actions</div><pre id="robot">Waiting...</pre></div>
</section>
<script>
const history = [];
function pct(v,max=100) {{ return Math.max(0, Math.min(1, Number(v || 0)/max)); }}
function drawGauge(id, label, value, max, colour) {{
  const c = document.getElementById(id), x = c.getContext('2d'), w=c.width, h=c.height; x.clearRect(0,0,w,h);
  x.strokeStyle='rgba(91,160,203,.35)'; x.fillStyle='rgba(8,22,36,.85)'; roundRect(x, 10, 10, w-20, h-20, 24, true, true);
  const p=pct(value,max), cx=w/2, cy=h*0.72, r=Math.min(w,h)*0.46;
  x.lineWidth=18; x.strokeStyle='rgba(91,160,203,.22)'; arc(x,cx,cy,r,Math.PI,0);
  x.strokeStyle=colour; x.shadowColor=colour; x.shadowBlur=18; arc(x,cx,cy,r,Math.PI,Math.PI + Math.PI*p); x.shadowBlur=0;
  x.fillStyle='#e8f3ff'; x.font='bold 18px Segoe UI'; x.fillText(label,22,42);
  x.fillStyle=colour; x.font='bold 34px Segoe UI'; x.textAlign='center'; x.fillText(Math.round(value),cx,cy-8); x.textAlign='left';
}}
function arc(x,cx,cy,r,a,b) {{ x.beginPath(); x.arc(cx,cy,r,a,b,false); x.stroke(); }}
function roundRect(ctx,x,y,w,h,r,fill,stroke) {{ if (w<2*r) r=w/2; if (h<2*r) r=h/2; ctx.beginPath(); ctx.moveTo(x+r,y); ctx.arcTo(x+w,y,x+w,y+h,r); ctx.arcTo(x+w,y+h,x,y+h,r); ctx.arcTo(x,y+h,x,y,r); ctx.arcTo(x,y,x+w,y,r); ctx.closePath(); if(fill)ctx.fill(); if(stroke)ctx.stroke(); }}
function drawTrend() {{
  const c=document.getElementById('trend'), x=c.getContext('2d'), w=c.width, h=c.height; x.clearRect(0,0,w,h);
  x.fillStyle='rgba(8,22,36,.85)'; x.strokeStyle='rgba(91,160,203,.35)'; roundRect(x,10,10,w-20,h-20,22,true,true);
  for(let i=0;i<5;i++){{ x.strokeStyle='rgba(91,160,203,.15)'; x.beginPath(); x.moveTo(28,28+i*34); x.lineTo(w-22,28+i*34); x.stroke(); }}
  const draw = (key, color, max=100) => {{ if(history.length<2) return; x.strokeStyle=color; x.lineWidth=3; x.shadowColor=color; x.shadowBlur=10; x.beginPath(); history.forEach((p,i)=>{{ const px=34 + i*(w-70)/(Math.max(1,history.length-1)); const py=h-28 - pct(p[key],max)*(h-62); if(i===0)x.moveTo(px,py); else x.lineTo(px,py); }}); x.stroke(); x.shadowBlur=0; }};
  draw('gpu','#7cffd4',100); draw('vram','#28d7ff',100); draw('tok','#ffc857',120);
  x.fillStyle='#8aa6c1'; x.font='13px Segoe UI'; x.fillText('GPU',34,25); x.fillText('VRAM',84,25); x.fillText('TOK/S',148,25);
}}
async function tick() {{
  try {{
    const r=await fetch('/dashboard/data'); const d=await r.json();
    document.getElementById('api').textContent = d.api.running ? 'Running\n' + d.api.host + ':' + d.api.port : 'Stopped';
    document.getElementById('model').textContent = 'Chat: ' + d.model + '\nVision: ' + d.vision_model;
    document.getElementById('route').textContent = (d.route || 'chat').toUpperCase() + '\n' + (d.route_reason || 'waiting');
    const gpu=Number(d.performance.gpu_util||0), vram=Number(d.performance.vram_pct||0), tok=Number(d.last_stats.tok_s||0);
    drawGauge('gpuGauge','GPU',gpu,100,'#7cffd4'); drawGauge('vramGauge','VRAM',vram,100,'#28d7ff'); drawGauge('tokGauge','TOK/S',tok,120,'#ffc857');
    history.push({{gpu:gpu,vram:vram,tok:tok}}); while(history.length>60) history.shift(); drawTrend();
    document.getElementById('yolo').textContent = d.yolo && d.yolo.summary ? d.yolo.summary : 'No detection yet';
    document.getElementById('yoloSmall').textContent = d.yolo && d.yolo.error ? d.yolo.error : '';
    document.getElementById('robot').textContent = JSON.stringify({{body:d.latest_body_state, actions:d.last_robot_actions}}, null, 2);
  }} catch(e) {{ document.getElementById('api').textContent = 'Offline'; }}
}}
setInterval(tick, 2000); tick();
</script>
</body>
</html>"""
