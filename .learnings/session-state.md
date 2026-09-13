# Session State — 2026-08-30 深夜 (1.5B 越墙验证)

## 任务
验证容量墙: 1.5B 基座/蒸馏的深度维度(数学/知识/内化)是否随容量解锁。v4c 基准: 数学0.5B级(7×8=16错, 2^10崩), C-Eval 15%, 内化12/20≈基座。

## 服务器 (A800, 已恢复开机 2026-08-30 ~21:5x)
- ssh: `sshpass -p '<REDACTED>' ssh -p <PORT> root@<SERVER>`
- A800 80GB 全空闲; autodl-tmp 99%满(611M); /root overlay 剩 ~4G
- **坑**: pkill -f 自匹配杀 ssh 会话(255) → 必须用 [x] 技巧
- **坑**: hf-mirror 对 Qwen/Qwen2.5-1.5B-Instruct 的分片 safetensors 404(官方是单文件 model.safetensors 3.09GB, 已下好)

## 模型状态
- /root/qwen15b: Qwen2.5-1.5B-Instruct safetensors 完整 (model.safetensors 3.09GB + tokenizer) ✅
- /root/models/qwen2.5-1.5b-instruct-q4_k_m.gguf: 1GB GGUF 备用 ✅
- 教师 R1-32B GGUF: /root/autodl-tmp/r1-32b-gguf/ ✅
- v4c: /root/distill_v4c, v4b: /root/autodl-tmp/distill_mix_v4b ✅

## 评测 (后台跑, log: /root/eval_15b_base.log)
- eval_ceval.py (C-Eval 20题, parquet 在 /tmp) + eval_all15.py (群论10/元认知5/泛化10/通用10/数学7)
- eval_all15.py 在本地 /workspace/eval_all15.py (可复用给后续蒸馏版)

## Smoke test (已跑)
- 2^10=1024 ✅ (v4c 崩) — 初步信号: 数学随容量解锁
- 7×8 输出歪到 Brainly 网页模板 (未直接答 56)

## 下一步
1. 等评测结果 → 对比 v4c 基准
2. 若基座显著强 → 容量墙实锤; 可选: 1.5B 蒸馏 (v4c 配方, distill_train.py 改路径)

## 更新 (2026-08-30 23:5x — 3B 路线)
- 跨尺寸几何: 1.5B rank-1 孤例实锤 (0.5B/3B/32B 正交流), 放弃 1.5B 死磕, 转 3B
- 3B: coder-3b-instruct Q4 GGUF, transformers 加载 OK (61s, fp16 6GB)
  - 目录 /root/qwen3b-hf (config + qwen15b tokenizer 复用)
  - 评测脚本: /root/eval_all15_gguf.py + eval_ceval_gguf.py (gguf_file 注入)
  - smoke: 数学答非所问 (7×8→8×16, 2^10→10^10) — coder 版 QA 怪癖, 待完整评测
- 运行中: /root/run_eval_3b.sh → /root/eval_3b_base.log
- 下一步: 3B 蒸馏 (distill_train_15b.py 改 student=3B) → fix_template → 评测
- 磁盘: autodl-tmp 850M 空 (蒸馏输出 6GB fp16 放不下! 需要先腾空间: 删 qwen15b safetensors 3.1G + distill_15b_v4c 2.9G 或转 GGUF 后删)
