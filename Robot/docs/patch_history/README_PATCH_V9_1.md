# Apply V9.1 Patch

Copy this ZIP to the Arduino Q home directory, then run:

```bash
cd ~/Arduino_Q_Client_V1
unzip -o ~/BX1_Arduino_Q_Wake_Listening_Indicators_Patch_V9_1.zip -d ~/Arduino_Q_Client_V1
sudo systemctl restart bx1-web.service
```

Then hard refresh the browser:

```text
CTRL + F5
```

Open **Chat / Debug** and check the new voice/wake status panel.
