
## [LRN-20260824-001] shell无root可调高通性能锁
**Logged**: 2026-08-24T23:50:00+08
**Priority**: high
**Status**: in_progress
**Area**: infra

### Summary
小米 HyperOS (onyx/25053RT47C, 骁龙) 的 SELinux 策略允许 shell 域 binder call vendor.perfservice (高通 IPerfManager), 无 root 即可获取性能锁。

### Details
- service call vendor.perfservice 3 i32 <dur_ms> i32 1 i32 <hint> → 返回 handle (perfLockAcquire 成功)
- hint 0x10800000/0x40800000 等需试验; 释放接口 code 4 参数格式待研究
- 附带发现: /dev/kgsl-3d0 mode 666 + shell 有 ioctl/map/write → GPU 用户态通道完全开放; NPU(fastrpc) 半开放; debug_prop/powerctl 可写; vendor_sysfs_kgsl_shell 有 write
- SELinux policy 已 dump: /workspace/policy.bin; 审计脚本: /workspace/selinux_audit.py
- 内核 config: /workspace/kernel_config.txt (DEBUG_FS_ALLOW_ALL, SELINUX_DEVELOP, BPF_LSM)

### Suggested Action
- perflock.sh 工具已建 (workspace/perflock.sh); 试验正确 hint 组合, 用于 AI 推理时防降频
- 下一步: 原生 Termux Vulkan llama.cpp (GPU 通道已确认可用)
---

## [LRN-20260830-001] 用户偏好：汉语思考/回复
**Logged**: 2026-08-30T14:00:00+08
**Priority**: medium
**Status**: resolved
**Area**: docs

### Summary
用户要求用汉语思考和回复（"汉语思考"）。

### Details
- 2026-08-30 用户明确指示："汉语思考"
- 之前会话中用户全程使用中文交流，且交接文档均为中文
- 内部思考与输出统一使用中文；保留代码/文件路径/专业术语原文

### Suggested Action
默认以中文回应；代码、路径、模型名、技术术语保持原文不译。

### Metadata
- Source: user_feedback
- Related Files: 所有交接文档
- Tags: language, preference
---

## [LRN-20260830-002] 容量墙实验实锤: 1.5B 基座深度随容量解锁
**Logged**: 2026-08-30T22:15:00+08
**Priority**: high
**Status**: in_progress
**Area**: backend

### Summary
1.5B 基座 (Qwen2.5-1.5B-Instruct) vs v4c (0.5B 蒸馏链顶点): C-Eval 15%→40%, 数学从"7×8=16/2^10崩"到"解方程/群论全对", 深度维度随容量显著解锁。

### Details
- C-Eval 20题: v4c 15% → 1.5B 基座 40% (8/20)
- 数学: 打八折96→120✅, 3x+5=20→x=5✅, 2^10=1024✅, 模7逆元=5✅, D_6=12✅, 2的阶推导✅, 无穷级数S=1/2✅ (v4c 全崩)
- 通识: 引力波/光合作用/自注意力/结冰 ✅ 内容充实
- **代价**: 1.5B 基座模板复述病 (Brainly/百度知道/雨露学习互助 网页模板), 元认知差 ("你是谁"→"我是王老师"), 对话框架不如 v4c
- 结论: 深度=容量的函数 (再次实锤); 蒸馏定位从"造能力"转为"修格式"

### Suggested Action
- 1.5B 蒸馏版评测中 (R1-32B teacher, 339条, CE+KL, 3ep): 验证能否保深度+洗模板病
- 评测脚本: /workspace/eval_all15.py (任意路径, temp0.7/top_p0.9, 数学greedy)

### Metadata
- Source: experiment
- Related Files: /workspace/eval_15b_base.log, /workspace/eval_all15.py
- Tags: capacity-wall, distillation, 1.5b
---

## [ERR-20260830-001] hf-mirror 单文件 safetensors 404 + 多层引号嵌套
**Logged**: 2026-08-30T22:15:00+08
**Priority**: medium
**Status**: resolved
**Area**: infra

### Summary
hf-mirror 对 Qwen/Qwen2.5-1.5B-Instruct 的分片文件名 (model-0000X-of-00002.safetensors) 返回 404 (官方仓库是单文件 model.safetensors); 多层引号嵌套 heredoc 导致 patch 静默失败。

### Error
- `curl -I .../model-00002-of-00002.safetensors` → HTTP/2 404; wget -c 下载成 0 字节文件还报成功
- ssh bash -c '...' 内嵌 python heredoc + 转义 \" 时 replace 未匹配, 训练脚本配置未改 → 0 样本空训练

### Context
- 下载 Qwen2.5-1.5B-Instruct: 用 snapshot_download (hf-mirror) 成功 (单文件 model.safetensors 3.09GB); GGUF 仓库 Qwen/Qwen2.5-1.5B-Instruct-GGUF 可用 (302→200)
- patch 脚本改用 scp 本地文件上传 → PATCH_OK

### Suggested Fix
- 下载 safetensors 优先 snapshot_download (hf 会解析真实文件名), 别猜分片文件名
- 复杂修改脚本 → 本地写文件 + scp 上传 + 远程执行, 避免多层引号嵌套
- pkill -f 自匹配杀 ssh (255) → 用 [x] 技巧 (老坑复踩)

### Metadata
- Reproducible: yes
- Related Files: /workspace/patch_15b.py, /workspace/dl15b_wget.sh
---

## [LRN-20260830-003] 蒸馏双刃剑: 1.5B 蒸馏洗模板但冲掉数学 (灾难性遗忘)
**Logged**: 2026-08-30T22:40:00+08
**Priority**: critical
**Status**: resolved
**Area**: backend

### Summary
1.5B 基座 + R1-32B 蒸馏 (339条/3ep/全参bf16/LR5e-5): 通用对话/代码提升 (黑洞/快排/睡眠 ✅ 格式干净), 但数学/群论/C-Eval 全崩 (C-Eval 40%→25%, 解方程→复读机乱码). 0.5B 时代看不见的现象: 蒸馏会冲掉已有的深度.

### Details
- 三方对比: v4c(C-Eval 15%, 数学崩, 对话好R1格式) | 1.5B基座(C-Eval 40%, 数学✅解方程/群论, 对话模板病) | 1.5B蒸馏(C-Eval 25%, 数学崩复读机, 对话✅格式干净+快排代码对)
- 机制: 蒸馏数据是通用对话型 (339条黑洞/代码/睡眠等), 把模型往对话分布拉; 数学/精确推理是"稀有技能", 不在数据里 → 被覆盖 (灾难性遗忘)
- 0.5B 时代数学本来为0, 蒸馏无损失可言; 1.5B 时代数学为40%, 蒸馏损失可见 → "蒸馏加广度损深度"在 1.5B 被实验证实
- 元认知两边都差 (基座"几何蒸馏"答成化学, 蒸馏版答成300KPa) — 非蒸馏之过

### Suggested Action
- 蒸馏配方需保护深度: 冻结浅层/LoRA/低LR/KL权重降/数学数据补进蒸馏集 (R1教师生成数学题)
- 数学最终解仍是外挂 (calc) — 容量墙+蒸馏遗忘双重确认
- 评测脚本: /workspace/eval_all15.py + eval_ceval.py 三版本全量 log 在 /workspace/

### Metadata
- Source: experiment
- Related Files: /workspace/eval_15b_base.log, /workspace/eval_15b_dist.log
- Tags: distillation, catastrophic-forgetting, 1.5b, capacity-wall
---

## [LRN-20260830-004] 1.5B 越墙验证实验记录 (服务器恢复后首轮)
**Logged**: 2026-08-30T22:40:00+08
**Priority**: medium
**Status**: resolved
**Area**: infra

### Summary
服务器 (A800, 第8次欠费后恢复) 完成 1.5B 越墙验证: 下载/训练/评测全链路复跑, 实验资产盘点更新.

### Details
- /root/qwen15b: Qwen2.5-1.5B-Instruct safetensors 完整; /root/models/qwen2.5-1.5b-instruct-q4_k_m.gguf (备用)
- /root/autodl-tmp/distill_out_15b: 1.5B 蒸馏版 (3.09GB, 数学崩, 留作标本/可删)
- teacher 数据 distill_data_full_a/b (339条) 仍在; distill_train_15b.py 是 1.5B 版配置
- 磁盘: 清了 test40/u60/unlock_test/vlog 日志 + distill_mix_v2 + distill_geom_v1 → autodl-tmp 3.9G 空闲
- v3 本地备份损坏 → 服务器 distill_mix_v3 保留 (唯一好副本, 别删!)

### Suggested Action
- 下次实验直接用 distill_train_15b.py 模板; 加数学保护需改数据/KL
- 待办: 干净 Δ 测量 (基座 safetensors 已具备)

### Metadata
- Source: experiment
- Related Files: /workspace/patch_15b.py, /workspace/eval_all15.py
- Tags: infra, 1.5b, server
---

## [LRN-20260830-005] 1.5B 几何解剖: 低秩共线流形 (rank-1) — 与 0.5B 正交残差流根本不同
**Logged**: 2026-08-30T23:40:00+08
**Priority**: critical
**Status**: resolved
**Area**: backend

### Summary
1.5B (Qwen2.5-1.5B, 28x1536) 严谨口径解剖 (20000 tokens float32 SVD): 中间23层 (L2-L24) 有效维=1 (50/90/99%能量全1主成分), adj-cos=+0.885 (0.5B=-0.013!), 概念锚定只有二分方向, 敏感区在 L2-L8 中层 (0.5B/32B 是深层!), 深层 L26-27 极钝 (Δ注入需100%范数才全翻转).

### Details
- [1] 骨架: adj-cos 均值+0.8845 (逐层0.06→0.81→0.86-0.97→0.38); off-diag|cos| 0.53; 有效维 L0:584 L1:506 L2-L24:1 L27:630 L28:393; 范数剖面 L1→L2 跳8.8x, 平台爬升至L26=550, L27/L28骤降(287/129)
- [2] 锚定(去均值): 中层L14 概念全二分(±1.0, 攻击/自我 vs 其他); 深层L26 分化: 图灵/几何蒸馏/拒绝/数学 组间0.97-1.0, 攻击/自我 -0.99 反向 → 概念只有两个方向簇, 无细粒度锚定
- [3] 层敏感性(相对扰动σ=1%范数): L2-L8 flip 0.89 最敏感, L27最钝(0.22), L0钝(0.00); σ=5%时 L2-L7 全flip 1.0
- [4] Δ注入(L26, 相对强度): 1%-50%范数 flip 恒 0.33 封顶, 100%范数才 flip 1.00 → 深层注入极钝
- 矛盾解释: 1.5B 数学比 0.5B 强但流形 rank-1 → 知识在权重里, 激活走窄管; 容量墙本质是权重容量不是流形宽度
- 对训练含义: ①蒸馏/注入应打 L2-L8 敏感区 (0.5B/32B 打深层经验在此反转) ②rank-1 无独立方向, Δ注入只能平移整条线 → 全参蒸馏大LR会把整条线推走 (数学崩根因) ③深层 L26-27 是知识钝区, 应保护

### Suggested Action
- 1.5B 蒸馏新配方: 只动敏感中层 L2-L8 (LoRA 或冻结 L9-L27), 保护深层知识区
- 解剖脚本: /workspace/geometry_15b_v3.py (可复用任何模型); log: /workspace/geometry_15b_v3.log

### Metadata
- Source: experiment
- Related Files: /workspace/geometry_15b_v3.py, /workspace/geometry_15b_v3.log
- Tags: geometry, 1.5b, rank-1, capacity-wall
---

## [LRN-20260830-006] 跨尺寸几何对比: 1.5B 是 Qwen2.5 家族的 rank-1 几何异常点
**Logged**: 2026-08-30T23:55:00+08
**Priority**: critical
**Status**: resolved
**Area**: backend

### Summary
严格同口径 (879段 mean向量, float32 SVD) 对比: 0.5B/3B/32B 都是正交残差流 (adj-cos≈0, 有效维12-631), 唯独 1.5B 中间24层 (L2-L25) 有效维=1, adj-cos=+0.92 — rank-1 共线流形, 家族几何异常点.

### Details
- 32B (R1-Distill-Qwen-32B Q4, dump_layers导出): adj-cos=-0.0001, off-diag 0.013, 有效维 L0-L63: 125-631, 范数单调爬升 (L63=156尖峰)
- 1.5B (mean口径879段, 与32B严格同口径): adj-cos=+0.92 (L2-L25全0.995-1.0), off-diag 0.84, 有效维 L2-L26=1/1/1 (50/90/99%能量1主成分), 范数 L1→L2 跳30x 平台~660 末尾L27骤降259
- 1.5B per-token口径 (20000 tokens): 同样 rank-1 → 不是口径假象
- 0.5B(旧): -0.013/13-15; 3B(旧): +0.004/12-15 → 与32B同家族
- 结论: 1.5B 是唯一 rank-1 孤例 — "窄管厚权重": 知识在权重(数学强)但激活读取是单方向线
- 解释容量墙: 流形维度 vs 权重容量错配; rank-1 上 Δ注入只能平移整条线 → 蒸馏一推就全崩 (数学崩根因几何版)
- 工具链: dump_layers_fix.c (KV clear 补丁, 修了连续文本KV溢出); analyze_mean.py (通用mean口径分析); dump_mean_15b.py (transformers mean dump)

### Suggested Action
- 补 3B 同口径 (服务器 qwen2.5-coder-3b GGUF) 确认 1.5B 是孤例还是 1.5B-3B 区间异常
- 若孤例: 1.5B 蒸馏只能走"保护深层+小步微调", 或直接放弃 1.5B 走 3B
- 待办: 干净 Δ 测量依旧 (GGUF 量化对 32B 有效维有污染可能, 但 rank-1 vs 125-631 是数量级差异, 量化污染不足以解释)

### Metadata
- Source: experiment
- Related Files: /workspace/analyze_mean.py, /workspace/dump_mean_15b.py, /root/acts32/, /root/acts15/
- Tags: geometry, cross-size, rank-1, 1.5b, 32b
---

## [LRN-20260830-007] 3B 同口径确认: 1.5B 是家族唯一 rank-1 异常点, 3B 是正流形越墙点
**Logged**: 2026-08-30T23:59:00+08
**Priority**: critical
**Status**: resolved
**Area**: backend

### Summary
3B (Qwen2.5-Coder-3B Q4, 879段同口径): adj-cos=-0.003, 有效维88-213 → 与 0.5B/32B 同为正交残差流家族. 1.5B (rank-1) 是 Qwen2.5 家族唯一几何异常点. 3B 是"正流形上的最小越墙点".

### Details
- 完整跨尺寸表 (严格同口径 879段 mean 向量):
  | 模型 | adj-cos | 有效维@90% | 范数剖面 |
  | 0.5B | -0.013 | 13-15 | 单调 |
  | 1.5B | +0.92 | 1 (L2-L25) | L1→L2跳30x, 末尾骤降 |
  | 3B | -0.003 | 88-213 | 平台+末尾爬升 |
  | 32B | -0.0001 | 125-631 | 单调爬升 |
- 3B coder GGUF 在 /root/autodl-tmp/models/ (2.1GB); dump_layers_fix 879段秒级完成
- 1.5B 异常含义: ①蒸馏崩数学=rank-1无方向自由度 ②执行强理解弱=窄管厚权重 ③0.5B/3B/32B 蒸馏注入正常=多维流形
- 路线修正: 1.5B 是错误中转站; 3B 是正流形最小越墙点 (容量>1.5B + 几何正常)

### Suggested Action
- 3B 做 v4c 式蒸馏 (或先测 3B 基座 C-Eval/数学对照 1.5B)
- 若坚持 1.5B: 只能保护深层+打 L2-L8 敏感中层微调, 天花板低于 3B
- 待办: 干净 Δ 测量 (32B 基座 safetensors) 依旧挂起

### Metadata
- Source: experiment
- Related Files: /root/acts3/, /workspace/analyze_mean.py
- Tags: geometry, cross-size, 3b, rank-1
---
