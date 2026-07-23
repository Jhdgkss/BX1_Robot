#!/usr/bin/env python3
from __future__ import annotations
import json, sys
from pathlib import Path

def main() -> int:
    if len(sys.argv) != 2:
        print('Usage: set_mic_v10_34_1.py /path/to/python/config.json', file=sys.stderr)
        return 2
    path = Path(sys.argv[1]).expanduser().resolve()
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise SystemExit('config root must be an object')
    data['app_version'] = '10.34.1'
    data['version'] = '10.34.1'
    data['mic_device'] = 'plughw:0,0'
    data['mic_channels'] = 1
    data['sample_rate'] = 16000
    data['stt_capture_method'] = 'alsa'
    data['web_enabled'] = True
    data['web_host'] = '0.0.0.0'
    data['web_port'] = 8088
    path.write_text(json.dumps(data, indent=4, ensure_ascii=False)+'\n', encoding='utf-8')
    print('Microphone locked to:', data['mic_device'])
    return 0
if __name__ == '__main__':
    raise SystemExit(main())
