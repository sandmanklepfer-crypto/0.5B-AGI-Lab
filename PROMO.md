# 推广文案（可直接复制）

仓库: https://github.com/sandmanklepfer-crypto/0.5B-AGI-Lab

---

## 🐦 版本 A：短推（英文 · 主推，配图 the_contradiction.png）

> A 0.5B model **cannot** compute `2x+1`. Asked 10 times, it failed 10 times.
>
> The same model **correctly** did 12 consecutive steps of calculus.
>
> No, that's not a bug. That's what we found after **479 experiments**.
>
> The bottleneck was never the parameters. It's the **form library**.
>
> Free. Open. Reproducible. 👇
> https://github.com/sandmanklepfer-crypto/0.5B-AGI-Lab

**为什么这条能爆：** 开头是个反直觉的悖论，读者会想"这怎么可能"，然后点进来。

---

## 🧵 版本 B：Thread（英文 · 技术帖，配图 boundary_report.png）

**1/**
We ran **479 experiments** on a 0.5B model to find out exactly where it breaks.

Not "it's small so it's dumb". Exact numbers.

Here's the boundary report 🧵

**2/**
What it CAN do (with no training):

· Tool-call trigger — **5/5**
· **12-step** calculus chains — **12/12**
· Near-synonym format generalization — PASS

[pic: boundary_report.png]

**3/**
What it CANNOT do:

· Own arithmetic (`2x+1`) — **0/10**
· Counterfactual reasoning — **0/1**
· Invent an algorithm — **0/1**
· Even given the full 11-step history — **still fails**

**4/**
The most important result:

We gave it the COMPLETE 11-step derivation history.
It still answered wrong.

→ The bottleneck is NOT memory capacity.
→ It's the **depth of a single forward pass**.

**5/**
Second result — the model's failures are *procedural*, not *capability*:

```
"The derivative of -1024cos(2x) is -2048sin(2x)"   ✅ correct
"...which simplifies to -4096*sin(2x)"             ❌ it simplified wrong
```

Add one constraint — "do not simplify" → **instantly correct**.

It isn't incapable. It just always does one extra wrong step.

**6/**
And the real headline:

Same seq `[2,7,20,57,166]`, same searcher.

· With only "closed-form" forms → **fails**
· Add ONE new form ("recurrence") → **solves it instantly**
  `a_n = 3a_(n-1) - 2n + 5`

**Every form you add opens an entire new problem domain.**

**7/**
We also removed the refusal behavior with **zero training**:

`bias = -100 * (W_embd @ d_refusal)` → written into `output.bias`

Causal check: reverse (α=+150) does **nothing**.
→ It's a real mechanism, not noise.

Takes seconds. No GPU.

**8/**
So here's where we are stuck — and where you come in.

The **form library** has 2 entries filled, 6 empty:

⬜ linear systems ⬜ ODEs ⬜ integral transforms
⬜ matrices ⬜ graph/combinatorics ⬜ probability

~50 lines each. One test case. **PRs welcome.**

**9/**
993 files, all experiments included — including every **negative result**.

Because knowing where a small model breaks is more useful than
another benchmark score.

🔗 https://github.com/sandmanklepfer-crypto/0.5B-AGI-Lab

⭐ if you think "small model + good forms" is the right direction.

---

## 🇨🇳 版本 C：中文（微博/知乎/即刻，配图 the_contradiction.png）

> 一个 0.5B 的模型，连 `2x+1` 都算不对 —— 问 10 次，错 10 次。
>
> 同一个模型，却连续做对了 **12 步微积分**。
>
> 这不是 bug。这是我们做了 **479 次实验** 得出的结论。
>
> 瓶颈从来不是参数量，是**形式库**。
>
> 全部免费开源，实验数据（含所有负结果）都在里面 👇
> https://github.com/sandmanklepfer-crypto/0.5B-AGI-Lab

---

## 🎯 发布策略

| 项 | 建议 |
|---|---|
| **首发** | 推特（版本A + 矛盾图） |
| **2小时后** | 同一条改成 Thread（版本B），引第一条 |
| **次日** | Reddit r/LocalLLaMA（用版本B） |
| **同日** | HN: `Show HN: 479 experiments on what a 0.5B model can('t) do` |
| **国内** | 微博/知乎（版本C） |

**标签（推特）：** `#LLM #OpenSource #AI #MachineLearning #EdgeAI`

**最佳时间：** 美东周二~周四 上午 9-11 点（北京时间 21:00-23:00）

---

## ⚠️ 三条铁律

1. **不要写"GPT-6级"/"AGI"** —— 会被挂，且毁掉数据可信度。
   你的"12/12 vs 0/10"矛盾，本身就足够炸。

2. **首条推里必须放图** —— 纯文字推的点击率差 3-5 倍。

3. **必须放链接** —— 但别放第一条，放回复里可以规避算法限流。
   （推特对首条带外链的推降权）
