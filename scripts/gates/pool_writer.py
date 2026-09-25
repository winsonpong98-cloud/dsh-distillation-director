# -*- coding: utf-8 -*-
r"""pool_writer.py —— 池写入的唯一受控入口（判官办法3 的"可追溯"实现）。
  设计取舍：文件型池无法"禁止"别的脚本直写 ⇒ 改为**见证制**——凡机选来源条目必须经本入口写入，
  本入口：①调白名单判据（不过则拒写并记录）②要求分类 ∈ 枚举 ③写见证行 pool-audit.jsonl。
  闸侧对"机选来源但无见证"的条目判红 ⇒ 绕过由"不可能"变为"必被发现"。"""
import io
import json
import os
import re
import time

ENUM = ('表格图表数据', '数值包络', '总纲', '阈值')
_REJ = re.compile(r'(?:如|见|参|下|上)?[图表]\s*\d|所示|走势图|可知|见图|见表|如下图|如上表|[图表]\d+-\d+')
_END = '。！？…」”"'
_MARKUP = re.compile(r'\||\*|http|Chart|Fig|Center|Source|Table|Data|Figure')


def anchor_ok(s):
    r = []
    t = (s or '').strip()
    if len(t) < 20:
        r.append('长度<20')
    if t and t[-1] not in _END:
        r.append('非句末收尾（疑截断）')
    if _REJ.search(t):
        r.append('指代装置')
    if _MARKUP.search(t):
        r.append('markup/竖线')
    return (not r), r


def audit_path(task_dir):
    return os.path.join(task_dir, 'pool-audit.jsonl')


def append_entry(task_dir, aid, anchor, quote, paraphrase, classification, origin='机选'):
    """受控写入一条池条目；返回 (ok, msg)。"""
    ok, why = anchor_ok(quote)
    cls = classification.split('：')[0].split(':')[0].strip()
    if not ok:
        _log(task_dir, dict(aid=aid, verdict='REJECT', reasons=why, origin=origin, quote=quote[:60]))
        return False, '白名单未过：%s' % '/'.join(why)
    if cls not in ENUM:
        _log(task_dir, dict(aid=aid, verdict='REJECT', reasons=['分类不在枚举'], origin=origin, quote=quote[:60]))
        return False, '分类不在枚举 %s' % (ENUM,)
    vp = os.path.join(task_dir, 'verified.md')
    t = io.open(vp, encoding='utf-8').read()
    if '### %s ' % aid in t:
        return False, 'id 已存在：%s' % aid
    t = t.rstrip('\n') + '\n\n### %s [PR] [技能=真探针发现轮]\n- 锚：%s\n- 原文：「%s」\n- 转述：**%s**\n- 备注：真探针发现轮补选（%s）（未选：%s——白名单判据通过；判官签章后转 R 或撤）\n' % (
        aid, anchor, quote, paraphrase, time.strftime('%Y-%m-%d'), cls)
    io.open(vp, 'w', encoding='utf-8', newline='\n').write(t)
    _log(task_dir, dict(aid=aid, verdict='ADMIT', classification=cls, origin=origin, quote=quote[:60]))
    return True, '已写入并见证'


def _log(task_dir, rec):
    rec['ts'] = time.strftime('%Y-%m-%d %H:%M:%S')
    with io.open(audit_path(task_dir), 'a', encoding='utf-8', newline='\n') as f:
        f.write(json.dumps(rec, ensure_ascii=False) + '\n')


def witnessed(task_dir):
    p = audit_path(task_dir)
    out = set()
    if os.path.isfile(p):
        for line in io.open(p, encoding='utf-8'):
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get('verdict') == 'ADMIT':
                out.add(r.get('aid'))
    return out
