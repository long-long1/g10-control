# 第七轮许可审查状态（2026-10-20）

主项目正式 MIT 已完成，准确署名为所有者提供的 2026 WYL；整仓协议来源边界仍待审。SOURCE_READY=false，BINARY_READY=false。以下是审查输入，不是法律合规认证。

- pystray 保留方案 A；完整固定版本源码、GPL/LGPL 文本及 13 个 Python 文件逐字节匹配证据已收集，拟走重组方案，见 LGPL-PYSTRAY.md。两个 PYZ 都含库，不能声称相邻文件可替换；应用材料授权和最终法律审查未完成。
- proxy_tools 0.1.0 原始 sdist 无许可证。安装源码与固定上游 commit 相等；取得的 LICENSE.txt 是 BSD 风格且尾文异常，与 metadata 的 MIT 冲突。原样保留，不补造权利人、不直接标 MIT 或 SPDX BSD；需上游/所有者澄清。
- 九个 winrt-* 3.2.1 的 wheel/sdist 无文本；取得 v3.2.1 固定 commit 的 MIT 文本，记录各自 sdist 哈希与比对。比对不覆盖所有文件，不能把共同上游文本当作 native SDK 完整许可；C++/WinRT、Windows SDK、MSVC 仍待审。
- Python 3.12.10、Pillow 13.0.0、NumPy 2.5.4 的安装发行包已附完整文本栈，自动随候选复制。Pillow LICENSE 包含各编解码库 notices，NumPy 保留内部及 bundled libraries 文本；仍需核对实际静态组件和二进制来源。
- PortAudio：已安装 sounddevice 的 portaudio-binaries 构建配方固定 v19.7.0，已取对应上游 MIT 文本；只保留原有 x64 非 ASIO DLL。DLL/配方与编译器/Windows API 附加条款的完整对应关系待审。
- Tcl/Tk PE 版本为 8.6.15，取各自固定版本 license.terms；候选内已有的数据许可也另行复制。Python 本地安装逐字节原生映射用于证明来源，非完整 native 法律结论。
- WebView2 Core/WinForms/三个架构 Loader 的 PE 为 1.0.3856.49，取得相同版本官方 NuGet LICENSE/NOTICE，并逐个哈希对照（见 upstream/index.json）。SDK 条款不是 MIT，Runtime 安装器不随包携带，分发条件仍须审查。

候选 license-review.json 为每个 SBOM 组件（包括未安装 npm 平台可选项）列版本、是否进入候选/证据范围、经核实才填写的 SPDX、官方来源、文本位置、版权义务、源码/替换/重链接需求、审查状态和风险。THIRD-PARTY-LICENSES.md 为人可读等价表。三个已安装 npm 平台构建包没有自带文本（@esbuild/win32-x64、@rollup/rollup-win32-x64-gnu、@rollup/rollup-win32-x64-msvc），只用于构建且不复制二进制进候选；其缺项与未安装平台项分开记录。未知保留 null 或明确待审，不隐藏组件；SBOM 本身含构建环境超集、缺完整依赖关系图/静态子组件。

来源固定在 desktop-ui/licenses/upstream/index.json（SHA256）。另外，本机构建 TOC 显示 44 个 Windows API/UCRT 文件来自项目/Python 安装之外的无关工具链搜索路径；未核实其再分发来源。保留组件与哈希，license-review.json 记录匹配及脱敏来源类别，不输出私人绝对路径。原始下载包在本机 output/upstream-review，未提交运行日志、配置或原生二进制。候选许可证收集器完全离线，只读取已核对的来源材料。


## 历史审查背景（第六轮，状态已由上述更新）

# Beta 候选版许可与再分发审查

状态：**只供本地验收，尚不能声明可对外分发。** 本文不是许可证，不替所有者授予第三方权利。不制作对外 ZIP，不上传二进制或建立 Release。

## 已完成的机械核对

- `build/stage_beta.py` 只允许两个 EXE、`_internal`、marker 和指定文档进入独立候选目录，不复制工作区、用户 data 或测试报告。
- 从固定 Python distribution、npm lock/实际安装包收集现有 license/notice；Python 顶层命名空间与 EXE 内 PYZ 模块对照，开发/可选工具另标 scope。
- `license-inventory.json` 列实际版本、声明许可证、收集文本及缺失标记；复制 Python 3.12 完整 LICENSE 栈，保留 Tcl/Tk/NumPy 自带文本。它是审查输入，不是认证 SBOM 或合规证明。
- `manifest.json` 记录逐文件 SHA-256；内容审查覆盖文件名、已知本机身份字节、ZIP 内部及 EXE 压缩 Python 模块，不执行提取的代码。
- sounddevice 上游 hook 原收集不同架构、macOS 和 ASIO 的 PortAudio。此 x64/WASAPI 候选只保留 libportaudio64bit.dll，排除无用 ASIO、x86、ARM、dylib；不改 WASAPI 算法。

## 待解决与所有者决定

### 本轮证据及义务分类（2026-10-20）

候选新增 `sbom.cdx.json`（CycloneDX 1.6）、`build-evidence.json`、完整 `requirements-build.lock.txt` 核对。SBOM 同时列 Python 构建环境、npm 锁中所有平台可选包及实际原生文件哈希；它是含构建工具的保守超集，不声称全部 npm 包进入浏览器。Python namespace match 来自两个 EXE 的实际 PYZ；原生文件逐个记录 SHA256，不从 DLL 文件名猜版本。依赖关系图、静态链接子组件和精确权利来源仍待核实。版本快照没有 wheel 哈希，不能声称供应链验证完成。

| 分类 | 已核对事实 / 应采取的行动 | 发行影响 |
| --- | --- | --- |
| 已确认的许可义务 | pystray 0.19.5 附 LGPLv3/GPLv3 文本；库使用告知、许可文本及适用的源码/替换要求不能只靠一个清单满足。冻结 PYZ 的具体替换方案尚未落实。 | 方案落实前阻塞 |
| 已确认的许可义务 | BSD/MIT/PSF 等已收集文本要求保留适用版权、许可和免责文本；需保留组件自身 notices，不能以项目许可证覆盖。 | 机械收集已做，仍需逐件复核 |
| 待确认 | pywebview、pythonnet/clr_loader、WinRT 的实际运行/原生携带项以 inventory + PYZ + native 文件清单交叉核对。缺完整文本的 wheel 不可仅凭 MIT 声明推定完成。 | PyWinRT/proxy_tools 缺项阻塞 |
| 待确认 | PortAudio 仅携带 x64 非 ASIO DLL；sounddevice 的 MIT 与 PortAudio 自身及二进制第三方条款分别审查。Pillow 编解码、NumPy/OpenBLAS、Python/Tcl/Tk、VC runtime、WebView2 Loader/SDK 需要对应实际哈希的来源及许可链。 | 原生链核实前阻塞 |
| 所有者决定 | 项目整体授权、参考边界、LGPL 应用材料和分发条款；本轮不选择项目开源许可证。 | 阻塞 |
| 包外前提 | WebView2 Runtime、.NET、VB-CABLE、豆包均不随包携带；SDK/Loader 文件仍是包内审查对象。 | 不把系统安装器许可误计为已处理 |

本轮重新查阅 [pystray 固定版本 LGPL 文本](https://github.com/moses-palmer/pystray/blob/v0.19.5/COPYING.LGPL)及 [Microsoft WebView2 分发说明](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution)。前者作为 LGPL 要求核对依据，后者区分 Runtime 部署与 Loader/SDK；不是对本项目的法律结论。**法律审查尚未完成，redistribution_ready 始终为 false。**

1. **项目整体授权**：尚无整体许可证。需明确复制、修改、试用与分发授权及贡献来源，确认协议参考和独立实现边界。不能从源码公开推导二进制授权。见 LICENSE_STATUS.md。
2. **pystray 0.19.5**：元数据为 LGPLv3，已收集 COPYING/COPYING.LGPL。库在 PYZ 内，需确定适用的库源码、必要应用材料、替换/重链接和告知方案，并验证方案可操作；附文本不代表义务全部完成。依据：[固定版本 COPYING.LGPL](https://github.com/moses-palmer/pystray/blob/v0.19.5/COPYING.LGPL)、[GNU LGPL v3 第 4 节](https://www.gnu.org/licenses/lgpl-3.0.en.html)。
3. **缺失/版本对应的文本**：部分 PyWinRT 3.2.1 wheel、proxy_tools 0.1.0 声明 MIT 却未附完整 license 文件。应取得对应版本版权和许可，不能凭 SPDX/MIT 字符串补写权利人。[PyWinRT 上游 LICENSE](https://github.com/pywinrt/pywinrt/blob/main/LICENSE)仍需与实际版本对应。其他缺项见 inventory，区分运行与构建可选范围。
4. **原生链**：PortAudio 当前二进制的完整许可、WebView2 Core/WinForms/Loader SDK、Python/Tcl/Tk、Pillow 编解码库、NumPy/OpenBLAS/LAPACK/编译器运行库及 VC runtime 均需核对。总许可证表达式不能代替每个 native 组件材料；以实际文件哈希核对，不从导入成功推断合规。
5. **系统/外部软件**：不随包提供 WebView2 Runtime、.NET 安装器、VB-CABLE 或豆包安装文件。SDK/Loader 与系统 Runtime 不同；[Microsoft 分发说明](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution)仅作为核对入口。
6. **Python、工具与前端**：保留 [Python 许可栈](https://docs.python.org/3.12/license.html)、PyInstaller bootloader exception、BSD/MIT/PSF 等文本。核对锁定 React/React DOM/scheduler/lucide 的运行产物与 notices；TypeScript/Vite/esbuild 只复制许可文本，不将 node_modules 作为运行环境分发。

脚本不替所有者作最终选择。即使内容/隐私审查通过，redistribution_ready 仍为 false，直到明确决定并补齐材料；还需干净 Windows 和授权硬件验收，再单独确认对外试用包。
