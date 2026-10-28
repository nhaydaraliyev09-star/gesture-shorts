"""Entry point for python -m gesture_shorts."""

from __future__ import annotations

import sys
from tkinter import Tk

from gesture_shorts.ui import PiPApp


def main() -> None:
    root = Tk()
    _ = PiPApp(root)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
