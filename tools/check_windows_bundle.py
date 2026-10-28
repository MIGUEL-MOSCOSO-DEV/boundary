import ctypes
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = "Boundary"


def main():
    if sys.platform != "win32":
        raise SystemExit("Windows bundle check requires Windows.")
    internal = ROOT / "dist" / NAME / "_internal"
    if (internal / "icuuc.dll").exists():
        raise RuntimeError("A bundled ICU DLL would shadow the Windows ICU API.")
    handles = [os.add_dll_directory(str(internal / name)) for name in (".", "PySide6", "shiboken6")]
    for name in ("QtCore", "QtGui", "QtWidgets", "QtSvg"):
        ctypes.WinDLL(str(internal / "PySide6" / f"{name}.pyd"))
    if not handles:
        raise RuntimeError("DLL paths unavailable")
    print("Packaged Qt DLL imports passed.")


if __name__ == "__main__":
    main()
