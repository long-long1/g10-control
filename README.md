# G10 Control

面向 Windows 11 的 G10 / 3K 蓝牙空中飞鼠语音桥接与桌面管理原型。

已在一台真实 G10 上跑通：**按住红色麦克风键 → BLE / ATVV 音频 → IMA ADPCM 解码 → VB-CABLE → 手动开启的豆包输入法 → 文字**。

> 当前是开发原型，不是安装即用的正式软件。**红键自动唤起豆包仍未成功，按键映射目前仅支持只读检测。** 不同批次遥控器可能使用不同协议，不能仅凭“3K / G10”名称判断兼容。

## 功能状态

| 功能 | 当前状态 |
|---|---|
| Windows BLE 连接、GATT / ATVV 服务发现 | 已在实机验证 |
| 能力协商、麦克风会话、音频通知 | 已在实机验证 |
| IMA ADPCM 解码与本地音频分析 | 已验证当前样机 |
| VB-CABLE 音频转发 | 已验证，用户自行安装驱动 |
| 豆包输入法手动唤起后识别文字 | 用户已确认成功 |
| 中文桌面界面、托盘、配置持久化、单实例 | 已实现开发版本 |
| 红键自动唤起豆包 | **未通过实测；仅保留诊断实现** |
| 遥控器按键来源 / HID 报告观察 | 已实现，只观察指定设备 |
| 自定义映射、单击 / 双击 / 长按、多步骤动作 | 未完成 |
| 自动重连、休眠恢复、Windows 安装包 | 未完成 |
| 开机自启 | 当前用户启动项入口已实现，需用户明确开启；未完成发行级回归 |

桌面外壳实际使用 **Python + pywebview / WebView2 + React / TypeScript**，复用独立 Python 音频服务。Tauri 2 + Rust 是后续可评估的迁移方向，不是当前已实现的技术栈。

## 语音链路

```mermaid
flowchart LR
  Remote[G10 红键与麦克风] --> BLE[BLE / ATVV 会话]
  BLE --> ADPCM[IMA ADPCM 解码]
  ADPCM --> WASAPI[48 kHz WASAPI 输出]
  WASAPI --> Cable[VB-CABLE: CABLE Input → CABLE Output]
  Cable --> Doubao[手动开启的豆包输入法]
  Doubao --> Text[当前输入框文字]
```

VB-CABLE 的命名容易混淆：桥接向播放端 **CABLE Input** 写声音，豆包选择录音端 **CABLE Output**。无需使用 ChatGPT 聊天输入框自身的听写按钮。

## 环境与依赖

v0.1.0 Beta 目前只生成本地验收候选目录，不提供公开 ZIP。便携版运行不需要 Python/Node；开发构建仍需要下列环境。参见[中文便携说明](docs/README-PORTABLE.zh-CN.md)、[本轮版本说明](docs/RELEASE-NOTES.zh-CN.md)和[干净 Windows 验收步骤](docs/ACCEPTANCE-WIN11-X64.md)。项目授权、第三方再分发材料和干净机/硬件验收仍有阻塞。

- Windows 11 x64，具备可用的 BLE 蓝牙适配器。
- Python 3.12 x64；本机开发依赖版本见 `requirements.txt`。
- Node.js 20+、npm，用于构建桌面界面。
- Microsoft Edge WebView2 Runtime。
- 用户自行从 [VB-Audio 官方网站](https://vb-audio.com/Cable/) 安装 VB-CABLE，并确认本机设备；仓库不会自动安装驱动。
- 豆包输入法；当前结论来自本机 0.9.2.7，其他版本需重新验证。

## 从源码启动

在 PowerShell 中执行：

```powershell
git clone https://github.com/long-long1/g10-control.git
cd g10-control
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
cd desktop-ui\web
npm ci
npm run build
cd ..\..
```

### 1. 识别自己的遥控器

已配对设备无需重新配对。只读清单：

```powershell
.\.venv\Scripts\python.exe diagnose.py inventory --output output\inventory.json
```

在本机结果中确认 G10 的设备实例和蓝牙地址。清单包含个人设备信息，只保存在 `output/`，不要提交。没有明确确认的目标地址时，不启动按键监听或业务会话。

### 2. 保存本机配置

将下面的 `你的G10地址` 换成清单中确认的12位地址，可以带冒号：

```powershell
.\.venv\Scripts\python.exe configure_local.py --address 你的G10地址
```

该命令只查询音频设备并生成被 Git 忽略的 `local-settings.json`，不连接 BLE、不安装驱动、不修改默认麦克风。需要恰好一个可识别的标准 CABLE Output / CABLE Input 配对；有歧义就拒绝保存。也可以参照 `local-settings.example.json` 手工填写，或使用 `G10_BLUETOOTH_ADDRESS`、`G10_CABLE_CAPTURE_ID` 环境变量。

### 3. 在本机验证虚拟声卡路由

下面的测试仅向明确识别的虚拟端点发送合成信号，再从其录音端检查相关性，不使用物理麦克风或扬声器兜底：

```powershell
.\.venv\Scripts\python.exe virtual_audio_probe.py --profile vbcable --probe --output output\phase3-vbcable-probe
```

只有 `route-test.json` 的 `passed` 为 `true` 且端点身份一致，桥接才会运行。公开版本没有携带原开发电脑的验证结果，必须重新生成。

### 4. 打开桌面界面

```powershell
.\desktop-ui\start_g10_control.cmd
```

点击「连接 G10」。此按钮会在已配置的目标上执行文档化的 ATVV 会话控制和通知订阅；请先阅读[协议说明](docs/ATVV_PROTOCOL.md)，确认是要测试这台设备。

自动唤起保持关闭。在豆包输入法设置中将麦克风选择为 **CABLE Output**。聚焦目标输入框并切到豆包输入法，手动开启语音，再配合红键说话。沿用当前样机验证顺序时，先按住红键，再手动开启豆包语音，松开红键后等尾音送完再结束豆包录音。

首次使用新设备必须重新验证服务、能力响应和解码格式。ATVV 版本、采样率、帧布局与半字节顺序不能从商品名称推断。

关闭窗口默认进入托盘；用界面「安全停止服务」或托盘「安全退出」释放音频与 BLE 资源。桥接默认持续运行，已移除旧的一小时限制。公开快照使用 `%APPDATA%\G10ControlPublic` 和 `%LOCALAPPDATA%\G10ControlPublic`，避免覆盖原开发电脑的配置。

## 为什么自动唤起还没有完成

实体右 Alt 能打开豆包录音；普通权限和临时管理员权限下的 `SendInput` 都只触发普通 Alt 提示。对本机版本做离线机器码检查发现，豆包语音键钩子明确跳过 `LLKHF_INJECTED` 事件，因此更换扫描码和提权不能解决该路径。

定向 `PostMessage` 也未观察到录音。状态栏是自绘界面，已检查的 UIA / MSAA 接口没有可调用的麦克风按钮；没有确认可公开调用的语音开始 / 停止 API。

独立探针中已准备“实际鼠标定点点击”的候选实现，但**尚未运行、尚未证明有效、未集成到日常桥接**。用户当前要求停止实验并交接。后续使用必须重新征得临时鼠标输入授权，不能直接运行管理员测试脚本。

## 源码导航

| 路径 | 作用 |
|---|---|
| `desktop-ui/app.py` | WebView2 外壳、托盘、生命周期、只读按键观察入口 |
| `desktop-ui/app_runtime.py` | 配置、服务监督、状态和日志接口 |
| `desktop-ui/web/` | React / TypeScript 中文界面 |
| `g10_audio_bridge.py` | 已验证的 BLE → 解码 → WASAPI 音频服务 |
| `phase2_handshake.py` / `atvv_protocol.py` | 受控 ATVV 状态机与命令白名单 |
| `phase2_readonly.py` / `diagnose.py` | 原始通知、时间标记、设备和服务诊断 |
| `analyze_audio.py` | 离线解码、统计与 WAV 分析 |
| `raw_input.py` | 指定设备的 Windows Raw Input 观察；不拦截 |
| `virtual_audio_probe.py` | 本地虚拟音频路由验证 |
| `doubao_voice.py` | 实验性自动控制；未通过实机验证 |
| `doubao_ui_probe.py` / `doubao_accessibility_probe.py` | 独立唤起实验与只读界面检查 |
| `local_config.py` / `configure_local.py` | 本机身份配置，不提交私有值 |

完整接手步骤、限制和下一阶段任务见 **[开发交接文档](docs/HANDOFF.md)**。

## 测试

以下测试不需要遥控器，不发送 BLE 业务命令，不录音、不发送键鼠输入：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -p "test_*.py" -v
.\.venv\Scripts\python.exe -m unittest discover -s desktop-ui -p test_runtime.py -v
cd desktop-ui\web
npm ci
npm run build
```

可选 AxonKey 源码交叉检查需要相邻 `../axonkey-reference` 固定版本；仓库不内置该源代码。缺少参考副本只跳过这一项交叉检查，协议白名单和禁止只读工具业务写入的检查仍会运行。自动测试通过不代表真实硬件或自动唤起通过。

## 操作边界

- 不修改遥控器固件，不删除配对，不安装内核驱动。
- 不向未知 GATT 服务扫描式写入，不通过未证实的 RPC 参数调用豆包。
- 不自动修改 Windows 默认录音 / 播放设备，不自动安装虚拟声卡。
- 不全局拦截普通键盘、鼠标；Raw Input 的“观察”不是设备级“拦截”。
- 手动桥接不保存录音或识别文字；带录制选项的诊断命令属于另行选择的本地测试。
- 本项目不主动上传设备信息或日志。豆包自身的识别联网行为遵循豆包的设置和条款。

## 参考与许可

功能和 ATVV 行为参考 [AxonKey](https://github.com/leowzz/axonkey)，分析版本 `a8c23b98fc6468013c9647a8b27646e5a9821303`。未包含参考仓库、商品照片、第三方程序二进制或反汇编转储。

仓库整体尚未指定开源许可证；第三方依赖分别遵循其许可。详见 [许可状态](LICENSE_STATUS.md) 与 [第三方说明](desktop-ui/THIRD-PARTY-NOTICES.md)。
