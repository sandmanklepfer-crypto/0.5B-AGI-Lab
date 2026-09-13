#!/usr/bin/env python3
"""
V105 爆炸-回落训练 (SGLD 退火) — 治 v104 的"模糊中间解"
v104病: 标准Adam慢慢爬 → 停模糊局部极小 (Tensor2/MLP 全 ~0.53-0.55, 而非结构化吸引子)
V105药: 用户方案 = 先极致爆炸(高温大扰动, 参数剧烈漫游章程空间) → 自然回落(温度/lr退火, 跌进吸引子)
实现: 随机梯度朗之万 (SGLD): θ -= lr·∇ + N(0, σ²), σ² ∝ lr·T
  爆炸期 T1: lr大+温度T高 → loss 剧烈震荡不收敛, 参数逛全局
  回落期 T2: lr,T 指数退到≈0 → 自然结晶跌入低能结构
对比 (二阶交互任务, 同v104): oracle上限 / Adam对照 / 爆炸-回落Tensor2 / 爆炸-回落MLP
多一个指标: 学到张量B与真实B的余弦(结构是否真的"结晶"成章程, 不是模糊平均)
"""
import numpy as np
import torch
import torch.nn as nn

torch.manual_seed(0); np.random.seed(0)
D=12; N_PAIRS=5; NTRAIN=2000; NTEST=4000

rng=np.random.RandomState(0)
pairs=[]
while len(pairs)<N_PAIRS:
    i,j=rng.randint(D),rng.randint(D)
    if i!=j and (i,j) not in pairs and (j,i) not in pairs: pairs.append((i,j))
coefs=rng.randn(N_PAIRS)
def gen_y(X):
    y=np.zeros(len(X))
    for k,(i,j) in enumerate(pairs): y+=coefs[k]*X[:,i]*X[:,j]
    return np.sign(y).astype(np.float32)
Xtr=rng.randn(NTRAIN,D).astype(np.float32); Xte=rng.randn(NTEST,D).astype(np.float32)
ytr=gen_y(Xtr); yte=gen_y(Xte)
B_true=np.zeros((D,D))
for k,(i,j) in enumerate(pairs): B_true[i,j]=B_true[j,i]=coefs[k]/2
Xtt=torch.tensor(Xtr); ytt=torch.tensor(ytr); Xee=torch.tensor(Xte); yee=torch.tensor(yte)

# oracle 上限
s=np.einsum('ni,ij,nj->n',Xte,B_true,Xte)
print('[V105] oracle(真实B) acc=%.3f' % ((np.sign(s)==yte).mean()), flush=True)

class Tensor2(nn.Module):
    def __init__(self):
        super().__init__(); self.B=nn.Parameter(torch.randn(D,D)/np.sqrt(D))
        self.w=nn.Parameter(torch.randn(D)/np.sqrt(D)); self.b=nn.Parameter(torch.zeros(1))
    def forward(self,x): return (x@self.B*x).sum(-1)+x@self.w+self.b
class MLP(nn.Module):
    def __init__(self,h=512):
        super().__init__(); self.fc1=nn.Linear(D,h); self.fc2=nn.Linear(h,1)
    def forward(self,x): return self.fc2(torch.tanh(self.fc1(x))).squeeze(-1)

def acc(model):
    with torch.no_grad(): return ((model(Xee)>0).float()==(yee>0).float()).float().mean().item()

def adam_train(model, name, lr=3e-3, ep=3000):
    opt=torch.optim.Adam(model.parameters(),lr=lr); lossf=nn.BCEWithLogitsLoss()
    for _ in range(ep):
        opt.zero_grad(); lossf(model(Xtt),(ytt>0).float()).backward(); opt.step()
    a=acc(model)
    print('  Adam %s: acc=%.3f' % (name,a), flush=True)
    return a

def anneal_train(model, name, T1=400, T2=2500, lr0=0.08, temp0=2.0):
    """爆炸(高温漫游) → 回落(温度退火结晶)"""
    lossf=nn.BCEWithLogitsLoss()
    params=list(model.parameters())
    def sgld_step(lr, temp):
        lossf(model(Xtt),(ytt>0).float()).backward()
        with torch.no_grad():
            for p in params:
                p.data -= lr*p.grad
                p.grad=None
                p.data += torch.randn_like(p)*np.sqrt(2*lr*temp)  # 朗之万噪声
    # 爆炸期: lr大温度高, 剧烈震荡
    for t in range(T1):
        lr = lr0*(1-t/T1)+lr0*0.3
        temp = temp0*(1-t/T1)+temp0*0.2
        sgld_step(lr, temp)
        if t%100==0: print('    [爆炸 %d/%d] loss=%.3f (震荡中)' % (t,T1,lossf(model(Xtt),(ytt>0).float()).item()), flush=True)
    # 回落期: 指数退火到0
    for t in range(T2):
        frac = t/T2
        lr = lr0*0.3*np.exp(-6*frac)+1e-5
        temp = temp0*0.2*np.exp(-8*frac)
        sgld_step(lr, temp)
    a=acc(model)
    # 结构恢复: B 与真实B的余弦
    Bl = ((model.B.data+model.B.data.T)/2).numpy()
    cos = (Bl*B_true).sum()/(np.linalg.norm(Bl)*np.linalg.norm(B_true)+1e-9)
    print('  Anneal %s: acc=%.3f  B结构恢复cos=%.3f' % (name,a,cos), flush=True)
    return a

print('=== 对照: Adam (慢慢爬, 预期模糊) ===', flush=True)
adam_train(Tensor2(),'Tensor2')
adam_train(MLP(),'MLP512')
print('\n=== 爆炸-回落 (用户方案) ===', flush=True)
torch.manual_seed(0)
anneal_train(Tensor2(),'Tensor2')
torch.manual_seed(0)
anneal_train(MLP(),'MLP512')
print('\n[V105] 完成', flush=True)
