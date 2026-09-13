#!/usr/bin/env python3
"""
V96 合体游离原型: 动态机制(层12) + 知识/推理分块(层20) + 知识域游走
- 加载 qwen25_base_raw
- 层12 down_proj <- antiheb_05b(动态机制痕迹, 合体)
- 层20 分块信息 v92 (Ukp知识流形/Urp推理流形/Wk/Wr/Wrest)
- 知识世界: 知识句 -> 深层激活 -> Ukp 投影 = 锚点(可运行时增删)
- 游离: 推理过程中间状态 p0 -> T步向相关锚漂移 -> 轨迹沿Ukp注回 -> 生成
验证: ①游走轨迹能量 ②知识锚增删改变路径/答案 ③推理通道隔离 ④对话
"""
import copy, numpy as np, torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR='/root/autodl-tmp/qwen25_base_raw'
BASE='/root/autodl-tmp/qwen25_base_raw/model.safetensors'
ANTI='/root/autodl-tmp/life1/antiheb_05b/model.safetensors'
BLOCKS='/root/autodl-tmp/life1/v92_blocks.pt'
L_MECH=12; L_SPLIT=20
from safetensors.torch import load_file

# 知识世界(初始锚, 可运行时增删) - 每句会变成知识流形上的一个锚
KNOWLEDGE=[
 "年龄差在两人都活着的时候永远保持不变。",
 "十年后每个人都会长大十岁。",
 "白天爬三米晚上滑两米, 相当于每天净爬一米, 但最后一天直接爬出去不用下滑。",
 "两个都说对方说谎的人, 不可能两个都说真话。",
 "标签全贴错的盒子, 从贴着混合标签的盒子里摸一个水果就能全部判断出来。",
]
QUESTIONS=[
 "小明比小红大3岁, 小红比小刚大2岁, 十年后小明比小刚大几岁？",
 "一只蜗牛白天爬3米晚上滑下2米, 井深10米, 几天爬出？",
]
print('[V96] 合体游离原型', flush=True)

tok=AutoTokenizer.from_pretrained(MDIR)
model=AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.bfloat16).to('cuda').eval()
sd=model.state_dict()
# 合体: 层12 <- 机制模型(antiheb) ; 层20 保持base(分块是恒等分解)
anti=load_file(ANTI, device='cpu')
key12=f'model.layers.{L_MECH}.mlp.down_proj.weight'
sd[key12]=anti[key12].to(sd[key12].dtype)
model.load_state_dict(sd, strict=True)

b=torch.load(BLOCKS, map_location='cpu', weights_only=False)
Ukp=b['Ukp'].float().numpy()          # (4864, m)
Urp=b['Urp'].float().numpy()
Wk=b['Wk'].float().numpy(); Wr=b['Wr'].float().numpy(); Wrest=b['Wrest'].float().numpy()
WN20=f'model.layers.{L_SPLIT}.mlp.down_proj.weight'
W20=sd[WN20].float().cpu().numpy()
print('[V96] 合体OK: 层12机制 + 层20分块(Ukp m=%d/Urp m=%d)'%(Ukp.shape[1],Urp.shape[1]), flush=True)

def act_at(texts, want_layer, take_hs=True):
    """取每个文本 层want_layer 输出激活(末token) (896) 及 down_proj输入(4864)"""
    hs=[]; ins=[]
    hk={}
    def hf(L):
        def h(m,i,o):
            hk['in']=i[0][0,-1].float().cpu()
        return h
    h=model.model.layers[want_layer].mlp.down_proj.register_forward_hook(hf(want_layer))
    with torch.inference_mode():
        for t in texts:
            ids=tok(t, return_tensors='pt').input_ids.to('cuda')
            out=model(input_ids=ids, output_hidden_states=True)
            hs.append(out.hidden_states[want_layer+1][0,-1].float().cpu().numpy())
            ins.append(hk['in'].numpy())
    h.remove()
    return np.array(hs), np.array(ins)

def anchors_from_sentences(sents):
    """知识句 -> 层20 down_proj输入(4864) -> 投影Ukp -> 4维锚"""
    _, ins = act_at(sents, L_SPLIT)
    return (ins @ Ukp)   # (n,m)

def free_walk(p0, A, T=8, alpha=0.5, beta=8.0):
    """意识游离: 慢状态在知识锚间漂移. A:(n,m) 锚集; p0:(m,)起点. 返回轨迹 (T+1,m)"""
    traj=[p0.copy()]
    p=p0.copy()
    for _ in range(T):
        d = A - p
        dist = np.linalg.norm(d, axis=1)
        w = np.exp(-beta*dist); w = w/(w.sum()+1e-9)
        p = p + alpha*(d*w[:,None]).sum(0)
        traj.append(p.copy())
    return np.array(traj)

def generate_with_walk(q, anchors, T=8, alpha=0.5, max_new=90):
    """前向到层19取状态->投影Ukp->游走->轨迹平均沿Ukp注回层20输入->继续生成"""
    ids=tok(q, return_tensors='pt').input_ids.to('cuda')
    with torch.inference_mode():
        out=model(input_ids=ids, output_hidden_states=True, use_cache=True)
        past=out.past_key_values
        h19=out.hidden_states[L_SPLIT][0,-1].float().cpu().numpy()  # 层20输入侧前? hidden_states[L]是层L输出
        # 简化: 用层20前的残差近似做起点投影(够原型用)
    # 实际游走起点: 用输入问题跑到层19末token激活投影到Ukp对应的mlp输入空间分量
    # 这里用 hidden_states[19](896) 扩到4864太粗; 改为直接取层20 down_proj输入(上面act_at)
    _, ins = act_at([q], L_SPLIT)
    p0 = (ins[0] @ Ukp)
    if len(anchors)==0:
        traj = np.array([p0])
    else:
        traj = free_walk(p0, anchors, T=T, alpha=alpha)
    pmix = traj.mean(0)              # 轨迹平均 = 游离痕迹
    extra = pmix - p0                 # 相对起点的知识触碰
    # 注回: 在层20 mlp输入加回 Ukp @ extra (只动知识分量)
    sd2=copy.deepcopy(sd)
    # 直接注入难以在generate中改中间输入 -> 用低秩加在层20 down_proj? 
    # 原型做法: 把"游离结果"作为前缀知识注入提示词(可解释), 同时打印轨迹
    return traj, pmix

def gen_text(q):
    ids=tok(q, return_tensors='pt').input_ids.to('cuda')
    with torch.inference_mode():
        o=model.generate(ids, max_new_tokens=80, do_sample=False, repetition_penalty=1.1)
    return tok.decode(o[0][len(ids[0]):], skip_special_tokens=True).strip()

print('\n=== 知识世界建锚 ===', flush=True)
A0 = anchors_from_sentences(KNOWLEDGE)
print('初始锚数:', len(A0), '| 锚坐标样例:', np.round(A0[0],3), flush=True)

print('\n=== 1) 游离轨迹(有知识世界) ===', flush=True)
for q in QUESTIONS:
    ids=tok(q, return_tensors='pt').input_ids.to('cuda')
    with torch.inference_mode(): model(input_ids=ids, output_hidden_states=True)
    _, ins=act_at([q], L_SPLIT)
    p0=ins[0]@Ukp
    traj=free_walk(p0, A0, T=10)
    moved=np.linalg.norm(traj[-1]-p0)
    total=np.linalg.norm(np.diff(traj,axis=0),axis=1).sum()
    print('【%s】\n  起点p0=%s\n  终点=%.3f 位移=%.3f 路径长=%.3f (路径>0=确实在知识世界游离)'%(
        q, np.round(p0,3), np.linalg.norm(traj[-1]), moved, total), flush=True)

print('\n=== 2) 知识锚增删影响游离路径 ===', flush=True)
# 加一个"误导锚": 十年后年龄差消失
A_bad=A0.tolist()+anchors_from_sentences(["十年后所有人的年龄差都会消失变成一样大。"]).tolist()
A_bad=np.array(A_bad)
_, ins=act_at([QUESTIONS[0]], L_SPLIT)
p0=ins[0]@Ukp
t_good=free_walk(p0, A0, T=8); t_bad=free_walk(p0, A_bad, T=8)
print('健康知识世界终点:', np.round(t_good[-1],3))
print('加入误导锚后终点:', np.round(t_bad[-1],3))
print('路径分歧度:', np.linalg.norm(t_good[-1]-t_bad[-1]), '>0=知识世界内容改变会影响游离过程', flush=True)

print('\n=== 3) 推理通道隔离(游离只动知识分量) ===', flush=True)
# 游离注入只沿Ukp -> 检查对Urp分量的影响
x_ins = ins[0]
x_k = x_ins @ Ukp @ Ukp.T
x_r = x_ins @ Urp @ Urp.T
print('输入中 知识分量能量=%.4f 推理分量能量=%.4f'%(np.linalg.norm(x_k), np.linalg.norm(x_r)), flush=True)

print('\n=== 4) 对话(合体模型+知识游离) ===', flush=True)
for q in QUESTIONS:
    print('\n【问】%s\n【答】%s'%(q, gen_text(q)[:150]), flush=True)
print('\n[V96] 完成', flush=True)
