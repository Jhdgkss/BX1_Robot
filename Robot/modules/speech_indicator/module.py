class SpeechIndicator:
    """Example only: publishes display intent; it owns no LED or audio hardware."""

    def start(self, context):
        self.context = context
        self.active = False
        context.widget({"id": "speech", "type": "metric", "title": "Speech indicator", "placement": "dashboard", "data": {"label": "State", "value": "Idle"}})
        context.subscribe("speech.started", self._started)
        context.subscribe("speech.finished", self._finished)

    def _started(self, event):
        self.active = True
        self.context.widget({"id": "speech", "type": "metric", "title": "Speech indicator", "placement": "dashboard", "data": {"label": "State", "value": "Speaking"}})
        self.context.publish("indicator.speech", {"state": "speaking"})

    def _finished(self, event):
        self.active = False
        self.context.widget({"id": "speech", "type": "metric", "title": "Speech indicator", "placement": "dashboard", "data": {"label": "State", "value": "Idle"}})
        self.context.publish("indicator.speech", {"state": "idle"})

    def health(self):
        return {"state": "healthy", "active": self.active, "hardware_access": False}

    def stop(self):
        self.active = False
