#!/usr/bin/env python3
"""
V97b 合体骨架(修复版): 内部 × 外部哈希时间链
修复 v97 两个 bug:
  1. 目标名解析把"十年后/现在"等词吃进人名 → 限定在题面已知人名集合内匹配
  2. base 生成漂移跑题(△ABC题库/复读) → 跑题检测丢弃重试 + max_new_tokens收紧
  3. 解析放宽: "甲比丙大7+2=9岁" 计算式 → 算出数值
判据不变: 年龄难题解对 + 哈希链展示 + 组合器/符号器刚性兜底
"""
import re, hashlib, copy
from collections import deque
import numpy as np
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL_DIR = '/root/autodl-tmp/life1/antiheb_05b'
BLOCKS    = '/root/autodl-tmp/life1/v92_blocks.pt'
MAX_STEPS = 10
RETRIES   = 3
ANCHOR_LAYER = 22

KNOWLEDGE = [
    "年龄差在两人都活着时永远保持不变，不管过多少年。",
    "如果甲比乙大n岁，乙比丙大m岁，那么甲比丙大n+m岁。",
    "十年后，每个人都长大十岁，但任何两人之间的年龄差不变。",
    "n年后某人的年龄 = 现在年龄 + n。",
]
QUESTIONS = [
    ("小明比小红大3岁，小红比小刚大2岁，十年后小明比小刚大几岁？", "5"),
    ("甲比乙大7岁，丙比乙小2岁，现在甲比丙大几岁？", "9"),
]
NAME_RE = re.compile(r'([\u4e00-\u9fa5A-Za-z]+)比([\u4e00-\u9fa5A-Za-z]+)(大|小)(\d+)岁')
REL_LOOSE = re.compile(r'([\u4e00-\u9fa5A-Za-z]+)比([\u4e00-\u9fa5A-Za-z]+)(大|小)([0-9+\-×x*=]+?)岁')
BAD_PATTERNS = ['△', 'ABC', '阅读下面', '任务栏', '请逐步推理，找出', 'Human:', 'Assistant', '一个零也不读']

def sha(prev, t, text):
    return hashlib.sha256(f"{prev}|{t}|{text}".encode()).hexdigest()[:16]

def parse_relations(text, known_names):
    """从文本抽取 (A,B,delta): A比B大delta岁(小=-). 名字必须∈known_names. 支持计算式"""
    out = []
    for m in REL_LOOSE.finditer(text):
        a, b, op, expr = m.group(1), m.group(2), m.group(3), m.group(4)
        if a not in known_names or b not in known_names or a == b: continue
        expr = expr.replace('×', '*').replace('x', '*').replace('X', '*').replace('=', '')
        try:
            n = int(eval(expr))
        except Exception:
            continue
        if abs(n) > 1000 or n == 0: continue
        d = n if op == '大' else -n
        out.append((a, b, d))
    return out

def diff_chain_solve(relations, target):
    names = {}
    for a, b, d in relations:
        names.setdefault(a, []).append((b, d))
        names.setdefault(b, []).append((a, -d))
    x, y = target
    dq = deque([(x, 0.0)]); seen = {x}
    while dq:
        cur, acc = dq.popleft()
        if cur == y: return acc
        for nxt, d in names.get(cur, []):
            if nxt not in seen:
                seen.add(nxt); dq.append((nxt, acc + d))
    return None

def extract_known(q):
    names = set()
    for m in NAME_RE.finditer(q):
        names |= {m.group(1), m.group(2)}
    rels = []
    for m in NAME_RE.finditer(q):
        a, b, op, n = m.group(1), m.group(2), m.group(3), int(m.group(4))
        rels.append((a, b, n if op == '大' else -n))
    return sorted(names), rels

def find_target(q, known_names):
    """在含'几岁'的段中找 (X,Y): X比Y…几岁, X、Y用朴素定位(排除'大'字吃进名字)"""
    for s in q.split('，'):
        if '几岁' not in s and '多少岁' not in s:
            continue
        for y in known_names:
            idx = s.find('比' + y)
            if idx < 0:
                continue
            tail = s[idx:]
            if '几岁' in tail or '多少岁' in tail:
                before = s[:idx]
                x = None
                for n in known_names:
                    if n != y and before.rfind(n) >= 0:
                        if x is None or before.rfind(n) > before.rfind(x):
                            x = n
                if x:
                    return (x, y)
    return None

def main():
    print('[V97b] 合体骨架(修复): 内部机制底子 + 知识锚 × 外部哈希链 + 符号刚性器', flush=True)
    torch.manual_seed(0)
    tok = AutoTokenizer.from_pretrained(MODEL_DIR)
    model = AutoModelForCausalLM.from_pretrained(MODEL_DIR, torch_dtype=torch.bfloat16).to('cuda').eval()
    b = torch.load(BLOCKS, map_location='cpu', weights_only=False)
    print('[V97b] 底子: antiheb_05b (层12机制) | 分块: 层%d Ukp%d/Urp%d' % (
        b['layer'], b['Ukp'].shape[1], b['Urp'].shape[1]), flush=True)

    def embed(texts):
        vecs = []
        with torch.inference_mode():
            for t in texts:
                ids = tok(t, return_tensors='pt').input_ids.to('cuda')
                out = model(input_ids=ids, output_hidden_states=True)
                vecs.append(out.hidden_states[ANCHOR_LAYER][0, -1].float().cpu().numpy())
        return np.array(vecs)
    Kvec = embed(KNOWLEDGE)

    def gen(prompt, max_new=36):
        ids = tok(prompt, return_tensors='pt').input_ids.to('cuda')
        with torch.inference_mode():
            o = model.generate(ids, max_new_tokens=max_new, do_sample=False,
                               repetition_penalty=1.2, pad_token_id=tok.eos_token_id)
        return tok.decode(o[0][len(ids[0]):], skip_special_tokens=True).strip()

    for q, gold in QUESTIONS:
        print('\n' + '=' * 70, flush=True)
        print('【题】%s (标准=%s)' % (q, gold), flush=True)
        known_names, base_rels = extract_known(q)
        target = find_target(q, known_names)
        print('  解析: 人名=%s 目标=%s 题面关系=%s' % (known_names, target, base_rels), flush=True)
        if target is None:
            print('  ❌ 目标解析失败', flush=True); continue
        # 外部链
        relations = list(base_rels)
        steps = []
        prev_hash = '0' * 16
        status = '无解'
        ans = None
        # 先试直接链式求解
        ans = diff_chain_solve(relations, target)
        if ans is not None:
            text = '题面直接给出: %s比%s大%d岁' % (target[0], target[1], int(ans))
            steps.append((1, prev_hash, text)); prev_hash = sha(prev_hash, 1, text)
            status = 'OK(题面直解)'
        for step in range(len(steps) + 1, MAX_STEPS + 1):
            ans = diff_chain_solve(relations, target)
            if ans is not None:
                text = '差值链求和得出: %s比%s大%d岁' % (target[0], target[1], int(ans))
                steps.append((step, prev_hash, text)); prev_hash = sha(prev_hash, step, text)
                status = 'OK'; break
            rtext = ' | '.join('%s比%s%s%d岁' % (a, b, '大' if d > 0 else '小', abs(int(d))) for a, b, d in relations)
            qv = embed([q])[0]
            sims = Kvec @ qv / (np.linalg.norm(Kvec, axis=1) * np.linalg.norm(qv) + 1e-9)
            anchor = KNOWLEDGE[int(np.argmax(sims))]
            got_new = False
            for attempt in range(RETRIES):
                prompt = ('你是严格的推理助手。请只输出一句形如"X比Y大N岁"或"X比Y小N岁"的推理，'
                          '其中X、Y必须是{%s}中的名字，N是数字。不要解释，不要多余字。\n'
                          '题面: %s\n已推出: %s\n规则: %s\n下一步:'
                          % ('、'.join(known_names), q, rtext or '无', anchor))
                text = gen(prompt)
                if any(p in text for p in BAD_PATTERNS):
                    continue
                new = parse_relations(text, known_names)
                ok = True
                for a2, b2, d2 in new:
                    for a1, b1, d1 in relations:
                        if (a1, b1) == (a2, b2) and d1 != d2: ok = False
                        if (b1, a1) == (a2, b2) and -d1 != d2: ok = False
                if new and ok:
                    relations.extend(new)
                    steps.append((step, prev_hash, text))
                    prev_hash = sha(prev_hash, step, text)
                    got_new = True
                    break
            if not got_new:
                # 组合器(刚性): 两条关系共享节点 → 合成新关系
                merged = False
                for i in range(len(relations)):
                    for j in range(len(relations)):
                        if i == j: continue
                        a1, b1, d1 = relations[i]; a2, b2, d2 = relations[j]
                        if b1 == a2:
                            cand = (a1, b2, d1 + d2)
                            if cand[0] != cand[1] and all(not ((c[0] == cand[0] and c[1] == cand[1])) or c[2] == cand[2] for c in relations):
                                if not any(c[0] == cand[0] and c[1] == cand[1] for c in relations):
                                    relations.append(cand)
                                    t = '%s比%s%s%d岁（%s比%s%s%d岁 + %s比%s%s%d岁合成）' % (
                                        a1, b2, '大' if cand[2] > 0 else '小', abs(int(cand[2])),
                                        a1, b1, '大' if d1 > 0 else '小', abs(int(d1)),
                                        a2, b2, '大' if d2 > 0 else '小', abs(int(d2)))
                                    steps.append((step, prev_hash, t))
                                    prev_hash = sha(prev_hash, step, t)
                                    merged = True; break
                    if merged: break
                if not merged:
                    status = '无解(组合器也无法推进)'
                    break
        print('【外部哈希时间链】%d步:' % len(steps), flush=True)
        ok_hash = True
        for t, ph, text in steps:
            h = sha(ph, t, text)
            if ph != prev_hash if False else True: pass
            print('  t%-2d hash=%-16s | %s' % (t, h, text[:88]), flush=True)
        # 校验连续性
        cur = '0' * 16
        for t, ph, text in steps:
            if ph != cur: ok_hash = False; break
            cur = sha(cur, t, text)
        print('【哈希链校验】%s | 【结果】%s 解=%s 标准=%s → %s' % (
            '连续✅' if ok_hash else '断裂❌', status, ans, gold,
            '✅' if str(ans) == gold else ('✅' if ans is not None and int(ans) == int(gold) else '❌')), flush=True)
    print('\n[V97b] 完成', flush=True)

if __name__ == '__main__':
    main()
