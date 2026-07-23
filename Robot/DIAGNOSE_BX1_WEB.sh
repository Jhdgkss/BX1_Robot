#!/usr/bin/env bash
set +e
cd "$(dirname "$0")"
echo "---- BX1 folder ----"
pwd
ls -ld . main.py python python/main.py .venv 2>/dev/null
wc -c main.py python/main.py 2>/dev/null

echo ""
echo "---- Python ----"
if [ -x .venv/bin/python ]; then
  .venv/bin/python --version
else
  python3 --version
fi

echo ""
echo "---- Direct import/start smoke check ----"
if [ -x .venv/bin/python ]; then
  .venv/bin/python - <<'PY'
from pathlib import Path
print('root main exists:', Path('main.py').exists(), 'size:', Path('main.py').stat().st_size if Path('main.py').exists() else 0)
print('python/main exists:', Path('python/main.py').exists(), 'size:', Path('python/main.py').stat().st_size if Path('python/main.py').exists() else 0)
PY
fi

echo ""
echo "---- Port 8088 ----"
ss -ltnp | grep 8088 || echo "Nothing listening on 8088"

echo ""
echo "---- Local web test ----"
curl -I --max-time 3 http://127.0.0.1:8088 || echo "Web app not responding"

echo ""
echo "---- systemd service ----"
sudo systemctl status bx1-web.service --no-pager || true

echo ""
echo "---- recent service logs ----"
sudo journalctl -u bx1-web.service -n 120 --no-pager || true

echo ""
echo "---- starter log ----"
tail -120 runtime/logs/web_startup.log 2>/dev/null || echo "No starter log yet"
