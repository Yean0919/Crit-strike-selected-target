"""Build a native-architecture macOS app with bundled licenses and an ad-hoc signature."""

import importlib.metadata
import platform
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    if sys.platform != "darwin":
        raise SystemExit("macOS build requires macOS 14 or later")
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
            "--osx-bundle-identifier",
            "io.github.Yean0919.CritStrike",
            "--target-architecture",
            platform.machine(),
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
    app = ROOT / "dist" / "CritStrike.app"
    resources = app / "Contents" / "Resources"
    for name in ["LICENSE", "README.md", "THIRD_PARTY_NOTICES.md"]:
        shutil.copy2(ROOT / name, resources / name)
    for package in [
        "PySide6",
        "PySide6-Essentials",
        "PySide6-Addons",
        "shiboken6",
        "numpy",
        "opencv-python-headless",
        "mss",
        "pyinstaller",
        "pyobjc-core",
        "pyobjc-framework-Cocoa",
        "pyobjc-framework-Quartz",
        "pyobjc-framework-CoreMedia",
        "pyobjc-framework-ScreenCaptureKit",
    ]:
        distribution = importlib.metadata.distribution(package)
        for item in distribution.files or []:
            if any(word in item.name.lower() for word in ["license", "copying", "notice"]):
                source = Path(distribution.locate_file(item))
                if source.is_file():
                    output = resources / "licenses" / package / Path(*item.parts)
                    output.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, output)
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if python_license.exists():
        shutil.copy2(python_license, resources / "licenses" / "PYTHON-LICENSE.txt")
    plist_path = app / "Contents" / "Info.plist"
    with plist_path.open("rb") as stream:
        info = plistlib.load(stream)
    info.update(LSMinimumSystemVersion="14.0", NSHighResolutionCapable=True)
    with plist_path.open("wb") as stream:
        plistlib.dump(info, stream)
    subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(app)], check=True)
    subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app)], check=True)
    archive = ROOT / "dist" / f"CritStrike-macos-{platform.machine()}.zip"
    subprocess.run(
        ["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(app), str(archive)], check=True
    )
    print(f"Built {archive.name} (ad-hoc signed, not notarized)")


if __name__ == "__main__":
    main()
