class SpeechIndicator:
    """Example only: publishes display intent; it owns no LED or audio hardware."""

    def start(self, context):
        self.context = context
        self.active = False
        context.subscribe("speech.started", self._started)
        context.subscribe("speech.finished", self._finished)

    def _started(self, event):
        self.active = True
        self.context.publish("indicator.speech", {"state": "speaking"})

    def _finished(self, event):
        self.active = False
        self.context.publish("indicator.speech", {"state": "idle"})

    def health(self):
        return {"state": "healthy", "active": self.active, "hardware_access": False}

    def stop(self):
        self.active = False
