class Safety:
    def __init__(self): self.estop=False
    def ok(self,pitch=0.0,roll=0.0): return not self.estop and abs(pitch)<35 and abs(roll)<35
