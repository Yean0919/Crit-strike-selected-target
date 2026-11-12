"""Build a redistributable portable directory using the current virtual environment."""

import importlib.metadata
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    if sys.platform != "win32":
        raise SystemExit("Windows build requires Windows")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--windowed",
            "--onedir",
            "--name",
            "CritStrike",
            "--paths",
            "src",
            "--collect-data",
            "crit_strike",
            "--exclude-module",
            "PySide6.QtWebEngineCore",
            "--exclude-module",
            "PySide6.QtQml",
            "--exclude-module",
            "PySide6.QtQuick",
            "--exclude-module",
            "pytest",
            "--exclude-module",
            "setuptools",
            "--exclude-module",
            "pkg_resources",
            "--specpath",
            "build",
            "tools/launch.py",
        ],
        cwd=ROOT,
        check=True,
    )
    destination = ROOT / "dist" / "CritStrike"
    for name in ["LICENSE", "README.md", "THIRD_PARTY_NOTICES.md"]:
        shutil.copy2(ROOT / name, destination / name)
    for package in [
        "PySide6",
        "PySide6-Essentials",
        "PySide6-Addons",
        "shiboken6",
        "numpy",
        "opencv-python-headless",
        "mss",
        "pyinstaller",
    ]:
        distribution = importlib.metadata.distribution(package)
        for item in distribution.files or []:
            if any(word in item.name.lower() for word in ["license", "copying", "notice"]):
                source = Path(distribution.locate_file(item))
                if source.is_file():
                    output = destination / "licenses" / package / Path(*item.parts)
                    output.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, output)
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if python_license.exists():
        shutil.copy2(python_license, destination / "licenses" / "PYTHON-LICENSE.txt")
    shutil.copytree(
        ROOT / "src" / "crit_strike" / "mods", destination / "example-mods", dirs_exist_ok=True
    )
    shutil.make_archive(str(ROOT / "dist" / "CritStrike-windows-x64"), "zip", destination)
    print("Portable package built in dist/")


if __name__ == "__main__":
    main()
