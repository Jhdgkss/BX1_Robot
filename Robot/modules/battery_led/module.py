class BatteryLed:
    """Battery event to high-level Body LED intent; no raw hardware access."""
    def start(self, context):
        self.context = context; self.percent = None; self.charging = None; self.led = "Body LED capability unavailable"
        context.subscribe("battery.status", self._battery)
        self._widget()
    def _battery(self, event):
        value = event.get("payload", {}); percent = value.get("percent"); charging = value.get("charging")
        if isinstance(percent, (int, float)): self.percent = max(0, min(100, round(float(percent), 1)))
        if isinstance(charging, bool): self.charging = charging
        colour = "blue" if self.charging else "green" if (self.percent or 0) >= 50 else "amber" if (self.percent or 0) >= 20 else "red"
        result = self.context.led_status_request(target="status", colour=colour, effect="solid")
        self.led = "Applied by Robot Body" if result.get("ok") else "Body LED capability unavailable"
        self._widget()
    def _widget(self):
        self.context.widget({"id":"battery","type":"panel","title":"Battery","placement":"dashboard","health":"warning" if "unavailable" in self.led else "healthy","data":{"percentage":"Unknown" if self.percent is None else self.percent,"charging":"Unknown" if self.charging is None else self.charging,"intended_led":self.led}})
    def health(self): return {"state":"warning" if "unavailable" in self.led else "healthy","battery_percent":self.percent,"charging":self.charging,"led":"status-request only","hardware_access":False}
    def stop(self): pass
