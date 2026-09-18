# -*- coding: utf-8 -*-
"""check_desc_placeholders.py —— A-21 闸（只读）：扫描技能 desc 内的尖括号占位符

模式：<[a-zA-Z][a-zA-Z0-9\\-_]{0,13}>（字母开头，排除 PE<10 这类数值比较）。
历史：A-21 检测器首跑抓到 dev-<年龄>（批13 修）与 dev-<年龄段>（W2/批14 修）；2026-09-13 起升格为 rc=0 闸。
用法：python check_desc_placeholders.py <skillsRoot> [<skillsRoot> …]
退出码：0＝全部干净；1＝发现占位符；2＝用法错误。
"""
import io, os, re, sys

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass
if os.environ.get('PYTHONIOENCODING', '').lower() != 'utf-8':
    os.environ['PYTHONIOENCODING'] = 'utf-8'

PAT = re.compile(r'<[a-zA-Z][a-zA-Z0-9\-_]{0,13}>')
DESC = re.compile(r'(?m)^description:[ \t]*(.+?)[ \t]*$')

def desc_value(line):
    v = line.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
        return v[1:-1]
    return v

def main():
    roots = [a for a in sys.argv[1:] if not a.startswith('-')]
    if not roots:
        print('用法：python check_desc_placeholders.py <skillsRoot> [...]'); return 2
    hits = []
    scanned = 0
    for root in roots:
        for slug in sorted(os.listdir(root)):
            p = os.path.join(root, slug, 'SKILL.md')
            if not os.path.isfile(p):
                continue
            scanned += 1
            t = io.open(p, encoding='utf-8').read()
            m = DESC.search(t)
            if not m:
                continue
            for hm in PAT.finditer(desc_value(m.group(1))):
                hits.append('%s: %s' % (slug, hm.group(0)))
    if hits:
        print('✗ A-21 占位符 %d 处：' % len(hits))
        for h in hits:
            print('   ' + h)
        return 1
    print('✔ A-21 占位符扫描：%d 件 desc 全部干净（0 处尖括号占位符）' % scanned)
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
