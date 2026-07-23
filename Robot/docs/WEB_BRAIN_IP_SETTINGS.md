# BX1 Web Brain App IP Settings

The Arduino Q web interface now has a **Brain App Connection** panel at the top of the page.

Use this when your laptop IP address changes and BX1 can no longer reach the Brain App.

## Recommended quick method

1. Start the BX1 Brain App on the laptop.
2. Press **Start API** in the Brain App.
3. Start the Arduino Q web service.
4. Open the web interface from the laptop:

```text
http://BX1.local:8088
```

5. Press **Use This Browser PC**.
6. Press **Test Brain Connection**.

This saves the laptop IP into:

```text
python/config.json
```

Example saved value:

```json
"brain_base_url": "http://192.168.68.53:8765"
```

## Manual method

Type the Brain App URL directly:

```text
http://192.168.68.53:8765
```

Then press **Save Brain URL**.

Bare IP addresses are also accepted:

```text
192.168.68.53
```

If the port is missing, BX1 assumes the Brain App API port is `8765`.

## Firewall check

If the test fails, check that the Brain App API is started and that Windows Firewall allows inbound traffic on port `8765`.
