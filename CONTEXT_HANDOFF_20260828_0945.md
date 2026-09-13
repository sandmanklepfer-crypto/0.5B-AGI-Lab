# 交接总结 (2026-08-28 09:45) — v4c 版本 + 几何蒸馏探索

## 一句话
v4c（模板修复版）定为当前最佳；几何蒸馏 v1 失败（坐标系不匹配）；LFM2-RAG 蒸馏数据 56 条已生成但 v1 过拟合；模板串扰已根治。

## 服务器
- `sshpass -p 'vUSYaqTH1J+B' ssh -o StrictHostKeyChecking=no -p 29589 root@connect.nma1.seetacloud.com`
- 2×A800 80GB；**/root/autodl-tmp 只剩 611M（99% 满）**；/root(overlay) 剩 23G
- 新环境: transformers 5.16.1 装在 **/root/venv_lfm2** (--target, 用 PYTHONPATH 引用; conda 环境仍是 4.49 不认识 LFM2)
- pip 默认源 aliyun 挂掉 → 必须 `-i https://pypi.org/simple`
- ssh 后台任务必须 `setsid nohup ... < /dev/null`（nohup 会被 ssh 断开带走）

## 模型版本状态 (最新优先)
| 版本 | 位置 | 特点 |
|---|---|---|
| **v4c** | /root/distill_v4c | v4b + 模板串扰微调(60样本/1ep/lr1e-5) + 截断规则。**当前最佳** |
| v4b | /root/autodl-tmp/distill_mix_v4b | sym_w=0.5 平衡版; noctx=20/20 是模板污染虚高 |
| v4 | /root/autodl-tmp/distill_mix_v4 | sym_w=2.0, 过度对称 |
| rag_v1 | /root/autodl-tmp/distill_rag_v1 | LFM2-RAG 蒸馏 v1, 56条过拟合, 全面退化 ❌ |
| geom_v1 | /root/autodl-tmp/distill_geom_v1 | 距离矩阵蒸馏, 损失没降(目标不可达) ❌ |

## 实测定位 (v4c 实测)
- 概念锚定(图灵书名): 7B+级 (0.927 激活相似, 与基座持平) / 表达: 3B级(R1框架) / 代码: 1.5-3B(有真代码,小bug)
- 数学: 0.5B级(7×8=16错, 2^10崩) / 知识 C-Eval: 15% (无提升, 容量上限)
- **真实内化(无文档): 12/20 ≈ 基座** — 蒸馏未提升内化, 之前的20/20是模板数字污染
- 有文档作答 ctx: 16/20 (真实能力, 略高于基座15)

## 关键教训/发现 (新)
1. **模板串扰**: v4/v4b 答完接"请提供一份关于2008金融危机..." — 来自 gemma_ctx/rag 模板数据。修法: 微调answer+eos + 生成截断规则(双层)。**指标虚高警告: 任何"含数字即过"的评测会被模板数字污染**
2. **几何蒸馏v1失败**: ||D_s - D_t||_F 损失没降(0.501→0.505)。根因: 学生用自己SVD空间(96维), teacher用R1空间(256维), 坐标系不可比, 目标不可达。**v2方向: CCA共享投影桥 + 排序损失(对投影鲁棒)**
3. **RAG蒸馏v1失败**: 56条数据过拟合(CE拟合太狠, 泛化退化)。需175条/源标准 + 从v4c起步
4. **v1-v4行为蒸馏让几何偏离R1**: geom_rmse 基座0.445 < 蒸馏版0.50 — 行为对但流形结构被拉偏, 印证用户"泛化几何没内化"判断
5. LFM2-RAG 可用: 中文RAG grounded回答正常, greedy解码, ChatML模板, 支持中文

## 数据/工具 (服务器)
- /root/lfm2-rag: LFM2-1.2B-RAG safetensors + 配套 (2.3GB, 在/root不占autodl-tmp)
- /root/rag_data.jsonl: 56条 (context,query,answer,variants) — RAG蒸馏数据
- /root/probes.txt (96个probe) + /root/probe_geom_t.npz (D_t 96×96, mean=0.651) — 泛化几何目标
- /root/probe_r1/*.bin: R1-32B层58激活 (teacher_dump max_new=1)
- 脚本: gen_rag_data.py / distill_rag_v1.py / distill_geom_v1.py / eval_all.py / fix_template.py / qa_v4b.py / probe_geom.py
- 训练日志: rag_train.log / geom_train.log / fix_template.log / eval_v4c.log

## ⚠️ 待办: 备份缺口
- **v4b/v4c 本地无备份** (本地只有 v1/v2/v3/geom_v1); 09:5x 备份 v4b 时服务器第3次停机(Connection refused), 备份失败
- 服务器恢复后立即: ssh cat > 本地备份 v4b (959M) + v4c (954M); 本地磁盘剩 2.0G, 两者合计 1.9G 勉强可放, 需先清理本地旧备份(distill_geom_v1 944M 可删/压缩)

## agent 综合定位 (用户问答)
- v4b/v4c agent 实际使用 ≈ **1B 级** (0.5~1.5B): 意图/知识 0.5-1B, 表达 3B(错觉来源), 锚定 7B(不转化), 数学 0.5B(穿帮点)
- 3B 表达+7B锚定制造"话痨但不会做事"体验; agent 可用门槛 ≈ 3B

## 下一步 (用户方向)
1. **顶级难题压测 v4c** (用户要求: "上最顶级的难题")
2. 几何蒸馏 v2: CCA 共享投影 + 排序损失, 数据175条/源, 从v4c起步
3. 知识外挂: LFM2-RAG 引擎接入 (rag_engine.py 已就绪)
4. 修数学: 符号计算器外挂 (容量上限, 训练修不动)

## 用户偏好
- 要成果不要过程; 中文; 认可几何框架但需工程落地; 指标要挤水分(警惕虚高)
