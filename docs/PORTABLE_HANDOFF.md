# G10 Control Portable 版本开发交接

> 阶段：第一阶段审查与准备。本文记录代码现状和可复现的检查结果；没有执行 PyInstaller 打包、真实蓝牙测试、Windows 新机测试、硬件实验或系统设置修改。下一位接手者应从第二阶段第 1 步开始，不得把本文计划误读为已完成实现。

## 1. 仓库状态

- 仓库：`https://github.com/long-long1/g10-control`
- 审查时分支：`main`，审查前工作树干净，且跟踪 `origin/main`。
- 审查时提交：`8d170a337b12956a5b9bb6382b44b11790f23189` (`Make IMA decoder independent of external reference checkout`，2026-10-19)。
- 本文件随本阶段提交进入仓库；该提交标识由 Git 提交记录和最终交接报告给出。
- 架构为 Python + pywebview / WebView2 + React / TypeScript；音频桥接是独立 Python 子进程。本轮新增 PyInstaller 初稿 spec/脚本和独立路径管理模块，但尚未接入现有桌面运行时。

## 2. 功能状态（按现有证据分类）

### 已经实机验证

依据 `README.md` 功能表和 `docs/HANDOFF.md`：

- 一台 G10 样机的 BLE / GATT / ATVV 服务发现、能力协商、麦克风会话控制和音频通知。
- 该样机的 128 字节帧、低半字节优先 IMA ADPCM 解码，以及 WASAPI 输出到 VB-CABLE 的播放端 `CABLE Input`。
- 用户在豆包输入法手动开启语音、选择录音端 `CABLE Output` 后确认识别到文字。
- 当前样机飞鼠本身的移动/点击正常；本项目桌面 UI 的按键观察是另一项只读功能。

这些结果只适用于已测试设备、协议配置和环境，不能推导所有商品标称 G10/3K 均兼容。不要修改 ATVV、解码和缓冲/WASAPI 核心实现来迁就打包。

### 代码存在，但没有发行级/便携环境验证

- `desktop-ui/app.py`：pywebview 窗口、托盘、单实例、用户确认后的当前用户启动项、关闭窗口行为和 UI API。
- `desktop-ui/app_runtime.py`：配置存储、服务状态监督、桥接启动/安全停止。
- React UI 的状态页、设备页、设置、日志与诊断导出；`desktop-ui/web/` 可在开发环境构建。
- 配置 JSON 原子写入、默认关闭自动唤起和自动重连，以及缺少本机地址/CABLE ID 时拒绝启动的入口逻辑。
- WebView2 缺失检测、便携路径、打包后主/子进程启动、打包后退出清理、以及无 Python 环境机器运行都未验证。

### 未实现 / 不作为 v0.1.0 发布前提

- 可靠的红键自动唤起豆包；源码 UI 明确显示实测未通过，README 也说明失败。保持默认关闭。
- 可配置按键动作/映射、拦截、自动重连和休眠恢复的发行级实现与回归。
- Portable 目录发现、首次运行向导、正式构建、压缩包、干净 Windows 机器验收。
- 支持任意遥控器；首版只面向已验证的 G10/3K 类型及实际协议匹配设备。

## 3. Portable 风险与逐项建议

风险级别是当前代码审查判断，不代表运行时故障已在打包程序中复现。

| 项 | 代码依据 | 具体风险 | 建议 |
|---|---|---|---|
| A. 开发机设备身份 | `local_config.py:7,10-17` 从仓库旁 `local-settings.json` 或 `G10_BLUETOOTH_ADDRESS` 读取地址；`desktop-ui/app_runtime.py:23,214-215` 在模块导入时读取并向状态对象返回；`app_runtime.py:212-215` 把 VID/PID 固定为 `0x620A / 0x0407`；`desktop-ui/web/src/App.tsx:234` 展示它们。 | 当前已公开快照未发现实际私人蓝牙地址或端点 ID 硬编码；但打包开发目录旁的本地 JSON 会成为身份来源，不能随包分发。UI 的 VID/PID 是固定展示值，并未由当前设备枚举确认，可能误导用户。配置模块把源码目录当配置目录，冻结后位置语义变化。 | 在第二阶段清除对源码相邻本机配置的发行依赖；启动向导从 Windows BLE 设备枚举中让用户选择候选设备，并以实际 ATVV 服务/能力与已验证配置判定兼容，明确拒绝“只看名称就支持”。界面显示实时发现的身份或“不适用”，不要把常量伪装成检测结果。私有地址仅在用户本机配置内保存。 |
| B. Python/Node/开发目录 | `desktop-ui/app_runtime.py:16-20,134-152` 固定仓库路径与 `.venv/Scripts/pythonw.exe`；`desktop-ui/app.py:227-240,282` 固定 `.venv/Scripts/python.exe` 与仓库脚本；`desktop-ui/start_g10_control.cmd:5-21` 依赖 `.venv` 的 `pythonw.exe`；README 源码启动步骤需要 Python 3.12 和 Node/npm。 | 直接启动要求开发环境。打包后仍会因缺少 `.venv` 被拒绝；Node/npm 不需运行时依赖，但需构建期安装。 | 发布采用 PyInstaller `onedir`，将所有 Python 运行时放入发布目录；运行代码不调用外部 Python/Node。构建机使用锁定依赖与 Node 仅构建 React。不得把 `.venv` 直接复制当正式包。 |
| C. 主程序与桥接子进程 | `app_runtime.py:18-20,89-101,124-153` 把桥接作为 `pythonw.exe g10_audio_bridge.py` 子进程并 `cwd=PROJECT_ROOT`；`app.py:220-241` 按键观察器另起 `python.exe raw_input.py`；桥接本身为 `g10_audio_bridge.py`。 | PyInstaller 主 EXE 下 `sys.executable` 是应用 EXE 而非 Python 解释器；现有参数会错误启动应用第二份或找不到 `.py`。冻结进程路径与 `psutil` 查找脚本命令行的单实例桥接检查也不匹配。 | 推荐把主 UI 和桥接分别冻结为 `G10-Control.exe`、`G10-AudioBridge.exe`（同一 onedir/spec，分别 entry point，共用打包依赖或验证可裁剪依赖）。监督器按 `sys.frozen` 与资源路径选择 companion EXE，参数/停止信号/日志契约保持不变。Raw Input 若首版保留也应使用独立 `G10-KeyObserver.exe` 或与 bridge helper 明确路由；若暂不纳入首版，应隐藏不可运行的 UI 入口，不能无声降级。由监督器协调子进程关闭，停止超时保持当前安全语义，不强杀 BLE 进程。 |
| D. React 资源与路径 | `desktop-ui/web/vite.config.ts:3` 使用 `base: './'` 和 `dist`；`desktop-ui/app.py:17,291-295` 从 `APP/web/dist/index.html` 绝对路径加载；`start_g10_control.cmd` 要求该构建产物。 | 相对资源路径适合本地文件，当前构建未指向开发服务器；但打包需将整个 `dist` 放入预期资源位置，并处理 PyInstaller `sys._MEIPASS`/onedir 资源根。工作目录不能作为资源定位依据。 | 先固定 onedir 资源布局并让主程序以 `Path(__file__)`（冻结时应用资源根）解析 UI；始终加载本地 `index.html`，生产启动不启 Vite/dev server。验收检查 HTML 的 JS/CSS 相对 URL，移动整个目录后可显示 UI。 |
| E. 配置、日志、资源和移动 | `app_runtime.py:27-32,41-65,89-100` 配置写 `%APPDATA%\G10ControlPublic`、日志/状态写 `%LOCALAPPDATA%\G10ControlPublic`；`app.py:17-19` import 时创建用户日志目录；`g10_audio_bridge.py:131-140` 硬编码要求 `phase3-vbcable-probe` 路由证明在 `phase2_readonly.ROOT/output`；`local_config.py:7` 配置在脚本相邻。 | 当前是用户目录模式，不是可移动的 portable 配置。更关键的是路由证明在 `.gitignore` 的 `output/` 中，不进入源码/ZIP；干净用户没有证明，桥接无法启动。只读介质下 import 即创建 `%LOCALAPPDATA%` 尚可，但配置选择与迁移无定义。资源/日志的分散规则难以支持移动目录。 | 单一数据根策略：尝试 EXE 所在目录的 `data/`（例如 `portable.marker` 明确启用 portable 模式）；写入失败则退至 `%LOCALAPPDATA%\G10Control`，配置为 `%APPDATA%\G10Control` 或统一到 LocalAppData，并在 UI 明确显示实际位置。一次性迁移/导入由用户确认，不复制机器专属 CABLE ID/地址。路由证明改为首次运行期间生成到数据根并绑定当前端点身份；在证明生成前禁止启动桥接，端点变化后重新提示验证。 |
| F. 无 Python 开发环境 | 同 B、C；`requirements.txt` 有 bleak、numpy、sounddevice、winrt、pywebview、pystray、psutil 等运行依赖。 | 源码启动文档要求本地 Python；当前没有冻结依赖，也没有“仅系统依赖”机器验收。 | onedir 带入 Python 与运行依赖，并在隔离 Windows 11 x64 虚拟机/干净账户验收；验证既不安装也不调用系统 Python/Node。 |
| G. WebView2 / VB-CABLE 检测 | `README.md:46-47` 只列 WebView2 与用户自行安装 VB-CABLE；`app.py:90-99` 查询音频端点名称；`App.tsx:128-129,258` 有手动刷新 UI；`app_runtime.py:124-140` 缺配置时启动拒绝；`g10_audio_bridge.py:131-140` 依赖本机路由证明。 | 未见 WebView2 Runtime 检测/友好错误路径；pywebview 启动错误可能只留在启动器/控制台。CABLE 探测仅按名称分类，CABLE 不存在、重复/歧义、端点变化及“驱动已安装但路由未验证”需在首次向导中解释。 | 启动时调用 WebView2 Runtime 可用性检查/捕捉 pywebview 初始化异常，显示官方安装说明和“重新检测”；不自动下载安装。音频向导以端点名称+方向/唯一性+实际端点 ID 识别候选，用户确认后执行现有合成路由证明，保存结果、端点 ID、采样率和版本；没有 VB-CABLE 时说明需由用户自行安装官方驱动，不修改默认设备、不下载。提供重新检测及重跑路由测试。 |
| H. 托盘/单实例/退出/自启动 | `app.py:24-35` 本地命名 mutex；`:121-143` 写当前用户 Run 注册表，命令固定为 Python 路径+`app.py`；`:163-198` 退出与关闭窗逻辑；`:200-212` 托盘；`:284-304` finally 安全停止服务、释放 mutex。 | 单实例与托盘是代码实现但没有冻结版回归。启动项命令在便携目录移动后失效；冻结时 `sys.executable`/`__file__` 写入方式需专门验证。关闭 UI 到托盘是预期行为，退出路径会等待服务安全清理；强制退出/Windows shutdown 行为未知。 | 单实例保留并验证不同用户会话语义。启动项只在用户明确启用后写入绝对 EXE 路径，移动/找不到时提示修复；Portable 可禁用启动项或标记路径易失。测试关闭进程、托盘完全退出、helper 正常终止；不因停止超时直接 kill。 |
| I. ZIP 敏感信息/隐私 | `local_config.py` 将本机身份读自未跟踪文件；`.gitignore:1-17` 忽略 local-settings、output、日志、录音和二进制；`g10_audio_bridge.py:131-140,325-333` 会读取开发机路由证明并在显式验证模式下写 WAV；仓库 README/HANDOFF 记录没有提交私有值。 | 忽略规则不等于构建清单排除。若对整个工作区打包会意外带入 `local-settings.json`、设备/路由报告、录音、日志、`.venv`、`node_modules`、git 历史。`.gitignore` 也把 `*.dll`/`*.exe` 全忽略，未来打包资源需从明确 staging 目录组装。桥接支持本地验证录音开关，正式调用不应传入。 | 只从干净 staging 目录生成 ZIP，允许列表复制冻结输出、前端 dist、许可文本、说明和空数据目录；拒绝读取 git 工作区直接压缩。打包前扫描归档文件清单与个人路径/地址/端点 ID/日志/WAV/录音等标记；不给正式启动参数传 `--verify-session`。发布复核 ZIP 清单与哈希。 |
| J. 许可/依赖再分发 | `LICENSE_STATUS.md` 声明项目未指定整体许可证；`desktop-ui/THIRD-PARTY-NOTICES.md` 明确当前不是完整 SBOM，且 pystray LGPLv3、pywebview BSD、Python/npm 依赖需上游许可文本；`requirements.txt` 与 `package-lock.json` 锁版本。 | 仓库源码公开不等于项目拥有明确再分发许可；冻结文件会捆绑 Python/npm 的直接及传递依赖。现有 notice 不足以证明满足所有依赖的再分发义务。 | 发布前先由仓库所有者明确项目许可证/分发授权；对实际冻结依赖生成 SBOM/license report，逐一核实传递依赖许可证并随包包含要求的文本和 LGPL 对应材料。检查 pywebview、pythonnet、WinRT、numpy、PortAudio/sounddevice、Pillow 等的实际二进制携带项。此项完成前不要公开 Portable ZIP。 |

## 4. 推荐的 onedir 目录

候选目录（实际 PyInstaller 布局须由第二阶段验证）：

```text
G10-Control-v0.1.0-win64-portable/
  G10-Control.exe
  G10-AudioBridge.exe
  G10-KeyObserver.exe              # 若首版保留只读按键观察
  _internal/                        # PyInstaller Python DLL、扩展与依赖
  web/index.html
  web/assets/...
  licenses/...
  THIRD-PARTY-NOTICES.txt
  README-PORTABLE.txt
  portable.marker
  data/                             # 首次运行创建；设置、路由证明、日志
```

PyInstaller `onedir`（建议先 `--onedir --noconfirm --clean`，后续固定 `.spec`）比 onefile 更适合共享的本地资源、原生扩展和可诊断子进程。主界面与 helper 用不同入口构建为独立 EXE；均放同一目录，子进程路径按冻结应用目录解析而非 `cwd`。具体是否共享 `_internal`、依赖裁剪和启动参数需通过实构建确定，不预先声称成功。React 先用 `npm ci && npm run build`，将 `dist` 复制到 `web/`。

只读解压目录策略：portable marker 存在时优先尝试 `data/`；建立目录/原子写入失败时转到 `%LOCALAPPDATA%\G10Control`，并在界面显示“便携目录不可写，当前数据保存于……”。运行时日志、状态、路由证明都使用同一数据根；`_internal`/`web`/EXE 永远只读。配置和旧开发目录数据迁移不得静默搬运设备身份。

## 5. 设备发现与首次运行向导建议

1. 不连接时显示 BLE 设备选择与“重新扫描”；只在用户启动扫描后查询系统已配对/可见设备，不把地址或 VID/PID 写入发布默认值。
2. 对用户选择设备读取目标 ATVV 服务/特征，核对受支持能力版本、codec 与帧长。只有与已验证的 G10 配置匹配才显示兼容；仅名称或“3K”字符串不能作为支持依据。连接、订阅等业务动作仍由现有白名单状态机处理并保留用户明确操作。
3. 查询音频端点方向，定位唯一 VB-CABLE 播放端和录音端；显示准确的 `CABLE Input` 写入 / `CABLE Output` 录音概念，不触碰 Windows 默认端点。
4. 用户确认后运行现有的合成路由验证，不采集物理麦克风，不保存真实语音；把结果和当前端点身份写入数据目录。缺失、重复、采样率不符或证明失败时提供“重新检测/查看说明”，不自动下载或安装驱动。
5. 最后显示手动豆包工作流与限制；自动唤起保持关闭。BLE 音频链路和 ADPCM 算法保持原样。

## 6. 测试基线（本次真实执行）

执行环境：Windows 工作区 `E:\working\yaokong\g10-control`；全局 Python `3.12.10`、Node `v26.1.0`、npm `11.13.0`。本仓库没有 `.venv`，当前全局 Python 未安装 `requirements.txt` 中的全部依赖。`desktop-ui/web/node_modules` 可用。

| 命令 | 真实结果 | 解释 |
|---|---|---|
| `python -m unittest discover -p "test_*.py" -v`（仓库根目录） | **失败**：Ran 20 tests，13 passed、7 errors；退出码 1。通过的包含 `test_audio` 3 项、`test_local_config` 3 项、`test_phase2` 5 项，以及 handshake 的 2 项。 | `test_doubao_ui_probe`、`test_doubao_voice` 缺 `comtypes`；3 个 handshake 用例执行时缺 `winrt`；`test_live_bridge`、`test_virtual_audio` 导入时缺 `sounddevice`。这是不完整全局环境下不能完成的基线，不可描述为全套测试通过，也不能据此判定功能回归。 |
| `python -m unittest -v test_runtime`（`desktop-ui`） | **失败**：测试模块导入失败，缺 `psutil`；没有测试用例运行，退出码 1。 | 桌面测试尚未验证；不是通过。 |
| `npm run build`（`desktop-ui/web`） | **通过**：`tsc -b && vite build` 成功；Vite 6.4.4，1578 modules；产物 `dist/index.html`、CSS、JS；退出码 0。 | 只证明前端在当前 Node/npm 依赖环境下可构建，不证明 WebView2 加载或打包运行。`dist/` 是被忽略的构建产物，未纳入交接提交。 |
| 静态路径审查（`rg` 检查路径/启动方式/设备标识） | **已执行，非自动测试**。 | 发现项详见第 3 节；没有做静态类型以外的 linter 检查。 |

本次没有执行 `pip install`、真实设备、BLE/GATT 写操作、按键/鼠标模拟、管理员操作、默认音频设置修改、PyInstaller 构建或干净 Windows 用户测试。

## 7. 未解决风险

- 便携模式下主/子进程冻结与资源定位尚未实现；没有 spec 和生成包。
- 路由证明目前绑定原开发工作区 `output/phase3-vbcable-probe`，干净机器无法直接启动桥接；必须设计首次验证写入数据目录。
- WebView2 Runtime 探测、VB-CABLE 唯一端点和设备重发现 UX 尚未接入。
- PyInstaller 对 WinRT、pywebview/WebView2、numpy、sounddevice/PortAudio、pythonnet/comtypes、pystray 的隐藏导入、DLL 收集和原生依赖尚未验证。
- 注册表启动项持久化路径在移动 Portable 目录后会失效；托盘/单实例/安全退出只在源码运行路径有实现。
- 项目没有总体许可证，第三方依赖再分发清单未完整生成。
- 本阶段 Python 测试因为全局环境缺依赖未全量运行；WebView2/设备链路没有在任何新机器上验证。

## 8. 第二阶段改造顺序与逐步验收

不在本阶段执行。接手时仍先保护已验证 BLE/ATVV、ADPCM、WASAPI、VB-CABLE 链路，不处理 Windows 搜索弹窗，不扩展到所有遥控器。

1. **构建基线与边界测试**：新增冻结路径 resolver、数据目录选择、只读目录回退、helper 命令构造的单元测试（纯临时目录/假进程）；补齐 requirements 虚拟环境后运行现有测试。验收：测试真实报告全通过或逐项说明失败；不需硬件，不声称实机通过。
2. **路径和配置抽象**：修改 `local_config.py`、`desktop-ui/app_runtime.py`，使打包数据目录可注入、配置与资源根分离，兼容源码开发模式；移除对源码相邻设备配置作为发布配置的依赖。验收：可写便携目录写入其 `data/`；只读目录自动落到 LocalAppData；目录移动不丢设置；缺配置仍安全拒绝 BLE 服务。
3. **首启设备/音频检测**：修改 `desktop-ui/app.py`、`desktop-ui/app_runtime.py`、`desktop-ui/web/src/App.tsx` 与相关 UI 组件；用现有受控协议入口匹配设备，检测 WebView2、端点和 CABLE route proof。验收：无设备、未知设备、缺 WebView2、无/多 CABLE 端点、失败证明都有明确状态和重新检测；不改默认音频、不安装驱动；自动唤起默认关闭。
4. **冻结桥接监督器**：修改 `desktop-ui/app_runtime.py` 和 `desktop-ui/app.py`，将 Python 脚本调用改为 onedir companion helper，并适配进程识别、状态路径、停止信号。必要时新增 `desktop-ui/bridge_entry.py`、`desktop-ui/key_observer_entry.py`。验收：打包后从含空格路径启动 helper；无系统 Python；正常停止释放资源；超时不会强杀；重复实例能被阻止。
5. **PyInstaller 构建和静态前端封装**：新增 `build/` 下 `.spec`、构建说明/脚本与 staging allowlist；修改 `desktop-ui/app.py` 的资源定位及 `desktop-ui/web/vite.config.ts`（若测试发现需要）。验收：构建输出有主程序、helper、`_internal`、本地 `web`、许可和说明；断网启动不访问开发服务器；整个目录移动后静态 UI 能加载。
6. **生命周期/发布隐私/许可**：修改 `desktop-ui/app.py` 启动项逻辑、日志初始化和退出处理；更新 `LICENSE_STATUS.md`、`desktop-ui/THIRD-PARTY-NOTICES.md` 与 portable 使用说明；新增 ZIP 清单隐私扫描。验收：托盘隐藏、恢复、单实例、完全退出、重启、移动路径后的 Run 项都可重复验证；归档没有 local-settings、蓝牙地址、端点 ID、`output/`、日志、WAV、源码历史或开发依赖；许可证审查确认后才允许发布 ZIP。
7. **Windows 11 干净环境验收**：使用不含 Python/Node 的干净 VM/账户解压 staging 包。先验证 WebView2 缺失提示/重新检测和只读目录回退，再按自愿的手动流程验证匹配的 G10 与已安装 VB-CABLE。验收记录机器条件、实际版本、每项结果；未实测就明确标注未验证。只有用户另外授权才进行真实设备会话；本阶段没有进行这一步。

## 9. GPT-6.1 Sol 不得误报为通过

以下项目**没有通过/没有执行**，尤其不可将静态构建结果泛化：

- 全部 Python 根测试：本次有 7 errors，且缺少 `comtypes`、`winrt`、`sounddevice`。
- `desktop-ui/test_runtime.py`：缺少 `psutil`，零用例运行。
- PyInstaller onedir/onefile 打包、运行、无 Python 新机运行、目录移动、只读目录行为。
- pywebview/WebView2 冻结资源加载、WebView2 缺失提示和重新检测。
- 主程序与桥接/Raw Input 子进程打包启动、单实例、托盘和安全退出回归。
- Portable 首次运行设备发现、ATVV 能力匹配、VB-CABLE 检测/路由证明生成与重检测。
- 任何新 G10 / 3K 型号、任何非已验证设备的 BLE/ATVV/ADPCM/WASAPI 实机兼容性。
- 红键自动唤起豆包、按键映射、自动重连/休眠恢复。
- Portable ZIP 的隐私扫描、完整第三方许可证/SBOM 和公开发布审核。
- README/HANDOFF 中已记录的旧实机成功链路不能冒充本次测试结果；本次没有连接设备。

## 10. 后续准备进展（2026-10-19）

本轮基于上面的基线提交 `78c053381cd804aaa08ddb32e8dee679036ddd76` 开展。工作环境为 Windows 11 x64、全局 Python 3.12.10；仓库虚拟环境为 `.venv`（Git 忽略），未向全局 Python 安装包。

### 新增文件

- `portable_paths.py`：独立路径 resolver，未被 `app_runtime.py` 或桥接引用。
- `test_portable_paths.py`：4 个纯临时目录测试，涵盖移动便携目录后读回 data、模拟便携目录不可写并回退、源码/冻结资源与 exe 目录分离、资源/data 路径越界拒绝及数据保存。
- `requirements-build.txt`：引用 `requirements.txt` 并固定构建工具 `PyInstaller==6.22.3`；单独用于构建环境。
- `build/portable_onedir.spec`：主程序与 `g10_audio_bridge.py` 两个入口构建到同一个 onedir 输出树；主 EXE 静态资源目的地是 `web/dist`，对应当前 `app.py` 冻结路径预期 `<_MEIPASS>/web/dist/index.html`。
- `build/build_portable.ps1`：在仓库 `.venv` 中执行前端 `npm ci` / `npm run build`，再调用 spec；不会修改系统设置或生成 ZIP。
- `.gitignore`：忽略 PyInstaller 中间文件和 `dist/` 构建产物。

### 路径模块接口

```python
from portable_paths import resolve_paths

paths = resolve_paths()  # source / frozen 自动判断
ui_file = paths.resource("web/dist/index.html")
settings_file = paths.data_path("settings.json")
```

`RuntimePaths` 区分 `resource_dir`、`executable_dir`、`data_dir`。源码模式资源根来自模块位置；冻结模式资源根来自 PyInstaller `sys._MEIPASS`（可注入覆盖）；exe 目录来自 `sys.executable`。默认在 exe 同级存在 `portable.marker` 时启用便携模式，先对同级 `data/` 做创建和真实临时写入探测；探测报 `OSError` 时回退到 `%LOCALAPPDATA%\G10Control`。`RuntimePaths.resource()` 与 `data_path()` 均阻止 `..` 越界。测试通过注入 `probe_writable` 模拟 ACL/只读失败，不改真实 ACL。模块目前是准备件，未影响现有配置、日志、设备身份或桥接路径。

### Python 环境与测试结果

- 创建仓库独立 `.venv`，使用 `python -m pip install --upgrade pip` 及 `.venv\Scripts\python.exe -m pip install -r requirements.txt`。`comtypes 1.4.17`、WinRT 3.2.1 组件、`sounddevice 0.5.6`、`psutil 7.2.2` 均按项目固定版本成功安装；未改 `requirements.txt`，未用全局 Python。
- `\.venv\Scripts\python.exe -m unittest discover -p "test_*.py" -v`（仓库根目录）：**43 run, 43 passed, 0 failures, 0 errors, 0 skipped**；包含新增 4 项路径测试及原有 39 项离线测试。
- `..\.venv\Scripts\python.exe -m unittest -v test_runtime`（`desktop-ui`）：**5 run, 5 passed, 0 failures, 0 errors, 0 skipped**。
- 上述测试只覆盖离线替身/本地逻辑；handshake、设备、声卡测试没有连接 BLE、打开硬件音频端点或修改音频设置。通过不代表实机或便携环境验证。

### PyInstaller 初稿构建结果

- 执行 `powershell -NoProfile -ExecutionPolicy Bypass -File .\build\build_portable.ps1`：React `npm ci` 与 `npm run build` 均通过（Vite 构建 1578 modules）。首次 PyInstaller 尝试因 spec 对 `SPECPATH` 的目录层级假设错误，在 Analysis 前退出。修正后第一轮 Analysis 成功但 `COLLECT` 收参错误（TOC 项被展平）；再次修正 spec 后才完成最终构建。
- 执行 `\.venv\Scripts\python.exe -m PyInstaller --noconfirm .\build\portable_onedir.spec`：**退出码 0，PyInstaller 6.22.3 Build complete**。生成 `dist\G10-Control\G10-Control.exe`、`G10-AudioBridge.exe`、`_internal\` 及 `_internal\web\dist\index.html` 和相对资源。初稿静态资源目标路径与现有 `APP/web/dist/index.html` 冻结预期相符。
- PyInstaller Analysis 有警告，包括 Windows 目标下可选 POSIX 模块、若干 WinRT 子模块和 `pycparser.lextab/yacctab` 未发现。Warning 文件在被忽略的 `build/portable_onedir/` 中。需核查哪些是可选项并在无硬件条件下验证各模块导入。
- 这里只确认 spec 能完成分析、exe 组装和 onedir 收集。**没有启动生成的任一 EXE**；也未证明 helper 被现有 supervisor 正确调用、WebView2 能启动、冻结 WinRT 能工作、托盘/安全退出有效或音频可用。因此它不是已运行验证或 Portable 产品验收。

### 本轮仍未解决及下一轮优先任务

1. 优先完善 `portable_paths.py` 的测试/接口评审，再以最小 diff 接入 `desktop-ui/app_runtime.py`，让设置、日志、桥接状态与资源目录使用统一 resolver；不要改 `g10_audio_bridge.py` 音频算法和协议。补上源码模式和冻结模式的路径回归测试。
2. 修正 `app_runtime.py` 子进程启动器：onedir 下从 exe 同级定位 `G10-AudioBridge.exe`（当前 spec 的实际同级输出），源码模式仍保留现有脚本路径；对命令构造加假进程测试。评估按键观察 helper 是否需要独立打包，不能声称现有 `.venv` 路径已解决。
3. 逐项检查本次 `build/portable_onedir/warn-portable_onedir.txt` 的 WinRT/Python 运行时告警，并先增加无硬件的冻结导入/启动诊断；在用户明确允许前不进行 BLE 或设备音频验证。
4. spec 当前把主 EXE 与桥接 EXE 汇入同一 `dist/G10-Control` 并共享 `_internal`，但没有运行兼容性验证。先在不启动服务的约束下完成 UI/WebView2 启动评审和 helper 参数入口，再做纯本地冻结程序启动/退出验证。
5. `portable_paths.py` 还未将 `portable.marker`/LocalAppData 选择接入运行时；`local_config.py` 仍从源文件相邻配置取设备身份；桥接仍要求开发工作区 `output/phase3-vbcable-probe`。设备发现/首次向导、WebView2 缺失提示、VB-CABLE 检测与新机路由证明均未实现。
6. 项目总体许可证仍未确定。不得生成/发布 ZIP 或 Release，直到依赖许可与分发授权审查完成。

本轮只改路径准备件、测试、构建准备、忽略规则和本文档；没有修改 `app_runtime.py`、`g10_audio_bridge.py`、协议、ADPCM 或设备配置流程。
