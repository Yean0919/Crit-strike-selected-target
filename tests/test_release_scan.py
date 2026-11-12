import importlib
from pathlib import Path


def test_public_constants_are_scoped_to_exact_library_and_content(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "tools"))
    scan = importlib.import_module("scan_release")
    name = "CritStrike.app/Contents/Frameworks/cv2/__dot__dylibs/libssh.4.10.1.dylib"
    algorithm = "sk-" + "ecdsa-sha2-nistp256-cert-v01"
    assert scan.is_public_constant(name, algorithm)
    assert not scan.is_public_constant(name, algorithm + "changed")
    assert not scan.is_public_constant("application.py", algorithm)
    assert not scan.is_public_constant(name.replace("libssh", "other"), algorithm)


def test_upstream_build_path_exception_preserves_application_path_detection(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "tools"))
    scan = importlib.import_module("scan_release")
    name = "CritStrike.app/Contents/Frameworks/cv2/cv2.abi3.so"
    upstream = "/Users/runner/work/opencv-python/opencv-python/opencv/modules/core/test.cpp"
    local_paths = ["/Users/runner", "/Users/runner/work/CritStrike"]
    assert not scan.has_local_path(name, upstream, local_paths)
    assert scan.has_local_path(name, upstream + " /Users/runner/private", local_paths)
    assert scan.has_local_path("application.py", upstream, local_paths)
