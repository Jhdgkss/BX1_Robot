import json
def encode_status(status): return json.dumps(status)+'\n'
def decode_command(line):
    try: return json.loads(line)
    except Exception: return None
