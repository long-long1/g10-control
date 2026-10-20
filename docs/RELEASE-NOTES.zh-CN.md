# G10 Control 0.1.0-beta — GitHub Release Notes 草稿

**未发行，未经批准，不附下载链接。** 目标环境为 Windows 11 x64，Portable onedir；使用者需自行安装 WebView2/.NET、VB-CABLE 和豆包输入法。没有捆绑驱动、Runtime 或输入法安装器。

本候选在此前 BLE/ATVV、IMA ADPCM、WASAPI 语音桥接基础上，提供中文桌面界面、托盘、首次配置向导、显式设备能力/路由证明、损坏配置恢复和安全停止。既有样机历史链路成功不代表本候选已完成真实端到端验收，也不保证所有 G10/3K 设备兼容。

本轮发行准备：所有者已选 MIT，版权署名待确认；补充标准条款草稿、社区文件、固定来源许可文本、pystray 库源码与重组说明，以及无发布动作的 Windows CI、逐组件审查报告、SBOM/native 映射、manifest/SHA256 核验。

使用方式见 README-PORTABLE.zh-CN.md：用户在自己的机器上完成向导，桥接向 CABLE Input 输出，豆包选择 CABLE Output 并手动开启语音。不自动修改默认设备或安装驱动。程序关闭到托盘，从菜单安全退出。

已知限制：自动唤起豆包未通过；冻结按键观察器不可用；异常不自动重连，不强杀 BLE 进程。需要查看 UI 显示的数据目录，分享诊断前脱敏；正常桥接不保存录音或识别文字。

本轮离线自动化、clean 构建、非业务诊断和重复构建结果见 docs/PORTABLE_HANDOFF.md 第 15 节；这些不能替代干净 Windows、真实 G10 能力/音频/异常退出验收。LICENSE_STATUS.md 区分原创 MIT 与第三方条款；proxy_tools 声明冲突、LGPL 完整应用重组材料和原生许可链仍需审查。

发布前须补全准确版权、正式 LICENSE、第三方合规材料、干净机及硬件验收、审核的 commit/manifest/EXE 哈希，以及所有者对源码和二进制的分别批准。当前 SOURCE_READY=false，BINARY_READY=false。完整清单见 RELEASE-PROCESS.md。
