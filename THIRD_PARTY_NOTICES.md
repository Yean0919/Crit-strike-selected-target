# Third-party components

The project retains its original Apache-2.0 license. Effects and test artwork are procedurally
drawn. The Hakai adaptations below retain their upstream MIT license.

## Hakai source adaptations

Copyright (c) 2026 Matjaz Lipus. MIT license.

Upstream https://github.com/matjaz/hakai/tree/9e6fe469545abbd1a252ebb1fc45ba5e4d7f9ee3

- `src/crit_strike/hakai_effects.py` adapts `hakai-core/src/decals.rs` functions
  `make_crack` and `make_phaser_hit`, with Python seeded randomness, QPainter rendering,
  bounded image caches, configurable tint and finite-duration animation.
- `src/crit_strike/platform_macos.py` adapts the overlay window setup from
  `hakai-mac/src/macos.rs` to PyObjC and Qt. Capture uses a new ScreenCaptureKit backend.
- The original license text is included in `src/crit_strike/licenses/HAKAI-MIT.txt` and
  distributed as `crit_strike/licenses/HAKAI-MIT.txt` in wheels and desktop bundles.

The imported scope consists of MIT source algorithms. Hakai's separately licensed sound
and font assets remain outside this distribution.

| Component | Version | License and upstream |
| --- | --- | --- |
| Python | 3.11 runtime in the tested build | PSF license, https://www.python.org/ |
| PySide6 / Shiboken6 | 6.8.3 | LGPL-3.0 / GPL / commercial options, https://code.qt.io/cgit/pyside/pyside-setup.git/tag/?h=v6.8.3 |
| Qt | 6.8.3 | Applicable module licenses including LGPL-3.0, https://download.qt.io/archive/qt/6.8/6.8.3/single/ |
| OpenCV | 4.11.0 | Apache-2.0 and bundled third-party notices, https://github.com/opencv/opencv/tree/4.11.0 |
| opencv-python-headless packaging | 4.11.0.86 | MIT wrapper and third-party notices, https://github.com/opencv/opencv-python |
| NumPy | 2.2.6 | BSD-3-Clause and bundled third-party notices, https://github.com/numpy/numpy/tree/v2.2.6 |
| MSS | 10.0.0 | MIT, https://github.com/BoboTiG/python-mss/tree/v10.0.0 |
| PyObjC and Cocoa / Quartz / CoreMedia / ScreenCaptureKit wrappers | 11.1, macOS only | MIT, https://github.com/ronaldoussoren/pyobjc/tree/v11.1 |
| PyInstaller build tooling | 6.13.0 | GPL with bootloader exception, https://github.com/pyinstaller/pyinstaller/tree/v6.13.0 |

The Windows portable build includes available installed distribution license files under
`licenses/`. Qt libraries are dynamically loaded from the portable directory. Users may replace
these libraries with compatible modified builds and rebuild the application from source.
The upstream source links above identify the versions used. Refer to the included license texts
for the applicable rights and conditions. Third-party fonts are not bundled by this project.
