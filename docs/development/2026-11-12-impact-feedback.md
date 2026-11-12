# 2026-11-12 锤击与爆破反馈增强

## 用户反馈

锤子与火花效果像轻点，缺少重量感和威慑力。本轮增强两个绘制器的动作与命中反馈。

## 改动

- `effects.py` 将锤击拆成抬锤蓄力、加速挥落、命中停顿和回弹。锤体增加金属渐变、厚重锤头、握柄与倒角，命中增加裂纹和碎屑。
- 火花爆破增加收缩蓄能、白热爆心、放射爆闪、扩张烟团、双层冲击波和连续弹道拖尾。
- 局部震动随命中时间衰减。碎屑角度与速度由固定序号计算，重复绘制相同时间点得到相同图像。
- 既有 JSON 模组继续通过颜色、大小、总时长和次数控制效果。
- `preview_effects.py` 使用正式绘制入口生成关键帧与六秒双效果视频，背景和头像为程序生成内容，保存于忽略的 `artifacts/`。
- 更新重击需求、模组说明及关键帧回归测试。

## 验证结果

| 命令或检查 | 结果 |
| --- | --- |
| `python -m ruff check src tests tools` | 通过 |
| `python -m pytest -q` | 39 项通过 |
| `python tools/preview_effects.py` | 关键帧和六秒预览视频生成成功，已检查关键帧 |
| `python tools/desktop_check.py` | 七项桌面链路检查通过，特效层捕获像素差为 0 |
| `python tools/build_windows.py` | Windows EXE 与便携 ZIP 构建通过 |
| `CritStrike.exe --smoke-test` | 退出码 0 |
| `python tools/privacy_scan.py` | 源码扫描通过 |
| `python tools/scan_release.py` | 332 个打包条目及 11 个应用模块扫描通过 |

实机验证为单屏 2560×1600、150% 缩放。视觉验证覆盖程序生成的目标背景，实际观感可使用 `artifacts/impact-preview.mp4` 或应用中的预览按钮复核。
