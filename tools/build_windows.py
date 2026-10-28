import hashlib
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = "Boundary"
SLUG = "boundary"
GO = False


def command(*args):
    subprocess.run(args, cwd=ROOT, check=True)


def main():
    if sys.platform != "win32":
        raise SystemExit("Build this Windows distribution on Windows.")
    os.chdir(ROOT)
    if GO:
        command(
            "go",
            "build",
            "-trimpath",
            "-ldflags=-s -w",
            "-o",
            f"bin/{SLUG}-cli.exe",
            f"./cmd/{SLUG}",
        )
    binaries = [(str(ROOT / "bin" / f"{SLUG}-cli.exe"), ".")] if GO else []
    spec = ROOT / "build" / "portable.spec"
    spec.parent.mkdir(exist_ok=True)
    spec.write_text(
        f"""from pathlib import Path
root = Path({str(ROOT)!r})
a = Analysis([str(root / "launch.py")], pathex=[str(root)], binaries={binaries!r}, datas=[(str(root / "THIRD_PARTY_NOTICES.md"), "."), (str(root / "licenses"), "licenses")], hiddenimports=[], hookspath=[], runtime_hooks=[], excludes=[], noarchive=False)
# Qt uses the native Windows ICU API. A PATH copy can export incompatible symbols.
a.binaries = [entry for entry in a.binaries if Path(entry[0]).name.lower() != "icuuc.dll"]
p = PYZ(a.pure)
e = EXE(p, a.scripts, [], exclude_binaries=True, name={NAME!r}, debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=False)
c = COLLECT(e, a.binaries, a.datas, strip=False, upx=False, name={NAME!r})
""",
        encoding="utf-8",
    )
    command(sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", str(spec))
    folder = ROOT / "dist" / NAME
    shutil.copy2(ROOT / "THIRD_PARTY_NOTICES.md", folder)
    shutil.copytree(ROOT / "licenses", folder / "licenses", dirs_exist_ok=True)
    (folder / "LEEME.txt").write_text(
        f"Abre {NAME}.exe. Conserva _internal junto al ejecutable. No necesitas Python.\n",
        encoding="utf-8",
    )
    command(sys.executable, "tools/check_windows_bundle.py")
    if GO:
        shutil.copy2(ROOT / "bin" / f"{SLUG}-cli.exe", ROOT / "dist")
    else:
        command(
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--onefile",
            "--console",
            "--name",
            "boundary-cli",
            "launch_cli.py",
        )
    archive = ROOT / "dist" / f"{NAME}-windows-x64.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as package:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                package.write(path, path.relative_to(folder.parent))
    with zipfile.ZipFile(archive) as package:
        if package.testzip():
            raise RuntimeError("Archive integrity check failed")
    assets = [archive, ROOT / "dist" / f"{SLUG}-cli.exe"]
    sums = []
    for path in assets:
        with path.open("rb") as source:
            sums.append(f"{hashlib.file_digest(source, 'sha256').hexdigest()}  {path.name}\n")
    (ROOT / "dist" / "SHA256SUMS.txt").write_text("".join(sums), encoding="utf-8")
    print(archive)


if __name__ == "__main__":
    main()
