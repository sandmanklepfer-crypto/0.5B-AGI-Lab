#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""say.py — 自造核在「真权重语义流形」上跑, 输出 BPE token
关键: 符号划分用 BPE(人类语言), 不是随机K  → 符号有意义
"""
import numpy as np, struct
FMT={0:('B',1),1:('b',1),2:('H',2),3:('h',2),4:('I',4),5:('i',4),6:('f',4),7:('?',1),10:('Q',8),11:('q',8),12:('d',8)}

def read_meta(path,head=40_000_000):
    d=open(path,'rb').read(head)
    nt,nk=struct.unpack('<Q',d[8:16])[0],struct.unpack('<Q',d[16:24])[0]
    o=24
    def rd(t,o):
        if t==8:
            l,=struct.unpack('<Q',d[o:o+8]);o+=8
            return d[o:o+l].decode('utf-8','ignore'),o+l
        if t==9:
            et,=struct.unpack('<I',d[o:o+4]);o+=4;n,=struct.unpack('<Q',d[o:o+8]);o+=8;v=[]
            if et==8:
                for _ in range(n):
                    l,=struct.unpack('<Q',d[o:o+8]);o+=8;v.append(d[o:o+l].decode('utf-8','ignore'));o+=l
            else:
                f,s=FMT.get(et,('I',4));v=list(struct.unpack('<%d%s'%(n,f),d[o:o+n*s]));o+=n*s
            return v,o
        f,s=FMT[t];v,=struct.unpack('<'+f,d[o:o+s]);return v,o+s
    K={}
    for _ in range(nk):
        kl,=struct.unpack('<Q',d[o:o+8]);o+=8;k=d[o:o+kl].decode();o+=kl
        vt,=struct.unpack('<I',d[o:o+4]);o+=4;v,o=rd(vt,o);K[k]=v
    tens=[]
    for _ in range(nt):
        nl,=struct.unpack('<Q',d[o:o+8]);o+=8;name=d[o:o+nl].decode();o+=nl
        nd,=struct.unpack('<I',d[o:o+4]);o+=4
        dims=struct.unpack('<%dQ'%nd,d[o:o+8*nd]);o+=8*nd
        tt,=struct.unpack('<I',d[o:o+4]);o+=4
        off,=struct.unpack('<Q',d[o:o+8]);o+=8
        tens.append((name,dims,tt,off))
    al=32-(o%32);data0=o+(al if al!=32 else 0)
    return K,tens,data0

def get_emb(path,ntok,need_meta=True,cache=None):
    from gguf.quants import dequantize
    K,tens,data0=read_meta(path)
    t=[x for x in tens if x[0]=='token_embd.weight'][0]
    D=int(t[1][0]);ty=t[2]
    BLK={6:22,2:18,3:20,8:34,7:24}.get(ty,22)
    VPT=D//32
    raw=np.fromfile(path,dtype=np.uint8,count=ntok*VPT*BLK,offset=data0+t[3])
    E=dequantize(raw,ty).astype(np.float32).reshape(ntok,D)
    return E,K.get('tokenizer.ggml.tokens'),K
