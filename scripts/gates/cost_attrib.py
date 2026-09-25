# -*- coding: utf-8 -*-
r"""cost_attrib.py —— **会话级**成本归属器（只读；读 DSH cost-meter storages 台账）

为什么需要它（与 `cost_meter.py` 的分工）：
  `cost_meter.py` 读 `~/dsh-usage/usage-ledger.json`，那是**按天 × 模型**聚合的账
  ⇒ 只要**同一天有别的会话（或别的任务）在跑**，差值就**混入无关成本**，报告里只能标
  「含其它任务，非纯量」，**无法剥离**。
  本脚本读 DSH 自己的 **`home/storages/cost-meter/ledger.json`**，它**按会话 id 记账**
  （每条含 input/output/cacheRead/reasoning/calls/cost/apiCost/title/at）
  ⇒ 于是可以做到：**开工拍一张"会话成本快照" → 交付再拍一张 → 差值逐会话列出**，
  本任务自己起的子代理会以**新会话**出现（可逐条认领），而**并发会话的成本被单独列出来**、
  不再被迫算进本任务。

用法（**零书别参数**：标签是自取字符串，本脚本不认识任何书/任务名）：

    python tools\cost_attrib.py snapshot --label <标签>
    python tools\cost_attrib.py diff --before <标签A> --after <标签B> [--top N]
    python tools\cost_attrib.py list [--date YYYY-MM-DD] [--match <子串>]

纪律（与手册 §0.3 / §8 / A-63 / A-64 一致）：
  - **只有两个合法来源**：① 台账/接口的**计费字段**（本脚本的 `cost`/`apiCost`）
    ② **余额差**（`provider-snapshots.json`）。**"单价 × 用量"只能标估算。**
  - 本脚本给的是**逐会话计费字段**之和；与**余额差**可能不一致（两套口径），
    **不一致时如实并列，不择一、不平均**。
  - 跨天快照 ⇒ 差值含两天，报告须注明；`takenAt` 随快照落盘，可自证时刻。
"""
import argparse
import datetime
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import os as _dsp_os, sys as _dsp_sys          # 可移植根目录：单一来源 tools\_paths.py
_dsp_sys.path.insert(0, _dsp_os.path.dirname(_dsp_os.path.abspath(__file__)))
from _paths import HOME, ROOT  # noqa: E402
STORAGE_LEDGER = os.path.join(HOME, "storages", "cost-meter", "ledger.json")
PROVIDER_SNAPS = os.path.join(HOME, "dsh-usage", "provider-snapshots.json")
# ⚠ 2026-09-21（异机可用性）：原为作者机绝对路径 ⇒ 异机必挂、发版闸 A 判据判红。
#   改为按工作区根推导（`_paths.ROOT` 唯一来源），并留 `DSH_COST_STORE` 环境变量出口。
STORE = os.environ.get("DSH_COST_STORE") or os.path.join(ROOT, ".work", "cost")

FIELDS = ["input", "output", "cacheRead", "cacheWrite", "reasoning", "calls", "cost"]


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def balance():
    """账户余额（第二来源，用于交叉验证）。"""
    try:
        d = _load(PROVIDER_SNAPS)
        b = ((d.get("providers", {}) or {}).get("deepseek-official", {}) or {}).get("balance", {}) or {}
        return b.get("totalBalance"), b.get("currency"), b.get("updatedAt")
    except Exception as exc:                                  # A-71：静默吞异常 ⇒ 必须响
        print(f"⚠ 余额读取失败（{type(exc).__name__}: {exc}）——本次不给余额，不影响会话级差值。")
        return None, None, None


def collect():
    """→ (days{date:{...}}, sess{id:{...累计...}}, bydate{(id,date):{...当日...}}, raw)

    口径（**必须看清，否则会把长寿会话误读成当日成本**）：
      `sess[sid]` = 该会话**全期间累计**（跨天相加）——用于 snapshot/diff 的差值（差值＝窗口内成本，正确）；
      `bydate[(sid,date)]` = 该会话**当日**成本——用于 `list --date` 的"当日"栏。
    """
    led = _load(STORAGE_LEDGER)
    days, sess, bydate = {}, {}, {}
    for date, node in (led.get("days") or {}).items():
        days[date] = {k: (node.get(k) or 0) for k in FIELDS}
        days[date]["apiCost"] = node.get("apiCost") or 0
        for s in node.get("sessions") or []:
            sid = s.get("id")
            if not sid:
                continue
            day_cost = {k: (s.get(k) or 0) for k in FIELDS}
            bydate[(sid, date)] = day_cost
            cur = sess.setdefault(sid, {k: 0 for k in FIELDS})
            for k in FIELDS:
                cur[k] += day_cost[k]
            # 标题取该会话最近一条非空 title
            t = (s.get("title") or "").strip()
            if t:
                cur["title"] = t[:80]
            cur["lastAt"] = max(cur.get("lastAt", 0), s.get("at") or 0)
            cur.setdefault("dates", set()).add(date)
    for sid, v in sess.items():
        v["dates"] = sorted(v.get("dates") or [])
    return days, sess, bydate, led


def cmd_snapshot(label):
    os.makedirs(STORE, exist_ok=True)
    days, sess, bydate, led = collect()
    bal, cur, bat = balance()
    snap = {
        "label": label,
        "takenAt": datetime.datetime.now().isoformat(timespec="seconds"),
        "source": STORAGE_LEDGER,
        "balance": bal, "currency": cur, "balanceUpdatedAt": bat,
        "days": days,
        "sessions": {k: {kk: (sorted(vv) if isinstance(vv, set) else vv) for kk, vv in v.items()}
                     for k, v in sess.items()},
        "byDate": {f"{sid}|{d}": v for (sid, d), v in bydate.items()},
        "sessionCount": len(sess),
    }
    p = os.path.join(STORE, f"attrib-{label}.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent=1)
    print(f"✅ 会话级快照已存：{p}")
    print(f"   时刻：{snap['takenAt']}　会话条目：{len(sess)}　账户余额：¥{bal}")


def cmd_diff(before, after, top):
    pb = os.path.join(STORE, f"attrib-{before}.json")
    pa = os.path.join(STORE, f"attrib-{after}.json")
    for p in (pb, pa):
        if not os.path.exists(p):
            print(f"❌ 缺快照：{p}")
            sys.exit(1)
    b, a = _load(pb), _load(pa)

    rows = []
    for sid, av in (a.get("sessions") or {}).items():
        bv = (b.get("sessions") or {}).get(sid) or {}
        d = {k: (av.get(k) or 0) - (bv.get(k) or 0) for k in FIELDS}
        if all(v == 0 for v in d.values()):
            continue
        rows.append({
            "sid": sid,
            "new": sid not in (b.get("sessions") or {}),
            "title": (av.get("title") or "")[:52],
            "dates": ",".join(av.get("dates") or []),
            "lastAt": av.get("lastAt") or 0,
            **d,
        })
    rows.sort(key=lambda r: -r["cost"])

    tot = {k: sum(r[k] for r in rows) for k in FIELDS}
    print(f"{'会话':<40}{'新':<4}{'调用':>6}{'输入tok':>11}{'输出tok':>11}{'缓存读tok':>13}{'成本¥':>10}  标题")
    print("-" * 132)
    for r in rows[:top]:
        sid = r["sid"]
        sid = sid if len(sid) <= 38 else sid[:36] + "…"
        print(f"{sid:<40}{'★' if r['new'] else ' ':<4}{r['calls']:>6}{r['input']:>11}{r['output']:>11}"
              f"{r['cacheRead']:>13}{r['cost']:>10.4f}  {r['title']}")
    if len(rows) > top:
        print(f"...（另有 {len(rows) - top} 个会话有增量，用 --top 调大查看）")
    print("-" * 132)
    print(f"{'合计':<40}{'':<4}{tot['calls']:>6}{tot['input']:>11}{tot['output']:>11}"
          f"{tot['cacheRead']:>13}{tot['cost']:>10.4f}")

    print()
    print(f"快照时刻：{b.get('takenAt')} → {a.get('takenAt')}")
    for nm, s in (("开工", b), ("交付", a)):
        print(f"  {nm}余额：¥{s.get('balance')}（provider-snapshots.updatedAt={s.get('balanceUpdatedAt')}）")
    try:
        bbf, abf = float(b.get("balance")), float(a.get("balance"))
        print(f"  余额差：¥{bbf - abf:.4f}　（与会话级合计 ¥{tot['cost']:.4f} 属**两套口径**，"
              f"不一致时如实并列）")
    except Exception:
        pass

    # ⚠ 口径修正（2026-09-17 本册实测）：旧版把**所有有增量会话的 dates 并集**当作"涉及日期"，
    #   而长寿会话带着几个月前的历史日期 ⇒ **每次都误报"跨天，非纯量"**（本册实测首跑即误报）。
    #   正确口径：**窗口＝两次快照的 takenAt**（会话累计成本的差值本就只反映窗口内的新增消耗）。
    d0, d1 = str(b.get('takenAt', ''))[:10], str(a.get('takenAt', ''))[:10]
    print('  窗口：%s → %s%s' % (d0, d1, '　⚠ 跨天：差值含两天，**非纯量**' if d0 != d1 else '　（同日）'))
    print(f"  新增会话（本任务期间新起，含子代理）：{sum(1 for r in rows if r['new'])} 个"
          f"　有增量的既有会话（可能是并发会话）：{sum(1 for r in rows if not r['new'])} 个")
    print("  ⚠ 「合计」= 窗口内**所有**会话的增量。**要报本任务纯量，必须逐条认领**"
          "（子代理为新会话可认领；并发会话须单列剔除，见手册 A-12／A-64）。")


def cmd_list(date, match, top):
    days, sess, bydate, _ = collect()
    rows = []
    for sid, v in sess.items():
        if date and date not in (v.get("dates") or []):
            continue
        if match and match not in (v.get("title") or "") and match not in sid:
            continue
        rows.append({"sid": sid, **v,
                     "dayCost": (bydate.get((sid, date), {}) or {}).get("cost") if date else None})
    rows.sort(key=lambda r: -(r.get("lastAt") or 0))
    hdr = f"{'会话':<40}{'累计调用':>8}{'累计¥':>10}"
    if date:
        hdr += f"{'当日调用':>8}{'当日¥':>10}"
    hdr += "  标题"
    print(hdr)
    print("-" * 132)
    for r in rows[:top]:
        sid = r["sid"] if len(r["sid"]) <= 38 else r["sid"][:36] + "…"
        line = f"{sid:<40}{r.get('calls', 0):>8}{r.get('cost', 0):>10.4f}"
        if date:
            dc = bydate.get((r["sid"], date), {}) or {}
            line += f"{dc.get('calls', 0):>8}{dc.get('cost', 0):>10.4f}"
        line += f"  {(r.get('title') or '')[:44]}"
        print(line)
    print("-" * 132)
    print(f"会话数：{len(rows)}　累计成本合计：¥{sum(r.get('cost', 0) for r in rows):.4f}"
          + (f"　当日成本合计：¥{sum((bydate.get((r['sid'], date), {}) or {}).get('cost', 0) for r in rows):.4f}"
             f"　（当日账合计 ¥{(days.get(date, {}) or {}).get('cost', 0):.4f}，两数应相等，可交叉验证）"
             if date else ""))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s1 = sub.add_parser("snapshot"); s1.add_argument("--label", required=True)
    s2 = sub.add_parser("diff")
    s2.add_argument("--before", required=True); s2.add_argument("--after", required=True)
    s2.add_argument("--top", type=int, default=40)
    s3 = sub.add_parser("list")
    s3.add_argument("--date"); s3.add_argument("--match"); s3.add_argument("--top", type=int, default=40)
    a = ap.parse_args()
    if a.cmd == "snapshot":
        cmd_snapshot(a.label)
    elif a.cmd == "diff":
        cmd_diff(a.before, a.after, a.top)
    else:
        cmd_list(a.date, a.match, a.top)
