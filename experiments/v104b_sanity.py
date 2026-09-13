import numpy as np, torch, torch.nn as nn
torch.manual_seed(0); np.random.seed(0)
D=12; N_PAIRS=5; N_TRAIN,N_TEST=2000,4000
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
Xtr=rng.randn(N_TRAIN,D).astype(np.float32); Xte=rng.randn(N_TEST,D).astype(np.float32)
ytr=gen_y(Xtr); yte=gen_y(Xte)
print('y+比例 train: %.3f test: %.3f' % (ytr.mean(), yte.mean()))
# oracle: 真实B
B=np.zeros((D,D))
for k,(i,j) in enumerate(pairs): B[i,j]=B[j,i]=coefs[k]/2  # 对称: x^T B x = sum_{i<j} 2B_ij xi xj
s=np.einsum('ni,ij,nj->n',Xte,B,Xte)
acc=(np.sign(s)==yte).mean()
print('ORACLE (真实B) acc=%.3f' % acc)
# 离决策边界距离分布
s_tr=np.einsum('ni,ij,nj->n',Xtr,B,Xtr)
print('|s| <0.5 比例: %.3f (接近0的样本多=任务本身模糊)' % (np.abs(s_tr)<0.5).mean())
# 提高训练强度重试 Tensor2 + MLP512
Xtt=torch.tensor(Xtr); ytt=torch.tensor(ytr); Xee=torch.tensor(Xte); yee=torch.tensor(yte)
class Tensor2(nn.Module):
    def __init__(self):
        super().__init__(); self.B=nn.Parameter(torch.randn(D,D)/np.sqrt(D))
        self.w=nn.Parameter(torch.randn(D)/np.sqrt(D)); self.b=nn.Parameter(torch.zeros(1))
    def forward(self,x): return (x@self.B*x).sum(-1)+x@self.w+self.b
class MLP(nn.Module):
    def __init__(self,h=512):
        super().__init__(); self.fc1=nn.Linear(D,h); self.fc2=nn.Linear(h,1)
    def forward(self,x): return self.fc2(torch.tanh(self.fc1(x))).squeeze(-1)
for model,name in [(Tensor2(),'Tensor2'),(MLP(),'MLP512')]:
    opt=torch.optim.Adam(model.parameters(),lr=3e-3)
    lossf=nn.BCEWithLogitsLoss()
    for ep in range(3000):
        opt.zero_grad(); loss=lossf(model(Xtt),(ytt>0).float()); loss.backward(); opt.step()
    with torch.no_grad():
        acc=((model(Xee)>0).float()==(yee>0).float()).float().mean().item()
    print('%s acc=%.3f' % (name,acc))
# 用均方误差重训 Tensor2 (可能BCE+sign标签钝)
for model,name in [(Tensor2(),'Tensor2-MSE')]:
    opt=torch.optim.Adam(model.parameters(),lr=3e-3)
    for ep in range(3000):
        opt.zero_grad(); loss=((model(Xtt)-ytt)**2).mean(); loss.backward(); opt.step()
    with torch.no_grad():
        acc=((model(Xee)>0).float()==(yee>0).float()).float().mean().item()
    print('%s acc=%.3f' % (name,acc))
