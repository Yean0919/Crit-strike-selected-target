"""Scan the portable archive and embedded application bytecode before distribution."""

import marshal
import re
import types
import zipfile
from pathlib import Path

from privacy_scan import FORBIDDEN, PATTERNS, ROOT, inspect_text
from PyInstaller.archive.readers import CArchiveReader


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
    archive = ROOT / "dist" / "CritStrike-windows-x64.zip"
    executable = ROOT / "dist" / "CritStrike" / "CritStrike.exe"
    if not archive.is_file() or not executable.is_file():
        raise SystemExit("Build the Windows portable package first")
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
                for local_path in local_paths:
                    if local_path.lower() in text.lower():
                        findings.add((name, "local-build-path"))
                for kind, pattern in patterns.items():
                    if pattern.search(text):
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
