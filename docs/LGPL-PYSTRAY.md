# pystray 0.19.5 保留与 LGPL 重组材料

结论：选择方案 A，保留已验证的 pystray，继续使用现有 onedir/PYZ。没有改写托盘。此为技术准备与待审方案，不是已经取得法律合规结论。

| 方案 | 技术与许可代价 | 当前决定 |
| --- | --- | --- |
| A 保留 pystray | 已有托盘生命周期证据；LGPL/GPL 文本、版权、库源码、对应应用材料及重组说明需随分发落实 | 采用；拟走 LGPL 4(d)(0)，待完整重组证据及法律审查 |
| B 宽松托盘依赖 | Qt/PySide 等也有 LGPL/商业条款；wxPython 及其依赖引入新的 GUI 运行时，需重新评估活跃维护、Windows/WebView2 兼容和生命周期 | 本轮未引入，也不虚构已验证的可靠替代品 |
| C 有限 Win32 自实现 | Shell_NotifyIconW、消息循环、TaskbarCreated、DPI、菜单线程和安全退出都需自己维护；许可证更简单不能代替兼容性验证 | 不实施，避免无故改动已验证行为 |

固定版本源码头声明 LGPL v3 或更新版本，Copyright (C) 2016–2022 Moses Palmér。原样保留 COPYING（GPLv3）、COPYING.LGPL 及每个源码文件的版权。来源为 [pystray v0.19.5](https://github.com/moses-palmer/pystray/tree/v0.19.5)。完整上游源码归档在 desktop-ui/licenses/sources，哈希与逐文件匹配证据在 pystray-source-evidence.json；13 个已安装 Python 文件逐字节相等。归档也在候选 licenses/sources 中，未以项目 MIT 重新授权。

现有两个 EXE 的 PYZ 都含 pystray；直接往 EXE 旁放同名 .py 并不能证明它可替换。[PyInstaller 导入机制](https://pyinstaller.org/en/v6.22.3/advanced-topics.html#python-imports-in-a-bundled-app)会优先解析归档。**不声称满足 LGPL 4(d)(1) 的共享库机制。**

拟依据 [LGPLv3 第 4 节](https://www.gnu.org/licenses/lgpl-3.0.en.html) 的 4(d)(0) 提供最小对应源码及对应应用代码，以允许修改库后重新组合。是否足够仍需审查；源码下载链接、只给编译后的 PYZ 或只附两份许可证文本均不能单独证明义务履行。拟交付材料必须包含：

- 精确库源码及版权/许可，所有改动与修改告知（当前无功能改动）。
- 精确应用源码、前端资源源码、spec、构建/运行时 hooks、锁文件、工具链版本、构建及安装说明。主项目已由 WYL 以 MIT 授权原创部分，但协议参考来源边界和完整对应应用材料仍待审，当前不能声称整个重组材料包已具备全部分发权。
- 库使用告知和 LGPL/GPL 文本。若运行时展示版权信息，需同时展示适用的库版权及文本位置；现有 UI 尚无完整法律信息页，发行前复核。
- 不限制用户修改库部分或为调试这些修改进行逆向；发行附加条款不得破坏这些许可。
- 按 GPLv3 第 6 节选定并履行对应源码提供方式；推荐在同一下载位置提供完整对应材料，不能把第三方可变链接当作长期履约保证。是否需要 Installation Information 应按适用条款另行判定，当前没有签名/锁定机制证明材料可省略。

## 本地重组步骤（只在隔离开发目录执行）

1. 保存与候选 build-evidence.json 对应的完整源码快照，核对逐文件哈希及工具链。使用 Python 3.12.10、Node 26.1.0、npm 11.13.0；按 requirements-build.lock.txt 和 npm lock 安装到新环境。
2. 从随附 pystray-0.19.5.tar.gz 取出源码到隔离目录，检查归档哈希。库的 Python 源位于 lib/pystray。修改该副本，保留版权及 LGPL 声明并说明修改。
3. 运行 `powershell -File build/build_portable.ps1 -PystraySource <隔离源码根> -DistPath dist/recombined -WorkPath output/recombined-build`。显式参数只改变构建的模块搜索路径，默认构建清除环境覆盖；不修改已安装库。spec 收集两个入口，因此两个 PYZ 都应包含修改后的库。
4. 使用 PyInstaller CArchiveReader 检查两个 PYZ 内的目标模块，确认修改进入产物。运行非业务 --diagnose-startup；不得连接 BLE、打开音频或启动业务。真实托盘和安全退出的兼容性需要额外本地验收。
5. 保留源码差异、工具链、构建记录、PYZ 证据及诊断报告。可重复构建仅限同一输入；修改库后的 EXE 哈希应变化。

本轮控制实验结果见 PORTABLE_HANDOFF.md 第 15 节和本机 output/mit-* 证据。完整 LGPL 重组分发包、权利条款、公开源码托管履约与专业许可审查尚未完成，因此 BINARY_READY=false。
