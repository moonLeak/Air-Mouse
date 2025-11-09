from __future__ import annotations

from airmouse.app import AirMouseApplication


def main() -> None:
    app = AirMouseApplication()
    try:
        app.run()
    except KeyboardInterrupt:
        app.stop()


if __name__ == "__main__":
    main()
