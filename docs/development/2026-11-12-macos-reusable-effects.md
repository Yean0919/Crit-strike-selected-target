# 2026-11-12 macOS 与 Hakai 效果复用

## 起点与改动

起点为 `4103c0a`，工作区干净。上游复用来源为 Hakai 提交 `9e6fe469545abbd1a252ebb1fc45ba5e4d7f9ee3`，通过 GitHub 核对原始 MIT 许可与源码。

- 将 `make_crack`、`make_phaser_hit` 移植至 QPainter。新增 glass 和 phaser 模组，重锤使用移植后的裂纹。缓存分别限制为 8 和 32 张图像，动画到期清空。
- 保留原有三种绘制器和 JSON 格式。旧用户模组若已使用 glass/phaser ID，加载时保留旧模组。
- 增加统一平台入口与 Mac AppKit 覆盖层，移植 Hakai 的置顶和跨 Space 配置。新增 ScreenCaptureKit 截图、应用排除、Retina 坐标及权限处理。
- Mac 自动检测最低版本为 14。全局功能键通过 AppKit 监听，辅助功能权限不足时使用界面按钮。
- 增加按本机架构构建 `.app` 的工具、ad-hoc 签名验证、Mac 产物扫描，以及 Apple Silicon 和 Intel CI 任务。
- 许可证随源码、wheel 和桌面产物分发。更新模组、平台说明、任务清单和验收标准。

## 本地验证

| 命令或检查 | 实际结果 |
| --- | --- |
| `python -m ruff check src tests tools` | 通过 |
| `python -m pytest -q` | 47 项通过，1 项 Mac 原生图像转换测试在 Windows 跳过 |
| `python tools/preview_effects.py` | 四种效果关键帧及六秒视频生成成功，关键帧已检查 |
| `python tools/desktop_check.py` | 原重锤七项桌面检查通过 |
| `python tools/desktop_check.py --effect glass` | 七项通过，首次触发 4.500 秒，捕获像素差 0 |
| `python tools/desktop_check.py --effect phaser` | 七项通过，首次触发 3.750 秒，捕获像素差 0 |
| `python -m crit_strike --smoke-test` | 退出码 0 |
| `python -m build` | sdist 与 wheel 构建通过，包含 Hakai 许可证与新模组 |
| `python tools/build_windows.py` | EXE 与便携 ZIP 构建通过 |
| `CritStrike.exe --smoke-test` | 退出码 0 |
| `python tools/privacy_scan.py` | 无发现 |
| `python tools/scan_release.py` | 338 个打包条目、14 个应用模块，无发现 |
| `git diff --check` | 通过 |

Windows 实机为单屏 2560×1600、150% 缩放。玻璃效果扫描均值 628.8 ms，能量效果扫描均值 566.7 ms。三秒为最低稳定时间，实际触发受捕获与检测周期影响。

## Mac 验证状态

本地为 Windows。Mac 系统调用已加入原生 CI 测试，双架构构建与打包冒烟结果待 GitHub 执行后更新。本轮未取得用户 Mac 的屏幕录制及辅助功能授权环境。真实自动识别、Retina 多屏、Space 切换、全屏应用与全局快捷键仍待实机验收。应用尚未完成 Developer ID 签名与 Apple 公证。
