# -*- coding: utf-8 -*-
"""make_edu_root_stamp.py —— 生成教育线源根版本戳（副本新鲜度闸的基准）

戳文件：家庭教育\\.dsh\\edu-root-version.json（在 skills/ 之外，加载器不扫）
  { stamp_iso, root, count, pieces: { slug: { files: { 相对路径: sha256 } } } }

用法：python tools\\make_edu_root_stamp.py          # 生成/覆盖戳
      python tools\\make_edu_root_stamp.py --print  # 只打印摘要不写
"""
import datetime
import hashlib
import io
import json
import os
import sys

if os.environ.get('PYTHONIOENCODING', '').lower() != 'utf-8':
    os.environ['PYTHONIOENCODING'] = 'utf-8'
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

# ⚠ 2026-09-21（异机可用性）：此处原为作者机绝对路径 ⇒ 换机器必挂、发版闸 A 判据判红。
#   现按"工作区父目录 ＋ 宿主名"推导，并留 `DSH_EDU_SKILLS_ROOT` 出口（换任何宿主名都可用）。
import os as _dsp_os, sys as _dsp_sys
_dsp_sys.path.insert(0, _dsp_os.path.dirname(_dsp_os.path.abspath(__file__)))
from _paths import WS as _WS  # noqa: E402

ROOT = (os.environ.get('DSH_EDU_SKILLS_ROOT')
        or os.path.join(_WS, '家庭教育', '.dsh', 'skills'))
STAMP = (os.environ.get('DSH_EDU_STAMP')
         or os.path.join(os.path.dirname(ROOT), 'edu-root-version.json'))   # 与 skills/ 同级（加载器不扫）


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for c in iter(lambda: f.read(65536), b''):
            h.update(c)
    return h.hexdigest()


def build():
    pieces = {}
    for slug in sorted(os.listdir(ROOT)):
        sdir = os.path.join(ROOT, slug)
        if not os.path.isdir(sdir):
            continue
        files = {}
        for dp, _dns, fns in os.walk(sdir):
            for fn in fns:
                p = os.path.join(dp, fn)
                files[os.path.relpath(p, sdir).replace('\\', '/')] = sha(p)
        pieces[slug] = {'files': files}
    return {
        'stamp_iso': datetime.datetime.now().isoformat(timespec='seconds'),
        'root': ROOT,
        'count': len(pieces),
        'pieces': pieces,
    }


def main():
    data = build()
    summary = {s: len(v['files']) for s, v in data['pieces'].items()}
    if '--print' in sys.argv:
        print(json.dumps({'stamp_iso': data['stamp_iso'], 'count': data['count'], 'files_per_slug': summary},
                         ensure_ascii=False, indent=2))
        return 0
    io.open(STAMP, 'w', encoding='utf-8', newline='').write(json.dumps(data, ensure_ascii=False, indent=1) + '\n')
    print('✔ 版本戳已写：%s（%d 件，%s）' % (STAMP, data['count'], data['stamp_iso']))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as _e:
        sys.stderr.write('\n\U0001F534 本步骤无法执行：%s: %s\n   多半是工作区脚手架/数据文件未就绪。\n'
                         '   请先运行：python tools/init_workspace.py <你的工作区根>\n' % (type(_e).__name__, _e))
        sys.exit(2)
