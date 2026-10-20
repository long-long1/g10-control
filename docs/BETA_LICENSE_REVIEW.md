# Beta 候选版许可与再分发审查

状态：**只供本地验收，尚不能声明可对外分发。** 本文不是许可证，不替所有者授予第三方权利。不制作对外 ZIP，不上传二进制或建立 Release。

## 已完成的机械核对

- `build/stage_beta.py` 只允许两个 EXE、`_internal`、marker 和指定文档进入独立候选目录，不复制工作区、用户 data 或测试报告。
- 从固定 Python distribution、npm lock/实际安装包收集现有 license/notice；Python 顶层命名空间与 EXE 内 PYZ 模块对照，开发/可选工具另标 scope。
- `license-inventory.json` 列实际版本、声明许可证、收集文本及缺失标记；复制 Python 3.12 完整 LICENSE 栈，保留 Tcl/Tk/NumPy 自带文本。它是审查输入，不是认证 SBOM 或合规证明。
- `manifest.json` 记录逐文件 SHA-256；内容审查覆盖文件名、已知本机身份字节、ZIP 内部及 EXE 压缩 Python 模块，不执行提取的代码。
- sounddevice 上游 hook 原收集不同架构、macOS 和 ASIO 的 PortAudio。此 x64/WASAPI 候选只保留 libportaudio64bit.dll，排除无用 ASIO、x86、ARM、dylib；不改 WASAPI 算法。

## 待解决与所有者决定

1. **项目整体授权**：尚无整体许可证。需明确复制、修改、试用与分发授权及贡献来源，确认协议参考和独立实现边界。不能从源码公开推导二进制授权。见 LICENSE_STATUS.md。
2. **pystray 0.19.5**：元数据为 LGPLv3，已收集 COPYING/COPYING.LGPL。库在 PYZ 内，需确定适用的库源码、必要应用材料、替换/重链接和告知方案，并验证方案可操作；附文本不代表义务全部完成。依据：[固定版本 COPYING.LGPL](https://github.com/moses-palmer/pystray/blob/v0.19.5/COPYING.LGPL)、[GNU LGPL v3 第 4 节](https://www.gnu.org/licenses/lgpl-3.0.en.html)。
3. **缺失/版本对应的文本**：部分 PyWinRT 3.2.1 wheel、proxy_tools 0.1.0 声明 MIT 却未附完整 license 文件。应取得对应版本版权和许可，不能凭 SPDX/MIT 字符串补写权利人。[PyWinRT 上游 LICENSE](https://github.com/pywinrt/pywinrt/blob/main/LICENSE)仍需与实际版本对应。其他缺项见 inventory，区分运行与构建可选范围。
4. **原生链**：PortAudio 当前二进制的完整许可、WebView2 Core/WinForms/Loader SDK、Python/Tcl/Tk、Pillow 编解码库、NumPy/OpenBLAS/LAPACK/编译器运行库及 VC runtime 均需核对。总许可证表达式不能代替每个 native 组件材料；以实际文件哈希核对，不从导入成功推断合规。
5. **系统/外部软件**：不随包提供 WebView2 Runtime、.NET 安装器、VB-CABLE 或豆包安装文件。SDK/Loader 与系统 Runtime 不同；[Microsoft 分发说明](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution)仅作为核对入口。
6. **Python、工具与前端**：保留 [Python 许可栈](https://docs.python.org/3.12/license.html)、PyInstaller bootloader exception、BSD/MIT/PSF 等文本。核对锁定 React/React DOM/scheduler/lucide 的运行产物与 notices；TypeScript/Vite/esbuild 只复制许可文本，不将 node_modules 作为运行环境分发。

脚本不替所有者作最终选择。即使内容/隐私审查通过，redistribution_ready 仍为 false，直到明确决定并补齐材料；还需干净 Windows 和授权硬件验收，再单独确认对外试用包。
