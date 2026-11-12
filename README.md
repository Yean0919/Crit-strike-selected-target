# Crit Strike

Windows / macOS 全桌面头像识别与娱乐特效工具。上传头像后，目标在任意可见窗口中稳定停留三秒，即在对应位置播放打击动画。macOS 适配的验证范围见下方环境说明。

## 功能

- 全桌面多尺度头像匹配，最多保存八个目标。
- 同一头像的不同位置独立计时，支持移动重计时、短暂漏检容错和停留去重。
- 自动检测与手动选点切换，透明特效层支持鼠标穿透。
- 内置重锤敲击、火花爆破、能量冲击、Hakai 玻璃碎裂及 Hakai 能量灼击五种效果。
- JSON 模组支持绘制器、颜色、大小、时长和次数调整。
- 多显示器坐标映射、托盘控制、暂停和立即停止。
- 本地保存模板与设置，截图仅在内存中处理。

## 环境

Windows 10 2004 或更高版本、Windows 11，x64。源码运行使用 Python 3.11～3.13，推荐 Python 3.11。自动检测需要系统支持将特效窗口排除截图。

macOS 14 或更高版本，Apple Silicon / Intel。采用 ScreenCaptureKit 排除本应用后捕获桌面，首次启动自动识别需要屏幕录制权限。Mac 原生屏幕、Space、多屏与快捷键交互仍需实机验收，CI 验证状态见开发记录。

## 源码启动

在项目根目录使用 PowerShell 执行以下命令。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.lock
.\.venv\Scripts\python.exe -m pip install -e . --no-deps
.\.venv\Scripts\python.exe -m crit_strike
```

macOS 在终端执行以下命令。

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.lock
python -m pip install -e . --no-deps
python -m crit_strike
```

Mac 首次自动检测时，在系统设置的“隐私与安全性 → 屏幕录制”中允许应用，然后退出并重新打开。源码启动时授权对象可能显示为 Python 或终端。手动播放可以直接使用。全局 F8/F9/F10 需要辅助功能权限，系统将功能键用于媒体控制时按住 Fn；也可使用窗口或托盘按钮。

## 使用

1. 点击“导入头像”，选择图片并拖动裁剪方形区域。
2. 选择目标，设置匹配阈值与特效。默认匹配阈值为 0.88。
3. 根据屏幕中头像的物理像素大小调整识别尺寸，默认范围为 24～160。
4. 选择“自动识别”，点击“启动检测”。主窗口可收起到托盘。
5. 目标在同一位置稳定至少三秒后触发。同一位置持续停留时只触发一次。
6. 手动操作时切换到“手动选点”，点击“选择打击位置”，在桌面上左键选点。

修改目标或识别设置后自动暂停，需要重新启动。默认允许五个物理像素的抖动。漏检容错以 0.6 秒为基线，结合实际扫描周期调整。较慢设备上的触发会晚于三秒。

| 快捷键 | 操作 |
| --- | --- |
| F8 | 自动模式暂停或恢复 |
| F9 | 停止检测与所有特效，退出选点 |
| F10 | 切换为手动选点 |
| Esc / 鼠标右键 | 取消选点 |

快捷键被其他软件占用时显示提示，可继续使用窗口或托盘按钮。关闭主窗口退出程序，收起到托盘使用专用按钮。

## 简单模组

复制内置 JSON，修改 ID 和参数，通过“导入模组”加载。五种绘制器均可用于自动识别、手动点选和效果预览。制作说明见 [模组文档](docs/mods.md)。复杂动作及外部素材时间轴列入后续扩展。

## 测试与构建

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check src tests tools
.\.venv\Scripts\python.exe -m crit_strike --smoke-test
.\.venv\Scripts\python.exe tools/desktop_check.py
.\.venv\Scripts\python.exe -m build
.\.venv\Scripts\python.exe tools/build_windows.py
.\.venv\Scripts\python.exe tools/privacy_scan.py
.\.venv\Scripts\python.exe tools/scan_release.py
git diff --check
```

桌面集成测试会短暂显示人工生成的头像并播放特效，使用临时配置。生成的检查结果与应用窗口预览存入已忽略的 `artifacts/`。测试过程中的桌面截图保留在内存。

Windows 构建输出为 `dist/CritStrike/CritStrike.exe` 及 `dist/CritStrike-windows-x64.zip`。解压整个便携包后运行 EXE。运行依赖与许可证随目录分发。

macOS 在 Mac 上执行 `python tools/build_macos.py`，生成 `dist/CritStrike.app` 和当前 Python 架构对应的 `CritStrike-macos-arm64.zip` 或 `CritStrike-macos-x86_64.zip`。执行 `python tools/scan_release.py` 检查本机产物。CI 分别构建两种架构，成功后在 Actions 的 Artifacts 中提供 ZIP。应用使用 ad-hoc 签名，尚未办理 Apple Developer ID 签名与公证。

## 数据与隐私

目标头像、配置、导入模组保存在 Qt 的系统用户应用数据目录中，应用组织名与名称均为 `CritStrike`。头像导入时使用随机 ID 保存，不保留原始文件名。程序启动时保持暂停。

源码与构建流程排除用户数据、真实截图、日志和环境变量文件。隐私扫描检查常见凭据、私网地址、个人目录和私人数据文件，并检查打包后的应用代码与内容。安装依赖时需要访问包源，应用识别与特效播放在本地完成。

## 已知边界

- 识别对象为相同图片，相同头像的不同使用者都会匹配。网页、通知及文件预览中的相同头像也会参与识别。
- 当前可见区域参与检测。遮挡、最小化、锁屏、受保护视频或安全桌面的内容可能无法捕获。
- 动态头像、严重遮挡、头像更换、过小或低纹理头像可能漏检。默认拒绝纹理过少的模板。
- 主窗口中的模板列表排除自动检测，避免软件自身的头像预览触发。
- 工作量随屏幕像素、模板数量和尺寸范围增长。完全静止的画面复用检测结果，动态画面需要重新匹配。
- 多屏与混合缩放采用单屏物理坐标映射。跨显示器边界被切开的头像可能漏检，动画在目标所属显示器边缘裁切。
- 效果参数模组支持五种内置绘制器。可执行脚本插件、外部序列帧和自定义音频尚未实现。
- Mac 的锁屏、安全界面和系统级受保护内容仍受系统限制。全屏应用、Space 切换、混合 Retina 显示器需要实机验收。
- 实际验证环境及未覆盖的硬件条件见 [开发记录](docs/development/README.md)。

## 工程文档

[任务清单](docs/TASKS.md) · [需求与验收](specs/desktop-target.md) · [技术决策](docs/decisions/001-desktop-engine.md) · [第三方声明](THIRD_PARTY_NOTICES.md)

本项目沿用仓库原有 Apache-2.0 许可。第三方组件遵循各自许可证，详见 [LICENSE](LICENSE) 与第三方声明。
