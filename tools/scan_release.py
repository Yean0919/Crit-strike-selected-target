"""Scan the portable archive and embedded application bytecode before distribution."""

import hashlib
import marshal
import platform
import re
import sys
import types
import zipfile
from pathlib import Path

from privacy_scan import FORBIDDEN, PATTERNS, ROOT, inspect_text
from PyInstaller.archive.readers import CArchiveReader

# Exact public constants verified against both official OpenCV 4.11.0.86 macOS wheels.
# Restrict exceptions to the named native dependency and exact matched content digest.
# Provenance and wheel checksums are recorded in the macOS development record.
PUBLIC_CONSTANTS = {
    "libgnutls.30.dylib": {
        "d039c8119a029ab9f9c83c04d67002d887b6bc6026c4264402ab27cdf24cf138",
        "91ea1699ff6b1a34b4a1d500a9c75a808441e47b9ea68da6fb0195e01ce1dc61",
        "ef237ea8db4f2ae9ee100e8ced96d29b5dceb0e6a948443e6b8a00b1791f9ec9",
        "fa0b06a72461ec0a963dcfccb8d5b61bd88a6074fc7271573bff68ab86b8c1af",
        "a4d138d7ef9748464117b44fb9c0a4b5b85a1599a127d02690abaa96d03c16e6",
    },
    "libssh.4.10.1.dylib": {
        "3ba30ddc57c5e012f28276fa224e3485067a139cd220da03b730060afb01b2b9",
    },
    "libunistring.5.dylib": {
        "9103350cce17b3e46c97994f20396b630eb81b4359990e7c184f2d79253a55d4",
    },
}


def is_public_constant(name: str, value: str) -> bool:
    if "/cv2/__dot__dylibs/" not in name:
        return False
    reviewed = PUBLIC_CONSTANTS.get(Path(name).name, set())
    return hashlib.sha256(value.encode("utf-8")).hexdigest() in reviewed


def has_local_path(name: str, text: str, local_paths: list[str]) -> bool:
    if name.endswith("/cv2/cv2.abi3.so"):
        # The upstream wheel was also built on GitHub's shared /Users/runner account.
        text = text.replace("/Users/runner/work/opencv-python/opencv-python/", "<opencv-build>/")
        text = text.replace(
            "/Users/runner/hostedtoolcache/Java_Temurin-Hotspot_jdk/17.0.13-11/"
            "x64/Contents/Home/include",
            "<opencv-build-jdk-headers>",
        )
    return any(path.lower() in text.lower() for path in local_paths)


def code_strings(code):
    if not isinstance(code, types.CodeType):
        return
    yield code.co_filename
    for constant in code.co_consts:
        if isinstance(constant, str):
            yield constant
        elif isinstance(constant, types.CodeType):
            yield from code_strings(constant)


def main():
    if sys.platform == "darwin":
        archive = ROOT / "dist" / f"CritStrike-macos-{platform.machine()}.zip"
        executable = ROOT / "dist" / "CritStrike.app" / "Contents" / "MacOS" / "CritStrike"
    else:
        archive = ROOT / "dist" / "CritStrike-windows-x64.zip"
        executable = ROOT / "dist" / "CritStrike" / "CritStrike.exe"
    if not archive.is_file() or not executable.is_file():
        raise SystemExit("Build the native desktop package first")
    findings = set()
    local_paths = [str(ROOT), str(Path.home())]
    patterns = {name: pattern for name, pattern in PATTERNS.items() if name != "user-profile"}
    # TLS libraries contain PEM parser delimiters. A delimiter alone is not key material.
    patterns["private-key"] = re.compile(
        r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----\s+"
        r"[A-Za-z0-9+/=\r\n]{64,}\s+-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    )
    with zipfile.ZipFile(archive) as package:
        for name in package.namelist():
            parts = Path(name).parts
            if any(part in FORBIDDEN or part.startswith(".env.") for part in parts):
                findings.add((name, "private-data-file"))
            raw = package.read(name)
            # Native libraries may contain their upstream build-machine paths.
            # Check personal local paths exactly, and common secrets across binary bytes.
            for encoding in ["utf-8", "utf-16-le"]:
                text = raw.decode(encoding, errors="ignore")
                if has_local_path(name, text, local_paths):
                    findings.add((name, "local-build-path"))
                for kind, pattern in patterns.items():
                    if any(
                        not is_public_constant(name, match.group())
                        for match in pattern.finditer(text)
                    ):
                        findings.add((name, kind))
            if name.lower().endswith((".py", ".json", ".md", ".txt")):
                for kind in inspect_text(raw.decode("utf-8", errors="ignore")):
                    findings.add((name, kind))
        entries = len(package.namelist())
    executable_archive = CArchiveReader(str(executable))
    python_archive = executable_archive.open_embedded_archive("PYZ.pyz")
    modules = 0
    for name in python_archive.toc:
        for text in code_strings(python_archive.extract(name)):
            if any(path.lower() in text.lower() for path in local_paths):
                findings.add((name, "local-build-path"))
        if name == "crit_strike" or name.startswith("crit_strike."):
            modules += 1
            for text in code_strings(python_archive.extract(name)):
                for kind in inspect_text(text):
                    findings.add((name, kind))
                if any(path.lower() in text.lower() for path in local_paths):
                    findings.add((name, "local-build-path"))
    for name, entry in executable_archive.toc.items():
        if entry[-1] == "s":
            for text in code_strings(marshal.loads(executable_archive.extract(name))):
                for kind in inspect_text(text):
                    findings.add((name, kind))
    if modules < 10:
        findings.add(("executable", "application-modules-missing"))
    for name, kind in sorted(findings):
        print(f"{kind}: {name}")
    print(
        f"Scanned {entries} packaged entries and {modules} application modules; "
        f"findings={len(findings)}"
    )
    return bool(findings)


if __name__ == "__main__":
    raise SystemExit(main())
