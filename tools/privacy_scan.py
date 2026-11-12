"""Scan release inputs without printing sensitive matched values."""

import argparse
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    "credential": re.compile(
        r"(?:gh[pousr]_[A-Za-z0-9]{24,}|github_pat_[A-Za-z0-9_]{30,}"
        r"|sk-[A-Za-z0-9_-]{24,}|AKIA[A-Z0-9]{16})"
    ),
    "private-key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "user-profile": re.compile(
        r"[A-Za-z]:[\\/](?:Users|Documents and Settings)[\\/]"
        r"[A-Za-z0-9_.-]+",
        re.I,
    ),
    "private-network": re.compile(
        r"https?://(?:10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+"
        r"|172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+)"
    ),
}
FORBIDDEN = {".env", "settings.json", "app.lock", "avatars", "local-data"}


def inspect_text(data: str) -> list[str]:
    return [name for name, pattern in PATTERNS.items() if pattern.search(data)]


def scan_paths(paths: list[Path]) -> list[tuple[str, str]]:
    findings = []
    for path in paths:
        relative = path.relative_to(ROOT).as_posix()
        if any(part in FORBIDDEN or part.startswith(".env.") for part in path.parts):
            findings.append((relative, "private-data-file"))
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
            findings.append((relative, "unreviewed-image"))
        try:
            data = path.read_text(encoding="utf-8")
        except UnicodeError:
            continue
        for kind in inspect_text(data):
            findings.append((relative, kind))
    return findings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--staged", action="store_true")
    args = parser.parse_args()
    if args.staged:
        command = ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"]
    else:
        command = ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"]
    names = subprocess.check_output(command, cwd=ROOT).decode("utf-8").split("\0")
    paths = [ROOT / name for name in set(names) if name and (ROOT / name).is_file()]
    findings = scan_paths(paths)
    if args.staged:
        changed = (
            subprocess.check_output(["git", "diff", "--name-only", "-z"], cwd=ROOT)
            .decode("utf-8")
            .split("\0")
        )
        for name in set(changed).intersection(names) - {""}:
            findings.append((name, "index-worktree-mismatch"))
    for path, kind in findings:
        print(f"{kind}: {path}")
    print(f"Scanned {len(paths)} source files; findings={len(findings)}")
    return bool(findings)


if __name__ == "__main__":
    raise SystemExit(main())
