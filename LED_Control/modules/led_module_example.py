"""Example optional LED module. Register it in brain_modules/modules.json."""
from brain_api.client import LEO


def main():
    leo = LEO()
    leo.led.task("listening")


if __name__ == "__main__":
    main()
