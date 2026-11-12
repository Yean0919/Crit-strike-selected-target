# 002 macOS 平台与 Hakai 特效复用

## 决策

保留 Python、Qt 和 OpenCV 主体，将 Hakai 的 Rust 程序化裂纹与能量命中算法移植到 QPainter，使用现有 Effect 和 Overlay 接口。复用来源固定为 `matjaz/hakai` 提交 `9e6fe469545abbd1a252ebb1fc45ba5e4d7f9ee3`。原始 MIT 授权随源码、wheel 和桌面包分发。

Mac 窗口采用 Hakai 的 AppKit 置顶层级、跨 Space、无阴影实现。截图采用 macOS 14 的 ScreenCaptureKit SCScreenshotManager，通过 SCContentFilter 排除自身应用。该接口支持明确的应用排除，并避免依赖上游已经弃用的 CGWindowListCreateImage。

平台模块负责操作系统差异，CaptureWorker 继续负责识别循环与异常处理。Mac 输出每屏独立物理像素坐标，复用 Monitor.to_logical。PyObjC 依赖使用 darwin 条件标记。

## 取舍

本轮增加两个参数化效果。Qt 移植使用固定随机种子生成几何，缓存受限，保留原有模组格式。此路线无需引入 Rust 工具链。上游音效、字体与独立素材授权分别处理，本轮复用范围为 MIT 源码。

Mac 构建按运行构建命令的 Python 架构产出 arm64 或 x86_64 应用。签名、公证及 Mac 实机验收状态在开发记录中明确标注。
