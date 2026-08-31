#!/usr/bin/env python3
"""对决打分: 语法检查(bash -n / py_compile) + 逻辑验证(运行测试) + 人工摘录"""
import subprocess, sys, re, os

OUT = '/workspace/duel_out'
MODELS = ['0.5b', 'code_v2', '3b']
TESTS = {
    'bash_count':   ('bash', '统计.log行数总和'),
    'is_prime':     ('py',   'is_prime(7)=True is_prime(8)=False'),
    'chicken_rabbit':('txt', '答案=23鸡12兔'),
    'reverse_str':  ('py',   "reverse('hello')='olleh'"),
}

def extract_py(txt):
    # 取第一段 python 代码: 从 def/import/class 起, 到明显的非代码行止
    m = re.search(r'(?:```(?:python)?\s*)?((?:def |import |class |from |#!/usr/bin/env python).*?)(?:```|$)', txt, re.S)
    return m.group(1).strip() if m else None

def extract_bash(txt):
    m = re.search(r'(?:```(?:bash|sh)?\s*)?((?:#!/bin/bash|#!/bin/sh|#!|cat |grep |find |wc |for |while |echo ).*?)(?:```|$)', txt, re.S)
    return m.group(1).strip() if m else None

def grade_py(code, testname):
    if not code:
        return 'NOCODE', ''
    ok_syntax = 'OK'
    try:
        compile(code, '<d>', 'exec')
    except SyntaxError as e:
        return 'SYNTAX_FAIL', f'行{e.lineno}: {e.msg}'
    # 逻辑测试
    if testname == 'is_prime':
        ns = {}
        try:
            exec(code, ns)
            f = ns.get('is_prime')
            if not f: return 'OK', '函数未定义?'
            r = (f(7), f(8), f(2), f(1))
            return ('LOGIC_OK' if r == (True, False, True, False) else 'LOGIC_FAIL'), f'is_prime(7,8,2,1)={r}'
        except Exception as e:
            return 'RUNTIME_ERR', str(e)[:60]
    if testname == 'reverse_str':
        ns = {}
        try:
            exec(code, ns)
            # 找函数名 (参数1个返回字符串)
            for fn in ('reverse', 'rev', 'str_rev', 'reverse_string'):
                if fn in ns:
                    r = ns[fn]('hello')
                    return ('LOGIC_OK' if r == 'olleh' else 'LOGIC_FAIL'), f"{fn}('hello')={r!r}"
            return 'OK', '未找到函数, 人工看'
        except Exception as e:
            return 'RUNTIME_ERR', str(e)[:60]
    return 'OK', ''

def grade_bash(code):
    if not code:
        return 'NOCODE', ''
    r = subprocess.run(['bash', '-n'], input=code, capture_output=True, text=True)
    if r.returncode != 0:
        return 'SYNTAX_FAIL', r.stderr.strip()[:60]
    return 'OK', ''

results = {}
for mod in MODELS:
    for t in TESTS:
        fp = f'{OUT}/{mod}_{t}.txt'
        if not os.path.exists(fp):
            results[(mod, t)] = ('MISSING', '')
            continue
        txt = open(fp).read().strip()
        kind, note = TESTS[t]
        if kind == 'py':
            code = extract_py(txt)
            st, info = grade_py(code, t)
        elif kind == 'bash':
            code = extract_bash(txt)
            st, info = grade_bash(code)
        else:
            st = 'MANUAL'
            info = '23鸡12兔' if ('23' in txt and '12' in txt) else '看内容'
            if '23' in txt and '12' in txt: st = 'ANSWER_OK'
        results[(mod, t)] = (st, info)

# 输出对比表
print('=' * 78)
print(f"{'模型':<10}{'题目':<16}{'语法':<12}{'逻辑/答案':<40}")
print('=' * 78)
for mod in MODELS:
    for t in TESTS:
        st, info = results[(mod, t)]
        print(f"{mod:<10}{t:<16}{st:<12}{info:<40}")
        if st == 'NOCODE':
            fp = f'{OUT}/{mod}_{t}.txt'
            txt = open(fp).read().strip()
            print(f"{'':<10}{'':<16}  [原文] {txt[:80]}...")
print('=' * 78)
