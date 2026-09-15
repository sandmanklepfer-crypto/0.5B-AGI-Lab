# -*- coding: utf-8 -*-
import sys, json, math
sys.path.insert(0,'/workspace/agilab/src')
from form_library import search
BANK=[]
def add(n,s,x): BANK.append({'name':n,'seq':s,'next':x})
# n^2 / n^3 / 2^n / 三角 / 等差 / 多项式 / catalan / fib(标准)
for k in range(1,9):
    add(f'n2_{k}',[i*i for i in range(k,k+5)],(k+5)**2)
for k in range(1,7):
    add(f'n3_{k}',[i**3 for i in range(k,k+4)],(k+4)**3)
for a in [2,3,5,7]:
    add(f'g{a}',[a*2**i for i in range(5)],a*2**5)
for a in [2,3,4,5]:
    add(f'T{a}',[a*i*(i+1)//2 for i in range(1,6)],a*21)
for d in [3,5,7,9]:
    add(f'ap{d}',[1+d*i for i in range(5)],1+d*5)
for a,b,c in [(1,2,0),(2,1,3),(3,2,1),(1,3,2),(2,3,1),(4,1,2),(1,4,3)]:
    add(f'p{a}{b}{c}',[a*i*i+b*i+c for i in range(1,6)],a*36+b*6+c)
for a,b in [(3,-2),(2,0),(2,1),(3,1)]:
    s=[];x=1
    for i in range(1,6): s.append(x); x=a*x+b*(i+1)
    add(f'r{a}_{b}',s,x)
cat=[math.comb(2*i,i)//(i+1) for i in range(14)]
for k in range(1,4): add(f'cat{k}',cat[k:k+5],cat[k+5])
fib=[1,1]
for i in range(10): fib.append(fib[-1]+fib[-2])
add('fib',fib[:5],fib[5])
def primes(n):
    o=[];c=2
    while len(o)<n:
        if all(c%p for p in o if p*p<=c): o.append(c)
        c+=1
    return o
P=primes(30); add('prime',P[:5],P[5])
# 差分型 (二阶差分固定)
for a in [2,3,4]:
    s=[1,2,5,10,17]  # n^2+1 变体
    add(f'q{a}',[a*i*i+1 for i in range(1,6)],a*36+1)
print(f"共 {len(BANK)} 题")
hit=0;miss=[]
for b in BANK:
    try:
        r=search(b['seq']); pred=r[2][0] if (r and len(r)>2 and r[2]) else None
        if pred==b['next']: hit+=1
        else: miss.append((b['name'],b['seq'],b['next'],pred))
    except Exception: miss.append((b['name'],b['seq'],b['next'],'ERR'))
print(f"形式库命中 {hit}/{len(BANK)}")
for m in miss[:8]: print("  未命中",m)
json.dump(BANK,open('/workspace/_BANK60.json','w'),ensure_ascii=False,indent=1)
