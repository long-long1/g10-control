# 本地候选与正式发行门槛

版本以 release-metadata.json 为项目发行记录，当前 0.1.0-beta；前端、运行时和 SBOM 使用同一版本。MIT 已正式落地（2026 WYL），license_effective=true；source_ready/binary_ready/release_approved 均为 false，整仓来源边界和二进制验收分别待审。

## 离线构建与核验

```powershell
powershell -File build/build_portable.ps1
.\.venv\Scripts\python.exe build/stage_beta.py --destination dist/G10-Control-v0.1.0-Beta-mit-review-win64
.\.venv\Scripts\python.exe build/check_release.py --bundle dist/G10-Control-v0.1.0-Beta-mit-review-win64
powershell -File build/accept_win11.ps1 -Bundle dist/G10-Control-v0.1.0-Beta-mit-review-win64 -OutputDirectory output/mit-exe-acceptance
```

check_release 执行精确 manifest/SHA256、SBOM/native 映射、报告数量、许可文本哈希和隐私审查；`--schema-directory` 可使用官方 CycloneDX 1.6 schema（校验器环境需要 jsonschema）。证据扫描不等于完整敏感数据审计或许可认证。候选 data 必须为空；不归档整个仓库，不打包本机配置。

另用独立 dist/work 目录运行相同 clean 构建，再执行 build/compare_builds.py 比较；构建脚本对两个构建均使用同一 HEAD 提交时间 SOURCE_DATE_EPOCH 和 PYTHONHASHSEED=0。不要在两个构建之间提交或修改输入。只证明同机相同工具链重复性，未证明跨机器；Python wheel 尚无内容哈希锁。

## 人工审批清单

以下每项必须有实际证据和所有者签字/明确批准，不能以 CI 绿灯代替：

- [ ] MIT 2026 准确版权署名、原创材料权属和参考边界确认，根 LICENSE 生效；GitHub 识别检查。
- [ ] 第三方逐组件许可审查完毕；proxy_tools 声明冲突解决，原生 SDK/静态库/运行库来源及条款核清，包括本机从外部工具链解析的 44 个 API/UCRT 文件，不能把文件名当成已获微软分发许可。
- [ ] pystray 源码、应用代码、可重组材料和许可告知完整；修改库重组可操作且法律适用性审查完成。
- [ ] 干净 Windows 11 x64 普通用户验收通过，包含缺依赖、移动目录、只读回退；没有开发环境依赖。
- [ ] 实际 G10 的 BLE/GATT/ATVV 服务、能力、帧布局兼容性验证通过。
- [ ] 真实语音桥接与手动豆包端到端通过；长按、松开、断连、异常停止和退出安全通过。
- [ ] 候选无私人配置、设备身份、音频、日志、开发路径；逐文件 manifest/SHA256、SBOM Schema、依赖锁与许可文本校验通过。
- [ ] 所有者明确批准本次源码公开；与二进制批准分开记录。
- [ ] 所有者明确批准本次二进制对外发布，确认审核的精确 commit/manifest/EXE 哈希。
- [ ] 安全私密报告渠道已配置并验证。

GitHub Actions 只做无硬件的 Windows 检查和本地候选生成，不上传构建文件、不创建 Release、无发布凭据。托管 Runner 没有可依赖的桌面/WebView2/硬件，EXE 桌面/硬件验收保留为本地任务；不以跳过后显示“已验收”。未来发布必须另建人工 dispatch + 受保护 environment 审批，并在流程内核验签字记录；当前仓库没有任何可执行发布动作。

## Release Notes 草稿

见 RELEASE-NOTES.zh-CN.md。只在全部门槛通过后由所有者人工确认并发布，不能附上未授权的 EXE/ZIP。本轮不执行 git push、上传或公开发布。
