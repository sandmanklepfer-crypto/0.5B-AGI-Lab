# MiniGPT 隐空间移植项目 — 上下文交接 (2026-08-22)

## 一、项目目标（一句话）
把 Qwen 0.5B（5亿参数）的"隐空间/权重结晶"通过免训练方式移植进手机小模型（130万-990万），让它获得对话能力。

## 二、已完成（一笔带过）
- Qwen 0.5B 已下载 (379MB GGUF)、llama.cpp 编译成功、本地推理 11 t/s
- 130万 wasm 核心 (minigpt_kv_v3.wasm) + 逐层隐藏状态导出接口 (layer_out)
- 全加速器训练脚本 train_dialog_v3.js (难例cap/作弊内化/多世界线/PBT/replay/独立存档)
- 浏览器 HTML 全套件 (MiniGPT_FullKit/): 终端/插件/爬虫/隧道/权重手术台/文件导入
- **15次移植实验** 全记录: embedding投影/权重倾倒/SVD双投影/逐层对齐/分布式聚合/因果移植 → 跨维度(896→128)全部失败(乱码), 同维度(192→192)成功(4/4继承)
- **已定位并修复 stride bug**: v3 wasm 静态数组 MAX_EMBED=256 → 层间stride=65536(非128²), bias/FFN/LN/weight-tying 全补全
- **哈希指纹校验工具**: 移植块写入即校验, 错位立刻报警 (已验证有效)
- **节点级因果定位**: "真好vs很糟" → 层23节点#95/#287/#92 是语义分化关键 (层21:#629/#624, 层12:#25/#58)
- **逐层隐空间提取工具 dump_layers4**: 用 llama.cpp cb_eval 计算回调, 24层×896维全部提取成功 (关键成果!)

## 三、接下来重点做 (新对话主任务)
**两阶段流形降维方案 (用户核心构想)**:

阶段1(离线,慢,一次): 用流形学习(Isomap/LLE)学习 Qwen 隐空间的"展平变换"——把弯曲的896维流形坐标变换到"接近刚体"(局部线性)的新坐标
阶段2(在线,极快): 新数据点套用展平映射 → 平直坐标下 896→128 线性投影(刚体变换) → 几千几万倍加速

**理论依据**: 光滑流形局部=切空间(刚体) [用户微积分洞察]; SVD全局线性投影撕裂流形(乱码根源), 流形学习分段展平不撕裂

**待办步骤**:
1. [ ] 用 Qwen 批量生成 200+ 条文本 (后台, 不占对话) → 提取层23隐空间 → 200×896 矩阵
2. [ ] 实现 Isomap (测地距离+经典MDS) / LLE (局部线性重建) 降维 896→128
3. [ ] 对比 SVD vs 流形学习: "真好/很糟"区分度保留率 (降维后距离/原始距离)
4. [ ] 若流形学习保留率显著高 → 两阶段方案成立 → 用展平坐标重做移植
5. [ ] 移植后测试: 学生是否学会条件化(不同问题→不同答案)

**数据现状**: 12个点太少(Isomap出NaN), 需200+点才可靠

## 四、关键文件清单
- /workspace/dump_layers4.cpp — 逐层隐空间提取 (编译: clang++ -I llama.cpp/include -I llama.cpp/ggml/include dump_layers4.cpp -o dump_layers4 -L llama.cpp/build/bin -lllama -Wl,-rpath,... -lm)
- /workspace/graft_fingerprint.js — 哈希指纹移植 (stride已修正: 层间65536)
- /workspace/isomap_test.js — Isomap vs SVD 对比 (需扩数据)
- /workspace/minigpt_kv_v3.wasm — 学生核心 (MAX_EMBED=256, 层stride=65536)
- /workspace/minigpt_kv_896.wasm — 896维核心 (MAX_EMBED=1024, 未用)
- /workspace/qwen2.5-0.5b-instruct-q4_k_m.gguf — Qwen 老师
- /tmp/qa_layers_L*.bin — 10条QA逐层隐空间 (24层×896)
- /workspace/zh_token_map.json / qwen_proj128.json — 字符映射/投影

## 五、关键坑(血泪)
- v3 wasm 层间stride=MAX_EMBED²=65536 (不是E²), bias/FFN/LN都要对应
- Qwen 输出层=token_embd转置(weight tying), 学生需 OUT_W[j*512+i]=tokenEmbed[i*128+j]
- Qwen 是 GQA(K/V 896→128低秩), 学生是全注意力 — 结构不完全对应
- llama.cpp 的 layer_inp API 是半成品(会崩), 用 cb_eval 计算回调才对
- 反量化 Q5_0: qh(16B高位bit)+ql(16B低位4bit) 布局, d=fp16 scale
- proot 里 pkill/fuser 杀进程会误伤容器, 用精确PID
- 后台长任务输出必须重定向, 否则刷爆对话
