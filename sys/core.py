# -*- coding: utf-8 -*-
"""统一调度器 — 输入 → 路由 → 算子/验证 → 输出+审计"""
import sys, re, json
sys.path.insert(0,'/workspace'); sys.path.insert(0,'/workspace/sys')
import ops_math as M, ops_social as S, lexicon as LX, verifiers as V
try:
    import form_v3 as F
except Exception: F=None
try:
    import value_port as VP
except Exception: VP=None

def route(q):
    """意图路由 → (类别, 处理函数)"""
    if re.search(r'素数|质数|因数|分解|gcd\(|最大公约|欧拉|φ\(|phi',q,re.I): return '数论',do_nt
    if re.search(r'组合数|C\(|catalan|卡特兰|阶乘|排列|perm|fib|斐波',q,re.I): return '组合',do_comb
    if re.search(r'等于|计算|求值|多少|√|平方|方程|解',q): return '算术/代数',do_alg
    if re.search(r'数列|规律|下一项|序列',q): return '数列',do_seq
    if re.search(r'纳什|均衡|博弈|占优|最优|策略',q): return '博弈',do_gt
    if re.search(r'投票|选举|排序|偏好|社会选择',q): return '社会选择',do_sc
    if re.search(r'背包|指派|运输|调度|规划',q): return '运筹',do_or
    if re.search(r'该不该|应该|伦理|道德|公平|价值',q): return '规范',do_val
    if re.search(r'是什么|什么是|谁的|哪个|哪年|定义',q): return '知识',do_kb
    return '通用',do_gen
# ---- 各处理器 ----
def do_nt(q):
    nums=[int(x) for x in re.findall(r'\d+',q)]
    if not nums: return None,'无数'
    n=nums[0]
    if '素数' in q or '质数' in q:
        return {'n':n,'is_prime':M.is_prime(n)},'L1验证'
    if '因数' in q or '分解' in q:
        return {'n':n,'factors':M.factorize(n)},'L1验证'
    if ('公约' in q or 'gcd' in q.lower()) and len(nums)>=2:
        return {'gcd':M.gcd(nums[0],nums[1])},'L1验证'
    if 'φ' in q or 'phi' in q.lower() or '欧拉' in q:
        return {'euler_phi':M.euler_phi(n)},'L1验证'
    return {'euler_phi':M.euler_phi(n)},'L1验证'
def do_comb(q):
    nums=[int(x) for x in re.findall(r'\d+',q)]
    if not nums: return None,'无数'
    if re.search(r'C\(|组合数',q,re.I) and len(nums)>=2:
        return {'C(n,k)':M.C(nums[0],nums[1])},'L1验证'
    if re.search(r'catalan|卡特兰',q,re.I):
        return {'catalan':M.catalan(nums[0])},'L1验证'
    if re.search(r'阶乘|factorial|!',q):
        return {'n!':__import__('math').factorial(nums[0])},'L1验证'
    if re.search(r'perm|排列',q,re.I) and len(nums)>=2:
        return {'perm(n,k)':M.perm(nums[0],nums[1])},'L1验证'
    if re.search(r'fib|斐波',q,re.I):
        return {'fib':M.fib(nums[0])},'L1验证'
    return None,'未知组合查询'
CN={'乘以':'*','乘':'*','×':'*','加上':'+','加':'+','减去':'-','减':'-',
    '除以':'/','除':'/','的平方':'**2','平方':'**2'}
def do_alg(q):
    # 中文算术
    q2=q
    for k,v in sorted(CN.items(),key=lambda x:-len(x[0])): q2=q2.replace(k,v)
    nums=re.findall(r'\d+',q2)
    if len(nums)>=2 and re.search(r'[\*\+\-/]',q2):
        expr=re.search(r'(\d+\s*[\*\+\-/]\s*\d+(?:\s*[\*\+\-/]\s*\d+)*)',q2)
        if expr:
            try:
                v=eval(expr.group(1),{"__builtins__":{}},{})
                return {'expr':expr.group(1),'value':v},'L1可执行(中文解析)'
            except Exception: pass
    m=re.search(r'([\d\s\+\-\*/\(\)\.]+)=',q)
    if m:
        try:
            v=eval(m.group(1),{"__builtins__":{}},{})
            return {'expr':m.group(1),'value':v},'L1可执行'
        except Exception: pass
    m=re.search(r'x\s*\^\s*2|平方|quad',q)
    nums=[float(x) for x in re.findall(r'-?\d+\.?\d*',q)]
    if ('方程' in q or '=' in q) and len(nums)>=3:
        r=M.solve_quad(nums[0],nums[1],nums[2])
        return {'roots':r,'coef':nums[:3]},'L1可执行'
    return None,'无法解析'
def do_seq(q):
    if F is None: return None,'form库未加载'
    nums=[int(x) for x in re.findall(r'\d+',q)]
    if len(nums)<3: return None,'太短'
    r,p=F.search_v2(nums)
    return {'rule':r,'next':p},'形式库+验证'
def do_gt(q):
    m=re.search(r'\[\[(.+?)\]\]',q)
    if m:
        rows=[[float(x) for x in r.split(',')] for r in m.group(1).split(';')]
        import numpy as np
        A=np.array(rows)
        return {'dominant':S.dominant(A),'matrix':rows},'博弈论'
    nums=[float(x) for x in re.findall(r'-?\d+\.?\d*',q)]
    if len(nums)==4:
        import numpy as np
        A=np.array(nums[:2]).reshape(2,2)
        return {'nash_pure':S.nash_pure(A,A)},'博弈论'
    return None,'需[[矩阵]]'
def do_sc(q):
    # 支持 '012,021,102' 紧凑格式 与 空格分隔
    groups=re.findall(r'\d{3,}',q)
    if groups:
        votes=[[int(c) for c in g] for g in groups]
    else:
        nums=[int(x) for x in re.findall(r'\d+',q)]
        if len(nums)%3!=0 or len(nums)<3: return None,'需投票数据'
        votes=[nums[i*3:(i+1)*3] for i in range(len(nums)//3)]
    n=len(votes[0])
    b=S.borda(votes,n); c=S.condorcet(votes,n)
    return {'borda':b,'condorcet':c,'votes':votes},'社会选择'
def do_or(q):
    nums=[float(x) for x in re.findall(r'-?\d+\.?\d*',q)]
    if '背包' in q and len(nums)>=5:
        W=nums[-1]; rest=nums[:-1]; h=len(rest)//2
        return {'max_value':S.knapsack_01(rest[:h],rest[h:],int(W))},'DP精确'
    return None,'需参数'
def do_val(q):
    if VP is None: return None,'无价值层'
    opts={'方案A':{'vals':[3,2,1]},'方案B':{'vals':[2,4,0]},'方案C':{'vals':[1,1,5]}}
    return {'by_bridge':VP.compare_bridges(opts)},'价值插口(需显式选桥)'
def do_kb(q):
    D=LX.load()
    ws=[w for w,_ in LX.cut(re.sub(r'[什么是谁的哪年？?]','',q)) if len(w)>=2]
    hit={w:D[w] for w in ws if w in D}
    return {'words':hit},'词典'
def do_gen(q):
    return {'tokens':[(w,t) for w,t in LX.cut(q)]},'词典分词'
def answer(q, bridge='utilitarian'):
    cat,fn=route(q)
    try: res,how=fn(q)
    except Exception as e: res,how=None,f'错误:{e}'
    return {'q':q,'category':cat,'result':res,'verified_by':how}
if __name__=='__main__':
    tests=['97是素数吗','分解360的因数','37乘以23等于多少','数列 1,4,9,16,25 的下一项',
           '求3和12的最大公约','[[3,0;5,1]] 的占优策略','这个方案应该选哪个']
    for t in tests:
        a=answer(t)
        print(f"[{a['category']}] {t}")
        print(f"    → {a['result']}   ({a['verified_by']})")
