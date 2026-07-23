# Arduino Q Client v9.6 - Portable Brain Connection

This update removes fixed Brain PC IP defaults and makes the web page easier to use on different networks.

## Changes

- Brain Connection page now has **Use This Browser PC for Brain + Voice**.
- When opened from the Windows Robot Brain PC, that button saves:
  - Brain API: `http://<browser_pc_ip>:8765`
  - Brain TTS: `http://<browser_pc_ip>:8091`
- The saved TTS URL is also synced into the robot voice profile.
- Default config no longer hard-codes John’s old `192.168.2.121` or home `192.168.68.51` addresses.
- Startup banner now shows whether Brain API and Brain TTS are configured.
- Robot personality defaults are less formal and less generic.

## Portable use

At a new location or on a new Wi-Fi network:

1. Start Robot Brain V1 on the Windows PC.
2. Open `http://BX1.local:8088/connection` from that same Windows PC.
3. Press **Use This Browser PC for Brain + Voice**.
4. Press **Test Brain Connection**.
5. Open Speech / Voice and run **Test Speech**.

Do not use `BX1.local` as the Brain URL. `BX1.local` is the robot. The Brain URL must be the Windows PC running Robot Brain.
