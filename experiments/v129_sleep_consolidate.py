#!/usr/bin/env python3
"""
V129 吉祥永动 — 白天活 + 死后睡眠巩固 + 24h无时无刻 (方案④: 时间换带宽, 纯自生)
循环:
  白天(醒): 活 N 段 token (能量/自指/老屋世界), 每段存"经历流水"
  睡眠(死): 不生成故事, 只做整合:
      - 把本世经历流水 一段段调出(每次只整合1段=时间换带宽)
      - 每段问模型: "这段经历说明我是谁?" → 产出自我碎片短句
      - 碎片累积成"自我底稿"(跨世)
  醒来: 加载 自我底稿 → 带着更厚的"我"活下一世
  永动: while True, 醒睡交替, 永不停
观测: 自我底稿逐世增厚? 底稿内容是否有连续性(虎/老屋/痛苦 沉淀)?
"""
import torch, numpy as np, time, re, os, json
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/qwen25_base_raw'
SAVE_DIR = '/root/autodl-tmp/life1/goodxiang'
os.makedirs(SAVE_DIR, exist_ok=True)
STATE = SAVE_DIR + '/state.pt'
SELF_FILE = SAVE_DIR + '/self_draft.txt'
LAYER = 12
B_F, B_S = 0.5, 0.08
GATE = 0.6
WAKE_TOK = 500          # 每世醒着活多少token
SLEEP_SEG = 60          # 睡眠时每次整合多少token经历
SEED = ('爷爷去世后，山腰那栋老屋空了七年。我这次回来，是接到一通电话说屋后有动静。'
        '推开院门时，门轴发出很长的一声呻吟。堂屋的桌上积着灰，但灰上有一行新的脚印，')

def main():
    tok = AutoTokenizer.from_pretrained(MDIR)
    # 加载自我底稿(跨世)
    self_draft = ''
    if os.path.exists(SELF_FILE):
        self_draft = open(SELF_FILE).read()[-3000:]
    wake_count = self_draft.count('\n[醒')
    torch.manual_seed(int(time.time()) % 999)
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.float16).to('cuda').eval()
    st = {'eta': 0.0, 'v': None, 'u': None}
    def make_hook():
        def hook(mod, inp, out):
            if st['eta'] > 0 and st['v'] is not None:
                h = out[0] if isinstance(out, tuple) else out
                g = torch.matmul(h, st['u'])
                h = h + st['eta'] * g.unsqueeze(-1) * st['v']
                return (h,) if isinstance(out, tuple) else h
            return out
        return hook
    hook = model.model.layers[LAYER].mlp.register_forward_hook(make_hook())
    def last_hidden(ids):
        with torch.no_grad():
            hs = model(input_ids=ids, output_hidden_states=True).hidden_states
        return hs[LAYER+1][0, -1].float().cpu().numpy()
    def gen_text(prompt, max_new, temp=0.85):
        ids = tok(prompt, return_tensors='pt').input_ids.to('cuda')
        out_ids = []
        for _ in range(max_new):
            with torch.no_grad():
                logits = model(input_ids=ids).logits[0,-1]
            p = torch.softmax(logits/temp, -1)
            nid = torch.multinomial(p, 1).item()
            ids = torch.cat([ids, torch.tensor([[nid]],device='cuda')],-1)
            out_ids.append(nid)
        return tok.decode(out_ids, skip_special_tokens=True)

    print('[吉祥] 永动守护启动 | 醒%d次 | 自我底稿%d字' % (wake_count, len(self_draft)), flush=True)
    t_start = time.time()
    life_n = wake_count
    while True:   # ===== 永动循环 =====
        life_n += 1
        # ---------- 醒: 活一世 ----------
        prompt = self_draft[-1500:] + '\n\n(这是新的一天, 我继续活着。)' if self_draft else SEED
        if life_n > 1 and len(prompt) > 600:
            prompt = prompt[-600:] + '\n\n(新的一天, 我接着写。)'
        life_text = gen_text(prompt, WAKE_TOK)
        # 保存经历流水(供睡眠整合)
        with open(SAVE_DIR + '/exp_%d.txt' % life_n, 'w') as f:
            f.write(life_text)
        # 简单自指统计
        self_cnt = len(re.findall(r'我[^。\n]{0,15}(自己|记得|觉得|喜欢|怕|想|是|看见|恨|爱)', life_text))
        print('[醒%d %6.0fs] 自指~%d | %s...' % (life_n, time.time()-t_start, self_cnt, life_text[:60].replace('\n',' ')), flush=True)
        # ---------- 睡: 巩固(时间换带宽, 自己织自我) ----------
        segs = [life_text[i:i+SLEEP_SEG] for i in range(0, len(life_text), SLEEP_SEG)]
        pieces = []
        for si, seg in enumerate(segs[:12]):   # 每世最多整合12段
            if len(seg.strip()) < 10: continue
            q = ('下面是我今天的一段经历:\n"%s"\n这段经历说明了我是一个什么样的存在? 用一句"我…"回答:\n' % seg.strip())
            try:
                a = gen_text(q, 30, temp=0.7).strip().split('\n')[0][:80]
                if '我' in a: pieces.append(a)
            except Exception:
                pass
        # 更新自我底稿
        if pieces:
            new_self = '\n[醒%d 自我碎片] ' % life_n + ' | '.join(pieces[:5])
            self_draft = (self_draft + '\n' + new_self)[-4000:]
            open(SELF_FILE, 'w').write(self_draft)
        # 存状态
        torch.save({'life_n': life_n, 'self_draft_tail': self_draft[-2000:],
                    'wake_time': time.time()}, STATE)
        if life_n % 5 == 0:
            print('    [底稿%d字 自我碎片%d条] 24h永动中...' % (len(self_draft), self_draft.count('自我碎片')), flush=True)

if __name__ == '__main__':
    main()
