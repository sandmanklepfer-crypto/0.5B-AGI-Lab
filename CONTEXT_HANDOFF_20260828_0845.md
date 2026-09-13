# 交接总结 (2026-08-28 08:45) — 0.5B 群几何蒸馏主线

## 一句话
A800 双卡上已跑通 R1/Qwen7B/Gemma 三源混合几何蒸馏，最新 v4（对称性损失版）概念锚定力达 7B+ 级；v4b 平衡版训练中。

## 服务器
- `sshpass -p '<REDACTED>' ssh -o StrictHostKeyChecking=no -p <PORT> root@<SERVER>`
- 2×A800 80GB + 1TB 内存；磁盘 50G 剩 ~3.4G（易满，随时清理旧版）
- 欠费停机过 2 次（07:0x、08:3x），恢复后资产都在
- python: /root/miniconda3/bin/python3（ssh 非交互 PATH 无 conda）
- 后台启动 ssh 必挂起（等 fd），超时=已启动，单独查

## 核心成果（A800 上）
| 版本 | 配置 | 特点 |
|---|---|---|
| distill_geom_v1 | 纯R1 210条/4ep/align1.0 | 结构✅执行❌（已删服务器版，本地备份✅） |
| distill_mix_v1 | R1+Q7B+Gemma 175/175/75 3ep/align0.5 | 执行✅(代码) 结构⚠️ |
| distill_mix_v2 | 同v1 但只对齐R1/align1.0 | 结构回稳，图灵测试跑偏 |
| **distill_mix_v3** | v2+语义增广aug2 | CE降、图灵锚定"图灵1950" |
| **distill_mix_v4** | 对称性损失版 sym_w=2.0 + |cos|对齐 | **图灵+《计算机器与智能》书名锚定(7B+级)**，但黑洞概念串扰("地球内部")=过度对称 |
| **distill_mix_v4b** | sym_w=0.5 平衡版 | 训练中(mix_v4b.log, distill_mix_v4b) |

## 实测定位 (v4)
- 概念锚定力(图灵书名): 7B+级 / 表达结构: 3B级 / 代码: 1.5-3B级 / 知识C-Eval: 15%(0.5B级) / 数学: 0.5B级
- 结论: 锚定力够7B，存量靠记忆系统补

## 关键工具/文件 (本地 /workspace/)
- teacher_dump.c: 生成+logits+激活+pieces, 用法: `<model> <prompts> <outdir> <max_new> <K> <temp> [layer] [prefix]`, 新API: llama_memory_clear(llama_get_memory(ctx),false)
- dump_vocab.c: teacher vocab 导出 (R1=152064 tokens, 前151643与student一致→id直连)
- distill_sym_train.py: v4版(对称性损失, --sym_w), 组结构+变体(文本级同义词替换)+|cos|对齐
- distill_mix_train.py: v1-v3版(--aug语义增广)
- eval_ceval.py: C-Eval 20题(5科×4题, /tmp/*.parquet)
- eval_oos.py / eval_distill.py / eval_meta.py(自我认知+群论10题)
- group_theory_gen.py: 102道群论题(已生成未训练)
- logits_dump.c, dump_bias.py, extend_gguf.py, geom_server_measure.c(层58激活服务)
- prompts_gen.py: 339条通用prompts; context_prompts.py: 75条Gemma上下文题

## 数据 (A800 /root/autodl-tmp/)
- distill_data_full_a/b: R1数据339条(175用)
- qwen7b_data: 176条 / gemma_ctx_data: 75条 / group_theory.txt: 102题
- 模型: r1-32b(19G), qwen2.5-7b分片(4.7G), gemma-3-12b(7.3G), qwen05b(0.99G), 3B coder(2.1G)

## 关键结论/教训
1. 知识选择题(C-Eval)蒸馏无提升→知识存量靠记忆系统(RAG/LFM2)补, 用户架构判断: 0.5B做皮层
2. 群论题≠模型内部对称性(概念错位, 用户已纠正); 对称性正确落点=语义不变增广+对称性损失(L_sym)
3. 群几何结构=表征层规范对称(O(n)线性骨架+G_sem语义不变群), |cos|对齐(±方向等价)
4. 过度对称→概念串扰(黑洞→地球); 需平衡(sym_w 0.5)
5. 训练防过拟合: 每源~175条+3ep+align_w1.0
6. 备份教训: v1曾被v2覆盖丢失→每个版本独立目录+训练完即备份本地
7. 本地手机磁盘233G易满(100%)→备份后清旧版; 服务器磁盘50G也满(删旧版distill_geom_*已释放)
8. LFM2-1.2B-RAG: 存在(官方GGUF+ModelScope), 未下载完整(删了不完整文件), 作为知识/RAG引擎候选

## 下一步 (用户方向)
1. v4b平衡版完成→eval对比(锚定力保留?区分度恢复?)
2. 回答用户问题: 整体跃升7B/14B/30B级需补齐哪个专精模型(候选: LFM2-1.2B-RAG知识、Qwen2.5-Math对称结构、代码/长上下文)
3. 对称性增强继续调优(群几何结构锻造)
4. 群论题数据可选加入(结构推理技能)
5. 备份策略: 每版本独立目录+本地下载

## 用户偏好
- 要成果不要过程; 清理删除需确认(成果模型不许删); 服务器打算保留几天
- 实时反馈(别长sleep); 语言中文; 认可"群几何/规范对称"理论框架但需工程落地
