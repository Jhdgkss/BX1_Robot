# Patch Notes - Robot Brain V1.4.0 / Body Client V10.16

Robot name, character and personality now belong to the desktop Robot Brain instance, not the Arduino/UNO Q body client.

## Multi-robot examples

```bat
START_BX1_BRAIN.bat --profile bx1 --robot-name BX1 --api-port 8765 --tts-port 8091
START_BX1_BRAIN.bat --profile bx2 --robot-name BX2 --api-port 8766 --tts-port 8092
```

Arduino/body client port override:

```bash
./START_BX1_WEB.sh --web-port 8089 --brain-url http://YOUR_PC_IP:8766
```

The Brain prompt and repair pass are stronger so responses stay in character.
