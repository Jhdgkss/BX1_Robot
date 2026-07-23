"""Modulino Movement adapter using Arduino's MicroPython modulino package."""
try:
    from modulino import ModulinoMovement
except ImportError:
    ModulinoMovement=None
class MovementIMU:
    def __init__(self): self.sensor=None; self.error='not_started'
    def begin(self):
        if ModulinoMovement is None: self.error='Install the official modulino MicroPython package'; return False
        try: self.sensor=ModulinoMovement(); self.error=''; return True
        except Exception as exc: self.error=str(exc); return False
    def read(self):
        if self.sensor is None: return None
        try:
            if hasattr(self.sensor,'update'): self.sensor.update()
            def get(*names,default=0.0):
                for name in names:
                    value=getattr(self.sensor,name,None)
                    if callable(value): value=value()
                    if value is not None: return float(value)
                return default
            return {'ax':get('x','get_x','getX'),'ay':get('y','get_y','getY'),'az':get('z','get_z','getZ'),'gx':get('roll','get_roll','getRoll'),'gy':get('pitch','get_pitch','getPitch'),'gz':get('yaw','get_yaw','getYaw')}
        except Exception as exc: self.error=str(exc); return None
