"""Entry point for the DDS viewer (.pyw = no console window)."""

import sys

from PyQt6.QtWidgets import QApplication

from viewer import MainWindow


def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    # Allow opening a file passed on the command line (e.g. drag onto the .exe).
    for arg in sys.argv[1:]:
        if arg.lower().endswith(".dds"):
            win.load_path(arg)
            break
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
