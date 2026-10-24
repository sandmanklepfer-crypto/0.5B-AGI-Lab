#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
天泪纪元 · 停留时长报告
========================================================================
数据来源：retained  zhz/tianlei/dwell/<uid>
  由 js/fp.js 的 dwellStart/dwellFlush 写入，字段：
    sec     本次会话「页面可见」的停留秒数（切后台不计）
    wall    墙上时间（含后台），用来对比"是不是挂着"
    scroll  最大滚动深度 0~1
    clicks  点击次数
    page    site / game / forum / poster
    why     beat(15s心跳) / hide(切后台) / bye(关页面) / end / flush

判读口径
  · sec < 5      → 秒退（基本没看）
  · 5~30         → 浅看
  · 30~120       → 有在看
  · >120         → 深度兴趣
  · wall >> sec  → 挂着没看（切后台了）
  · scroll >0.7 且 clicks>0 → 真的在浏览

用法
  python3 tools/dwell.py            # 今日报告
  python3 tools/dwell.py --all      # 全部（不限日期）
  python3 tools/dwell.py --raw      # 打印原始记录
========================================================================
"""
import json, sys, time, datetime, argparse, collections

BROKER = 'broker.hivemq.com'
TOPIC = 'zhz/tianlei/dwell/+'
TZ = datetime.timezone(datetime.timedelta(hours=8))


def fetch(wait=10):
    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        print('缺少 paho-mqtt：pip install paho-mqtt', file=sys.stderr)
        sys.exit(2)

    got = {}

    def on_connect(c, u, f, rc, p=None):
        c.subscribe(TOPIC, qos=0)

    def on_message(c, u, m):
        got[m.topic] = m.payload.decode('utf-8', 'replace')

    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id='zhzdw%d' % int(time.time()))
    c.on_connect, c.on_message = on_connect, on_message
    c.connect(BROKER, 1883, 30)
    c.loop_start()
    time.sleep(wait)
    c.loop_stop()
    c.disconnect()

    rows = []
    for t, v in got.items():
        try:
            o = json.loads(v)
            o['_topic'] = t
            rows.append(o)
        except Exception:
            pass
    return rows


def bucket(sec):
    if sec < 5:
        return '秒退'
    if sec < 30:
        return '浅看'
    if sec < 120:
        return '有看'
    return '深度'


def fmt_sec(s):
    s = int(s or 0)
    if s < 60:
        return '%d 秒' % s
    m = s // 60
    r = s % 60
    return '%d 分 %02d 秒' % (m, r) if r else '%d 分' % m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--wait', type=float, default=10)
    ap.add_argument('--all', action='store_true')
    ap.add_argument('--raw', action='store_true')
    a = ap.parse_args()

    now = datetime.datetime.now(TZ)
    d0 = now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000

    rows = fetch(a.wait)
    if not a.all:
        rows = [r for r in rows if (r.get('at') or 0) >= d0]
    rows.sort(key=lambda r: r.get('at') or 0, reverse=True)

    if a.raw:
        for r in rows:
            print(json.dumps(r, ensure_ascii=False))
        return 0

    print('现在 %s' % now.strftime('%Y-%m-%d %H:%M'))
    print('停留记录 %d 条%s\n' % (len(rows), '' if a.all else '（今日）'))

    if not rows:
        print('  —— 还没有停留数据 ——')
        print('  说明：埋点是刚加的，需要有人访问页面后才会产生。')
        print('  另外 fp.js 改过之后要等 CDN 缓存刷新（约 10 分钟）。')
        return 0

    print('%-6s %-10s %-9s %-9s %-6s %-6s %s' %
          ('时间', '名字', '可见停留', '墙上时间', '滚动', '点击', '页面'))
    print('-' * 76)

    secs = []
    for r in rows:
        sec = r.get('sec') or 0
        wall = r.get('wall') or 0
        secs.append(sec)
        t = datetime.datetime.fromtimestamp((r.get('at') or 0) / 1000, TZ).strftime('%H:%M')
        note = ''
        if wall > sec * 3 and wall > 60:
            note = ' ←挂着没看'
        print('%-6s %-10s %-9s %-9s %-6.2f %-6d %s%s' % (
            t,
            (r.get('name') or '(未起名)')[:10],
            fmt_sec(sec),
            fmt_sec(wall),
            r.get('scroll') or 0,
            r.get('clicks') or 0,
            r.get('page') or '-',
            note))

    print('\n=== 分布 ===')
    b = collections.Counter(bucket(s) for s in secs)
    total = len(secs)
    for k in ['秒退', '浅看', '有看', '深度']:
        n = b.get(k, 0)
        bar = '█' * int(n / max(1, total) * 24)
        print('  %-4s %2d 人 (%4.0f%%) %s' % (k, n, n / total * 100, bar))

    secs.sort()
    print('\n=== 统计 ===')
    print('  平均停留   %s' % fmt_sec(sum(secs) / len(secs)))
    print('  中位数     %s' % fmt_sec(secs[len(secs) // 2]))
    print('  最长       %s' % fmt_sec(secs[-1]))
    print('  最短       %s' % fmt_sec(secs[0]))
    really = [r for r in rows if (r.get('clicks') or 0) > 0 or (r.get('scroll') or 0) > 0.5]
    print('  真的在浏览 %d 人（有点击或滚动过半）' % len(really))
    return 0


if __name__ == '__main__':
    sys.exit(main())
