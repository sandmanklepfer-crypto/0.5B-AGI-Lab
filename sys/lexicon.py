# -*- coding: utf-8 -*-
"""词典层 — 35万词 + 55词性 + 最长匹配分词"""
import re
_D=None
def load(path='/workspace/jieba-0.42.1/jieba/dict.txt'):
    global _D
    if _D is not None: return _D
    _D={}
    for line in open(path,encoding='utf-8',errors='replace'):
        p=line.split()
        if len(p)>=3: _D[p[0]]=(int(p[1]),p[2])
        elif len(p)==2: _D[p[0]]=(int(p[1]),'n')
    return _D
def cut(s):
    D=load(); out=[];i=0;mx=8
    while i<len(s):
        for L in range(min(mx,len(s)-i),0,-1):
            if s[i:i+L] in D: out.append((s[i:i+L],D[s[i:i+L]][1])); i+=L; break
        else: out.append((s[i],'x')); i+=1
    return out
def tags(s): return [t for _,t in cut(s)]
def known(w): return w in load()
def info(w):
    D=load()
    return D.get(w)
# 词性→句法大类
CLS={}
for t in ['n','nr','ns','nt','nz','ng','nrt','j','l','i','s','zg','an']: CLS[t]='N'
for t in ['v','vd','vn','vf','vx','vg']: CLS[t]='V'
for t in ['a','ad','ag','b','z']: CLS[t]='A'
CLS.update({'r':'R','m':'M','q':'Q','d':'D','p':'P','c':'C','t':'T',
            'ul':'U','uj':'U','uv':'U','uz':'U','ud':'U','ug':'U',
            'y':'X','e':'X','o':'X','h':'X','k':'X','w':'X','x':'X','f':'P'})
def cls(s): return [CLS.get(t,'?') for t in tags(s)]
if __name__=='__main__':
    D=load()
    print(f"词典: {len(D)} 词, {len(set(v[1] for v in D.values()))} 词性")
    for s in ['我今天吃了一个苹果','小明比小红大3岁','该模型在测试集上达到了很高的准确率']:
        print(f"  {s}")
        print(f"    词: {'/'.join(w for w,_ in cut(s))}")
        print(f"    类: {' '.join(cls(s))}")
