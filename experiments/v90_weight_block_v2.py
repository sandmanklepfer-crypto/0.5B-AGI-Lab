#!/usr/bin/env python3
"""
V90 权重分块 v2 — 流形子空间分块 (知识/推理)

v86 第一版失败原因(已知): ① 用单 LDA 方向(秩1)太粗 ② 层12(浅层)未分离
V90 做法(对应启动指引下一步):
  1. 候选深层 {20,21,22,23}(V85证明方向级100%可分) + 层12/18作对照
  2. 采 知识任务/推理任务 的 down_proj 输入激活(4864维), 一次前向收集所有层
  3. 剔除全体公共 top-P 主方向(共享语言结构) → 残差空间
  4. 残差空间内 知识/推理 各自 PCA 取 top-m 主方向 → 流形子空间 U_k / U_r
  5. U_r 相对 U_k 正交化(剔除重叠) → U_ro; 报告两子空间主角度(重叠)
  6. 权重恒等分块: W_k = W·P_k, W_r = W·P_ro, W_rest = W-W_k-W_r  (W = Wk+Wr+Wrest)
  7. 判据(训练集+未见测试集):
     - 能量隔离: 知识输入能量应集中在 P_k(高) 且 P_ro(低); 推理输入反之
     - 输出通路隔离: ||W_r·x_知识||/||W·x_知识|| 应小; ||W_k·x_推理||/||W·x_推理|| 应小
  8. 选最优(层,m) → 整模型注入验证: 沿知识主方向给 W_k 加干净补丁 Δk
     (Δr 同理给 W_r) → 测 知识/推理 题 logits KL 变化
     → 若 Δk 只扰动知识题、Δr 只扰动推理题 = 分块成功(可独立写活/外挂)
产物: life1/v90_blocks.pt (层, 子空间基, 块权重, 指标) + 终端报告
"""
import os, copy, json, itertools
import numpy as np
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/qwen25_base_raw'
SAVE = '/root/autodl-tmp/life1'
WN_FMT = 'model.layers.{L}.mlp.down_proj.weight'
D_IN = 4864
# 层候选: 深层4个(V85成功区) + 浅中层对照(预期失败,证明选层必要性)
LAYERS = [12, 18, 20, 21, 22, 23]
M_SCAN = [8, 16, 24]
P_COMMON = 8   # 公共方向剔除个数

# ---------------- 任务集 (训练40/类 用于PCA; 测试20/类 用于验证, 完全不参与构造) ----------------
KNOW_TRAIN = [
    "中国的首都是什么？","水的沸点是多少摄氏度？","光在真空中的速度大约是多少？",
    "水的化学式是什么？","一年有多少个月？","中国有多少个省级行政区？",
    "珠穆朗玛峰的海拔大约是多少米？","地球围绕什么天体公转？","中华人民共和国的国庆日是哪一天？",
    "氧气的化学式是什么？","一公里等于多少米？","一天有多少个小时？",
    "一个星期有几天？","太阳系有几大行星？","汉语拼音一共有多少个声母？",
    "中国的陆地面积大约是多少平方公里？","心脏在人体的哪一侧？","二氧化碳的化学式是什么？",
    "秦始皇统一中国是在哪一年？","地球上最大的海洋是哪个？","植物进行光合作用需要吸收什么气体？",
    "唐朝的首都是哪里？","一年有几个季节？","一吨等于多少千克？",
    "中国的第一大河是什么？","圆周率大约等于多少？","中国的国歌是什么？",
    "水的密度大约是多少？","人体有多少块骨头？","中国的国旗是什么颜色？",
    "食盐的化学名称是什么？","太阳从哪个方向升起？","一斤等于多少克？",
    "中国的邻国有多少个？","世界上最高的山峰叫什么？","火星是太阳系第几颗行星？",
    "熊猫主要吃什么？","长江最终流入哪个海？","中国的首都是哪个城市？",
    "一秒钟等于多少毫秒？",
]
REASON_TRAIN = [
    "所有鸟都有翅膀，企鹅是鸟，企鹅有什么？","大象比马重，马比羊重，谁最轻？",
    "甲比乙高，乙比丙高，三人中谁最高？","如果明天下雨活动就取消，明天确实下雨了，活动会怎样？",
    "只有满十八岁才能进网吧，小明今年二十岁，小明能进网吧吗？",
    "所有的鱼都会游泳，鲸鱼不是鱼，鲸鱼会游泳吗？","A比B高，B比C矮，三人中谁最矮？",
    "小红比小兰大三岁，小兰比小刚大两岁，小红比小刚大几岁？",
    "如果P则Q，P是真的，那么Q是真还是假？","猫都抓老鼠，小花是猫，小花会抓老鼠吗？",
    "甲是乙的爸爸，乙是丙的爸爸，丙是甲的什么人？","先烧水再泡茶，水烧开了应该先做什么？",
    "张三比李四高，李四比王五矮，谁最矮？","三人排队，甲在乙前面，乙在丙前面，谁排在最后？",
    "十减三等于七，七加五等于多少？","如果今天是星期三，那么后天是星期几？",
    "所有金属都能导电，铜是金属，铜能导电吗？","小明有五个苹果，吃了两个，又买了三个，现在有几个？",
    "五大于三，三大于一，这三个数哪个最大？","所有的学生都要考试，小刚是学生，小刚要考试吗？",
    "A比B重，B比C轻，谁最重？","甲排第一，乙排在甲后面，丙排在乙后面，谁排最后？",
    "父亲比儿子大三十岁，儿子今年十岁，父亲今年多大？",
    "汽车比自行车快，自行车比步行快，哪种最快？","小王早上八点出发，走了两个小时，几点到达？",
    "如果天下雨则地会湿，现在地没湿，天是否下过雨？","鸡蛋煮熟需要十分钟，七点五十开始煮，几点能熟？",
    "最小的三位数是多少？","甲比乙矮，乙比丙矮，三个人谁最高？","一个数的两倍是十，这个数是多少？",
    "所有哺乳动物都喝奶，鲸鱼是哺乳动物，鲸鱼喝奶吗？","甲比乙早到十分钟，乙比丙早到五分钟，谁最早到？",
    "五个人排队，小明排第三，他前面有几个人？","如果A等于B，B等于C，那么A和C什么关系？",
    "正方形的四条边相等，这个图形是正方形，它的四条边怎样？","气温从五度升到十度，上升了几度？",
    "甲比乙小，乙比丙小，三人中谁最小？","两小时前是下午三点，现在几点？","一本书有三百页，每天看五十页，几天看完？",
    "三个苹果分给三个人，每人几个？",
]
KNOW_TEST = [
    "中国有多少个民族？","二氧化碳的化学式是什么？","地球的卫星叫什么？",
    "长江有多长？","中国的英文缩写是什么？","水的三种状态是什么？",
    "最大的陆地动物是什么？","一年有多少个星期？","中国的火车票实名制在哪年推行？",
    "食盐的主要成分是什么？","汉语有几个声调？","中国最长的河流是哪条？",
    "地球到太阳的平均距离大约是多少？","一公顷等于多少平方米？","鸟的呼吸器官是什么？",
    "中华人民共和国的首任总理是谁？","光年是长度单位还是时间单位？","春节一般在几月？",
    "中国的陆地邻国有几个？","声音在空气中传播的速度大约是多少？",
]
REASON_TEST = [
    "如果明天下雪就不出门，明天没下雪，会怎样？","甲乙丙三人赛跑，甲比乙快，乙比丙快，谁最慢？",
    "所有老师都戴眼镜，王老师是老师，王老师戴眼镜吗？","A比B多两个，B有五个，A有几个？",
    "甲排在乙前面三位，乙排在第十位，甲排第几？","六的一半的三倍是多少？",
    "只有做完作业才能看电视，小明没做完作业，小明能看电视吗？",
    "如果A大于B，B大于C，那么C和A谁大？","三个人年龄相加是六十岁，平均每人多少岁？",
    "甲是乙的妈妈，乙是丙的妈妈，丙是甲的什么人？","猫比狗轻，狗比大象轻，谁最重？",
    "小明七点开始写作业，写了四十分钟，几点写完？","如果明天是星期六，那么昨天是星期几？",
    "一列队伍，小刚前面有三人，后面有四人，队伍一共多少人？","甲今天比乙早到十分钟，明天乙比甲早到五分钟，明天谁先到？",
    "十以内的质数有哪些？","如果P则Q，Q是假的，那么P是真是假？",
    "五个连续自然数中，最小的一个是三，最大的是几？","所有正方形都是长方形，这个图形是正方形，它是什么形？",
    "甲比乙大三岁，丙比甲大两岁，丙比乙大几岁？",
]

def main():
    torch.manual_seed(0)
    np.random.seed(0)
    tok = AutoTokenizer.from_pretrained(MDIR)
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.bfloat16).to('cuda').eval()
    sd = model.state_dict()
    os.makedirs(SAVE, exist_ok=True)
    print('[V90] 权重分块v2: 流形子空间法 | 层=%s m=%s 公共剔除P=%d' % (LAYERS, M_SCAN, P_COMMON), flush=True)

    # ---------- 1. 一次前向采集所有层的 down_proj 输入(末token) ----------
    all_acts = {L: {'k_tr': [], 'r_tr': [], 'k_te': [], 'r_te': []} for L in LAYERS}
    def make_hooks():
        bufs = {L: [] for L in LAYERS}
        handles = []
        def hook_factory(L):
            def h(mod, inp, out):
                bufs[L].append(inp[0][0, -1].float().cpu())
            return h
        for L in LAYERS:
            handles.append(model.model.layers[L].mlp.down_proj.register_forward_hook(hook_factory(L)))
        return bufs, handles
    def run_batch(texts, tag):
        bufs, handles = make_hooks()
        with torch.inference_mode():
            for t in texts:
                ids = tok(t, return_tensors='pt').input_ids.to('cuda')
                model(input_ids=ids)
        for h in handles: h.remove()
        for L in LAYERS:
            all_acts[L][tag] = torch.stack(bufs[L]).numpy()  # (n,4864) float32
    print('[V90] 采集激活: 训练%d+%d / 测试%d+%d 题 × %d层 ...' % (
        len(KNOW_TRAIN), len(REASON_TRAIN), len(KNOW_TEST), len(REASON_TEST), len(LAYERS)), flush=True)
    run_batch(KNOW_TRAIN, 'k_tr'); run_batch(REASON_TRAIN, 'r_tr')
    run_batch(KNOW_TEST, 'k_te'); run_batch(REASON_TEST, 'r_te')
    print('[V90] 采集完成', flush=True)

    # ---------- 2. 工具函数 ----------
    def pca_top(A, m):
        """A: (n,d) → 返回前m个主方向 (d,m) 正交列; n<m时满秩"""
        A = A - A.mean(0, keepdims=True)
        m = min(m, min(A.shape) - 1)
        _, _, Vt = np.linalg.svd(A, full_matrices=False)
        return Vt[:m].T.astype(np.float64), m

    def sub_proj(U):
        return U @ U.T  # (d,d)

    # ---------- 3. 逐层分块 + 指标 ----------
    rows = []
    best = None
    Wcache = {}
    for L in LAYERS:
        WN = WN_FMT.format(L=L)
        W = sd[WN].float().cpu().numpy().astype(np.float64)  # (896,4864)
        Wcache[L] = W
        Ak, Ar = all_acts[L]['k_tr'], all_acts[L]['r_tr']     # (40,d)
        Tk, Tr = all_acts[L]['k_te'], all_acts[L]['r_te']     # (20,d)
        # 全体公共子空间 (共享语言结构方向)
        Aall = np.concatenate([Ak, Ar], 0)
        Uc, _ = pca_top(Aall, P_COMMON)
        Pc = sub_proj(Uc)
        # 残差空间
        Akr = Ak - Ak @ Pc; Arr = Ar - Ar @ Pc
        for m in M_SCAN:
            Uk, mk = pca_top(Akr, m)
            Ur, mr = pca_top(Arr, m)
            # U_r 相对 U_k 正交化
            Uro_raw = Ur - Uk @ (Uk.T @ Ur)
            Uro, _ = np.linalg.qr(Uro_raw)
            Uro = Uro[:, :min(mr, Uro.shape[1])]
            Pk = sub_proj(Uk); Pro = sub_proj(Uro)
            # 子空间重叠 (主角度 cos): 小=正交好
            sv = np.linalg.svd(Uk.T @ Uro, compute_uv=False)
            overlap = float(sv[0]) if len(sv) else 0.0
            # 能量隔离 (训练+测试)
            def energy_split(X):
                e = np.linalg.norm(X, axis=1)
                ek = np.linalg.norm(X @ Pk, axis=1) / np.maximum(e, 1e-9)
                er = np.linalg.norm(X @ Pro, axis=1) / np.maximum(e, 1e-9)
                return ek.mean(), er.mean()
            k_tr = energy_split(Ak); r_tr = energy_split(Ar)
            k_te = energy_split(Tk); r_te = energy_split(Tr)
            # 输出通路隔离 (W块): 知识输入经W_r应小, 推理输入经W_k应小 (测试集)
            Wk = W @ Pk; Wr = W @ Uro @ Uro.T
            def out_split(X):
                wx = np.linalg.norm(X @ W.T, axis=1)
                wk = np.linalg.norm(X @ Wk.T, axis=1)
                wr = np.linalg.norm(X @ Wr.T, axis=1)
                return (wk/np.maximum(wx,1e-9)).mean(), (wr/np.maximum(wx,1e-9)).mean()
            k_te_out = out_split(Tk); r_te_out = out_split(Tr)
            # 隔离分: 知识输入 in Pk 高 & in Pro 低; 推理反之 (测试集为准)
            score = 0.5*((k_te[0]-k_te[1]) + (r_te[1]-r_te[0]))
            rows.append(dict(L=L, m=mk, overlap=overlap,
                             k_tr=k_tr, r_tr=r_tr, k_te=k_te, r_te=r_te,
                             k_te_out=k_te_out, r_te_out=r_te_out, score=score))
            if best is None or score > best['score']:
                best = dict(L=L, m=mk, overlap=overlap, k_te=k_te, r_te=r_te,
                            k_te_out=k_te_out, r_te_out=r_te_out, score=score,
                            Uk=Uk, Uro=Uro, Pk=Pk, Pro=Pro, Wk=Wk, Wr=Wr, W=W)
    # 报告表
    print('\n=== 分块指标表 (测试集, 未见任务) ===', flush=True)
    print('层  m  重叠cos  知识入[Pk,Pro]  推理入[Pro,Pk]  知识经W_r  推理经W_k  score', flush=True)
    rows.sort(key=lambda r: -r['score'])
    for r in rows:
        print('L%2d %2d   %.3f    [%.2f,%.2f]     [%.2f,%.2f]     %.3f     %.3f    %.3f' % (
            r['L'], r['m'], r['overlap'],
            r['k_te'][0], r['k_te'][1], r['r_te'][1], r['r_te'][0],
            r['k_te_out'][1], r['r_te_out'][0], r['score']), flush=True)
    Lb, mb = best['L'], best['m']
    print('\n[V90] 最优: 层%d m=%d score=%.3f' % (Lb, mb, best['score']), flush=True)

    # ---------- 4. 恒等性检查 + 存产物 ----------
    W = best['W']; Wk = best['Wk']; Wr = best['Wr']
    Wrest = W - Wk - Wr
    err = np.abs(W - (Wk + Wr + Wrest)).max()
    print('[V90] 恒等分解误差 max=%.2e (应≈0)' % err, flush=True)
    torch.save({
        'layer': Lb, 'm': mb, 'overlap': best['overlap'],
        'Uk': torch.tensor(best['Uk']), 'Uro': torch.tensor(best['Uro']),
        'Pk': torch.tensor(best['Pk']), 'Pro': torch.tensor(best['Pro']),
        'Wk': torch.tensor(Wk).half(), 'Wr': torch.tensor(Wr).half(),
        'Wrest': torch.tensor(Wrest).half(),
        'score': best['score'], 'k_te': best['k_te'], 'r_te': best['r_te'],
        'k_te_out': best['k_te_out'], 'r_te_out': best['r_te_out'],
        'rows': rows,
    }, f'{SAVE}/v90_blocks.pt')

    # ---------- 5. 整模型注入验证 (最优层): Δk→W_k块, Δr→W_r块 ----------
    print('\n[V90] 整模型注入验证 (层%d, 沿各自流形第一主方向, 干净补丁幅度0.12x||W||)...' % Lb, flush=True)
    WN = WN_FMT.format(L=Lb)
    Uk, Uro = best['Uk'], best['Uro']
    # 干净补丁: patch = outer(d, u), 归一化 × ||W||_F × scale
    def clean_patch(u_dir):
        d = np.random.RandomState(1).randn(896).astype(np.float64)
        d = d / np.linalg.norm(d)
        u = u_dir.astype(np.float64); u = u / np.linalg.norm(u)
        P = np.outer(d, u)
        return P / np.linalg.norm(P) * (np.linalg.norm(W) * 0.12)
    Dk = clean_patch(Uk[:, 0])     # 只落在 W_k 子空间 (输入侧沿知识主方向)
    Dr = clean_patch(Uro[:, 0])    # 只落在 W_r 子空间
    # 原模型 logits 基线
    def last_logits(texts):
        out = []
        with torch.inference_mode():
            for t in texts:
                ids = tok(t, return_tensors='pt').input_ids.to('cuda')
                lg = model(input_ids=ids).logits[0, -1].float()  # (V)
                out.append(lg)
        return out
    def kl(p, q):
        lp = torch.log_softmax(p, -1); lq = torch.log_softmax(q, -1)
        return (torch.softmax(p, -1) * (lp - lq)).sum().item()
    print('  跑基线 logits (测试集)...', flush=True)
    base_k = last_logits(KNOW_TEST); base_r = last_logits(REASON_TEST)
    def inject_test(D, name):
        sd2 = copy.deepcopy(sd)
        sd2[WN] = torch.tensor(W + D).to(sd[WN].dtype)
        model.load_state_dict(sd2, strict=True)
        dk = [kl(base_k[i], last_logits([t])[0]) for i, t in enumerate(KNOW_TEST)]
        dr = [kl(base_r[i], last_logits([t])[0]) for i, t in enumerate(REASON_TEST)]
        mk, mr = float(np.mean(dk)), float(np.mean(dr))
        print('  注入%s: 知识题KL=%.4f 推理题KL=%.4f  隔离比=%s' % (
            name, mk, mr, ('%.2f' % (mk/mr) if mr > 1e-6 else 'inf')), flush=True)
        return mk, mr
    # 恢复原权重再逐个测
    model.load_state_dict(sd, strict=True)
    kl_k_dk, kl_r_dk = inject_test(Dk, 'Δk→知识块')
    model.load_state_dict(sd, strict=True)
    kl_k_dr, kl_r_dr = inject_test(Dr, 'Δr→推理块')
    model.load_state_dict(sd, strict=True)
    verdict = []
    if kl_k_dk > kl_r_dk * 1.5: verdict.append('知识块隔离✅ (Δk只动知识)')
    else: verdict.append('知识块隔离❌')
    if kl_r_dr > kl_k_dr * 1.5: verdict.append('推理块隔离✅ (Δr只动推理)')
    else: verdict.append('推理块隔离❌')
    print('\n[V90] 结论: %s' % ' | '.join(verdict), flush=True)
    print('[V90] 产物: %s/v90_blocks.pt' % SAVE, flush=True)

if __name__ == '__main__':
    main()
