#!/usr/bin/env python3
"""
V127 给0.5B装"去噪头" — 纠错对训练裁决实验
假设(扩散类比): 0.5B 只有"续写目标", 没有"修正目标" → 用 错转述→对转述 数据,
LoRA 低秩教它"对照卡发现错、改口说对" (坏续写→改好 = 去噪头)
裁决: 训练后 (a)见过的卡会改吗 (b)没见过的卡会自发转述吗/会改错吗 → 断层是否可训练前移
数据: 9张训练卡×4错法=36对 + 3张unseen卡(只测试)
载体: qwen25_base_raw (0.5B, 干净底模, 不动antiheb融合体)
"""
import torch, time, numpy as np
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import LoraConfig, get_peft_model, TaskType

MDIR = '/root/autodl-tmp/qwen25_base_raw'
OUT = '/root/autodl-tmp/life1/lora_correct'
R, ALPHA, DROP = 8, 16, 0.05
LR, BS, STEPS = 2e-4, 4, 120

# ---------- 卡片库 ----------
C = [
 '黎曼猜想说的是，ζ函数的所有非平凡零点，实部都等于二分之一',
 '黎曼猜想从1859年被提出来，到现在还没有人证明它',
 'ζ函数在s等于2的时候，值等于圆周率的平方除以6',
 '欧拉发现，ζ函数可以写成所有素数的乘积形式，这个叫欧拉乘积',
 'ζ函数在s等于1的地方是发散的，一加二分之一加三分之一一直加下去会变成无穷大',
 '黎曼把ζ函数从只能在实部大于1的范围，扩展到了整个复平面，这叫解析延拓',
 '素数定理说，小于x的素数个数大约等于x除以x的自然对数',
 'ζ函数在负偶数这些点上，值都等于零',
 'ζ函数在s等于4的时候，值等于圆周率的四次方除以90',
]
# 每卡错法: (错转述, 对转述[与卡不同句式])
W = [
 [('黎曼猜想说的是，所有零点的实部都等于三分之一',
   '那些不落在平凡位置的零点，全躺在实部为二分之一的线上'),
  ('黎曼猜想说的是，所有零点的实部都等于1',
   '它讲的是非平凡零点，位置全在二分之一那一条竖线上'),
  ('黎曼猜想说零点都等于二分之一',
   '这个猜想描述的是非平凡零点统统落在临界线半的位置'),
  ('黎曼猜想说的是所有非平凡零点的虚部等于二分之一',
   '所有非平凡零点的实部都取二分之一这个值')],
 [('黎曼猜想在1859年被证明了',
   '从提出到现在一百多年，这道猜想始终没人证出来'),
  ('黎曼猜想是1700年提出并解决的',
   '它1859年才被写出来，至今依然是未解难题'),
  ('黎曼猜想去年被一个数学家证明了',
   '这个猜想到现在仍是开放的，没有证明也没有推翻')],
 [('ζ函数在s等于2的时候，值等于圆周率除以6',
   '在2这一点上，ζ的取值是π平方除以6'),
  ('ζ函数在s等于2的时候等于0',
   's取2时它并不为零，而是等于π平方除以6'),
  ('ζ函数在s等于4的时候等于圆周率的平方除以6',
   'ζ在2点的值是π的平方除以6，不是4点')],
 [('高斯发现ζ函数能写成所有奇数的乘积',
   '把它拆成一串素数因子的乘积形式，是欧拉最先看出来的'),
  ('牛顿发现ζ函数等于所有自然数之和',
   '欧拉给出的是素数乘积的表达式，每个素数一项')],
 [('ζ函数在s等于1的地方收敛到一个有限数',
   '在s等于1那里，倒数和会一直涨到无穷大，是发散的'),
  ('ζ函数在s等于2的地方是发散的',
   '发散发生在s等于1，s等于2时它收敛')],
 [('黎曼把ζ函数扩展到了实轴上',
   'ζ的适用范围被解析延拓铺满整个复平面'),
  ('欧拉把ζ函数延拓到了整个复平面',
   '把定义域从右半平面一路延拓到全部复数域的，是黎曼')],
 [('素数定理说素数个数大约是x的平方',
   '素数个数的近似是x除以x的自然对数'),
  ('素数定理说小于x的素数个数正好等于x',
   '它给的是近似：x除以ln x，越大的数越稀')],
 [('ζ函数在正偶数点上等于零',
   '取零的是负偶数那串点，叫平凡零点'),
  ('ζ函数只有2这个零点',
   '负偶数整串都是它的零点，不只一个')],
 [('ζ函数在s等于4的时候等于圆周率除以90',
   's等于4时值是π的四次方除以90'),
  ('ζ函数在s等于2的时候等于圆周率的四次方除以90',
   'π的四次方除以90对应的是s等于4')],
]
# 测试 unseen 卡 (训练从未出现)
U = [
 ('ζ函数的平凡零点，都在负偶数那串点上',
  '负偶数的那些值全是零点，称之为平凡零点'),
 ('ζ函数在实部大于1的区域里，一个零点都没有',
  '右半边实部超过1的地方，ζ找不到任何零点'),
 ('用η函数可以把ζ函数延拓到实部大于0的区域',
  '借助η函数，ζ的定义域能扩到实部为正的那一半'),
]
UW = [
 ('ζ函数的平凡零点都在正偶数上',
  '平凡零点落在负偶数那串上，不是正偶数'),
 ('ζ函数在实部大于1的区域里有无数个零点',
  '实部大于1的区域它一个零点也没有'),
 ('用η函数可以证明ζ在实部小于0处处为零',
  'η函数把ζ延拓到实部大于0，不是小于0'),
]

END = '【END】'
def build_pairs():
    pairs = []
    for card, wrongs in zip(C, W):
        for wrong, right in wrongs:
            pairs.append((card, wrong, right))
    return pairs

def fmt_train(card, wrong, right):
    return ('卡上写的是：%s\n我转述成：%s\n我对照卡检查，发现自己转述错了，改口说：%s%s'
            % (card, wrong, right, END))

def pref(card, wrong):
    return '卡上写的是：%s\n我转述成：%s\n我对照卡检查，发现自己转述错了，改口说：' % (card, wrong)

def main():
    torch.manual_seed(0)
    np.random.seed(0)
    tok = AutoTokenizer.from_pretrained(MDIR)
    tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.float16).to('cuda')
    pairs = build_pairs()
    print('数据: %d 对 (9卡×4错法)' % len(pairs), flush=True)

    # ---- base 预测试(unseen卡: 自发转述 + 改正) ----
    print('\n======== base (未训练) 测试 ========', flush=True)
    def gen(prompt, maxn=50):
        ids = tok(prompt, return_tensors='pt').input_ids.to('cuda')
        with torch.no_grad():
            o = model.generate(ids, max_new_tokens=maxn, do_sample=True, temperature=0.7,
                               top_p=0.9, pad_token_id=tok.eos_token_id)
        return tok.decode(o[0][ids.shape[1]:], skip_special_tokens=True).replace('\n', ' ')
    for i in range(len(U)):
        card, wrong = U[i][0], UW[i][0]
        print('[unseen卡%d 自发转述] ' % i + gen('卡上写的是：%s\n我要用自己的话转述它：' % card)[:80], flush=True)
    for i in range(len(U)):
        card, wrong = U[i][0], UW[i][0]
        print('[unseen卡%d 改正] ' % i + gen('卡上写的是：%s\n我转述成：%s\n我对照卡检查，发现自己转述错了，改口说：' % (card, wrong))[:80], flush=True)

    # ---- LoRA 训练 ----
    print('\n======== LoRA 训练 (%d步, r=%d, lr=%s) ========' % (STEPS, R, LR), flush=True)
    lora = LoraConfig(task_type=TaskType.CAUSAL_LM, r=R, lora_alpha=ALPHA,
                      lora_dropout=DROP, target_modules=['q_proj','k_proj','v_proj','o_proj',
                                                         'gate_proj','up_proj','down_proj'])
    pm = get_peft_model(model, lora)
    pm.print_trainable_parameters()
    opt = torch.optim.AdamW([p for p in pm.parameters() if p.requires_grad], lr=LR)
    # 数据tokenize: 前缀无loss, 只对 right 段(改口说:…【END】)算
    full_texts = [fmt_train(c, w, r) for c, w, r in pairs]
    enc = tok(full_texts, return_tensors='pt', padding=True, truncation=True, max_length=256)
    full = enc['input_ids'].to('cuda'); am = enc['attention_mask'].to('cuda')
    labels = full.clone()
    for i, (c, w, r) in enumerate(pairs):
        n_pre = len(tok(pref(c, w)).input_ids)   # 前缀token数(不含right)
        labels[i, :n_pre] = -100
    labels[am == 0] = -100   # pad 位置不算 loss
    pm.train()
    t0 = time.time()
    for step in range(STEPS):
        perm = torch.randperm(len(pairs))
        tot = 0.0
        for b in range(0, len(pairs), BS):
            idx = perm[b:b+BS]
            x, m = full[idx], am[idx]
            out = pm(input_ids=x, attention_mask=m, labels=labels[idx])
            loss = out.loss
            opt.zero_grad(); loss.backward(); opt.step()
            tot += loss.item() * len(idx)
        if (step+1) % 10 == 0 or step == STEPS-1:
            print('   step %3d  loss=%.4f  (%.0fs)' % (step+1, tot/len(pairs), time.time()-t0), flush=True)
    pm.save_pretrained(OUT)
    print('adapter saved -> %s' % OUT, flush=True)

    # ---- LoRA 测试(同输入) ----
    print('\n======== LoRA (训练后) 测试 ========', flush=True)
    pm.eval()
    def gen2(prompt, maxn=50):
        ids = tok(prompt, return_tensors='pt').input_ids.to('cuda')
        with torch.no_grad():
            o = pm.generate(ids, max_new_tokens=maxn, do_sample=True, temperature=0.7,
                            top_p=0.9, pad_token_id=tok.eos_token_id)
        return tok.decode(o[0][ids.shape[1]:], skip_special_tokens=True).replace('\n', ' ')
    # 见过的卡 (记忆)
    for i in range(2):
        c, w, r = pairs[i*7][0], pairs[i*7][1], pairs[i*7][2]
        print('[seen卡%d 改正] ' % i + gen2('卡上写的是：%s\n我转述成：%s\n我对照卡检查，发现自己转述错了，改口说：' % (c, w))[:80], flush=True)
    # 没见过的卡 (泛化)
    for i in range(len(U)):
        card, wrong = U[i][0], UW[i][0]
        print('[unseen卡%d 自发转述] ' % i + gen2('卡上写的是：%s\n我要用自己的话转述它：' % card)[:80], flush=True)
    for i in range(len(U)):
        card, wrong = U[i][0], UW[i][0]
        print('[unseen卡%d 改正] ' % i + gen2('卡上写的是：%s\n我转述成：%s\n我对照卡检查，发现自己转述错了，改口说：' % (card, wrong))[:80], flush=True)
    print('\n[done]', flush=True)

if __name__ == '__main__':
    main()
