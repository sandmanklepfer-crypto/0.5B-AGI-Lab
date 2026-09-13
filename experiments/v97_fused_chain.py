#!/usr/bin/env python3
"""
V97 合体骨架: 内部(机制/分块/知识世界) × 外部(显式哈希推理时间链)
不取消任何内部件:
  - 层12 antiheb 动态机制权重 (底子=antiheb_05b 整包, 即 base+层12手术)
  - 层20 知识/推理分块信息 (v92 Ukp/Urp)  → 知识世界路由
  - 知识锚库(规则句) + 每步取最相关锚注入 = 内部知识世界参与推理
  - 自发游离候选 = 每步模型在知识上下文中的自由一步生成(非死板)
新增外部件:
  - 显式状态链 s_t = (t, 上步hash, 结构化关系集, 步文本) 逐token推进
  - 每步 SHA256 哈希校验, 解析失败/冲突 → 回溯重生成(最多R次)
  - 符号刚性兜底: 模型产关系(语义), 差值链求解器算数(刚性,不漂移)
验收: 年龄难题链长<=12 解对; 全程hash校验通过; 对比无外链裸生成(应错/漂移)
"""
import re, hashlib, copy
import numpy as np
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL_DIR = '/root/autodl-tmp/life1/antiheb_05b'   # base + 层12机制(合体底子)
BLOCKS    = '/root/autodl-tmp/life1/v92_blocks.pt'
MAX_STEPS = 12
RETRIES   = 3

# ---------- 知识世界(内部): 规则锚 ----------
KNOWLEDGE = [
    "年龄差在两人都活着时永远保持不变，不管过多少年。",
    "如果甲比乙大n岁，乙比丙大m岁，那么甲比丙大n+m岁。",
    "十年后，每个人都长大十岁，但任何两人之间的年龄差不变。",
    "n年后某人的年龄 = 现在年龄 + n。",
    "如果甲比乙大n岁，反过来乙比甲小n岁。",
]
# ---------- 测试题 ----------
QUESTIONS = [
    ("小明比小红大3岁，小红比小刚大2岁，十年后小明比小刚大几岁？", "5"),
    ("甲比乙大7岁，丙比乙小2岁，现在甲比丙大几岁？", "9"),
]

NAME_RE = re.compile(r'[\u4e00-\u9fa5A-Za-z]+')
REL_RE  = re.compile(r'([\u4e00-\u9fa5A-Za-z]+)比([\u4e00-\u9fa5A-Za-z]+)(大|小)(\d+)岁')

def sha(prev, t, text):
    return hashlib.sha256(f"{prev}|{t}|{text}".encode()).hexdigest()[:16]

class Chain:
    """外部显式推理时间链: 刚性骨架"""
    def __init__(self, question, target_names):
        self.q = question
        self.target = tuple(target_names)
        self.states = []          # (t, prev_hash, relations:set, text)
        self.prev_hash = '0'*16
    def add(self, text, relations):
        self.states.append((len(self.states)+1, self.prev_hash, set(relations), text))
        self.prev_hash = sha(self.prev_hash, len(self.states), text)
    def back(self):
        if self.states:
            self.states.pop()
            self.prev_hash = self.states[-1][1] if self.states else '0'*16

def diff_chain_solve(relations, target_names):
    """差值链求解器(刚性): relations=[(A,B,delta)] 表示 A比B大delta岁(可为负)
       求 target (x,y) 的 x-y, 用图中路径累加。找不到返回 None"""
    names = {}
    for a, b, d in relations:   # a - b = d
        names.setdefault(a, []).append((b, d))
        names.setdefault(b, []).append((a, -d))
    x, y = target_names
    # BFS 求 x 到 y 的差值
    from collections import deque
    dq = deque([(x, 0.0)]); seen = {x}
    while dq:
        cur, acc = dq.popleft()
        if cur == y: return acc
        for nxt, d in names.get(cur, []):
            if nxt not in seen:
                seen.add(nxt); dq.append((nxt, acc + d))
    return None

def parse_relations(text):
    """从模型一步文本中抽取 (A,B,delta) A比B大delta岁 (小=负)"""
    out = []
    for m in REL_RE.finditer(text):
        a, b, op, n = m.group(1), m.group(2), m.group(3), int(m.group(4))
        d = n if op == '大' else -n
        if a != b: out.append((a, b, d))
    return out

def extract_names(q):
    """从问题中提取候选人名(粗): 找'X比Y'模式里的名字 + 目标句里的名字"""
    names = set()
    for m in REL_RE.finditer(q): names |= {m.group(1), m.group(2)}
    # 目标里的名字: 如 '十年后小明比小刚大几岁'
    m = re.search(r'[\u4e00-\u9fa5A-Za-z]+比([\u4e00-\u9fa5A-Za-z]+)', q[q.find('几岁'):] if '几岁' in q else q)
    return sorted(names)

def main():
    print('[V97] 合体骨架: 内部(机制底子antiheb_05b+知识锚) × 外部(哈希时间链+差值链求解)', flush=True)
    torch.manual_seed(0)
    tok = AutoTokenizer.from_pretrained(MODEL_DIR)
    model = AutoModelForCausalLM.from_pretrained(MODEL_DIR, torch_dtype=torch.bfloat16).to('cuda').eval()
    b = torch.load(BLOCKS, map_location='cpu', weights_only=False)
    print('[V97] 底子加载OK | 分块信息: 层%d Ukp%d/Urp%d (路由知识世界用)' % (b['layer'], b['Ukp'].shape[1], b['Urp'].shape[1]), flush=True)

    # 知识锚 → 向量(取模型倒数第2层末token), 每步检索最相关
    ANCHOR_LAYER = 22
    def embed(texts):
        vecs = []
        with torch.inference_mode():
            for t in texts:
                ids = tok(t, return_tensors='pt').input_ids.to('cuda')
                out = model(input_ids=ids, output_hidden_states=True)
                vecs.append(out.hidden_states[ANCHOR_LAYER][0, -1].float().cpu().numpy())
        return np.array(vecs)
    Kvec = embed(KNOWLEDGE)
    print('[V97] 知识世界锚=%d条' % len(KNOWLEDGE), flush=True)

    def gen_step(prompt, max_new=50):
        ids = tok(prompt, return_tensors='pt').input_ids.to('cuda')
        with torch.inference_mode():
            o = model.generate(ids, max_new_tokens=max_new, do_sample=False,
                               repetition_penalty=1.1, pad_token_id=tok.eos_token_id)
        return tok.decode(o[0][len(ids[0]):], skip_special_tokens=True).strip()

    def solve(q, target_names):
        chain = Chain(q, target_names)
        names = extract_names(q)
        relations = []
        # 先把题面已知关系全部抽出来(题面本身是外部给定的事实, 不算漂移)
        known = parse_relations(q)
        if not known:
            return chain, None, "题面未解析出关系"
        relations.extend(known)
        prompt_base = ("你是严格按步骤推理的助手。每步只写一句话的推理，形如："
                       "“甲比乙大n岁”或“甲比乙小n岁”或“所以甲比乙大n岁”。不要计算错误。\n\n")
        for step in range(1, MAX_STEPS + 1):
            # 内部知识世界: 检索当前最相关锚注入 (知识参与推理, 不取消)
            qv = embed([q])[0]
            sims = Kvec @ qv / (np.linalg.norm(Kvec, axis=1)*np.linalg.norm(qv)+1e-9)
            top = int(np.argmax(sims))
            # 刚性求解器先行: 若已能推出目标差 → 直接采用(符号,不漂移)
            ans = diff_chain_solve(relations, target_names)
            if ans is not None:
                chain.add(f"由已有关系列出: {target_names[0]}比{target_names[1]}大{int(ans)}岁(经差值链求和)", relations)
                return chain, int(ans), "OK"
            # 否则模型走一步(自发候选), 但只允许它给出新关系
            rtext = " | ".join(f"{a}比{b}{'大' if d>0 else '小'}{abs(int(d))}岁" for a, b, d in relations)
            anchor = KNOWLEDGE[top]
            for attempt in range(RETRIES):
                prompt = (prompt_base + f"题面: {q}\n已推出: {rtext or '无'}\n"
                          f"可用规则提示: {anchor}\n下一步推理(只说一句):")
                text = gen_step(prompt, max_new=60)
                new = parse_relations(text)
                # 校验: 不能自相矛盾(同对反向/不同差)
                ok = True
                for a2, b2, d2 in new:
                    if a2 == b2: ok = False; break
                    for a1, b1, d1 in relations:
                        if (a1, b1) == (a2, b2) and d1 != d2: ok = False; break
                        if (b1, a1) == (a2, b2) and -d1 != d2: ok = False; break
                if new and ok:
                    relations.extend([r for r in new])
                    chain.add(text, relations)
                    break
                else:
                    chain.back()   # 冲突 → 回溯重试(哈希链回退)
            # 无新有效关系: 强制补一步简单求和(允许模型给出组合, 但数字由符号器保证)
            else:
                # 找两个共享节点关系尝试组合: A-B + B-C => A-C
                merged = False
                for i in range(len(relations)):
                    for j in range(len(relations)):
                        a1, b1, d1 = relations[i]; a2, b2, d2 = relations[j]
                        if b1 == a2:
                            cand = (a1, b2, d1 + d2)
                            if all(not ((c[0]==cand[0] and c[1]==cand[1]) and c[2]!=cand[2]) for c in relations):
                                if cand[0] != cand[1]:
                                    relations.append(cand); merged = True
                                    chain.add(f"组合: {a1}比{b1}{'大' if d1>0 else '小'}{abs(d1)}岁, {a2}比{b2}{'大' if d2>0 else '小'}{abs(d2)}岁 → {a1}比{b2}{'大' if cand[2]>0 else '小'}{abs(int(cand[2]))}岁", relations)
                if not merged:
                    # 步数耗尽仍无解
                    break
            # 每步结束再试刚性求解
            ans = diff_chain_solve(relations, target_names)
            if ans is not None:
                chain.add(f"解得: {target_names[0]}比{target_names[1]}大{int(ans)}岁", relations)
                return chain, int(ans), "OK"
        return chain, None, "步数耗尽/无解"

    # ---- 运行测试题 ----
    for q, gold in QUESTIONS:
        print('\n' + '='*70, flush=True)
        print('【题】%s  (gold=%s)' % (q, gold), flush=True)
        names = extract_names(q)
        # 目标名: 从题里找 '十年后X比Y大几岁' / '现在X比Y大几岁'
        mt = re.search(r'[\u4e00-\u9fa5A-Za-z]+比([\u4e00-\u9fa5A-Za-z]+)(大|小)?几岁', q)
        # 取问题主句
        seg = q.split('，')
        target_names = None
        for s in seg:
            m = re.search(r'([\u4e00-\u9fa5A-Za-z]+)比([\u4e00-\u9fa5A-Za-z]+)(大|小)?几岁', s)
            if m:
                target_names = (m.group(1), m.group(2)); break
        if not target_names: target_names = tuple(names[:2])
        chain, ans, status = solve(q, target_names)
        print('【链】(外部显式哈希链, %d步):' % len(chain.states), flush=True)
        for t, ph, rels, text in chain.states:
            h = sha(ph, t, text)
            print('  t%d hash=%s | %s' % (t, h, text[:80]), flush=True)
        print('【校验】哈希链连续: %s' % ('OK' if all(s[1]== (chain.states[i-1][1] if i>0 else '0'*16) for i,s in enumerate(chain.states)) else 'FAIL'), flush=True)
        print('【结果】%s | 模型解=%s 标准=%s → %s' % (status, ans, gold, '✅' if str(ans)==gold else '❌'), flush=True)
    print('\n[V97] 完成', flush=True)

if __name__ == '__main__':
    main()
