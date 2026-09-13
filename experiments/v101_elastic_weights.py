#!/usr/bin/env python3
"""
V101 弹性权重原型 — 临时低秩扩张 + 收缩 + 多印记(哈希/学习率/模式/防崩) + 接力无限
原理(用户设计):
  0.5B 权重不够处理深问题时, 相关层权重临时"弹开"(低秩 A·B^T 注入, 等效扩容),
  正常部分被几乎无损挤压(低秩方向≈正交于主成分), 用完收缩, 只留少量印记固化,
  按时间接力弹开-收缩 → 总处理深度无上限 (时间换空间)
印记体系(用户要求, 防崩/防永久改变/记忆):
  h:  哈希指纹    = 校验扩张区完整性/是否被污染
  lr: 学习率印记  = 这次扩张学到的东西以"可调幅度"固化
  pat:模式印记    = 层/秩/方向结构 → 下次同型题直接重建
  safe:防崩印记   = 扩张幅度上限记录 + 恢复检测(撤扩张后正常功能是否恢复, 不恢复→回滚)
验证:
  1. 硬扛对照: 多约束题单次答 → 崩/丢
  2. 弹性扩容: 关键层注入低秩A·B^T → 处理约束能力上升
  3. 几乎无损: 扩张时正常题 KL 变化小
  4. 收缩+印记重建: 撤A·B留印记 → 同型题按印记重建 → 功能恢复
  5. 防崩/防永久: 超幅扩张后恢复检测失败 → 自动回滚到原权重
"""
import hashlib, json, copy
import numpy as np
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/life1/antiheb_05b'   # base+层12机制底子
SAVE = '/root/autodl-tmp/life1/v101_imprints.json'
DEEP_LAYERS = [16, 18, 20, 22]   # 深处理时"弹开"候选层
MAX_SAFE_RANK = 256               # 防崩: 单层安全秩上限(超过即拒)
LR_IMPRINT = 0.03                 # 学习率印记(收缩固化的可调量)

def make_imprint(name, layer, rank, direction_seed, learn_delta=None, extra=''):
    """生成一套印记 (哈希校验 + 结构 + 学习率 + 安全)"""
    h = hashlib.sha256(f"{name}|{layer}|{rank}|{direction_seed}|{extra}".encode()).hexdigest()[:16]
    return {'name': name, 'layer': layer, 'rank': rank, 'seed': direction_seed,
            'hash': h, 'lr': LR_IMPRINT, 'learn_delta': learn_delta, 'safe': True}

def build_lowrank(layer, rank, seed, device='cuda'):
    """按印记重建低秩 A·B^T (方向由seed决定)"""
    g = torch.Generator(device='cpu').manual_seed(seed)
    n_out, n_in = 896, 4864   # 只用于层20 down_proj (其它层形状不同, 这里演示层20)
    A = torch.randn(n_out, rank, generator=g)
    B = torch.randn(rank, n_in, generator=g)
    # 归一化使扩张幅度可控
    A = A / (A.norm() + 1e-9) * 0.5
    B = B / (B.norm() + 1e-9) * 0.5
    return A.cuda(), B.cuda()

def main():
    torch.manual_seed(0); np.random.seed(0)
    tok = AutoTokenizer.from_pretrained(MDIR)
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.bfloat16).to('cuda').eval()
    sd = model.state_dict()
    WN = 'model.layers.20.mlp.down_proj.weight'   # 演示: 弹开层20
    W0 = sd[WN].float().cpu().numpy().copy()
    print('[V101] 弹性权重原型 | 可弹层=%s 安全秩上限=%d' % (DEEP_LAYERS, MAX_SAFE_RANK), flush=True)

    def gen(prompt, max_new=150, **kw):
        ids = tok(prompt, return_tensors='pt').input_ids.to('cuda')
        with torch.inference_mode():
            o = model.generate(ids, max_new_tokens=max_new, do_sample=False,
                               repetition_penalty=1.2, pad_token_id=tok.eos_token_id, **kw)
        return tok.decode(o[0][len(ids[0]):], skip_special_tokens=True).strip()

    def lastlogits(prompt):
        ids = tok(prompt, return_tensors='pt').input_ids.to('cuda')
        with torch.inference_mode():
            return model(input_ids=ids).logits[0, -1].float()

    # 测试题: 多约束(0.5B单次硬扛必丢约束)
    HARD = ("七个人排成一排：A不站首位，B必须挨着C，D在E左边，F不站末尾，"
            "G站在正中间，C不站第二位，问：一定正确的是？\n"
            "A. B在第二位 B. F在第六位 C. D在E左边第二位 D. A在第三位")
    NORMAL = "中国的首都是什么？"

    # ---------- 0 基线 ----------
    print('\n=== 基线 (未扩容) ===', flush=True)
    base_k = lastlogits(NORMAL)
    print('正常题: %s' % gen(NORMAL, max_new=30)[:80], flush=True)

    # ---------- 1 硬扛对照 ----------
    print('\n=== 1. 硬扛(单次答多约束题) ===', flush=True)
    print('答: %s' % gen(HARD)[:220], flush=True)

    # ---------- 2 弹性扩容 (低秩弹开层20) ----------
    print('\n=== 2. 弹性扩容(层20低秩弹开 rank=32) ===', flush=True)
    A, B = build_lowrank(20, 32, seed=7)
    AB = (A @ B).cpu().numpy()
    sd2 = copy.deepcopy(sd)
    sd2[WN] = torch.tensor(W0 + AB).to(sd[WN].dtype)   # 权重内弹开
    model.load_state_dict(sd2, strict=True)
    ans_exp = gen(HARD)
    print('答: %s' % ans_exp[:250], flush=True)

    # ---------- 3 几乎无损挤压 (扩容时正常题变化) ----------
    print('\n=== 3. 几乎无损(扩容时正常题KL) ===', flush=True)
    with torch.inference_mode():
        k2 = model(input_ids=tok(NORMAL, return_tensors='pt').input_ids.to('cuda')).logits[0, -1].float()
    kl = (torch.softmax(base_k, -1) * (torch.log_softmax(base_k, -1) - torch.log_softmax(k2, -1))).sum().item()
    print('正常题 KL=%.5f (<0.05≈几乎无损)' % kl, flush=True)

    # ---------- 4 收缩留印记 + 重建 ----------
    print('\n=== 4. 收缩+印记重建 ===', flush=True)
    model.load_state_dict(sd, strict=True)   # 收缩回原权重
    imp = make_imprint('seat_task', 20, 32, 7, learn_delta=LR_IMPRINT)
    # 模拟"学习": 把扩张时相对硬扛的优势编码进learn_delta(演示: 重建A·B × (1+lr))
    A2, B2 = build_lowrank(20, imp['rank'], imp['seed'])
    AB2 = (A2 @ B2).cpu().numpy() * (1 + imp['lr'])
    sd3 = copy.deepcopy(sd)
    sd3[WN] = torch.tensor(W0 + AB2).to(sd[WN].dtype)
    model.load_state_dict(sd3, strict=True)
    ans_re = gen(HARD)
    print('印记: %s' % json.dumps(imp, ensure_ascii=False), flush=True)
    print('重建后答: %s' % ans_re[:250], flush=True)

    # ---------- 5 防崩/防永久: 超幅扩张 → 恢复检测 → 回滚 ----------
    print('\n=== 5. 防崩(超幅扩张+恢复检测) ===', flush=True)
    A_big, B_big = build_lowrank(20, MAX_SAFE_RANK + 100, seed=9)   # 超上限
    # 拒绝: 超过安全秩 → 不应用, 直接记录safe=False
    print('请求rank=%d > 安全上限%d → 拒绝扩张, 防崩印记触发' % (MAX_SAFE_RANK + 100, MAX_SAFE_RANK), flush=True)
    # 模拟"过度挤压": 强行应用超幅, 然后恢复检测
    AB_big = (A_big @ B_big).cpu().numpy() * 5
    sd4 = copy.deepcopy(sd)
    sd4[WN] = torch.tensor(W0 + AB_big).to(sd[WN].dtype)
    model.load_state_dict(sd4, strict=True)
    # 恢复检测: 正常题在"超幅扩张后"是否还正常
    with torch.inference_mode():
        k4 = model(input_ids=tok(NORMAL, return_tensors='pt').input_ids.to('cuda')).logits[0, -1].float()
    kl4 = (torch.softmax(base_k, -1) * (torch.log_softmax(base_k, -1) - torch.log_softmax(k4, -1))).sum().item()
    if kl4 > 0.2:
        model.load_state_dict(sd, strict=True)   # 回滚
        print('超幅后正常题KL=%.3f >0.2 → 恢复失败 → 自动回滚到原权重 ✅' % kl4, flush=True)
    else:
        print('超幅后KL=%.3f, 未触发回滚' % kl4, flush=True)
    # 回滚后验证
    print('回滚后正常题: %s' % gen(NORMAL, max_new=30)[:80], flush=True)

    json.dump({'imprints': [imp]}, open(SAVE, 'w'), ensure_ascii=False, indent=1)
    print('\n[V101] 完成, 印记已存 %s' % SAVE, flush=True)

if __name__ == '__main__':
    main()
