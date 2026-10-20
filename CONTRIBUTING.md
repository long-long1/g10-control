# 贡献指南

项目以 MIT 授权有权授权的原创内容，版权为 2026 WYL；来源边界尚待核清；提交贡献前请阅读 LICENSE_STATUS.md。只能贡献自己有权授权的材料，并说明第三方来源、版本及许可证；不得复制授权不明的代码或界面资产。

使用 Windows 11 x64、Python 3.12.10 x64、Node 26.1.0 / npm 11.13.0。运行以下离线检查（不连接硬件、不打开音频流）：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.lock.txt
.\.venv\Scripts\python.exe -m unittest discover -p "test_*.py" -v
.\.venv\Scripts\python.exe -m unittest discover -s desktop-ui -p "test_*.py" -v
cd desktop-ui/web
npm ci
npm test
npm run build
```

本地构建：`powershell -File build/build_portable.ps1`；生成候选及验证见 docs/RELEASE-PROCESS.md。不要运行 build/verify_local_route.py 或真实桥接来替代离线测试。BLE、音频、启动项和输入模拟必须由操作者另行明确授权。

沿用现有 Python / TypeScript 风格，保持函数清晰、输入边界显式，前端通过 tsc。无须全仓重排格式。修改 BLE/ATVV、ADPCM、WASAPI、缓冲或路由证明时保持现有安全门槛，新增有意义的失败路径验证。

提交使用描述行为的简短标题；PR 说明问题、变更、离线检查、风险及未验证事项。硬件相关 PR 必须说明测试型号/协议、系统环境及真实结果；未实测要明确写待验证。禁止在公开 Issue、日志或截图中泄露 BLE 地址、端点 ID、设备实例、个人路径、令牌、录音或识别文本。仅附经过人工脱敏的最小片段。

遵守 CODE_OF_CONDUCT.md；漏洞遵循 SECURITY.md，勿公开敏感复现数据。
