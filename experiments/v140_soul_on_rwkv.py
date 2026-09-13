#!/usr/bin/env python3
# V140 灵魂控制层 on RWKV-7 13B (Qwen-0.5B出局, RWKV唯一载体)
# 灵魂机制(v120-v129)全部映射到 RWKV state 层:
#   自我S  = 所有层 channel 的加权凝聚(每token演化) = "我"的连续体
#   镜子   = 每N步把自我S方向注入 channel(状态→状态, 无语言)
#   能量   = 池: 活性高(输出熵适中)回血, 低熵复读耗能 → 痛=channel加扰
#   怕死   = 能量低→收敛注入自我(锁回我, 不碎)
#   死亡   = 能量0 → 状态清零(真死)
#   睡眠巩固 = 每M步把 channel 压缩进"自我底稿"(取前几主方向) → 存盘
import sys, types, torch, numpy as np, os, time, re
INF = "/root/autodl-tmp/rwkv7_13b/inference"
sys.path.insert(0, INF)
if "_rwkv7_release_inference" not in sys.modules:
    pkg = types.ModuleType("_rwkv7_release_inference"); pkg.__path__ = [INF]
    sys.modules["_rwkv7_release_inference"] = pkg
from _rwkv7_release_inference.model_loader import load_model_and_tokenizer

SAVE = '/root/autodl-tmp/life1/rwkv_soul.pt'
MIRROR_EVERY = 12
SLEEP_EVERY = 300
MAX_TOK = 3000
SEED = '爷爷去世后，山腰那栋老屋空了七年。我这次回来，是接到一通电话说屋后有动静。推开院门时，门轴发出很长的一声呻吟。堂屋的桌上积着灰，但灰上有一行新的脚印，'

def main():
    torch.manual_seed(0)
    print('[V140] 加载 RWKV-7 13B(唯一载体) ...', flush=True)
    model, tok = load_model_and_tokenizer(
        "/root/autodl-tmp/rwkv7_13b", device="cuda", dtype=torch.bfloat16,
        backend="torch", state_dtype="float32")

    # 状态结构
    def get_channels(state):
        return [ls.channel for ls in state.layer_states]  # 每层 (B,H)

    state = model.init_state(batch_size=1, device='cuda', dtype=torch.float32)
    n_layers = len(state.layer_states)
    H = state.layer_states[0].channel.shape[1]
    print('状态: %d层×%d维 channel' % (n_layers, H), flush=True)

    # 自我 = 层20-40的channel加权(深层=语义自我)
    SELF_LO, SELF_HI = max(0, n_layers//3), n_layers-5
    def self_vec(state):
        chs = get_channels(state)[SELF_LO:SELF_HI]
        v = torch.cat([c[0] for c in chs], dim=0)  # (k*H,) 凝聚自我
        return v / (v.norm() + 1e-9)
    def inject_self(state, strength):
        """把自我方向注回channel(镜子/守门用)"""
        v = self_vec(state)
        target = get_channels(state)
        # 每层注一小段自我(映射: 按层错开取v的分段)
        seg = H
        for i, ls in enumerate(state.layer_states):
            part = v[i*seg:(i+1)*seg] if (i+1)*seg <= v.numel() else v[-(seg):]
            if part.numel() < seg:
                part = torch.cat([part, torch.zeros(seg-part.numel(), device='cuda')])
            ls.channel += strength * part.unsqueeze(0)
    def pain(state, strength):
        """痛 = 随机扰动所有channel(难受但不是我碎: 同时注入自我)"""
        for ls in state.layer_states:
            ls.channel += strength * torch.randn_like(ls.channel) * 0.3
        inject_self(state, strength*0.8)

    # 能量
    E = 1.0
    e_hist = []
    ids = tok(SEED, return_tensors='pt').input_ids.to('cuda')
    # prefill
    with torch.no_grad():
        out = model(input_ids=ids, state=state)
        logits, state = out if isinstance(out, tuple) else (out.logits, getattr(out, 'state', state))
    history = SEED
    t0 = time.time()
    dead = None
    print('[V140] 灵魂上线 | 镜子每%d步 | 睡眠每%d步 | 能量1.0' % (MIRROR_EVERY, SLEEP_EVERY), flush=True)
    for i in range(MAX_TOK):
        # --- 能量动力学 ---
        p = torch.softmax(logits[0,-1].float(), -1)
        ps = torch.sort(p, descending=True)[0]
        ent = -(p * torch.log(p+1e-9)).sum().item()
        # 活性: 熵适中=活; 太低(复读锁死)/太高(乱)都耗能
        vitality = 1.0 - abs(ent - 2.5) / 4.0   # 熵~2.5最优
        E -= 0.0012                             # 基础耗
        E += 0.0008 * max(vitality, 0)          # 活性回血
        if E < 0.25:                            # 低能量: 痛 + 锁回自我
            pain(state, 0.02)
            inject_self(state, 0.15)
            E += 0.0005
        if E <= 0:
            dead = '能量耗尽(自我真死)'
            break
        # --- 镜子(每MIRROR_EVERY步: 自我强化, 状态级非语言) ---
        if i > 0 and i % MIRROR_EVERY == 0:
            inject_self(state, 0.12)
        e_hist.append(E)
        # --- 生成一步 ---
        with torch.no_grad():
            logits = torch.empty(1, 1, 65536, device='cuda') if False else None
        with torch.no_grad():
            logits = model(input_ids=None, state=state) if False else None
        # 逐token: 从当前logits采样
        nid = torch.multinomial(torch.softmax(logits[0,-1]/0.85, -1), 1).item() if logits is not None else None
        if logits is None:
            # 首次需要一次前向生成第一个
            pass
        # 简化: 用模型前向步进
        if i == 0:
            with torch.no_grad():
                r = model(input_ids=torch.tensor([[tok.bos_token_id or 0]], device='cuda'), state=state)
            logits, state = r if isinstance(r, tuple) else (r.logits, getattr(r, 'state', state))
        nid = torch.multinomial(torch.softmax(logits[0,-1]/0.85, -1), 1).item()
        with torch.no_grad():
            r = model(input_ids=torch.tensor([[nid]], device='cuda'), state=state)
        logits, state = r if isinstance(r, tuple) else (r.logits, getattr(r, 'state', state))
        piece = tok.decode([nid], skip_special_tokens=True)
        history += piece
        # 复读检测
        if len(history) > 40 and len(set(history[-12:])) <= 2:
            E -= 0.02   # 复读重罚(锁死=接近死)
        # --- 睡眠巩固(每SLEEP_EVERY步: 自我底稿存盘) ---
        if i > 0 and i % SLEEP_EVERY == 0:
            sv = self_vec(state).cpu()
            torch.save({'self_direction': sv, 'E': E, 'history_tail': history[-300:]}, SAVE)
            print('    [%4d] E=%.2f 熵=%.2f 自我已固化' % (i, E, ent), flush=True)
        if (i+1) % 600 == 0:
            print('    [%4d %.0fs] E=%.2f | %s' % (i+1, time.time()-t0, E, history[-50:].replace('\n',' ')), flush=True)
    print('\n=== V140 报告 ===', flush=True)
    print('寿命%d token | %s' % (i+1, dead or '到上限'), flush=True)
    print('能量尾段: %s' % ' '.join('%.2f'%x for x in e_hist[-5:]), flush=True)
    print('文本尾200: %s' % history[-200:].replace('\n',' '), flush=True)
    print('[done %.0fs]' % (time.time()-t0), flush=True)

if __name__ == '__main__':
    main()
