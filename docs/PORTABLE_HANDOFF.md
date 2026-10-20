# G10 Control Portable 版本开发交接

> 最新阶段：第 14 节（2026-10-20 离线恢复及发行准备），第 13 节为上一轮已验证背景。Windows 11 x64 v0.1.0 Beta 本地候选功能轮（2026-10-20），见第 13 节。第 1–12 节保留历史审查和各轮基线，其中“尚未接入/未构建/未运行”等描述仅代表当轮状态。本轮一次真实 VB-CABLE 合成验证通过；真实 BLE 及干净电脑验收仍待完成，候选目录尚不能对外分发。

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

## 11. 第三轮：Portable 运行时接入与冻结启动诊断（2026-10-20）

本轮基于 `a322f32cb3e4b5d67989d12bdb444d020a93c752`，仅处理运行时路径、冻结子进程与本地启动诊断。没有修改 `g10_audio_bridge.py`、BLE/ATVV、ADPCM、WASAPI 或缓冲算法；没有连接 G10、启动桥接业务、打开音频流、执行键鼠模拟、安装驱动或发布 ZIP/Release。

### 运行时路径及兼容边界

- `portable_paths.runtime_paths()` 缓存单次解析，主运行时、冻结配置及入口共用它；`RuntimePaths.frozen` 区分启动方式，`web_index` 区分源码与冻结静态资源布局。源码资源为仓库 `desktop-ui/web/dist/index.html`；冻结资源为 `<sys._MEIPASS>/web/dist/index.html`，companion EXE 则始终在 `<sys.executable.parent>`，均不依赖工作目录。
- spec 会在 onedir 的 EXE 同级生成空 `portable.marker`。有 marker 时尝试 `data/` 并做实际临时文件写入探测；失败回退 `%LOCALAPPDATA%/G10Control`，保存 `fallback_reason`。两个目录都不可写时明确报错，不吞掉错误。
- 主程序设置为数据根 `settings.json`，桌面/桥接日志在 `logs/`，状态及停止信号在 `runtime/`，按键观察的源码版临时文件也在数据根。WebView2 的用户数据位于 `webview/`；隐藏诊断使用独立 `webview-diagnostic/`。快照/诊断报告返回实际数据路径、portable 标记和回退原因。
- 源码版仍读取仓库旁的本机 `local-settings.json`，并保留环境变量覆盖；冻结版只从所选数据根 `local-settings.json` 读取本机身份，不读取 `_internal` 或开发机旁的身份文件。没有静默复制旧身份或配置。本轮统一设置目录后，旧 `%APPDATA%/G10ControlPublic` 设置不会自动迁移；旧本地资料保留原处。
- 源码桥接仍为 `.venv/Scripts/pythonw.exe g10_audio_bridge.py ...`；冻结桥接为同级 `G10-AudioBridge.exe ...`，cwd 为 EXE 目录。原有业务参数、增益、默认关闭的自动唤起、状态文件和安全停止契约保留。
- 外部进程检测兼容脚本绝对路径及冻结 EXE 的 `exe/name/cmdline[0]`；能阻止其他便携副本的桥接实例，只检查、不终止外部进程。正常停止写信号并等待；超时保留进程所有权，可重试，绝不 `kill/terminate`。
- 窗口模式 PyInstaller 会将 Python stdio 设为 `None`；入口对此做文件重定向。受监督桥接重开对应 `service.log`，启动错误另存数据根 `logs/g10-bridge-last-error.txt`。新增入口仅包装现有 `main()`，不改业务实现。
- 当前用户启动项在冻结模式保存 EXE 命令，源码模式保存 Python + 脚本命令；只测试命令构造，本轮没有写注册表。Portable 移动后既有启动项仍需要用户修复。
- 当前 spec 没有 `G10-KeyObserver.exe`。冻结版按键观察入口会明确拒绝并提示使用源码版；本轮不新增 helper，也未执行按键观察。源码观察器补齐既有 `time` 导入遗漏。

### 安全诊断方法

`desktop-ui/control_entry.py` 与 `bridge_entry.py` 为冻结入口。只有显式 `--diagnose-startup REPORT_JSON` 才进入诊断；解析器拒绝业务启动参数。诊断不调用桥接业务 `main()` 的正常分支：只以 `--help` 执行参数解析，并在任何业务许可、设备配置和路由证明检查前退出。进行必需模块导入、numpy 内存计算、CFFI 声明解析、WinRT DataWriter/DataReader 纯内存往返。PortAudio 只随 sounddevice 做库初始化，没有查询/打开录放音流。

主程序诊断会初始化 Application 的设置及监督器对象，确认 service 没启动，校验 HTML 中 JS/CSS 是存在的本地相对文件。`--diagnose-webview` 另创建隐藏 WebView2 窗口加载实际 React 产物，**没有 `js_api`**，前端无法调用 BLE、音频、按键或注册表方法。DOM 检查 React 根节点、正文和样式表，完成即销毁窗口；有 20 秒窗口 watchdog 和 45 秒诊断进程超时。

可复现命令（仓库根目录，构建后）：

```powershell
.\.venv\Scripts\python.exe build\diagnose_portable.py
```

该脚本仅复制两个 EXE、`_internal` 和 marker 到 `output/portable startup .../first location`，隔离 AppData、清除 G10/Python/WebView2 环境覆盖，将 PATH 限定到 Windows System32；从与程序不同的 cwd 启动。检查初始目录及移动到含中文/空格目录后运行，再用同名 `data` 文件阻止目录创建以实测回退；真实 ACL 拒绝另由注入 PermissionError 的测试覆盖。它不会修改系统 ACL。隔离副本、报告与日志保留在忽略的 `output/` 中，不是发行包。

正常主程序启动显式选 `edgechromium`，预检查 pythonnet/WinForms、WebView2 托管 DLL、native loader 和 `GetAvailableBrowserVersionString`。缺依赖时记录日志及显示错误/手动安装说明，不自动安装，也不回退旧 MSHTML。当前依赖不只有 WebView2：仍需系统 .NET Framework（pywebview 6.2.1 的检查下限为 4.6.2）。没有模拟卸载系统 Runtime。

依据：[PyInstaller 运行时目录](https://pyinstaller.org/en/stable/runtime-information.html)、[窗口模式 stdio 限制](https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html)、[Microsoft WebView2 版本探测 API](https://learn.microsoft.com/en-us/dotnet/api/microsoft.web.webview2.core.corewebview2environment.getavailablebrowserversionstring)。另核对本机固定版本的 pywebview `platforms/winforms.py`、`edgechromium.py` 和 pycparser/WinRT 源码及类型声明。

### 构建警告审查

两次 Analysis 原来会覆盖同一个 `warn-portable_onedir.txt`；现在 spec 分别保存 `build/portable_onedir/warn-control.txt`、`warn-bridge.txt`。本次两份各 311 条模块诊断记录（含 missing、excluded、runtime；集合一致）。没有通过 excludes 或压制日志来隐藏警告。

| 组别 | 判断及证据 |
|---|---|
| `pwd/grp/posix/fcntl/termios/_posix*`、macOS 的 AppKit/WebKit、Android、Xlib/GTK、Qt/CEF | 平台分支或未选渲染器；目标为 Windows + WinForms/WebView2，不需要为这些模块增装依赖。 |
| Bottle 的 gunicorn/gevent/twisted/mako 等可选服务器/模板，Pillow 的 olefile/defusedxml，setuptools 编译辅助模块 | 当前本地静态资源服务器、托盘内存图像不走这些分支；默认资源服务实际运行通过。当前不使用 TLS，自签名证书的 cryptography 分支也未使用。 |
| `ConfigParser/cPickle/urllib.quote` 等旧 Python 名称、`annotationlib/_typeshed`、`ctypes._CData*`、multiprocessing 的函数/异常、`six.moves` 和 PyInstaller importer | 兼容/类型声明/动态提供的对象被当模块分析，不是本轮所需的新依赖；冻结模块导入已实际执行。不能据此宣称所有 multiprocessing 分支已验证。 |
| `numpy._core.*` 大量函数/标量类型，yaml/threadpoolctl 等 | 多数是从扩展/重导出提供的属性，不是独立文件。冻结 numpy 导入及原生数组内存运算通过；yaml、f2py 编译及线程池控制等可选功能未使用。 |
| `pycparser.lextab/yacctab`、`cffi._pycparser` | 固定的 pycparser 3.11 是递归下降解析器，兼容构造参数不再使用 PLY 表；CFFI 首选独立 pycparser，另有可选旧路径。两个 EXE 都实际完成 `FFI().cdef(...)`，没有缺表错误。 |
| `System.*`、`Microsoft.Web`、`Microsoft`，旧 MSHTML 的 `WebBrowserInterop` | CLR 命名空间由 pythonnet 动态加载，不是常规 Python 包；实际 .NET/WebView2 DLL 加载、Runtime 版本探测和隐藏窗口渲染通过。旧 MSHTML 未选用。 |
| `winrt.windows.system/ui/security/applicationmodel/networking` 和 `bluetooth.rfcomm` | 本机固定 WinRT 组件的类型声明涉及其他 API：如 FileRandomAccessStream 的用户接口、设备配对凭据/选择器颜色/后台触发器、经典蓝牙 HostName/RFCOMM。它们不等于 BLE/GATT 当前入口的导入失败。所需 Bluetooth、GATT、Enumeration、Streams、Foundation/Collections 均在两个冻结 EXE 导入成功，Streams 纯内存往返成功。未安装这些扩展命名空间，未声称相关 API 可用；GATT 硬件调用的依赖闭包仍待后续授权验证。 |

结论限定为：**本轮覆盖的冻结导入、参数入口、内存逻辑和 WebView2 渲染没有发现真实必需依赖缺失**。没有以导入成功代替 WinRT 蓝牙、音频业务或全部可选分支运行验证。spec 明确收集 `pycaw.pycaw`，不依靠变量形式的动态 import 被自动识别；未增加或升级 `requirements.txt`。

### 实际执行结果

环境仍为仓库 `.venv` 的 Python 3.12.10、PyInstaller 6.22.3 / hooks 2026.8，Windows 11 x64（构建日志为 10.0.26200）。所有下列结果均为本轮实际执行，非计划：

| 检查 | 结果 |
|---|---|
| 根目录 `.venv/Scripts/python.exe -m unittest discover -p "test_*.py" -v` | **46 run, 46 passed**，0 failure/error/skip。日志 `output/portable-root-tests.log`。 |
| `desktop-ui` 内 `../.venv/Scripts/python.exe -m unittest discover -p "test_*.py" -v` | **18 run, 18 passed**，含原 5 项与新增 13 项。日志 `output/portable-desktop-tests.log`。不要只运行旧 `test_runtime` 而漏掉新 `test_portable_runtime`。 |
| `build/build_portable.ps1` | `npm ci`、`npm run build` 及 PyInstaller 成功，退出码 0；React 1578 modules。日志 `output/portable-build-round3.log`。 |
| 最终 `.venv/Scripts/python.exe -m PyInstaller --clean --noconfirm build/portable_onedir.spec` | **退出码 0，Build complete**；最后一轮入口及 stdio 修改已纳入此构建。日志 `output/portable-build-final.log`。 |
| `build/diagnose_portable.py` 最终运行 | **6 次独立 EXE 启动全部退出码 0，全部报告 ok=true**。日志 `output/portable-startup-final.log`，报告目录 `output/portable startup cdu21iwn/`。 |

新增测试覆盖：源码/冻结资源根、目录移动、无 marker、数据写入拒绝/双目录拒绝、冻结配置身份路径、统一设置/日志/状态根；以假 Popen/进程枚举验证两种命令、原参数、默认不自动唤起、缺 helper、启动失败关闭句柄、重复启动/外部桥接阻止、正常停止、已退出停止、超时不强杀且可重试、冻结启动项命令、未打包按键观察器的明确拒绝、窗口版 service.log、资源越界/缺失、诊断不调用业务方法。没有删除或跳过原测试。

最终 6 次启动记录：

| EXE / 场景 | 实际验证 | 边界 |
|---|---|---|
| `G10-AudioBridge.exe` / 初始便携目录 | 冻结模块导入、numpy/CFFI/WinRT 内存检查、桥接 `--help`、正确 portable 路径；自行退出 0 | 没有给业务许可参数，没有调用正常桥接分支。 |
| `G10-Control.exe` / 初始便携目录 | 同上，加 Application 初始化与实际 React/WebView2 渲染；自行退出 0 | 没有暴露 JS 业务 API，没有创建托盘或测试 mutex。 |
| `G10-Control.exe` / 移动到中文及空格目录 | 再次实际渲染，data 根跟随新目录，测试哨兵文件仍可读；自行退出 0 | 不代表已有 Windows 启动项随移动自动修复。 |
| `G10-AudioBridge.exe` / 移动目录 | 导入/内存/参数检查再次通过，路径正确；自行退出 0 | 未连接 BLE。 |
| `G10-Control.exe` / data 创建失败 | 保存明确 WinError 183 回退原因，数据及 WebView2 profile 落到隔离 LocalAppData；实际 React 渲染、自行退出 0 | 用同名文件触发实际创建失败，未更改系统 ACL。 |
| `G10-AudioBridge.exe` / 同一失败场景 | 同样选择隔离 LocalAppData，导入/内存/参数检查通过；自行退出 0 | 未打开音频流。 |

三个渲染场景均报告 `renderer=edgechromium`、Runtime `155.0.4283.62`、`react_children=1`、`stylesheets=2`、`text_length=653`，加载实际 `index-D9DxHMbo.js` / `index-C3blFDMn.css`。资源来自 pywebview 自带 Bottle 的 `127.0.0.1` 静态服务器，不依赖 Vite、Node 或外部网络。所有报告 `business_started=false`；主程序另报告 `service_running=false`。诊断结束后未发现存活的 G10 主/桥接 EXE。本轮确实运行了两个生成的 EXE，但**没有执行正常业务启动、托盘交互、单实例冲突或真实子进程的 BLE 清理验收**，停止契约只以假进程测试验证。

最终本机构建 EXE SHA-256（仅定位本轮二进制，不是发行签名）：

```text
G10-Control.exe      18A77E4D8AA3E24797F112F4DFE7E476926C45B546D6A4AD480889E95F1FBAF6
G10-AudioBridge.exe  8CD494E3F24B8FA984AEFF19DF9D3B9DE09CC91EFAC24111CE548CF862564EED
```

### 下一轮仍需完成（本轮结束后等待用户确认）

1. **音频路由证明**：核心 `select_verified_pair()` 仍依赖原 `ROOT/output/phase3-vbcable-probe`，本轮未移动或伪造证明。冻结业务目前不能因此被宣称可用。需设计由用户确认的合成路由验证，将证明绑定当前端点 ID/采样率并写入数据根；缺失/失效时安全拒绝。禁止为了打包放宽证明门槛或改动音频算法。
2. **设备发现**：去除“已有地址即支持”的发行依赖，经用户启动扫描、选择设备和受控协议能力检查判定兼容；设备身份只保存在本机数据根。当前固定展示的 VID/PID/validated 文案仍不代表实时发现。
3. **首次运行向导**：解释无设备/未知能力、缺失或歧义的 VB-CABLE、未验证路由、WebView2 缺失与手动处理；显示实际数据目录及只读回退原因。完善配置导入和启动项移动提示。本轮没有实现完整向导或设备 UX。
4. **干净电脑验证**：隔离 PATH 不是卸载 Python/Node，也不是干净 Windows 验收。需在无开发环境的 Windows 11 x64 上验证 WebView2/.NET 有无、真正只读目录 ACL、标准用户、首次启动与正常托盘/单实例/退出；获得明确设备授权后另验桥接真实正常启动、重复实例阻止、安全停止/超时、VB-CABLE 与 G10 音频。按键观察 helper 仍未打包。
5. **发行前约束**：总体许可证、第三方 notice/SBOM、许可材料及隐私 allowlist 审查仍未完成。本轮只提交源码/测试/交接文档；未创建 ZIP、未上传二进制、未推送 Release。后续公开分发需单独确认。

## 12. 第四轮：本机 VB-CABLE 路由证明与 Portable 持久化（2026-10-20）

基于 `3b918b967d9d9731801ebf5e89552f01464be05e`。本轮仅实现本机 VB-CABLE 检测、用户确认后的合成路由验证、证明持久化和桥接启动门槛。**真实路由验证待授权、待实测**；本轮没有枚举真实音频端点、打开真实音频流、连接 BLE、执行键鼠模拟、安装驱动或更改 Windows 默认音频设备。没有开发 BLE 发现、完整首次运行向导或 ZIP 发行。

### 原流程审查及保留边界

原 `g10_audio_bridge.select_verified_pair()` 从 `ROOT/output/phase3-vbcable-probe` 读取两个旧 JSON，检查 `passed`、同名活动端点 ID 是否一致及 48 kHz。开发电脑的这些输出不属于发行资源，其他用户不能依赖。本轮只替换该函数的证明入口；`g10_audio_bridge.py` 的其他函数与控制流不变。

原 `virtual_audio_probe.select_devices(..., 'vbcable')` 要求唯一标准 `VB-Audio Virtual Cable`、CABLE Output 为输入/录音方向、CABLE Input 为输出/播放方向、双声道，以及唯一活动 Core Audio 同名身份，拒绝静音/零音量，无物理端点 fallback。原 `probe()` 使用共享 WASAPI float32 双声道，先检查输入/输出设置，以原 `test_signal()` 的四段低幅度多音合成信号（总计 1.48 秒）写入 CABLE Input，并在 CABLE Output 的内存缓冲接收，原 `correlate()` 以任一声道绝对相关性大于 0.8 判定。缓冲上限 6 秒，原 finally 比较默认端点，默认不保存捕获内容。

**`virtual_audio_probe.py` 完全未修改**，没有改波形、相关性算法、WASAPI stream 参数/处理或 BLE/ATVV、ADPCM、缓冲算法。新 `audio_route.py` 包装并调用该真实流程，不会把检测成功或 `passed=true` 单字段当作完整证明。

### 使用方式与证明策略

1. 用户进入“语音设置”，点击“检测 VB-CABLE”。只有此显式操作或用户启动桥接前的复核才枚举音频元数据；启动程序和定时状态刷新不自动扫描端点。检测没有打开录放音流，也不创建成功证明。
2. UI 分别展示播放端（写入）CABLE Input、录音端（读取）CABLE Output 的名称、ID 和 48000 Hz。驱动/方向缺失、重复 WASAPI/Core Audio 端点、非活动状态、静音/零音量、元数据不可读或采样率不符都会拒绝。共享格式也必须支持双声道；不自动调整格式或音量。
3. 检测成功生成绑定当前两个端点及格式的 5 分钟一次性确认 token。“确认并验证路由”显示具体操作说明，再向后端传入 token 和显式布尔确认；未确认、错误/已使用/过期 token 均不能触发 probe。确认后重新枚举，端点变动时在打开流之前拒绝。验证期间禁止同一 UI 启动桥接，存在自有或可识别的外部桥接进程时拒绝检测/验证。
4. 复用原 `probe(info, ..., 'vbcable')`，没有可导入“成功结果”的 UI API。原 probe 的默认设备检查保留，新策略另要求六个默认端点角色均可读取，前后默认身份相同，验证结束后两个虚拟端点及格式仍一致。保留原大于 0.8 阈值和允许反相信号；增加非有限值、采集不完整、输入流状态异常及输出 underflow 的拒绝检查。相关性上界仅容许 1e-6 的浮点舍入误差。
5. 证明原子保存到 **`<实际数据根>/audio/route-proof.json`**：schema 1、验证版本 `vbcable-synthetic-1`、带时区的验证时间、两端的 ID/名称/方向/采样率/共享格式、默认端点未变化标记及原 probe 的纯数值结果。临时文件 flush/fsync 后 replace，不保存 WAV、PCM 或真实音频。旧开发目录证明不自动导入或充当 fallback。
6. 证明有效期固定为 **30 天**，时钟显著超前、格式损坏、版本不匹配、失败/缺失数据都拒绝。程序重启后先做文件/版本/时间校验，显示“已有证明，需重新检测当前端点”，此时不标为当前已验证；检测或启动桥接再用实时端点身份校验。设备索引不持久化，允许枚举顺序变化，但端点 ID/名称/格式变化必须重新验证。
7. 主监督器在 Popen 前调用 `require_verified()`；桥接脚本和冻结桥接 EXE 的 `select_verified_pair()` 再独立枚举并验证同一数据目录的证明，然后才可能进入原业务流。缺失/过期/损坏证明在音频枚举之前就拒绝；父进程已通过但之后文件/端点变化，子进程仍会拒绝。不会为了使第一次运行通过而放宽 gate。
8. 用户确认开始重验时先撤销旧成功证明。探测失败、默认端点变化、热插拔、校验失败或保存失败，不留下可用的旧成功记录；拒绝确认或用户取消确认框不会启动音频或主动删除原证明。

源码模式及冻结模式都使用现有 `runtime_paths()` 数据根；可写 Portable 为 EXE 同级 `data/`，不可写时为 LocalAppData/G10Control，源码默认也是 LocalAppData。移动整个可写 Portable 目录会携带证明；搬到其他电脑仍必须匹配当地端点身份。切换数据根不会静默搬运或迁移证明，需要在新数据根重新验证。

默认手动工作流的桥接录音端身份现在来自真实路由证明，不再要求预先用开发脚本写 `cable_capture_id`。原设置 JSON 的 `virtual_microphone_id` 保留为兼容字段，不负责选择实际路由。实验性自动唤起仍默认关闭，其独立旧配置检查保留：启用时录音 ID 必须与证明匹配，不匹配会明确拒绝；本轮未扩展自动唤起。G10 蓝牙地址配置仍是另一项启动前提，本轮不做设备发现。

状态页和语音设置不再凭“CABLE Output”名称显示已验证；只有当前端点与有效证明匹配才显示路由验证通过。UI 显示证明实际路径及失败原因，可重新检测/验证。这是单项路由设置页，不是完整首启向导。

### 真实验证授权边界

本轮未获得打开真实 VB-CABLE 端点的授权，**因此真实 Windows 音频路由结果仍为待验证**。没有将模拟结果写入正常 Portable 数据目录或当作本机实测证明。

后续用户授权时，具体操作仅为：确认唯一的 CABLE Input 播放端和 CABLE Output 录音端；以 48000 Hz 双声道共享模式向前者发送约 1.48 秒的原低幅度合成信号，短时从后者读入内存（上限 6 秒），计算相关性并核对默认端点未变；成功才在数据根保存 JSON 证明。不打开物理麦克风，不保存捕获音频，不改变默认端点或音量，不连接 G10。用户应先停止其他程序向 VB-CABLE 发送真实麦克风或私人音频，避免虚拟通道混入无关内容。

剩余边界：实际 Windows COM/驱动元数据及真实 WASAPI probe 尚待这次授权实测；端点在最后一次枚举与打开流之间热插拔存在原 PortAudio 索引流程的竞态，验证后复核会拒绝保存变化后的证明，但本轮未改 WASAPI 核心来实现端点 ID 原子绑定。证明是本地状态 JSON，不是防用户主动篡改的签名。重启/启动会重新检查，运行期间不新增持续热插拔监控。无开发环境的干净 Windows 11 测试、BLE 发现、完整首启向导、按键 helper 和发行许可/ZIP 工作仍未完成。

### 本轮实际测试与冻结运行结果

| 命令 / 检查 | 真实结果 |
|---|---|
| 根目录 `.venv/Scripts/python.exe -m unittest discover -p "test_*.py" -v` | **66 run, 66 passed**，0 failure/error/skip。日志 `output/route-root-tests.log`。较上一轮新增 20 项路由测试，没有删除或跳过旧测试。 |
| desktop-ui 内 `../.venv/Scripts/python.exe -m unittest discover -p "test_*.py" -v` | **24 run, 24 passed**。日志 `output/route-desktop-tests.log`。新增 6 项 API/监督器路由门槛测试；旧假进程启动测试显式注入已通过的路由策略，并另有未注入策略时缺失/变化证明拒绝 Popen 的测试。 |
| desktop-ui/web 内 `npm run build` | **退出码 0**，TypeScript + Vite 1578 modules 成功。当前产物 `index-BbJmrNBq.js` 与 `index-C3blFDMn.css`。没有改依赖版本。 |
| `.venv/Scripts/python.exe -m PyInstaller --clean --noconfirm build/portable_onedir.spec` | **退出码 0，Build complete**，PyInstaller 6.22.3 / hooks 2026.8。日志 `output/route-build.log`。音频策略通过静态 import 纳入两个 EXE，不需要额外 helper。 |
| `.venv/Scripts/python.exe build/diagnose_portable.py`（最终） | **6 次 EXE 启动均退出 0、ok=true**；初始目录、移动到中文/空格目录、同名 data 文件阻止创建后的 LocalAppData 回退各覆盖两个 EXE。日志 `output/route-startup-final.log`，报告 `output/portable startup xx0mdtm4/`。 |

离线测试涵盖双方向/唯一身份、驱动缺失与物理端点拒绝、重复/失活/静音/零音量/不可读、PortAudio 与共享采样率、一次性确认与过期、保存成功/失败/原子性、30 天有效期、时钟异常与错误版本、损坏/伪单字段成功证明、端点与格式变化、索引重排、默认端点不可读/变化、验证中热插拔、失败重验撤销旧证明、Portable 移动及源代码/冻结/回退数据路径。除假 probe 结果测试外，另用假 InputStream/OutputStream **真正执行未改的原 probe + test_signal + correlate**，实际生成相关性指标并经新策略保存到临时目录；没有真实音频设备访问。

桌面测试另验证：缺失证明在枚举及 Popen 前拦截；端点 ID 改变时拒绝启动；默认手动桥接无需开发机 capture ID 配置；实验性自动唤起仍拒绝不匹配的显式 ID；UI 后端要求确认；桥接使用中拒绝检测/验证。协议/音频保护检查通过：`virtual_audio_probe.py`、ATVV、解码、handshake、readonly、audio_defaults 等文件无差异；桥接脚本剔除 `select_verified_pair` 后的 AST 与基线完全一致。

首次安全诊断的两个初始 EXE 检查已成功，但接着移动目录时出现 Windows `WinError 5`，故首次整轮**退出 1**（日志 `output/route-startup.log`、目录 `output/portable startup oe8llq4n/`），没有报告整轮成功。诊断脚本现对已退出 EXE 后的目录移动进行最长 10 秒的 PermissionError 重试，保留原有绝对目标范围校验，超时仍抛错，不强杀进程。最终完整诊断的程序目录及数据目录移动分别重试 3 次和 7 次后成功；次数写入 `summary.json`。这是 Windows 文件占用释放的观察结果，没有把首次失败删除或掩盖。

最终 6 份报告均含 `route_proof_gate="missing proof blocked before audio access"`：诊断在数据根的独立临时目录中构造缺失证明，并注入一旦被调用就报错的 catalog，从而验证不会枚举真实端点。3 次主 EXE 隐藏 WebView2 渲染都成功，Runtime `155.0.4283.62`；加载实际前端后只用 DOM 切换到语音设置预览，检查 `audio_route_ui.visible=true`、`verify_disabled=true`。窗口没有 JS 业务 API，未点击检测或验证按钮，没有调用真实 route probe。报告均 `business_started=false`，主 EXE 另为 `service_running=false`；进程已自行退出。没有将这些结果称为真实 VB-CABLE 路由通过。

构建警告仍为两份各 311 条模块诊断，集合类别与第 11 节相同；日志仍报告 pycparser lextab/yacctab，未通过删警告或放宽检查消除它们。两个 EXE 的 CFFI/WinRT 内存检查与 WebView2 实际渲染继续通过；新的实际 COM 元数据和 WASAPI 驱动路径仍按上述授权边界待验。

本轮 EXE SHA-256（用于定位本机构建，非发行签名）：

```text
G10-Control.exe      A3A5F96CC58F8A0472C4712C8103DA8A0E5A70AC6B44AD489CBFBFFBF46661F7
G10-AudioBridge.exe  093124223A595629184B3ED4E8506390B79E0500A4298CAD46DC944A94607731
```

本轮结束后停止，等待用户确认。真实端点验证、干净电脑验收及未在本轮范围内的开发事项继续保持待办。

## 13. v0.1.0 Beta 候选功能轮（2026-10-20）

基线 `6e152ec5fc7d87ea9567e98226a1aa1415b098ef`。按五个阶段推进、逐阶段测试及提交。真实 BLE 扫描、连接、GATT 业务及麦克风会话均未授权，本轮不执行；无管理员操作、驱动安装、默认设备/音量修改、键鼠模拟或对外二进制发布。

### 阶段一：真实 VB-CABLE 验证

- 用户授权后执行只读音频会话元数据检查，两次检查在两个虚拟端点均只见 inactive 会话，没有 active 会话。打开流前再次确认空闲。没有读取样本来判断隐私或静音。
- **只执行一次真实合成路由测试，成功**。复用原 1.48 秒信号及原相关性算法，两声道相关性均为 `0.9999999968589501`，默认端点未变化；未保存录音、未打开物理麦克风。结果在 `output/beta-audio-real.json`，前置检查在 `output/beta-audio-preflight.json`（含本机身份，不提交）。
- 真证明保存于当时 `dist/G10-Control/data/audio/route-proof.json`，保存后重新枚举及校验成功。为避免后续 clean 构建清除本机结果，另保留到忽略的 `output/beta-local-proof/route-proof.json`；**不带入干净 Beta 构建目录**。
- 新增 `audio_idle.py` 元数据空闲检查，未知状态/读取失败均拒绝；生产 probe 包装在流操作前也执行同一检查，活动或无法确认时要求用户关闭相关程序。没有改原 WASAPI/波形/相关性核心。新增 `build/verify_local_route.py` 默认只读预检查，必须显式给 `--execute-when-idle` 才单次验证，无自动重试。
- 相关离线测试：`python -m unittest -v test_audio_idle test_audio_route` **26/26 通过**，日志 `output/beta-stage1-tests.log`。该组模拟结果与上述一次真实测试明确分开。

### 阶段二：设备发现、选择与兼容性

- 新 `device_setup.py` 在用户点扫描后才调用 BleakScanner，显示实际广播名称、地址和服务提示；选择仅允许本次扫描列表里的身份，原子保存到源码/冻结各自的本机 local-settings。选择不表示兼容，重选撤销旧证据。没有执行真实 BLE 扫描或连接。
- 兼容性入口要求独立明确确认，复用 `phase2_readonly.observe` 的目标服务、特征枚举和 CCCD 恢复，以及原 Controller 的单次 GET_CAPABILITIES 及解析。派生 CapabilityOnly 禁止任何非能力请求的发送，忽略触发/START/音频、不调用开麦和关麦、不保存通知；只在精确身份、ATVV 服务/特征属性、codec 2 / 128 字节能力和安全清理均通过时保存 30 天证据。
- 继承已验证传输的边界：目前只能检查 Windows 已配对且名称为 G10 的候选；名称本身、广播服务本身都不能证明兼容，其他名称不会伪标兼容。完整服务/能力真实测试本轮未授权、保持待验。
- UI 增加设备扫描、刷新、选择、检查入口；后端去除固定 VID/PID 实时检测假象，未知时显示“未检测/不适用”。主程序启动还需匹配有效设备证据；真实桥接仍会再走原协议能力门槛。
- 模拟设备/协议测试 **16/16**（11 项新设备测试及 5 项原握手测试）；桌面全部 **24/24**。前端 TypeScript/Vite 构建成功。不会以这些模拟结果代替真实设备验收。

### 阶段三：中文首次运行向导

- 增加五步向导：欢迎/Windows 11 x64、.NET、WebView2 检测 → 蓝牙扫描/选择/能力状态 → VB-CABLE 双端点检测 → 明确确认的合成验证 → 完成及手动豆包使用说明。所有按钮连接现有真实后端接口，渲染不触发扫描、连接或音频。
- `setup-progress.json` 保存当前步骤，支持前后切换、重新检测、暂时收起和退出后继续。环境/设备/端点/路由各自为未检测、检测中、通过、失败或待用户操作；实际数据根、Portable/LocalAppData 和回退原因始终可见。
- 完成条件由后端实时门槛计算，不信任保存的 completed 单字段或客户端状态；环境失败、设备证据缺失/过期、路由未检测/过期均不能完成。重启后进度保留，但尚未重新确认的环境/端点不会伪标为全部成功。
- 后端向导/设备/路由相关 **37/37** 测试，桌面全部 **24/24**，前端状态及实际组件服务端渲染 **7/7** 测试，TypeScript/Vite 构建通过。渲染测试覆盖五步、无硬件自动调用、未完成禁用、全部门槛通过才可完成，以及环境错误和回退路径展示。真实 BLE 未执行，因此当前电脑的向导设备步骤仍应为待验证。

### 阶段四：正常窗口与生命周期

- 增加显式 `--lifecycle-diagnostic REPORT`，走生产 `main()`、实际 pywebview 窗口、托盘和 Windows mutex。这个模式在后端先拒绝服务启动、BLE 扫描/选择/兼容性、端点检测/验证、按键观察和启动项写入；不靠操作者避免点击来保证安全。前端仍正常连接 API，使用隔离配置。
- **源码实际运行通过**：`output/beta-source-lifecycle.json` 的 `normal_ui_visible/tray_ready/close_to_tray/tray_restore/single_instance/settings_roundtrip/safe_exit` 均 true，8 项禁止业务入口被阻止。第二源码进程实际因 mutex 退出。没有键鼠输入模拟；隐藏走实际关闭处理，恢复/退出调用生产托盘菜单 callback。
- **冻结 EXE 实际运行通过**：先正常可见 UI、托盘、隐藏、恢复、单实例、无业务安全退出，再移动整个隔离目录到中文/空格路径重跑。两次均成功；移动后实际读回增益 6 和向导步骤 2。日志 `output/beta-stage4-lifecycle.log`，报告 `output/beta lifecycle a3_wguoj/`。程序均自行退出，未留下 G10 进程。窗口可见性用实际 Win32 IsWindowVisible 检查，不是只检查 mock 方法被调用。
- `get_status` 明确返回冻结版按键观察器不可用，UI 禁用按钮并显示原因。Windows 启动项状态可以识别旧/移动后的命令，只有用户再次明确确认才修复当前用户路径；真实启动项本轮未写。相关注册表写入全部在 mock 下测试。依赖缺失在窗口创建前报错/清理，向导展示中文处理方式；未卸载真实 WebView2/.NET 或驱动。
- 安全退出先停止按键观察再停止桥接；清理失败保持窗口供重试，主循环 finally 确保其他清理和 mutex 释放尝试不被前一步异常跳过。没有强杀 BLE 进程。
- 桌面 **33/33**（新增 9 项 shell/注册表/缺依赖/退出检查），环境向导 **7/7**，前端 **7/7** 与 TypeScript/Vite 构建通过。重新 clean 构建 PyInstaller 成功，日志 `output/beta-stage4-build.log`。以上实际生命周期检查均在非业务模式下，不能替代真实 BLE/音频桥接退出测试。

### 阶段五：本地 Beta 候选与交付边界

- 新增 `build/stage_beta.py`，从构建目录按允许列表生成独立本地候选，拒绝覆盖已有目录，不生成 ZIP、不上传。只带两个 EXE、`_internal`、marker、空 data、中文说明、验收清单与许可审查材料。逐文件 SHA-256 在 `manifest.json`；`package-audit.json` 检查禁止目录、配置/日志/录音、本机已知身份字节（含 ZIP 和两个 EXE 的压缩 PYZ），不执行提取的代码。此机械审查不等于全面安全审计或再分发授权。
- `docs/README-PORTABLE.zh-CN.md` 说明安装前提、五步配置、CABLE 方向、隐私确认、手动豆包、移动和回退、过期/缺依赖处理；`docs/ACCEPTANCE-WIN11-X64.md` 为尚未执行的干净电脑验收清单，分开无业务检查、单独授权的硬件验收与发行许可门槛。
- 修正主页残留的“已配对/已配置”和固定型号描述，改用实际设备选择、兼容性及路由状态。增加实际组件渲染断言，未检测不显示成功。补充设备证据与实际运行地址一致性、环境重检异常、无设备证据拒绝启动、诊断不得扫描 BLE 的测试；WebView2/CLR 启动异常提供中文处理说明。
- PyInstaller 的 sounddevice hook 原来收集所有平台/架构的 PortAudio（含 ASIO）；两个 analysis 仅保留当前 x64 WASAPI 所需 `libportaudio64bit.dll`。没有修改音频算法。冻结诊断实际导入 Windows Bleak scanner/client 和 WinRT 依赖，导入不等于扫描；没有创建真实 watcher、连接或 GATT 操作。
- 最终根目录 Python **97/97**、桌面 Python **34/34**，均无失败/错误/跳过；日志为 `output/beta-final-root-tests.log`、`output/beta-final-desktop-tests.log`。前端状态/组件 **9/9**（此前 7 项加主页两项），TypeScript/Vite 构建通过。PyInstaller 6.22.3 clean onedir 构建通过；构建日志 `output/beta-final-build.log`。静态警告中的跨平台后端、类型/旧模块和 pycparser 可选 lextab/yacctab 按第 11 节分类，不能由此推断未执行的功能通过；所需冻结 Windows 导入由实际诊断覆盖。
- 最后一轮重建曾在 `discover_hook_directories()` 的隔离子进程以 `0xC0000409` 退出，保留 `output/beta-build-hook-failure.log`。随后逐项加载 numpy、hooks-contrib、pythonnet、webview hooks 及同一隔离发现均成功（`output/beta-build-hooks-diagnostic.log`），未修改/排除 hook、未改依赖版本后重新 clean 构建。尚无证据确定该次原生异常根因，不能把重建成功说成已定位根因。
- `docs/BETA_LICENSE_REVIEW.md`、候选 `license-inventory.json` 和 notices 列出实际版本与缺项：34 个 Python distribution、72 个已安装 npm 包（含构建/可选范围）。整体项目授权未确定；pystray LGPLv3 的库源码、应用材料和替换/重链接方案需所有者决定；部分 PyWinRT/proxy_tools 完整许可文本缺失；PortAudio、WebView2 SDK/Loader、Python/Tcl/Tk、Pillow、NumPy/OpenBLAS/编译器/VC runtime 原生许可链待核对。已收集的文本不构成合规结论，`redistribution_ready=false`。不附带 VB-CABLE、WebView2 Runtime、.NET 或豆包安装器。
- 最终目录：`dist/G10-Control-v0.1.0-Beta-candidate-win64`（忽略、不提交）。共 **1,269 文件**，manifest 校验 **1,268** 条（不含自身）全部一致，data 为空；内容/隐私审查通过，两个 EXE 各 880 个 PYZ 模块无已知身份或自身测试模块命中，检查了 8 个本机已知身份编码/大小写模式。包内仅一份 `libportaudio64bit.dll`；无开发机地址/端点配置、日志/录音、output、.venv、node_modules 或 Git 历史。源码 web/dist 与包内静态文件逐一哈希相同（最终 JS `index-eMeECrVC.js`）。
- **最终候选实际安全启动 6/6 通过**：`output/beta-final-exe.log`、`output/portable startup rh3a7lbn/`，分别覆盖两个 EXE 的原目录、中文/空格移动目录、阻塞 data 创建后的 LocalAppData 回退，退出 0、ok=true；三次主程序实际加载 React/CSS、WebView2 155.0.4283.62，路由按钮在无证明时禁用，冻结按键入口明确不可用/禁用。没有启动桥接业务，缺证明在音频访问前拒绝。
- **最终候选正常生命周期 2/2 通过**：`output/beta-final-lifecycle.log`、`output/beta lifecycle s8t41f3h/`。原目录与移动目录均实际可见窗口、托盘、关闭隐藏、恢复、第二实例拒绝、设置持久化、安全退出，8 项业务操作被后端阻止。移动后读回增益 6 和向导步骤 2。此诊断使用隔离副本/数据根、System32-only PATH 和非业务开关；没有写真实用户自启动项或执行键鼠输入。不能代替干净电脑和真实桥接生命周期验收。

最终两个 EXE 的 SHA-256（构建成功和上述实际运行结果分别记录）：

```text
G10-Control.exe      B626AB65988C058CDAC4A34C36EF39C1DB427E3C725E436E8AD42261D16CC440
G10-AudioBridge.exe  C442F9BC892CF979F003421949EE51E9E686F6EE50C91A6B2639930C65D860BA
```

### 分阶段提交

| 阶段 | Git commit |
| --- | --- |
| 一：真实合成验证与空闲保护 | `e62953356b8794bd108b509b8bfb822fe7a3801e` |
| 二：显式发现、选择与兼容性 | `75a73c8a5b631b8363ffcbd52bb80eca8dce08fe` |
| 三：中文可继续向导 | `61a55a3d6bfa44cc661d93ca3d85e7933957dd2d` |
| 四：正常 UI 与安全生命周期 | `752bb3db4b81ef44e139bde05fbe8ecd835c706c` |
| 五：本地候选、审查与最终回归 | 本节随第五阶段提交，确切 ID 见 Git 记录和本轮最终报告。 |

### 给其他用户试用前仍须完成

1. 所有者确定项目授权、贡献/参考边界及第三方再分发方案，补齐并验证许可材料；之后再单独确认是否制作对外试用包。
2. 单独授权真实 BLE 扫描、已配对设备身份/ATVV 服务/特征/能力检查，验证通知恢复和安全清理。当前仅模拟通过，不能宣称真实兼容性检查已经验收；名称限制仍须明确告知。
3. 单独授权真实 G10 音频桥接、长按/松开/断连/退出及手动豆包端到端测试。本轮真实音频只证明本机 VB-CABLE 合成路由，不能证明 G10 音频业务。
4. 在无 Python/Node/开发路径的干净 Windows 11 x64 按清单验收，覆盖依赖缺失、安装后的路径、只读回退、目录移动、驱动/端点变化、证明过期及普通用户权限。真实自启动写入本轮未执行，须在专用验收账户明确启用验证；未卸载开发机依赖来模拟缺失。
5. 冻结版按键观察器仍不可用，界面已明确禁用。没有自动豆包唤起、驱动安装或系统默认设备修改；这些不是已完成的 Beta 功能。


## 14. 离线恢复与发行验收准备（2026-10-20）

本轮开工核验 main / HEAD `9623cc9501ef2e2a1edbc1bf659f5cb6e5d4761a`，工作树干净，origin/main ahead 9。先阅读第 13 节及当前源码/测试。用户离开开发电脑，本轮禁止真实 BLE/GATT、麦克风/音频流、键鼠模拟、系统设置修改及提权；不运行上一轮真实路由脚本，不公开 ZIP。

### 阶段一：离线异常与首次运行恢复

- 保持 BLE/ATVV、ADPCM、WASAPI 核心原实现。只修桌面状态/配置恢复：失活进程、断连、过期/未来心跳及非对象 JSON 不再显示活跃音频，音量表归静音；异常退出提示手动重试，不自动重启，不强杀。
- 损坏应用配置保留原件、使用安全默认值并在 UI/诊断提示；设备配置损坏不阻断桌面导入，重新选择设备时备份原件并撤销兼容性，必须重新验证。只读权限错误不伪装保存成功。
- 增加 test_failure_recovery 离线矩阵（所有硬件及进程均 fake），覆盖 BLE 断开、身份变化、证明到期、端点变化、配置损坏、启动失败及停止超时；复核向导完成标记实时失效与显式恢复。真实硬件均待执行。
- 构建/许可/验收脚本与最终结果将在后续阶段补记；本阶段提交 ID 见 Git 记录。

### 阶段二：SBOM、许可审查、验收脚本和构建控制

- 阶段一提交 `7cf68f9`。随后补齐前端状态读取失败撤销旧成功展示：显示“状态未知”、禁止完成配置、保持安全停止入口；不会因 API 失败自动启动业务。后端失效心跳也显示 unknown。
- requirements-build.lock.txt 固定完整 Windows 构建环境版本（不含 pip，无 wheel 哈希）；stage 对 installed/lock 漂移拒绝生成有效证据。npm 同时核对 lock 与安装版本，未安装平台可选项仍写入 SBOM。
- stage_beta 生成 CycloneDX 1.6 SBOM、build-evidence（锁文件/spec 哈希、实际 PYZ 模块、原生文件/许可文本 SHA256）和人可读第三方许可证清单。首轮 SBOM 273 组件（34 Python distribution、122 npm lock 项、117 原生文件），72 个实际安装 npm 包；通过官方 1.6 JSON Schema。依赖图/静态链接子组件仍待审，不声称合规完成。
- 已分类已确认许可义务、待确认和分发阻塞：项目授权未选，pystray LGPL 源码/替换方案未落实；PyWinRT/proxy_tools 文本和 PortAudio、Pillow、WebView2 SDK、NumPy/Python/Tcl/Tk/运行库许可链待核实。redistribution_ready=false。不附外部驱动或 Runtime 安装器。
- accept_win11.ps1 使用系统 PowerShell、精确核验 manifest 和额外文件、中文/空格隔离副本、System32-only 子进程 PATH、阻塞 data 创建模拟回退，当前进程变量在 finally 恢复；不改 ACL/系统配置、不安装卸载、不做键鼠或 DOM 点击、不强杀。首轮两个 EXE 4/4 安全诊断通过，仅开发机隔离环境；真正干净 VM、缺依赖、只读 ACL 仍待执行。
- 初始两次独立 clean 构建并非字节一致：仅两个 EXE 和 base_library.zip 不同。进一步检查 EXE 内 archive 各 entry 字节全同，ZIP 成员集合和内容相同、顺序不同；PyInstaller 本地实现明确 PE 时间取 SOURCE_DATE_EPOCH。构建脚本因此固定当前进程 PYTHONHASHSEED=0、SOURCE_DATE_EPOCH=源提交时间并恢复原值；最终独立构建比较结果下一阶段记录，不能用旧比较声称通过。
- 本轮源码/文档均未写入真实设备身份、路由证明、日志或录音。文档提供中文回退、损坏恢复和诊断隐私说明。最终候选将在这些改动后重新构建/生成。

### 阶段三：最终本地候选与回归结果

阶段二提交 `84c7199`；本节及生成器来源哈希补充随最后一次文档/证据提交进入 Git（确切 ID 见 git log 与最终报告）。冻结业务/UI 源码基于 `84c7199`；stage 还记录逐个源码输入哈希，不把提交号当作未修改工作树的保证。

| 检查 | 实际结果 | 本机证据（忽略、不提交） |
| --- | --- | --- |
| 根目录 unittest | **100/100**，无错误/失败/跳过 | output/offline-final-root-tests.log |
| 桌面 unittest | **45/45**，无错误/失败/跳过 | output/offline-final-desktop-tests.log |
| 前端状态/实际组件渲染 | **12/12**，含 API 失败撤销成功、unknown 时安全停止、向导返回与禁止完成 | npm test 的本轮实际输出 |
| TypeScript/Vite | 成功；第二次 npm ci / build 相同资源 | output/offline-final-build.log、offline-final-rebuild.log |
| PyInstaller clean onedir | 最终两次均成功；此前排查两次也成功 | 同上及 output/offline-build-first.log、offline-build-second.log |
| 同机可重复性 | **1,086/1,086 payload 文件 SHA256 完全相同**，无增加/删除/差异 | output/offline-final-reproducibility.json |
| 最终 EXE 安全启动 | **4/4**，两个 EXE 在中文/空格目录及数据写入失败回退，退出 0、ok=true、business_started=false；无残留 G10 进程 | output/offline-final-exe.log、output/offline-final-exe-acceptance/ |
| SBOM 官方 schema | CycloneDX 1.6 JSON Schema 验证通过（仅结构，不是完整性/法律认证） | output/offline-final-sbom-schema.log、output/sbom-schema/ |
| 候选清单与隐私 | **1,274 文件**；manifest **1,273 条**全部校验一致（不含自身）；data 空，20 个已知身份/开发路径字节模式无命中；两个 EXE 各 880 PYZ 模块，无已知敏感命中/自身测试模块；仅一份非 ASIO x64 PortAudio | 候选 package-audit.json、manifest.json |
| 前端内容一致性 | web/dist 与包内 _internal/web/dist 逐文件哈希一致；最终 JS index-BXb4oLcb.js | 候选文件与源构建产物 |

最终候选：`dist/G10-Control-v0.1.0-Beta-offline-final-win64`（忽略、不提交）。早期 rc2 是排查样本，请以 offline-final 为本轮结果。未生成或公开 ZIP、未上传/推送 Release。

```text
G10-Control.exe      480fe37b02fcd98cbdfba688d1819741333fd0478215e3d690e77fae977afaca
G10-AudioBridge.exe  e1f437184d6db463769d4c0e0e26f679b197f95ce746298522c013a4f65a9a8d
```

SBOM 共 **273 组件**：34 Python distribution、122 npm lock 项（72 实际安装包）、117 原生文件。实际 namespace 包含 pystray 0.19.5/LGPLv3、pywebview 6.2.1/BSD、pythonnet 3.2.1/MIT、sounddevice 0.5.6/MIT、Pillow 13.0.0/MIT-CMU 及 WinRT；其原生静态依赖不能仅靠 Python 声明覆盖。完整许可文件缺失清单为 proxy_tools 和 9 个 winrt-* distribution；其余原生归属和 LGPL 应用材料仍待核验。人可读清单见候选 THIRD-PARTY-LICENSES.md，已收集文本带独立 SHA256。

最终构建警告仍只有 pycparser 可选 lextab/yacctab 显式 hidden import 未找到；冻结诊断已通过 cffi/pycparser、Windows Bleak/WinRT 导入及内存运算，不创建 watcher 或音频流。其他 warn-control/warn-bridge 的跨平台/类型模块沿用第 11/13 节分类，不据此宣称硬件路径验收通过。上一轮 hook 原生退出根因仍未定位；本轮多次成功不等于解释了该历史故障。

### 必须保留的未完成/阻塞

1. **没有干净 Windows 11 VM**。无 Python/Node/开发目录、真实只读 ACL、真实缺 WebView2/.NET/VB-CABLE 场景均待执行；System32-only PATH 和文件阻塞仅是开发机隔离模拟。提供安全脚本与中文步骤，没有卸载软件/修改 ACL 制造缺失。
2. **没有执行任何真实硬件操作**：BLE 扫描、连接、GATT、麦克风会话、真实音频、系统音频设置、键鼠模拟及管理员操作均未运行。前轮 VB-CABLE 合成证明不带入新候选。新的首次配置/断线恢复真实行为仍需用户回来后单独授权验收。
3. **法律审查未完成**。项目整体授权、pystray LGPL 源码/替换方案、缺失文本和 native 许可链仍阻塞分发；未选择项目许可证，redistribution_ready=false。
4. 可重复性只在本机相同 Python/Node/依赖及相同源提交时间控制下验证；未验证跨机器/不同工具链，也未加入 wheel 内容哈希供应链锁。初始差异报告保留，最终通过结论只适用于受控两次构建。
5. 手动开启豆包语音输入的限制保留；自动唤起未通过、冻结按键观察器不可用。异常不自动重连、不强杀桥接。诊断可能含设备身份和本机路径，分享前须检查。

保护性核对：相对开工 9623cc9，`atvv_protocol.py`、`phase2_handshake.py`、`phase2_readonly.py`、`analyze_audio.py`、`g10_audio_bridge.py`、`virtual_audio_probe.py` 均无改动。真实路由/配置/日志/录音全部留在被忽略的本机位置，不进入本轮提交或候选。
