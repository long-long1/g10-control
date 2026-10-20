# 蓝牙身份与连接回归修复

## 旧版成功路径

只读对照 `diagnostic-3k` 的 `diagnose.py`、`phase2_readonly.py`、`phase2_handshake.py`、`atvv_protocol.py`、`g10_audio_bridge.py`、桌面运行层及已有诊断/握手/语音报告。

- `diagnose.py` 使用 Windows 已配对 BLE selector，按 Windows 名称选中 G10，调用 `BluetoothLEDevice.from_id_async(target.id)`，再从返回对象的 `bluetooth_address` 获取实际地址。广播名称不是这条路径的输入。
- 旧版运行桥接时地址固定在源码；`observe` 在已配对列表中匹配名称和 ID 内的已知地址，然后按完整 Windows ID 打开设备。旧版无需本机蓝牙配置文件，但依赖预先已配对的这台设备；不能直接作为其他用户的通用实现。
- 旧版还依赖本机 `output/phase3-vbcable-probe` 内的音频路由证明。这是启动音频桥接的独立条件，不是 BLE 设备发现条件。
- 成功报告证明：WinRT 获取 ATVV 服务和特征后，订阅音频/控制通知，发送一次既有能力请求，收到 codec 2 / 128 字节响应；红键触发 START、音频、STOP，最后恢复 CCCD。仅 Windows 显示已连接或存在服务 UUID 不足以证明协议兼容。报告中的成功轮次未实际发送 MIC_OPEN/MIC_CLOSE，不能扩大其已验证范围。

## 新版回归及当前状态

此前新版 `device_setup.scan_candidates` 仅调用 Bleak 广播扫描；已连接设备可能不再提供广播名称或持续广播。`check_candidate` 又要求候选名称恰好为 G10，导致 Windows 已配对的真实设备在进入原有 WinRT 链路前被漏掉或拒绝。

本轮开始时 HEAD 为 `d89fdad`，已有 Windows 已配对列表优先、广播补充、Windows 名称优先、无名称可选择、保存完整 WinRT ID、真实服务/能力校验的修复。本轮保留这些改动，没有重复重写界面。

仍存在的确定性缺陷是：`device_setup._address_from_device_id` 和 `phase2_readonly._address_from_windows_id` 用正则取第一个 MAC。旧版成功记录的 ID 形状是 `BluetoothLE#BluetoothLE<本机适配器 MAC>-<远端 MAC>`；当接口记录没有 AEP 地址属性时，两个函数都会误取本机地址，导致候选地址错误，最终与 `BluetoothLEDevice.bluetooth_address` 校验冲突。

## 本轮修改

- `local_config.py`：集中解析已知 WinRT BLE 接口格式，仅返回远端地址；未知、PnP 或不完整 ID 不猜测。保留 AEP 地址优先的现有逻辑。
- `device_setup.py`、`phase2_readonly.py`：发现与连接使用同一个解析函数，保持完整 WinRT ID 与标准化 BLE 地址分开保存和传递。
- `test_device_setup.py`：加入双地址 Windows ID 的发现→选择→连接身份解析回归；验证未知 ID 不误解析、实际地址不符时不访问 GATT，以及模拟完整能力检查和 CCCD 恢复。
- 本文记录分析、验证与本机验收步骤。

所有新增测试使用虚构地址，不包含个人设备标识。没有更改 ADPCM、WASAPI、VB-CABLE 核心算法或 ATVV 命令/能力规则。旧版目录未写入、未执行其中程序。本轮没有连接真实设备、发送真实 GATT 命令、启动音频流或改变 Windows 蓝牙设置。

## 离线验证

在新版现有 `.venv` 中执行：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s . -p test_*.py
$env:PYTHONPATH = 'E:\working\yaokong\g10-control'
Push-Location desktop-ui
..\.venv\Scripts\python.exe -m unittest discover -s . -p test_*.py
Pop-Location
Push-Location desktop-ui\web
npm test
npm run build
Pop-Location
```

结果：后端 119 项、桌面运行层 45 项、前端 12 项全部通过；TypeScript/Vite 构建通过。新增的端到端模拟检查执行原有 `observe`、能力请求白名单、响应解析和清理流程，WinRT 枚举、设备打开及特征传输均替换为模拟对象，不接触硬件。

另外以提交前解析函数替换测试中的发现解析函数，新增双地址 ID 回归按预期失败（得到本机地址）；修复后的同一测试通过。离线结果证实代码路径修复，实际无线连接恢复仍待用户本机验收。

## 用户本机验收

1. 退出正在运行的旧版/新版程序，避免两个桥接进程同时占用设备。运行新版源码入口 `desktop-ui\start_g10_control.cmd`；本轮构建已更新其使用的前端产物。已有便携 EXE 不会因源码修改而自动更新。
2. 在设备设置中点击“扫描 / 刷新设备”。预期看到 Windows 已配对 G10 及真实名称（若 Windows 提供）；广播名或 ATVV 提示缺失不应禁止选择。确认显示的是遥控器地址，而非电脑适配器地址。
3. 重新选择该 Windows 配对项，覆盖此前可能保存错误的身份。点击“检查兼容性”并在界面确认；这一步会实际连接、临时订阅通知并发送一次能力请求。应在真正取得服务/特征、codec 2 / 128 字节响应且清理成功后才显示通过。
4. 若现有音频路由检查已经有效，点击连接，观察 ATVV 就绪。需要继续验收语音时，再按原有流程手动唤起目标应用语音、选择 CABLE Output、按住红键说话，停止后安全断开。音频路由验证和语音测试会打开音频流，应由用户按需执行。
5. 若失败，保留界面错误及新版 `output` 内对应运行日志，区分枚举、地址校验、服务发现、能力响应和音频路由错误；不要把 Windows“已连接”当作 ATVV 兼容性通过，也无需仅因广播无名就重新配对。
