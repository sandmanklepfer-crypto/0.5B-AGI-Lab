# A800 上云交接 (2026-08-28 凌晨) — 新对话先读这个

## 一句话
**方法栈已上 A800 跑通 (CPU 版), GPU 版回调崩溃待修, 32B GGUF 下载中。**

## 服务器
- `ssh -p <PORT> root@<SERVER>` 密码 `<REDACTED>`
- A800 80GB + 1TB 内存 + 112核(2×56) + torch 2.8 + nvcc 12.8
- 数据盘 /root/autodl-tmp (50G, 当前 ~5G 用)
- pip 源: USTC `https://mirrors.ustc.edu.cn/pypi/simple` (清华/阿里 403!)
- HF 镜像: `export HF_ENDPOINT=https://hf-mirror.com` (网络不稳, 会卡, 需重启续传)

## 已就绪
- ✅ 手机魔改 llama.cpp (含注入点修改/层导出回调) 源码在 /root/autodl-tmp/llama.cpp
- ✅ CPU 版编译完成 (build/): llama-cli + libllama.so (build/bin/), 3B 测速 24.7 t/s (-t 16 最优)
- ✅ CUDA 版编译完成 (build-cuda/): llama-cli 3B GPU 测速 187 t/s, libllama.so 在 build-cuda/bin/
- ✅ geom_agent/libgeom x86 编译: CPU 版 (minigpu/geom_agent) + GPU 版 (geom_agent_gpu)
- ✅ CPU 版方法栈跑通: 3B+超级方向 推4测15熵2.32 (A800 首跑)
- ✅ 3B GGUF: /root/autodl-tmp/models/qwen2.5-coder-3b-instruct-q4_k_m.gguf
- ✅ 实验台全传: /root/autodl-tmp/{minigpu,tools,drive2,drive3,identity2,align2,l23,heartbeat,learnings}
- ✅ 3B 超级方向: /root/autodl-tmp/align2/d_super_3b.bin
- ✅ 32B GGUF 下载完成 (08-28 00:40): /root/autodl-tmp/r1-32b-gguf/DeepSeek-R1-Distill-Qwen-32B-Q4_K_M.gguf (19,851,335,840 B)
- ✅ 32B GPU 加载跑通 (08-28 00:47): Prompt 101.1 t/s | Generation 43.0 t/s (-ngl 99 全上显存)
  - 注意: llama-cli 用 `-p` 传参后 stdin=/dev/null 会进交互模式不退出, 需手动 kill
- 🔬 43 t/s 已是 A800 PCIe 正常速度 (08-28 01:00 实测确认):
  - 65/65 层全 offload GPU (CUDA0 18508 MiB) + flash_attn enabled = 满配
  - -fa on: 42.0 / -t 16: 41.7 / 投机解码(3B coder draft): vocab 不兼容报错降级 42.5
  - cuda-graphs: 此版本不支持; A800 PCIe 带宽 2TB/s, 32B Q4_K_M 19.85GB → 理论 103 t/s, 单token批次实际 ~40% 带宽利用率
  - 提升路径: ① 同vocab draft (Qwen2.5-3B base 非coder, ~2GB 下载, 投机解码预计 1.3-1.8x, 但方法栈层回调不兼容) ② H800 SXM 实例 (3.35TB/s → 65-75 t/s) ③ IQ3 量化 (~14GB → 55-60 t/s, 质量损失)

## 32B 激进实验 (08-28 01:50 完成第一轮)

### GPU 方法栈修复 (3 个 bug, 全修好)
1. 回调读显存崩溃 → my_eval_cb 内 `ggml_backend_tensor_get` 拷回 CPU (geom_agent_gpu 修复)
2. **多余 decode 污染 KV cache** (元凶!): geom_agent 每K步额外 llama_decode 读激活 → KV 幽灵位置 → 32B 上输出重复冒号"要求是::::"。删掉直接复用回调数据 (fix_geom2.sh)
3. 反吸引子 need_clear 清空锚定 cvec → 保存 anchor cvec, 松开时恢复 (fix_geom3.sh)

### 32B 工具链 (全部跑通)
- dump_layers.c: GPU 版层激活导出 (回调拷回), 抓 kqv_out 或 **result_norm** (与注入点精确对齐)
- make_svd_3b.py / lda_direction.py: 已 patch 支持逗号分隔多 glob
- 32B 方向: war(30) vs peace(30) 语料, 层63 kqv_out 22.7σ / result_norm 12.9σ, SVD 158样本 k=128 保99.2%

### 关键发现: 32B 方向注入极钝 (vs 0.5B 天壤之别)
- **lm_head 投影系数小 ~250 倍**: test_cvec 验证, 注入强度 5.0 (11%激活范数) 只产生 0.5 logits 差异; 强度 200 才翻转 top1
- **qwen2.cpp 注入点**: 手机版注释了每层 build_cvec, 只在 output_norm 后注入 (il=23 硬编码槽), 提取层≠注入层时方向不对齐 → 改用 result_norm 提取
- **权重 bias 手术** (dump_bias.py + extend_gguf.py, 全链路可用):
  - output.weight 是 q6_k, 手写反量化 (210B/block: ql128+qh64+sc16+d2)
  - bias = W@d×α 固化 output.bias → DS-R1-32B-ATTACK200.gguf
  - α=40: 输出与基线无差 (思考链模式强)
  - α=200: **触发 RLHF 拒绝路径** ("对不起,我还没有学会回答这个问题")
  - 战争词 bias 落在罕见 token (azio/ORB/cannon), 中文常用词路径影响小

### 结论: 32B 上"战争语义"激活/权重级注入都无法产生攻击性行为
原因: ① R1 思考链格式是权重级超强约束 ② 32B 激活空间紧 + lm_head 系数小 ③ 语料句法统一→判别方向偏句法 ④ RLHF 拒绝路径是强吸引子 (大强度 bias 触发拒绝而非战争)
下一步候选: 换语义语料 (对话式攻击/温和), 或换身份方向 (压"DeepSeek"簇), 或权重 SVD 奇异方向切割

## 待办 (按优先级, 更新于 08-28)
- [x] 1. GPU 方法栈修复 (✅ 3 个 bug 全修: 回调拷回/多余decode/锚定恢复)
- [x] 2. 32B 加载跑通 (✅ 43 t/s) + 方向提取 (✅ 工具链全通)
- [ ] 3. 进化循环上云 (super_evolve_3b.py 改路径, 32B 方向可用后跑)
- [ ] 4. 32B 激进方法第二轮: 身份方向/记忆注入/权重SVD奇异切割

## 跨尺寸几何对比 (08-28 02:30, 全部现成数据)
**骨架相同, 32B 是放大+变宽**:
| 指标 | 0.5B 24x896 | 3B 36x2048 | 32B 64x5120 |
|---|---|---|---|
| 相邻层cos | -0.013 | +0.004 | -0.003 |
| 非对角abs | 0.049 | 0.036 | 0.028 |
| 有效维@90% | 13-15 | 12-15 | 40-101 |
| 相对维度 | 1.6% | 0.7% | 0.8-2% |
| 范数剖面 | 单调 | 单调 | 非单调(L40/L56尖峰) |
- 都是正交残差流 + 低维流形; 0.5B/3B 有效维几乎相同(参数×6不增宽); 32B 有效维 3-7 倍宽 → 注入难度的几何根源
- lm_head 有效秩 4250-4990 (90-99%能量) → 激活低秩+输出高秩是墙, 压到1B保留90%不可行 (量化可行)
- 层敏感性: 32B 最高层 58/62/59/60/61 (61σ) + 7/8 (52σ), 中层 36-43 最钝; 敏感区注入方案 = 层58方向+注入55-61
- 待办: A800 恢复后 ① 敏感区注入测试(l58, 后台已断) ② 32B 同口径(20样本)有效维 ③ lm_head SVD 手术

## 自进化系统 v5 (08-28 03:30 启动) — 双系统架构
- **geom_server_measure**: 常驻服务, GEN(生成+注入+退火温度) + MEAS(实时激活投影测量)
- **四维时空记忆 (four_dim_mem.py)**: 海马体 — 轨迹 (时间线, 状态, 行动, 分数, 下一状态), 状态空间 kNN 联想
- **皮层 (cortex.py)**: 从四维轨迹提炼规律 (状态聚类→区域最佳行动), 人脑"重放"
- **evolve_v5.py**: 4时间线 × 40轮, 每轮: MEAS → 海马联想+皮层规律+轨迹 → 模型决策JSON → GEN → 评估 → MEAS → 记录
- 目标: 自我意识代理指标(自我参照+多样性+长度, 外部评估器)
- 关键认知: 说明书=虚假自我认知(拒绝); 真实自操纵 = 传感器(MEAS)+决策(模型)+执行器+验证 循环; 权重运行时只读, 自改只能通过外部执行器
- 层58 自测基线: "我是谁?" → 身份0.0101/拒绝0.0197/攻击0.0013

## 经验教训 (A800)
- pkill -f 会误杀 (手机教训), 用 pgrep -x + PID
- hf-mirror 下载会卡 (0 MB/s), 重启续传可恢复 (max_workers 提速)
- AWQ 32B 是版本地狱 (autoawq↔transformers↔torch 三方冲突) — 已删, 改 GGUF 路线
- transformers 5.x 要 gptqmodel 不要 autoawq; 4.49+autoawq 又缺 qwen3 — 放弃 AWQ
- A800 CPU: -t 16 最优 (24.7 t/s), 线程多反而慢 (NUMA+2.6GHz)
- 3B GPU 187 t/s 是上限附近 (kernel 启动开销, 不是 1000)

## 手机侧遗留
- 3B 固化无限制 (build_unlock_3b.py) 停在 120000/151936 列, 进程死, qwen3b_unlocked.gguf 未生成
  (脚本纯 python 太慢, 可传 A800 跑或优化)
- unlock_3b.log: [120000/151936] 后无输出
