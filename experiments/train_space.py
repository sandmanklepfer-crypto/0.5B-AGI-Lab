# -*- coding: utf-8 -*-
"""train_space.py — 空间能力蒸馏实验(真实训练 + 评估)
   L1: 让 0.5B 学会「坐标 → 空间关系」推理
   输出: 训练前后准确率对比(用数据回答"空间能力能否蒸馏进0.5B")
"""
import numpy as np, time, json, sys
import np_qwen, np_train2
from np_tok import Tok
from gen_short import build

TK = None; M = None

def prompt(user):
    return ("<|im_start|>system\n你是空间推理助手。<|im_end|>\n"
            "<|im_start|>user\n"+user+"<|im_end|>\n<|im_start|>assistant\n")

def encode(user, ans=None):
    ids = TK.encode(prompt(user))
    if ans is None: return ids
    a = TK.encode(ans)
    return ids + a + [151645]     # + <|im_end|>

def evaluate(tr, data, maxn=30, greedy=True):
    """对 data 前 maxn 条, 看模型能否生成正确首token, 统计准确率"""
    ok=0; tot=0; samples=[]
    for d in data[:maxn]:
        ids = encode(d["q"])
        # 前向得 logits
        logits,C,finals,kvs = tr.forward(ids)
        pred = int(np.argmax(logits))
        gold = TK.encode(d["a"])[0]     # 答案首 token
        tot += 1
        if pred==gold: ok+=1
        if len(samples)<5:
            samples.append((d["q"][-30:], d["a"], TK.decode([pred])))
    return ok, tot, samples

def main():
    global TK, M
    ntrain = int(sys.argv[1]) if len(sys.argv)>1 else 120
    nstep  = int(sys.argv[2]) if len(sys.argv)>2 else 40
    layers = [int(x) for x in (sys.argv[3].split(",") if len(sys.argv)>3 else ["21","22","23"])]

    print("=== 准备 ===")
    t0=time.time(); TK = Tok("/workspace/w.gguf", verbose=False)
    M = np_qwen.Qwen2("/workspace/w.gguf", verbose=False)
    print("模型加载 %.1fs"%(time.time()-t0))

    train = build(ntrain, seed=11)
    test  = build(60, seed=99)     # 不同种子 → 泛化测试
    print("训练集 %d 条 / 测试集 %d 条"%(len(train),len(test)))

    tr = np_train2.TrainQwen(M, layers=layers, r=8, alpha=16, seed=0)
    npar = sum(l.A.size+l.B.size for l in tr.loras.values())
    print("LoRA: %d层 %d参数 %.0fKB"%(len(layers),npar,tr.nbytes()/1024))

    # --- 训练前基线 ---
    print("\n=== 训练前 ===")
    ok,tot,smp = evaluate(tr, test, 12)
    print("测试准确率: %d/%d = %.0f%%"%(ok,tot,100*ok/max(tot,1)))
    for q,a,p in smp[:3]: print("   Q..%s | 期望 %s | 预测 %s"%(q,a,p))

    # --- 训练 ---
    print("\n=== 训练 (%d 步) ==="%nstep)
    lr=0.03; losses=[]
    t0=time.time()
    for step in range(nstep):
        d = train[step % len(train)]
        ids = encode(d["q"], d["a"])
        inp, tgt = ids[:-1], ids[-1]
        loss, prob = tr.train_step(inp, tgt, lr)
        losses.append(loss)
        if step%5==0 or step==nstep-1:
            print("  step %3d loss=%.4f p=%.3f (%.0fs)"%(step,loss,prob,time.time()-t0))

    # --- 训练后 ---
    print("\n=== 训练后 ===")
    ok,tot,smp = evaluate(tr, test, 12)
    print("测试准确率: %d/%d = %.0f%%"%(ok,tot,100*ok/max(tot,1)))
    for q,a,p in smp[:5]: print("   Q..%s | 期望 %s | 预测 %s"%(q,a,p))

    print("\n=== 结论 ===")
    print("loss: %.3f → %.3f"%(np.mean(losses[:5]), np.mean(losses[-5:])))
    # 保存 LoRA
    out = {"layers":layers, "r":8, "alpha":16}
    for (L,w),lo in tr.loras.items():
        out["L%d.%s.A"%(L,w)] = lo.A.tolist()
        out["L%d.%s.B"%(L,w)] = lo.B.tolist()
    with open("/workspace/space_lora.json","w") as f: json.dump(out,f)
    print("LoRA 已存 /workspace/space_lora.json (%.0f KB)"%(len(json.dumps(out))/1024))

if __name__=="__main__":
    main()
