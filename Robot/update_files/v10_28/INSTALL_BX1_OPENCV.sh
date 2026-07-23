#!/usr/bin/env bash
set -euo pipefail

PROJECT="${BX1_PROJECT:-/home/arduino/Arduino_Q_Client_V1}"
RESTART="true"

for arg in "$@"; do
  case "$arg" in
    --project=*) PROJECT="${arg#*=}" ;;
    --no-restart) RESTART="false" ;;
    -h|--help)
      cat <<'HELP'
Usage: ./INSTALL_BX1_OPENCV.sh [--project=/path] [--no-restart]

Installs Debian python3-opencv and exposes it to the BX1 virtual environment.
HELP
      exit 0 ;;
    *) echo "ERROR: unknown option: $arg" >&2; exit 2 ;;
  esac
done

PROJECT="$(realpath -m "$PROJECT")"
PY="$PROJECT/.venv/bin/python"
[[ -x "$PY" ]] || PY="$(command -v python3 || true)"
[[ -n "$PY" && -x "$PY" ]] || { echo "ERROR: Python 3 was not found." >&2; exit 127; }

if "$PY" -c 'import cv2; print("OpenCV", cv2.__version__)'; then
  echo "PASS: OpenCV is already available to BX1 Python."
else
  echo "Installing Debian OpenCV for BX1 face and motion awareness..."
  sudo apt-get update
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y python3-opencv

  if ! "$PY" -c 'import cv2; print("OpenCV", cv2.__version__)' >/dev/null 2>&1; then
    SITE="$($PY - <<'PY'
import site
paths = site.getsitepackages()
print(paths[0] if paths else site.getusersitepackages())
PY
)"
    mkdir -p "$SITE"
    printf '%s\n' '/usr/lib/python3/dist-packages' > "$SITE/bx1_system_dist_packages.pth"
  fi

  if "$PY" -c 'import cv2; print("OpenCV", cv2.__version__)'; then
    echo "PASS: OpenCV is available to BX1 Python."
  else
    echo "ERROR: OpenCV installed but the BX1 Python environment still cannot import cv2." >&2
    echo "Do not install an arbitrary pip opencv-python wheel on the UNO Q." >&2
    exit 1
  fi
fi

if [[ "$RESTART" == "true" ]] && command -v systemctl >/dev/null 2>&1; then
  sudo systemctl restart bx1-web.service
  sleep 5
  sudo systemctl status bx1-web.service --no-pager -l || true
fi
