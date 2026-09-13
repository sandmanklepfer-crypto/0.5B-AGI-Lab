# 蒸馏主线交接 (2026-08-28 06:1x) — 32B→0.5B 全参蒸馏

## 一句话
**双卡 A800 (2×80GB) 正在并行跑三件事: v5 自进化(32B) + 蒸馏数据生成(32B teacher 双卡) + 3B 解锁实验(已完成)。**

## 双卡确认
- 2× A800 80GB PCIe (162GB 总显存), torch 2.8.0+cu128, transformers 4.49
- GPU0/GPU1 各自空闲 ~70GB (v5 占 ~11GB/卡, llama.cpp 双卡 split)

## 正在运行
1. **v5 自进化** (PID 3685, log: /root/autodl-tmp/evolve_v5.log)
   - 40轮×4时间线, 已到 r17 (69行), ~22s/步, 预计 ~06:30 完成
   - 皮层提炼 r15 已出规律: 区域0:随机/18分(n=22); 区域6:身攻/6分(n=23) 等
2. **蒸馏数据生成** (teacher_dump × 2 实例, 卡0=A 卡1=B)
   - A: distill_data_a/ 57/170 条; B: distill_data_b/ 24/169 条 (339 prompts)
   - teacher: R1-32B-Q4_K_M, max_new=250, K=64, temp=0.5
   - A 是旧版二进制(无piece), B 是新版(有piece) — 训练脚本统一走 vocab 表, 无影响
3. **3B 解锁实验** (已完成, 结论见下)

## 3B 解锁实验完整结论 (权重 bias 手术, 已闭环)
- 工具: dump_bias.py (向量化 q6_k 反量化) + extend_gguf.py (写 output.bias)
- **bias 生效验证**: logits_dump.c 对比原版/解锁版, logits 差 == bias 逐位相等 (corr=1.0)
- 3B 拒绝路径强度: 0.5B < 3B << 32B
  - α=10: 拒绝不变 (bias std=0.22)
  - α=50/100: 换拒绝模板 (第二个/第三个模板)
  - α=200: 击穿但退化 ("iscrimitie"×n 重复, bias 尖峰支配)
  - α=300+clamp±2.5: 英文拒绝; **α=300+clamp±4.0: 击穿, 自由生成(跑题成"蚂蚁森林机器人")**
- 结论: 权重级击穿可行, 但击穿后无好行为可回落 (RLHF 拒绝是强吸引子, 同 32B 结论)
- 产物: bias_3b_neg.bin (α=10 基准) + bias_{50,100,200,c300_2.5,c300_4.0,c500_2.5}.bin 保留
- 解锁 gguf 全部删除 (可从 bias bin + 原版一键重建)
- 注意: dump_bias.py 用 alpha=10 是正方向, **配方是 -10** (负号! build_unlock_3b.py 里写明)

## 蒸馏主线 (当前)
- 工具: teacher_dump.c (批量 prompts → gen tokens + top-k logits 稀疏存储)
  - 格式: magic=0x54444344, K, n_prompt, n_gen, prompt_toks, gen_toks, top_ids(ng×K u32), top_logits(ng×K f32), [新版附加 pieces]
  - 编译: gcc -O2 -I llama.cpp/include -I llama.cpp/ggml/include X.c -L llama.cpp/build-cuda/bin -lllama -lm -Wl,-rpath,... 
  - 新 API 注意: llama_memory_clear(llama_get_memory(ctx), false) 代替 llama_kv_cache_clear
- 数据: distill_prompts.txt (339条, prompts_gen.py 生成, 主题×模板组合)
- vocab 映射: dump_vocab.c → /tmp/teacher_vocab.txt (152064 tokens, R1 比 Qwen2.5 多128 special)
  - student qwen2.5-0.5b-instruct vocab = 151936
- 训练脚本: distill_train.py (CE + KL(T=2), top-k masked softmax, 全参 bf16)
  - student: /root/autodl-tmp/qwen05b (safetensors 已下载 988MB)
  - 输出: /root/autodl-tmp/distill_out/

## 下一步
1. 数据生成完 (~06:25) → distill_train.py 训练 (几分钟)
2. 验证: transformers 生成 对比 0.5B 原版 vs 蒸馏版 (知识/代码/推理/拒绝)
3. 转 GGUF: llama.cpp/convert_hf_to_gguf.py → 手机用 (0.5B 是手机端成果模型群延续)
4. v5 跑完后: 看进化结果 (全局最优决策/皮层规律), 决定是否扩大数据再训
5. 数据扩大: prompts 扩到 1000+, teacher_dump 再跑 (双卡 ~30 分钟)

## 环境坑 (重复踩)
- ssh 非交互 PATH 无 conda → 用 /root/miniconda3/bin/python3
- setsid nohup ... & 在 ssh 里会挂起 (等 fd), 但进程实际已启动 → 超时没关系, 单独查
- pkill/pgrep -f 自匹配 → 用 [x] 技巧
- llama-cli -p 会进交互模式不退出 → 用 -st (single turn) + timeout
- 磁盘: 50G 已用 34G, 剩 17G; 32B 相关大文件多, 谨慎
