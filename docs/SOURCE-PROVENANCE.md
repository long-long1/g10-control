# 原创与参考材料核对（2026-10-20）

本轮检索了现有 LICENSE_STATUS、README、notices、源码版权/SPDX/来源注释和 Git 历史。没有把 Git 作者身份当成法律权利人；正式 MIT 的 WYL 来自本轮用户明确答复。

| 内容 | 已见证据 | 判断/待办 |
| --- | --- | --- |
| 原创界面/运行逻辑/测试/文档叙述 | 当前 Python/React 工程与项目历史；无拷入外部参考仓库 | WYL 的 MIT 仅覆盖有权授权的原创部分；非完整历史法证审计 |
| g10-remote.svg | 仅几何图形、文本和通用 sans-serif；未嵌入商品照片、字体文件或远端图像 | 依据原有原创示意图声明；没有生成/捏造截图 |
| IMA 表与解码器 | analyze_audio.py 注明标准 IMA/DVI 数值及 FFmpeg 数值交叉参考；8d170a3 移除外部 checkout 读取依赖 | 数值/算法与表达需区分；未复制 FFmpeg 或 Rust 源码文件，保留参考。该观察不代替完整来源审查 |
| ATVV 协议/控制器/协议文档 | atvv_protocol.py 的 source-derived、phase2_handshake.py 的 RC003-derived、文档固定上游行号 | 具体参考字节与独立表达边界尚未核清；不能仅凭改写语言宣称无派生问题。所有者/来源审查须确认独立实现或取得适用授权，当前排除相关第三方表达的 MIT 保证 |
| AxonKey | 固定参考 a8c23b98fc6468013c9647a8b27646e5a9821303；历史未发现根 LICENSE | 未复制整个仓库/界面/商品照片；不能据此推导参考实现可重新授权。不要改写核心算法来掩盖来源问题 |
| 第三方库和许可文本 | 固定上游文本/哈希、pystray 完整源归档 | 保留第三方许可，不以 WYL MIT 替代；proxy_tools 冲突单独待审 |

SOURCE_READY=false：整仓尚存在明确的来源审查事项。MIT 声明已正式完成，但不能把它作为整仓已核清的证据。BINARY_READY=false 另有第三方许可、LGPL 重组分发、干净 Windows、真实硬件与所有者批准门槛。
