from machine import Pin
import neopixel
def clamp(v,lo,hi): return max(lo,min(hi,v))
class LEDs:
    def __init__(self,cfg): self.cfg=cfg; self.pixels=neopixel.NeoPixel(Pin(cfg.LED_PIN),cfg.LED_COUNT)
    def zone(self,name,r,g,b,brightness=1.0):
        start,end=self.cfg.LED_ZONES[name]; scale=min(clamp(brightness,0,1),self.cfg.LED_BRIGHTNESS_LIMIT); colour=(int(r*scale),int(g*scale),int(b*scale))
        for human in range(start,end+1): self.pixels[human-1]=colour
        self.pixels.write()
