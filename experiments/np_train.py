# -*- coding: utf-8 -*-
"""np_train.py — 端侧 LoRA 训练(纯 numpy 手写反向)
   目标: 让 .life 里的 0.5B 能在手机上"自己学"(外部验证过的经验)
   只训 q_proj / v_proj 的 LoRA(低秩), 底图权重冻结 → 不灾难性遗忘
"""
import numpy as np, time, json, os

EPS = 1e-6
N_LAYER, N_HEAD, N_KV, HEAD_DIM = 24, 14, 2, 64
ROPE_THETA = 1000000.0

# ============ LoRA 层 ============
class LoRA:
    """y = base(x) + scale * B(A(x));  A:[r,in] B:[out,r]"""
    def __init__(self, out_dim, in_dim, r=8, alpha=16, seed=0, scale=0.0):
        rng = np.random.RandomState(seed)
        self.r = r; self.in_dim = in_dim; self.out_dim = out_dim
        self.A = (rng.randn(r, in_dim) * 0.01).astype(np.float32)
        self.B = np.zeros((out_dim, r), np.float32)   # B=0 → 初始无扰动
        self.scale = alpha / r
        self.gA = np.zeros_like(self.A); self.gB = np.zeros_like(self.B)
    def fwd(self, x):
        ax = self.A @ x                # [r]
        bx = self.B @ ax               # [out]
        return ax, (bx * self.scale)
    def bwd(self, x, ax, dout):
        # dout: dL/d(y_lora)  [out]
        d = dout * self.scale
        self.gB += np.outer(d, ax)
        dax = self.B.T @ d
        self.gA += np.outer(dax, x)
        return self.A.T @ dax          # dL/dx  (对输入的贡献)
    def step(self, lr):
        self.A -= lr * self.gA; self.B -= lr * self.gB
        self.gA[:] = 0; self.gB[:] = 0
    def flat(self):
        return np.concatenate([self.A.ravel(), self.B.ravel()])

# ============ 可微前向(存中间量) ============
class TrainQwen:
    def __init__(self, model, lora_layers=None, r=8, alpha=16, seed=0):
        """model: np_qwen.Qwen2 (已加载权重, w 为 fp32)"""
        self.m = model; self.w = model.w
        self.DIM = model.DIM; self.VOCAB = model.VOCAB
        if lora_layers is None: lora_layers = list(range(N_LAYER))
        self.lora_layers = lora_layers
        self.loras = {}
        for L in lora_layers:
            self.loras[(L,"q")] = LoRA(self.DIM, self.DIM, r, alpha, seed+L*2)
            self.loras[(L,"v")] = LoRA(N_KV*HEAD_DIM, self.DIM, r, alpha, seed+L*2+1)  # GQA: 128
        self.inv = 1.0/(ROPE_THETA ** (np.arange(0,HEAD_DIM//2,dtype=np.float32)/(HEAD_DIM//2)))

    @staticmethod
    def rms_f(x, w):
        ms = np.mean(x*x) + EPS
        inv = 1.0/np.sqrt(ms)
        return x*inv*w, (ms, inv)
    @staticmethod
    def silu_f(x):
        s = 1.0/(1.0+np.exp(-np.clip(x,-50,50)))
        return x*s, s
    def rope_f(self, x, pos):
        ang = pos*self.inv
        c = np.cos(ang).astype(np.float32); s = np.sin(ang).astype(np.float32)
        x1 = x[..., :HEAD_DIM//2]; x2 = x[..., HEAD_DIM//2:]
        y = np.concatenate([x1*c - x2*s, x2*c + x1*s], axis=-1)
        return y, (c, s, x1, x2)

    def forward_seq(self, toks):
        """整段前向, 存所有中间量供反向"""
        w = self.w
        T = len(toks)
        caches = []
        x = self.m.tok_emb[toks[0]].copy()
        # 逐 token 逐层(带 kv)
        kvs = [{"k":[], "v":[]} for _ in range(N_LAYER)]
        allx = [None]*T
        for t in range(T):
            x = self.m.tok_emb[toks[t]].copy()
            for L in range(N_LAYER):
                p = "blk.%d."%L
                x_in = x.copy()
                h, (ms, inv) = self.rms_f(x, w[p+"attn_norm.weight"])
                # q/k/v + LoRA(q,v)
                q = w[p+"attn_q.weight"] @ h
                if (L,"q") in self.loras:
                    ax, dl = self.loras[(L,"q")].fwd(h); q = q + dl
                k = w[p+"attn_k.weight"] @ h
                v = w[p+"attn_v.weight"] @ h
                if (L,"v") in self.loras:
                    axv, dlv = self.loras[(L,"v")].fwd(h); v = v + dlv
                if p+"attn_q.bias" in w: q = q + w[p+"attn_q.bias"]
                if p+"attn_k.bias" in w: k = k + w[p+"attn_k.bias"]
                if p+"attn_v.bias" in w: v = v + w[p+"attn_v.bias"]
                qr, qc = self.rope_f(q.reshape(N_HEAD,HEAD_DIM), t)
                kr, kc = self.rope_f(k.reshape(N_KV,HEAD_DIM), t)
                vr = v.reshape(N_KV,HEAD_DIM)
                kvs[L]["k"].append(kr); kvs[L]["v"].append(vr)
                Ks = np.stack(kvs[L]["k"]); Vs = np.stack(kvs[L]["v"])
                rep = N_HEAD//N_KV
                Kx = np.repeat(Ks,rep,axis=1); Vx = np.repeat(Vs,rep,axis=1)
                sc = np.einsum("hd,shd->hs", qr, Kx)/np.sqrt(HEAD_DIM)
                sc = sc - sc.max(axis=-1,keepdims=True)
                e = np.exp(sc); a = e/e.sum(axis=-1,keepdims=True)
                att = np.einsum("hs,shd->hd", a, Vx).reshape(-1)
                o = w[p+"attn_output.weight"] @ att
                x = x + o
                x_mid = x.copy()
                h2, (ms2, inv2) = self.rms_f(x, w[p+"ffn_norm.weight"])
                g, sg = self.silu_f(w[p+"ffn_gate.weight"] @ h2)
                u = w[p+"ffn_up.weight"] @ h2
                gu = g*u
                ff = w[p+"ffn_down.weight"] @ gu
                x = x + ff
                caches.append({"L":L,"t":t,"x_in":x_in,"x_mid":x_mid,
                               "h":h,"ms":ms,"inv":inv,"q":q,"qraw":q,
                               "qr":qr,"kr":kr,"k":k,"v":vr,"Ks":Ks,"Vs":Vs,
                               "a":a,"att":att,"o":o,"h2":h2,"ms2":ms2,"inv2":inv2,
                               "g":g,"sg":sg,"u":u,"gu":gu,"ff":ff})
            xf, (msf, invf) = self.rms_f(x, w["output_norm.weight"])
            allx[t] = {"x":x,"xf":xf,"msf":msf,"invf":invf}
        # logits for last token
        xfl = allx[T-1]["xf"]
        logits = w["output.weight"] @ xfl if "output.weight" in w else self.m.tok_emb @ xfl
        return logits, allx, caches, kvs

    def loss_and_backward(self, toks, targets):
        """交叉熵损失 + 反向(只更新 LoRA)"""
        T = len(toks)
        logits, allx, caches, kvs = self.forward_seq(toks)
        # CE on last token
        lg = logits - logits.max()
        p = np.exp(lg); p = p/p.sum()
        tgt = targets[-1]
        loss = -np.log(p[tgt] + 1e-12)
        dlogits = p.copy(); dlogits[tgt] -= 1.0
        # dL/dxf
        Wout = self.w.get("output.weight", self.m.tok_emb)
        dxf = Wout.T @ dlogits
        # backward through output_norm
        dx = self._bwd_rms(dxf, allx[T-1]["x"], self.w["output_norm.weight"], allx[T-1]["msf"], allx[T-1]["invf"])
        # 倒序走所有层缓存
        for c in reversed(caches):
            L = c["L"]
            # FFN 反向
            dff = dx
            dgu = self.w["blk.%d.ffn_down.weight"%L].T @ dff
            dg = dgu * c["u"]; du = dgu * c["g"]
            # silu'(x) = s + g*(1-s)   (因 g = x*s)
            dg_pre = dg * (c["sg"] + c["g"]*(1.0-c["sg"]))
            dh2 = self.w["blk.%d.ffn_gate.weight"%L].T @ dg_pre + self.w["blk.%d.ffn_up.weight"%L].T @ du
            dx = dx + self._bwd_rms(dh2, c["x_mid"], self.w["blk.%d.ffn_norm.weight"%L], c["ms2"], c["inv2"])
            # attention 反向
            do = dx
            datt = self.w["blk.%d.attn_output.weight"%L].T @ do
            datt2 = datt.reshape(N_HEAD, HEAD_DIM)
            rep = N_HEAD//N_KV
            Vx = np.repeat(c["Vs"], rep, axis=1)     # [seq,N_HEAD,HD]
            Kx = np.repeat(c["Ks"], rep, axis=1)
            da = np.einsum("hd,shd->hs", datt2, Vx)             # [N_HEAD,seq]
            dVx = np.einsum("hs,hd->shd", c["a"], datt2)        # [seq,N_HEAD,HD]
            # softmax 反向
            dsc = c["a"]*(da - (da*c["a"]).sum(axis=-1, keepdims=True))/np.sqrt(HEAD_DIM)
            dq = np.einsum("hs,shd->hd", dsc, Kx)               # [N_HEAD,HD]
            dKx = np.einsum("hs,hd->shd", dsc, c["qr"])         # [seq,N_HEAD,HD]
            # 只回传当前 token 的 k/v; GQA: 组内求和
            dk = dKx[-1].reshape(N_KV, rep, HEAD_DIM).sum(axis=1)   # [N_KV,HD]
            dv2 = dVx[-1].reshape(N_KV, rep, HEAD_DIM).sum(axis=1)  # [N_KV,HD]
            # rope 反向
            dq2 = self._bwd_rope(dq.reshape(N_HEAD,HEAD_DIM), c["t"])
            dk2 = self._bwd_rope(dk, c["t"])
            # 投影反向 (+ LoRA)
            dh = (self.w["blk.%d.attn_q.weight"%L].T @ dq2.reshape(-1)
                  + self.w["blk.%d.attn_k.weight"%L].T @ dk2.reshape(-1)
                  + self.w["blk.%d.attn_v.weight"%L].T @ dv2.reshape(-1))
            if (L,"q") in self.loras:
                axq = self.loras[(L,"q")].A @ c["h"]
                dh += self.loras[(L,"q")].bwd(c["h"], axq, dq2.reshape(-1))
            if (L,"v") in self.loras:
                axv = self.loras[(L,"v")].A @ c["h"]
                dh += self.loras[(L,"v")].bwd(c["h"], axv, dv2.reshape(-1))
            dx = dx + self._bwd_rms(dh, c["x_in"], self.w["blk.%d.attn_norm.weight"%L], c["ms"], c["inv"])
        return loss, p

    def _bwd_rms(self, dy, x, w, ms, inv):
        # y = x*inv*w ;  dy → dx
        # d/dx = inv*w*dy - (x*inv^3/ d) * sum(dy*w*x)
        d = len(x)
        dyw = dy * w
        s = np.sum(dyw * x)
        dx = dyw*inv - x*(inv**3/d)*s
        return dx

    def _bwd_rope(self, dy, pos):
        ang = pos*self.inv
        c = np.cos(ang).astype(np.float32); s = np.sin(ang).astype(np.float32)
        dy1 = dy[..., :HEAD_DIM//2]; dy2 = dy[..., HEAD_DIM//2:]
        dx1 = dy1*c + dy2*s
        dx2 = -dy1*s + dy2*c
        return np.concatenate([dx1,dx2],axis=-1)

    def step(self, lr):
        for lo in self.loras.values(): lo.step(lr)
    def num_params(self):
        return sum(l.A.size + l.B.size for l in self.loras.values())
