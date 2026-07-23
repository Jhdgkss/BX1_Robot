# Patch V9.0 Install Notes

Apply from the Arduino Q project folder:

```bash
cd ~/Arduino_Q_Client_V1
unzip -o ~/BX1_Arduino_Q_Main_STT_Camera_Web_Patch_V9_0.zip -d ~/Arduino_Q_Client_V1
sudo systemctl restart bx1-web.service
```

Then refresh the web page. The Chat page now has the main STT controls and the web/camera defaults.

Recommended first test:

1. Open Chat / Debug.
2. Tick **Auto use camera when asked**.
3. Tick **Allow laptop Brain App internet/web for this message** if the question needs online information.
4. Press **Ask Camera** or type: `What can you see?`
5. Test **Listen Once** and then **Listen Once + Send**.

This patch does not overwrite `python/config.json`.
