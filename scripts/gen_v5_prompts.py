#!/usr/bin/env python3
"""gen_v5_prompts.py — v5 七领域均匀蒸馏数据 (R1-32B teacher)
领域: math / logic / lang_world / code_world / knowledge / agent / express
每领域 120 条, 中文, 输出 /root/v5_prompts_{dim}.txt + all
"""
import random

random.seed(2026)

def gen_math(n=120):
    out = []
    for _ in range(n):
        t = random.choice(["arith", "alge", "geo", "seq"])
        if t == "arith":
            a, b = random.randint(6, 99), random.randint(6, 99)
            op = random.choice(["+", "-", "*"])
            out.append(f"计算：{a}{op}{b}等于多少？请给出答案。")
        elif t == "alge":
            x = random.randint(2, 20); a = random.randint(2, 9); b = a * x
            out.append(random.choice([f"解方程：{a}x={b}，求x。",
                                      f"如果{a}乘以某个数等于{b}，这个数是多少？",
                                      f"一个数的{a}倍是{b}，这个数是几？"]))
        elif t == "geo":
            r = random.randint(2, 12)
            out.append(f"一个圆的半径是{r}，它的周长是多少？（圆周率取3.14）")
        else:
            a, d = random.randint(1, 9), random.randint(2, 9)
            out.append(f"等差数列 {a}, {a+d}, {a+2*d}, ... 的第5项是多少？")
    return out

def gen_logic(n=120):
    out = []
    syll = [
        "所有的猫都是动物，咪咪是猫，那么咪咪是什么？",
        "如果今天下雨，路就会湿。今天路没湿，那么今天下雨了吗？",
        "所有的A都是B，所有的B都是C，那么所有的A是什么？",
        "要么去图书馆，要么去公园。小明没有去图书馆，那么他去了哪里？",
        "所有的鸟都有羽毛，企鹅是鸟，那么企鹅有什么？",
        "如果所有学生都通过了考试，小李是学生，那么小李怎么样了？",
        "凡金属都能导电，铜是金属，那么铜能导电吗？",
        "只有周末才放假，今天是周二，那么今天放假吗？",
        "如果明天下雨，运动会取消。运动会没有取消，那么明天怎么样了？",
        "所有人都要喝水，机器人不是人，那么机器人一定要喝水吗？",
    ]
    for _ in range(n):
        out.append(random.choice(syll))
    return out

def gen_lang_world(n=120):
    out = []
    qs = [
        "把玻璃杯从桌上推到地上，会发生什么？为什么？",
        "早上太阳从哪边升起？为什么？",
        "把一个铁球和一个木球同时从同样高度松手，哪个先落地？（忽略空气阻力）",
        "水烧到100度会怎么样？",
        "小明先吃了早饭，然后去上学。他吃早饭之前去了哪里？",
        "桌子左边有一个苹果，苹果左边有一个橘子。哪个水果在中间？",
        "如果明天下雪，路会很滑。人们走路应该注意什么？",
        "冬天北方冷还是南方冷？为什么？",
        "把冰块放在室温下，会发生什么？为什么？",
        "一辆车向东开，然后又向南开。它现在总体向哪个方向移动了？",
        "如果植物没有阳光，会怎么样？为什么？",
        "为什么夏天比冬天热？",
        "先闪电还是先打雷？为什么？",
        "把盐放进水里搅拌，盐去哪了？",
        "为什么船能浮在水上，而同样重的铁块会沉？",
    ]
    for _ in range(n):
        out.append(random.choice(qs))
    return out

def gen_code_world(n=120):
    out = []
    qs = [
        "写一个Python函数，输入两个数，返回它们的和。",
        "写一个Python函数，判断一个数是否为偶数。",
        "写一个Python函数，计算一个列表的平均值。",
        "写一个Python函数，返回字符串的长度。",
        "写一个Python函数，找出列表中的最大值。",
        "写一个Python函数，把摄氏温度转换为华氏温度。",
        "写一个Python函数，计算阶乘。",
        "写一个Python函数，检查一个字符串是否是回文。",
        "写一个Python函数，返回斐波那契数列的第n项。",
        "写一个Python函数，把字符串反转。",
        "下面代码执行后x的值是多少：x=1; x=x+2; x=x*3",
        "代码 a=[1,2,3]; b=a; b.append(4)，此时a是多少？为什么？",
        "循环 for i in range(3) 会执行几次？",
        "if 5 > 3 and 2 < 1: 这个条件成立吗？",
        "写一个Python函数，检查一个数是否为质数。",
        "代码 print(2**3) 输出什么？",
    ]
    for _ in range(n):
        out.append(random.choice(qs))
    return out

def gen_knowledge(n=120):
    out = []
    pairs = [
        "太阳系中距离太阳最近的行星是哪个？",
        "水的化学式是什么？",
        "中国最长的河流是哪条？",
        "光在真空中的速度大约是多少？",
        "人体最大的器官是什么？",
        "地球上面积最大的海洋是哪个？",
        "《红楼梦》的作者是谁？",
        "一年有多少个月？",
        "地球绕太阳公转一圈大约需要多长时间？",
        "声音在真空中能传播吗？",
        "谁发明了电灯？",
        "中国的首都是哪里？",
        "人的心脏有几个腔室？",
        "世界上最深的海洋是哪个？",
        "一公里等于多少米？",
        "水的冰点是多少摄氏度？",
    ]
    for _ in range(n):
        out.append(random.choice(pairs))
    return out

def gen_agent(n=120):
    out = []
    qs = [
        "用户想订一张明天去北京的机票，列出需要完成的步骤。",
        "如何为用户生成一份周报？请列出步骤。",
        "用户问天气，但没有网络。应该怎么处理？",
        "把一篇长文章总结成三条要点，需要哪些步骤？",
        "用户想要一份购物清单并算出总价，需要几步？",
        "如何为用户安排一次旅行？列出主要步骤。",
        "用户说'帮我查一下那个'，信息不完整。应该怎么回应？",
        "设计一个提醒用户喝水的小工具，需要什么功能？",
        "用户要发一封邮件给老板请假，需要哪些信息？",
        "如何判断用户的需求是否超出能力范围？",
        "写一个计划：早上7点起床后1小时内完成3件事。",
        "用户要比较两款手机，应该从哪些方面对比？",
    ]
    for _ in range(n):
        out.append(random.choice(qs))
    return out

def gen_express(n=120):
    out = []
    topics = [
        "人工智能的利与弊", "为什么要保护环境", "团队合作的重要性",
        "阅读的好处", "如何养成好习惯", "科技改变生活",
        "失败是成功之母", "为什么要学习历史", "城市与乡村生活",
        "运动对健康的影响", "诚信的价值", "好奇心为什么重要",
    ]
    for i in range(n):
        out.append(f"请用三段话论述：{random.choice(topics)}。要求结构清晰、有理有据。")
    return out

DIMS = [("math", gen_math), ("logic", gen_logic), ("lang_world", gen_lang_world),
        ("code_world", gen_code_world), ("knowledge", gen_knowledge),
        ("agent", gen_agent), ("express", gen_express)]

def gen_all(n):
    return [(d, fn(n)) for d, fn in DIMS]

if __name__ == "__main__":
    import sys
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 120
    total = 0
    for d, fn in DIMS:
        items = fn(n)
        with open(f"/root/v5_prompts_{d}.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(items) + "\n")
        total += len(items)
        print(d, len(items))
    with open("/root/v5_prompts_all.txt", "w", encoding="utf-8") as f:
        for d, _ in DIMS:
            f.write(open(f"/root/v5_prompts_{d}.txt", encoding="utf-8").read())
    print("total:", total)
