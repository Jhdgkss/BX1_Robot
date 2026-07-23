"""Safe future wheel interface. No drive packets are emitted while unarmed."""
class Wheels:
    def __init__(self,cfg): self.cfg=cfg; self.armed=False; self.last_error='motor protocol not confirmed'
    def arm(self):
        if not self.cfg.MOTOR_ARMED: raise RuntimeError('MOTOR_ARMED is false')
        raise RuntimeError('Implement and bench-verify exact motor protocol before arming')
    def stop(self): self.armed=False
    def drive(self,left,right):
        if not self.armed: raise RuntimeError('wheel output blocked: not armed')
