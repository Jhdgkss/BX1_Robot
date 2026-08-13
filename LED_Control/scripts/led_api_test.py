"""Manual LED API test. Run from the BX1 Brain project root."""
from brain_api.client import LEO

leo = LEO()
print(leo.status())
print(leo.led.task("listening"))
