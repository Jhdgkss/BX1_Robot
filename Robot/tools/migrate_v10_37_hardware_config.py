#!/usr/bin/env python3
"""Safely migrate an existing BX1 body configuration to v10.37 hardware metadata."""
from pathlib import Path
import json, shutil, time
ROOT=Path(__file__).resolve().parents[1]
PATH=ROOT/'python'/'config.json'
if not PATH.exists():
    print('[BX1] No python/config.json yet; runtime will create it from defaults.')
    raise SystemExit(0)
data=json.loads(PATH.read_text(encoding='utf-8'))
stamp=time.strftime('%Y%m%d_%H%M%S')
backup=PATH.with_name(f'config.json.before_v10_37_{stamp}.bak')
shutil.copy2(PATH,backup)
data['app_version']='10.37'; data['version']='10.37'
data['hardware_control']={**(data.get('hardware_control') if isinstance(data.get('hardware_control'),dict) else {}),'high_level_owner':'linux_python','high_level_language':'Python 3','mcu_transport':'arduino_router_rpc','mcu_runtime':'minimal_arduino_zephyr_bridge_shim','micropython_reference_bundle':'mcu_micropython','motor_armed':False}
reg=data.get('hardware_registry')
if isinstance(reg,dict):
    sens=reg.setdefault('sensors',{}).setdefault('modulino_movement',{})
    sens.setdefault('enabled',True); sens['driver']='Arduino_LSM6DSOX explicit Wire1'; sens['bus']='Wire1/Qwiic'; sens['i2c_address']='0x6A'; sens.setdefault('sample_rate_hz',50)
    drive=reg.setdefault('drive_buses',{}).setdefault('rs485_wheels',{})
    drive['enabled']=False; drive['motor_armed']=False; drive.setdefault('primary_control','step_dir_enable_pending_confirmation'); drive.setdefault('diagnostics_interface','rs485'); drive['protocol_confirmed']=False
PATH.write_text(json.dumps(data, indent=4, ensure_ascii=False) + '\n', encoding='utf-8')
print('[BX1] v10.37 config migration complete')
print('[BX1] Backup:',backup)
