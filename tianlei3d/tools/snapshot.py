#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
天泪纪元 · 访客快照
==========================================================================
为什么需要它
  公共 broker 只保留「每人最新一条」消息。某人明天再来，就把他今天的记录
  覆盖掉了 —— 于是「今天有几个人」这个事实过一天就永久消失。
  这个脚本每天把当时的全量保留消息抓下来，落成两份文件：

    stats/YYYY-MM-DD.json    当日快照（谁来过、从哪来、看了哪几页）
    stats/history.json       累计账本（每个人的首次/最后访问、总次数、地区）

数据来源
  retained  zhz/tianlei/stats/v/<uid>      访客留痕（fp.js 写入）
  retained  zhz/tianlei/inv/<邀请人>/<新人>  邀请关系（rewards.js 写入）
  retained  zhz/tianlei/reward/<uid>       积分（跨设备同步用，这里只做备份）

去重原则
  · 按 uid 去重（指纹派生，换浏览器也认得）
  · 同 IP 多 uid 视为「疑似同一人」，在报告里标出来但不合并 —— 宁可多算也别漏算
  · 机房/代理 IP（hosting / proxy）标注 suspect=true，不计入「真人」统计

用法
  python3 tools/snapshot.py               # 抓一次，写入 stats/
  python3 tools/snapshot.py --no-geo      # 跳过 IP 归属查询（更快、不联网）
  python3 tools/snapshot.py --report      # 顺便打印今日报告
==========================================================================
"""
import json, os, sys, time, datetime, argparse, collections, urllib.request

BROKER = 'broker.hivemq.com'          # 实测唯一存有数据的 broker
PORT = 1883
T_STATS = 'zhz/tianlei/stats/v/+'
T_INV = 'zhz/tianlei/inv/+/+'
T_REWARD = 'zhz/tianlei/reward/+'

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
STATS_DIR = os.path.join(ROOT, 'stats')
TZ = datetime.timezone(datetime.timedelta(hours=8))


def now8():
    return datetime.datetime.now(TZ)


def dstr(d):
    return d.strftime('%Y-%m-%d')


def ts2dt(ms):
    return datetime.datetime.fromtimestamp(ms / 1000, TZ)


# ------------------------------------------------------------------ 抓取
def fetch_retained(wait=12):
    """订阅三个主题，收 retained 消息。返回 {topic: payload_str}"""
    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        print('缺少 paho-mqtt：pip install paho-mqtt', file=sys.stderr)
        sys.exit(2)

    got = {}

    def on_connect(c, u, f, rc, p=None):
        c.subscribe(T_STATS, qos=0)
        c.subscribe(T_INV, qos=0)
        c.subscribe(T_REWARD, qos=0)

    def on_message(c, u, m):
        got[m.topic] = m.payload.decode('utf-8', 'replace')

    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                    client_id='zhzsnap%d' % int(time.time()))
    c.on_connect = on_connect
    c.on_message = on_message
    c.connect(BROKER, PORT, 30)
    c.loop_start()
    time.sleep(wait)
    c.loop_stop()
    c.disconnect()
    return got


# ------------------------------------------------------------------ 归属
def geo_lookup(ips):
    """批量查 IP 归属；标出机房/代理（这类不是真人）。失败就返回空。"""
    out = {}
    ips = [ip for ip in ips if ip and not ip.startswith('10.') and not ip.startswith('192.168.')]
    for i in range(0, len(ips), 90):          # ip-api 批量上限 100
        chunk = ips[i:i + 90]
        try:
            body = json.dumps([{'query': q} for q in chunk]).encode()
            req = urllib.request.Request(
                'http://ip-api.com/batch?lang=zh-CN&fields=query,country,regionName,city,isp,mobile,proxy,hosting',
                data=body, headers={'Content-Type': 'application/json'})
            for d in json.load(urllib.request.urlopen(req, timeout=25)):
                out[d.get('query', '')] = {
                    'country': d.get('country', ''),
                    'region': d.get('regionName', ''),
                    'city': d.get('city', ''),
                    'isp': d.get('isp', ''),
                    'mobile': bool(d.get('mobile')),
                    'suspect': bool(d.get('proxy') or d.get('hosting'))
                }
        except Exception as e:
            print('  ! 归属查询失败（跳过）:', e, file=sys.stderr)
        time.sleep(0.4)
    return out


# ------------------------------------------------------------------ 主流程
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--wait', type=float, default=12, help='订阅等待秒数')
    ap.add_argument('--no-geo', action='store_true', help='跳过 IP 归属查询')
    ap.add_argument('--report', action='store_true', help='打印今日报告')
    ap.add_argument('--day', default='', help='覆盖日期（默认今天，补录时用）')
    a = ap.parse_args()

    os.makedirs(STATS_DIR, exist_ok=True)
    today = a.day or dstr(now8())
    d0 = datetime.datetime.strptime(today, '%Y-%m-%d').replace(tzinfo=TZ)
    d0_ms = d0.timestamp() * 1000
    d1_ms = (d0 + datetime.timedelta(days=1)).timestamp() * 1000

    print('抓取 broker 保留消息 …（%s）' % BROKER)
    raw = fetch_retained(a.wait)
    print('  收到 %d 条' % len(raw))
    # ---- 拆成访客 / 邀请 / 积分 ----
    visitors, invites, rewards = {}, {}, {}
    for t, p in raw.items():
        try:
            if t.startswith('zhz/tianlei/stats/v/'):
                o = json.loads(p)
                uid = o.get('id') or t.rsplit('/', 1)[-1]
                if uid:
                    o['id'] = uid
                    visitors[uid] = o
            elif t.startswith('zhz/tianlei/inv/'):
                seg = t.split('/')                       # zhz tianlei inv <邀请人> <新人>
                if len(seg) >= 5:
                    inviter, newbie = seg[3], seg[4]
                    if inviter and newbie and inviter != newbie:
                        try:
                            o = json.loads(p)
                        except Exception:
                            o = {}
                        invites.setdefault(inviter, {})[newbie] = {
                            'at': o.get('at') or 0,
                            'name': o.get('name') or '',
                            'page': o.get('page') or ''
                        }
            elif t.startswith('zhz/tianlei/reward/'):
                o = json.loads(p)
                uid = o.get('uid') or t.rsplit('/', 1)[-1]
                if uid:
                    rewards[uid] = {'pts': o.get('pts', 0), 'title': o.get('title', ''),
                                    'at': o.get('at', 0)}
        except Exception:
            continue

    # ---- IP 归属 ----
    geo = {}
    if visitors and not a.no_geo:
        ips = sorted({(v.get('ip') or v.get('ipv4') or '') for v in visitors.values()} - {''})
        print('  查询 %d 个 IP 归属 …' % len(ips))
        geo = geo_lookup(ips)
    for uid, v in visitors.items():
        g = geo.get(v.get('ip') or v.get('ipv4') or '', {})
        v['geo'] = ((g.get('country') or '') + ' ' + (g.get('region') or '') + ' ' + (g.get('city') or '')).strip()
        v['isp'] = g.get('isp', '')
        v['suspect'] = bool(g.get('suspect'))

    # ---- 按「数据里真实的日期」分桶 ----
    # 为什么不用 now()：GitHub Actions 的 cron 常延迟 10~60 分钟，一旦跨过 0 点，
    # "今天"就变成新的一天，昨天的数据会被永远漏掉。这里改成从每条记录的
    # firstAt / at 反推它属于哪一天 → 只要 broker 还留着这些人，历史就能补齐。
    def day_bounds(ds):
        d = datetime.datetime.strptime(ds, '%Y-%m-%d').replace(tzinfo=TZ)
        return d.timestamp() * 1000, (d + datetime.timedelta(days=1)).timestamp() * 1000

    def build_day(ds):
        lo, hi = day_bounds(ds)
        rows = []
        for uid, v in visitors.items():
            at = v.get('at') or 0
            first = v.get('firstAt') or at
            if lo <= at < hi or lo <= first < hi:
                rows.append({
                    'uid': uid,
                    'name': v.get('name') or '',
                    'firstAt': first,
                    'lastAt': at,
                    'isNew': lo <= first < hi,
                    'visits': v.get('visits', 0),
                    'pages': v.get('pages') or {},
                    'ip': v.get('ip') or v.get('ipv4') or '',
                    'geo': v.get('geo', ''),
                    'isp': v.get('isp', ''),
                    'suspect': v.get('suspect', False),
                    'plat': v.get('plat', ''),
                    'cores': v.get('cores', 0),
                    'scr': v.get('scr', ''),
                    'tz': v.get('tz', ''),
                    'mobile': v.get('mobile', 0)
                })
        rows.sort(key=lambda x: x['lastAt'], reverse=True)
        rl = [x for x in rows if not x['suspect']]
        groups = collections.defaultdict(list)
        for x in rows:
            if x['ip']:
                groups[x['ip']].append(x['uid'])
        return {
            'date': ds,
            'generatedAt': int(now8().timestamp() * 1000),
            'broker': BROKER,
            'totals': {
                'records': len(rows),
                'unique': len(rows),
                'real': len(rl),
                'suspect': len(rows) - len(rl),
                'new': sum(1 for x in rows if x['isNew']),
                'returning': sum(1 for x in rows if not x['isNew']),
                'site': sum(1 for x in rows if (x['pages'] or {}).get('site')),
                'game': sum(1 for x in rows if (x['pages'] or {}).get('game')),
                'forum': sum(1 for x in rows if (x['pages'] or {}).get('forum')),
                'poster': sum(1 for x in rows if (x['pages'] or {}).get('poster')),
            },
            'regions': dict(collections.Counter((x['geo'] or '未知') for x in rl).most_common()),
            'sameIpGroups': {ip: ids for ip, ids in groups.items() if len(ids) > 1},
            'visitors': rows,
            'invites': {k: list(v.keys()) for k, v in invites.items()},
            'cumulativeVisitorsInBroker': len(visitors)
        }

    # 数据里出现过的所有日期
    dates = set()
    for v in visitors.values():
        for k in ('at', 'firstAt'):
            ms = v.get(k) or 0
            if ms > 0:
                try:
                    dates.add(dstr(ts2dt(ms)))
                except Exception:
                    pass
    if today not in dates:
        dates.add(today)

    day_docs = {}
    written = []
    for ds in sorted(dates):
        doc = build_day(ds)
        path = os.path.join(STATS_DIR, ds + '.json')
        exists = os.path.exists(path)
        # 今天总是重写；历史日期只在缺失时补录（不覆盖已归档的当天快照）
        if ds == today or not exists:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(doc, f, ensure_ascii=False, indent=1)
            written.append(ds + ('' if exists or ds != today else ' (新)'))
        else:
            try:
                with open(path, encoding='utf-8') as f:
                    doc = json.load(f)
            except Exception:
                pass
        day_docs[ds] = doc
    print('  ✅ 写入 %d 份日快照: %s' % (len(written), ', '.join(written) if written else '（无变化）'))

    day_doc = day_docs.get(today) or build_day(today)

    # ---- 累计账本（合并历史，永不丢）----
    hist_path = os.path.join(STATS_DIR, 'history.json')
    hist = {}
    if os.path.exists(hist_path):
        try:
            with open(hist_path, encoding='utf-8') as f:
                hist = json.load(f)
        except Exception:
            hist = {}
    people = hist.get('people', {})
    daily = hist.get('daily', {})

    for uid, v in visitors.items():
        at = v.get('at') or 0
        first = v.get('firstAt') or at
        p = people.get(uid, {})
        rec = {
            'uid': uid,
            'name': v.get('name') or p.get('name') or '',
            'firstAt': min(filter(None, [p.get('firstAt'), first])) if (p.get('firstAt') or first) else 0,
            'lastAt': max(p.get('lastAt', 0), at),
            'visits': max(p.get('visits', 0), v.get('visits', 0)),
            'pages': v.get('pages') or p.get('pages') or {},
            'ip': v.get('ip') or p.get('ip') or '',
            'geo': v.get('geo') or p.get('geo') or '',
            'isp': v.get('isp') or p.get('isp') or '',
            'suspect': v.get('suspect', p.get('suspect', False)),
            'days': sorted(set((p.get('days') or []) + ([dstr(ts2dt(x)) for x in (at, first) if x > 0])))
        }
        people[uid] = rec

    for ds, dd in day_docs.items():
        daily[ds] = {
            'records': dd['totals']['records'],
            'real': dd['totals']['real'],
            'new': dd['totals']['new'],
            'site': dd['totals']['site'],
            'game': dd['totals']['game'],
            'forum': dd['totals']['forum'],
            'poster': dd['totals']['poster']
        }

    # 邀请累计
    inv_hist = hist.get('invites', {})
    for inviter, members in invites.items():
        inv_hist.setdefault(inviter, {})
        for m, mo in members.items():
            if m not in inv_hist[inviter]:
                inv_hist[inviter][m] = {'at': mo.get('at', 0), 'name': mo.get('name', '')}

    hist = {
        'updatedAt': int(now8().timestamp() * 1000),
        'broker': BROKER,
        'people': people,
        'daily': daily,
        'invites': inv_hist,
        'summary': {
            'allPeople': len(people),
            'allReal': sum(1 for p in people.values() if not p.get('suspect')),
            'days': len(daily),
            'firstDay': min(daily) if daily else today,
            'lastDay': max(daily) if daily else today,
            'totalInvites': sum(len(v) for v in inv_hist.values())
        }
    }
    with open(hist_path, 'w', encoding='utf-8') as f:
        json.dump(hist, f, ensure_ascii=False, indent=1)
    print('  ✅ %s（累计 %d 人 / %d 天）' % (hist_path, len(people), len(daily)))

    # ---- 报告 ----
    if a.report:
        t = day_doc['totals']
        print('\n=== %s ===' % today)
        print('  记录 %d · 真人 %d · 疑似机房 %d' % (t['records'], t['real'], t['suspect']))
        print('  新访客 %d / 回访 %d' % (t['new'], t['returning']))
        print('  官网 %d · 游戏 %d · 论坛 %d · 海报 %d' %
              (t['site'], t['game'], t['forum'], t['poster']))
        if day_doc['regions']:
            print('  地区：' + ' / '.join('%s(%d)' % (k, v) for k, v in list(day_doc['regions'].items())[:8]))
        if day_doc['sameIpGroups']:
            print('  ⚠ 同 IP 多指纹：%d 组' % len(day_doc['sameIpGroups']))
        print('\n  时间     名字        新/回  设备             地区')
        for x in (day_doc.get('visitors') or [])[:20]:
            print('  %s %-10s %-4s %-8s %-12s %s%s' % (
                ts2dt(x['lastAt']).strftime('%H:%M') if x['lastAt'] else '  —  ',
                (x['name'] or '(未起名)')[:10],
                '新' if x['isNew'] else '回',
                (x['plat'] or '')[:8],
                (x['scr'] or '')[:12],
                x['geo'] or '未知',
                '  [机房]' if x['suspect'] else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main())
