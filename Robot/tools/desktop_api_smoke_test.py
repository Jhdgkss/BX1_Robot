#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import requests

base = sys.argv[1].rstrip('/') if len(sys.argv) > 1 else 'http://127.0.0.1:8765'
print('[test] status')
print(requests.get(base + '/api/status', timeout=5).text[:1000])

payload = {
    'robot_id': 'BX1',
    'message': 'look left and set your eyes blue',
    'body_state': {'safety_ok': True, 'pitch_deg': 0.2, 'roll_deg': -0.1},
    'speak': False,
}
print('[test] chat')
r = requests.post(base + '/api/chat', json=payload, timeout=180)
r.raise_for_status()
print(json.dumps(r.json(), indent=2))
