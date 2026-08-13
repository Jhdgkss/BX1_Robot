from brain_api.client import LEO


def main():
    leo = LEO()
    print("Brain:", leo.status())
    print("Balance:", leo.balance.status())
    # leo.head.center()
    # leo.led.task("thinking")
    # leo.drive.set_motion(5, 0)
    # leo.drive.hold()


if __name__ == "__main__":
    main()
