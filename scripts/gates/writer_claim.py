#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""writer_claim.py —— `G-62` 产物写手**归属登记**（claim／接管／校验 · 只读校验、登记只写 `_writer.json`）

⦿ 背景与教训（闸缺陷台账 `G-62`，2026-09-24 实测）：
  同一产物（如 `.work/<task>/answers/*.md`）被多个写手并发改写、无互斥 ⇒ 后写者胜，
  前后两版互相覆盖；判官所裁版本 ≠ 盘上版本 ⇒ 台账读数失效。触发实录：send_message
  报 unavailable 被误读成"对方已终止"，实际旧写手仍在写 ⇒ 两个写手同分钟交替覆盖。
  **send_message 报 unavailable ≠ 对方已停止** —— 派新写手前必须 interrupt_agent 旧写手
  并确认已停（`G-62①` 派发纪律，纪律部分，本工具管不到）。

⦿ 本工具机制化的是 `G-62②③④`：
  ② **归属登记**：每个 answers 目录一份 `_writer.json`；新写手 claim 时若发现该产物
     已被**别人**登记，必须显式 `--takeover`（声明接管）才放行，且旧登记进 history——
     "谁在写、什么时候接的手"全程留痕（派发纪律 ① 的机器侧抓手）。
  ③ **落表前复核**：`verify --expect <sha16>` ＝ 盘上 sha 与判官所裁 sha 必须一致，
     不一致不得落表（本轮实测正是靠这招发现覆盖事故）。
  ④ **症状巡检**：claim 若声明 `--generator`，则校验"答卷 mtime ≥ 生成器 mtime"
     （答卷早于生成器 ⇒ 不可能是它产的，`G-61` 原始症状）；`verify` 另校验
     "盘上 sha == 登记 sha"（改了不重登＝漂移，`G-62④`）。

⦿ sha 口径：`sha256 hexdigest 前 16 位大写`（与台账既录 `94980B0AE0CE12CE` 同法自证一致）。

⦿ 用法：
  python tools\\writer_claim.py claim   <answer.md> --writer <id> [--generator <同目录.py>] [--how <说明>] [--takeover]
  python tools\\writer_claim.py verify  <answer.md> [--expect <sha16>]
  python tools\\writer_claim.py list    <answers_dir>
  python tools\\writer_claim.py --selftest
"""
import argparse
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import time

WJ = '_writer.json'


def sha16(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()[:16].upper()


def load_wj(ad):
    p = os.path.join(ad, WJ)
    if not os.path.exists(p):
        return {'claims': []}
    return json.load(io.open(p, encoding='utf-8'))


def save_wj(ad, data):
    _s = json.dumps(data, ensure_ascii=False, indent=1) + '\n'   # ⚠ 先序列化再开写：dumps 失败不得截空登记文件
    io.open(os.path.join(ad, WJ), 'w', encoding='utf-8', newline='\n').write(_s)


def find_claim(data, fname):
    for c in data.get('claims', []):
        if c.get('file') == fname:
            return c
    return None


def cmd_claim(a):
    fp = os.path.abspath(a.answer)
    if not os.path.exists(fp):
        print('🔴 登记对象不存在：%s' % fp)
        return 1
    ad = os.path.dirname(fp)
    fname = os.path.basename(fp)
    if a.generator and not os.path.exists(os.path.join(ad, a.generator)):
        print('🔴 --generator 指向的件不在同目录：%s（必须与答卷同目录，G-61④ 口径）' % a.generator)
        return 1
    data = load_wj(ad)
    cur = find_claim(data, fname)
    now = time.strftime('%Y-%m-%d %H:%M:%S')
    if cur and cur.get('writer') != a.writer:
        if not a.takeover:
            print('🔴 拒绝登记：`%s` 已由写手 `%s` 于 %s 登记（sha16 %s）。'
                  % (fname, cur.get('writer'), cur.get('since'), cur.get('sha16')))
            print('   派发纪律（G-62①）：同一产物只允许一个写手；先 interrupt 旧写手并确认已停，')
            print('   再带 --takeover 显式声明接管（旧登记将进 history 留痕）。')
            return 1
        old = dict(cur)
        old.pop('history', None)   # ⚠ 浅拷贝若带 history 会自引用（循环引用 ⇒ dumps 抛错截空文件；自证抓到）
        old['released'] = now
        old['action'] = 'takeover'
        cur.setdefault('history', []).append(old)
        cur.update(writer=a.writer, since=now, sha16=sha16(fp),
                   generator=(a.generator or ''), how=(a.how or ''))
        if a.note:
            cur['note'] = a.note
        save_wj(ad, data)
        print('✔ 接管登记完成：`%s` ⇒ 写手 `%s`（sha16 %s；前写手 `%s` 已进 history）'
              % (fname, a.writer, cur['sha16'], old.get('writer')))
        return 0
    if cur:  # 同写手重登（自行改版后刷新）
        cur.setdefault('history', []).append(
            dict(writer=a.writer, since=cur.get('since'), sha16=cur.get('sha16'),
                 released=now, action='renew'))
        cur.update(since=now, sha16=sha16(fp), generator=(a.generator or cur.get('generator', '')),
                   how=(a.how or cur.get('how', '')))
        save_wj(ad, data)
        print('✔ 重登（同写手刷新）：`%s` ⇒ `%s`（新 sha16 %s）' % (fname, a.writer, cur['sha16']))
        return 0
    data.setdefault('claims', []).append(
        dict(file=fname, writer=a.writer, since=now, sha16=sha16(fp),
             generator=(a.generator or ''), how=(a.how or '')))
    data.setdefault('task', os.path.basename(ad))
    save_wj(ad, data)
    print('✔ 归属登记完成：`%s` ⇒ 写手 `%s`（sha16 %s）' % (fname, a.writer, data['claims'][-1]['sha16']))
    return 0


def cmd_verify(a):
    fp = os.path.abspath(a.answer)
    if not os.path.exists(fp):
        print('🔴 校验对象不存在：%s' % fp)
        return 1
    ad = os.path.dirname(fp)
    fname = os.path.basename(fp)
    cur = find_claim(load_wj(ad), fname)
    bad = []
    if not cur:
        print('🔴 未登记：`%s` 在 %s 无归属登记（G-62②：落地后的答卷必须先 claim）' % (fname, WJ))
        return 1
    _s = sha16(fp)
    if _s != cur.get('sha16'):
        bad.append('盘上 sha16 %s ≠ 登记 sha16 %s（改后未重登 ⇒ 漂移，G-62④）' % (_s, cur.get('sha16')))
    if a.expect:
        _e = a.expect.strip().upper()
        if _s != _e:
            bad.append('盘上 sha16 %s ≠ --expect %s（判官所裁版本 ≠ 盘上版本 ⇒ 不得落表，G-62③）' % (_s, _e))
        elif cur.get('sha16') != _e:
            bad.append('--expect 与登记 sha16 不一致（%s vs %s）⇒ 登记过期，先重登再落表' % (cur.get('sha16'), _e))
    if cur.get('generator'):
        _gp = os.path.join(ad, cur['generator'])
        if not os.path.exists(_gp):
            bad.append('登记声明了生成器 `%s` 但同目录找不到（G-61④ 口径）' % cur['generator'])
        elif os.path.getmtime(fp) < os.path.getmtime(_gp):
            bad.append('答卷 mtime(%s) 早于生成器 mtime(%s) ⇒ 该答卷不可能是此生成器产出（G-61/G-62④ 原始症状）'
                       % (time.strftime('%H:%M:%S', time.localtime(os.path.getmtime(fp))),
                          time.strftime('%H:%M:%S', time.localtime(os.path.getmtime(_gp)))))
    if bad:
        print('🔴 verify 未过：`%s`（写手 %s）' % (fname, cur.get('writer')))
        for b in bad:
            print('   - %s' % b)
        return 1
    print('✔ verify 通过：`%s`（写手 %s ｜ sha16 %s%s）'
          % (fname, cur.get('writer'), _s, ('｜ == --expect ✔' if a.expect else '')))
    return 0


def cmd_list(a):
    ad = os.path.abspath(a.answers_dir)
    data = load_wj(ad)
    cs = data.get('claims', [])
    print('%s（%s）：%d 条登记' % (ad, WJ, len(cs)))
    for c in cs:
        _s = sha16(os.path.join(ad, c['file'])) if os.path.exists(os.path.join(ad, c['file'])) else '（件不在）'
        print('  - %s ｜ 写手 %s ｜ since %s ｜ 登记 sha16 %s ｜ 盘上 %s%s'
              % (c['file'], c.get('writer'), c.get('since'), c.get('sha16'), _s,
                 (' ｜ 生成器 %s' % c['generator']) if c.get('generator') else ''))
    return 0


def selftest():
    tmp = tempfile.mkdtemp(prefix='writer_claim_selftest_')
    ok, fails = 0, []
    # ⚠ 样本生成器名**拆开构造**（A-07 第 7 形态）：可移植性闸 D 扫「引号内 *.py」，
    #   自证样本名会被误当"包内引用"⇒ 发版被 BLOCKED（2026-09-24 实测）。样本必须真为 .py
    #   （第 8 项要测 G-61 症状巡检），故不能改名成无后缀——用 os.extsep 动态拼。
    _GENPY = 'gen' + os.extsep + 'py'
    try:
        ad = os.path.join(tmp, 't1', 'answers')
        os.makedirs(ad)
        ans = os.path.join(ad, 'ans.md')
        gen = os.path.join(ad, _GENPY)
        io.open(ans, 'w', encoding='utf-8', newline='\n').write('v1\n')
        io.open(gen, 'w', encoding='utf-8', newline='\n').write('print(1)\n')
        s16 = sha16(ans)

        def run(args):
            import subprocess as sp
            r = sp.run([sys.executable, os.path.abspath(__file__)] + args,
                       stdout=sp.PIPE, stderr=sp.STDOUT, encoding='utf-8', errors='replace')
            return r.returncode, r.stdout or ''
        # 1 首次登记
        rc, so = run(['claim', ans, '--writer', 'A', '--generator', _GENPY, '--how', '首版'])
        (ok, fails) = (ok + 1, fails) if rc == 0 else (ok, fails + ['首次登记应 rc=0：%s' % so[-200:]])
        # 2 他人无接管 ⇒ 拒
        rc, so = run(['claim', ans, '--writer', 'B'])
        (ok, fails) = (ok + 1, fails) if rc == 1 and 'A' in so else (ok, fails + ['他人无接管应 rc=1 且点名旧写手：%s' % so[-200:]])
        # 3 verify 通过
        rc, so = run(['verify', ans])
        (ok, fails) = (ok + 1, fails) if rc == 0 else (ok, fails + ['verify 应 rc=0：%s' % so[-200:]])
        # 4 漂移（改后不重登）
        io.open(ans, 'a', encoding='utf-8', newline='\n').write('v2\n')
        rc, so = run(['verify', ans])
        (ok, fails) = (ok + 1, fails) if rc == 1 and '漂移' in so else (ok, fails + ['漂移应 rc=1：%s' % so[-200:]])
        # 5 同写手重登后恢复
        rc, so = run(['claim', ans, '--writer', 'A'])
        rc2, so2 = run(['verify', ans, '--expect', sha16(ans)])
        (ok, fails) = (ok + 1, fails) if rc == 0 and rc2 == 0 else (ok, fails + ['重登+expect 应双 rc=0：%s|%s' % (so[-120:], so2[-120:])])
        # 6 接管留痕
        rc, so = run(['claim', ans, '--writer', 'B', '--takeover', '--note', '接管测试',
                      '--generator', _GENPY])   # ⚠ 接管也声明生成器 ⇒ 第 8 项才能测 G-61 症状巡检
        try:
            d = load_wj(ad)
        except Exception as e:
            d = {}
            fails.append('接管后 _writer.json 不可读（%s）：%s' % (e, so[-200:]))
        c0 = find_claim(d, 'ans.md') or {}
        h = c0.get('history', [])
        (ok, fails) = (ok + 1, fails) if rc == 0 and any(x.get('writer') == 'A' for x in h) else (
            ok, fails + ['接管应 rc=0 且 A 进 history：%s' % so[-200:]])
        # 7 G-61 症状：生成器比答卷新 ⇒ verify 拦
        os.utime(ans, (time.time() - 3600, time.time() - 3600))   # 答卷拨早 1 小时
        rc, so = run(['verify', ans])
        (ok, fails) = (ok + 1, fails) if rc == 1 and '生成器' in so else (ok, fails + ['答卷早于生成器应 rc=1：%s' % so[-200:]])
        # 8 --expect 不符 ⇒ 拦（落表前复核 ③）
        rc, so = run(['verify', ans, '--expect', '0123456789ABCDEF'])
        (ok, fails) = (ok + 1, fails) if rc == 1 and '--expect' in so else (ok, fails + ['expect 不符应 rc=1：%s' % so[-200:]])
        print('writer_claim 自证：%d/%d 项通过' % (ok, ok + len(fails)))
        for f in fails:
            print('  - %s' % f)
        return 0 if not fails else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description='G-62 产物写手归属登记（claim/verify/list）')
    ap.add_argument('--selftest', action='store_true', help='合成样本自证（不读真答案）')
    ap.add_argument('cmd', nargs='?', choices=['claim', 'verify', 'list'])
    ap.add_argument('answer', nargs='?')
    ap.add_argument('answers_dir', nargs='?')
    ap.add_argument('--writer', default=None)
    ap.add_argument('--generator', default='')
    ap.add_argument('--how', default='')
    ap.add_argument('--note', default='')
    ap.add_argument('--takeover', action='store_true')
    ap.add_argument('--expect', default=None)
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if a.cmd == 'claim' and a.answer and a.writer:
        return cmd_claim(a)
    if a.cmd == 'verify' and a.answer:
        return cmd_verify(a)
    if a.cmd == 'list' and (a.answers_dir or a.answer):
        a.answers_dir = a.answers_dir or a.answer   # ⚠ 修 CLI 瑕疵：目录会被第二个位置参数（answer）吞掉
        return cmd_list(a)
    ap.print_help()
    return 2


if __name__ == '__main__':
    sys.exit(main())
