# BX1 UNO Q Client V8.5 - Vosk STT Install Support

Adds project virtual environment support for optional Python packages such as Vosk.

## Files changed

- `START_BX1_WEB.sh`
  - Now automatically uses `./.venv/bin/python` when present.
  - Keeps fallback to system `python3` when the venv has not been created.

- `INSTALL_VOSK_STT.sh`
  - Installs `python3-venv`, `python3-full`, `wget`, and `unzip`.
  - Creates `./.venv` inside the project.
  - Installs `vosk` into the venv.
  - Downloads the small English Vosk model if needed.
  - Creates compatibility symlinks for both `models/vosk-model` and `models/vosk-model-small-en-us-0.15`.
  - Creates `python/models -> ../models` because the service starts inside the `python` folder.

## Apply

```bash
sudo systemctl stop bx1-web.service
# copy patch files over the project
cd ~/Arduino_Q_Client_V1
chmod +x START_BX1_WEB.sh STOP_BX1_WEB.sh INSTALL_VOSK_STT.sh
./INSTALL_VOSK_STT.sh
sudo systemctl start bx1-web.service
```

Then open `/microphone` and press **Check STT Setup**.
