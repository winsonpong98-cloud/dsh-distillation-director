# -*- coding: utf-8 -*-
"""ocr_pages.py —— 扫描版 PDF 的 OCR（PaddleOCR-VL）+ **自带成本计量**

为什么要有它：OCR 走硅基流动 API（不经 DSH），**不会进 DSH 的 usage-ledger**，
若用旧脚本（裸调用不记 usage），OCR 成本就"蒸发"了 → 实测成本会偏低。
本脚本把每页 API 返回的 usage 逐条落盘，使 OCR 成本可核算。

用法：
  python tools\ocr_pages.py --pdf "<PDF路径>" --task <slug> [--pages 1-425] [--dpi 150] [--workers 6]

产出（都在 .work/<slug>/ 下）：
  ocr.txt           逐页转写文本（===== [PAGE n] ===== 分隔）
  ocr_usage.jsonl   每页 usage（prompt_tokens / completion_tokens / 耗时）
  ocr_progress.txt  已完成页（断点续跑）
  ocr_cost.json     汇总（总 token、页数、失败数）

成本换算：拿到 ocr_cost.json 的总 token 后，按硅基流动 PaddleOCR-VL 当前单价换算
（本机查不到硅基流动余额——其余额接口已 410，需到控制台核对单价）。
"""
import base64, json, re, os, sys, time, threading, argparse
import concurrent.futures as cf
import urllib.request
try:
    import fitz  # pymupdf
except ModuleNotFoundError:
    import sys as _s
    _s.stderr.write("\n[X] 缺第三方依赖 PyMuPDF（import fitz）——本工具无法运行。\n"
                   "    请先安装：pip install pymupdf（或 python -m pip install PyMuPDF）\n"
                   "    说明：本件负责 PDF 文本/版面提取，属可选能力；不装它不影响其它门禁。\n"
                   "    退出码 2 表示『依赖缺失（指引式失败）』，不是代码错误。\n")
    _s.exit(2)

sys.stdout.reconfigure(encoding="utf-8")

# ⚠ 2026-09-21（异机可用性）：此处原写死作者机凭据路径与工作区路径 ⇒ 别人电脑上必挂、发版闸 A 判据判红。
#   现：凭据走 `_creds.get_key`（先环境变量 SILICONFLOW_API_KEY，再按可移植规则找 yaml）；
#       工作区根走 `_paths.ROOT`（唯一来源）。
import os as _dsp_os, sys as _dsp_sys
_dsp_sys.path.insert(0, _dsp_os.path.dirname(_dsp_os.path.abspath(__file__)))
from _paths import ROOT as _WS_ROOT      # noqa: E402
from _creds import get_key               # noqa: E402

MODEL = "PaddlePaddle/PaddleOCR-VL-1.5"
UALEDGER_DSH = "DEDICATED_TO_SILICONFLOW"  # 说明：此账不进 DSH 台账


def read_key():
    return get_key("SILICONFLOW_API_KEY")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--task", required=True, help="任务 slug，产物落 .work/<slug>/")
    ap.add_argument("--pages", default="", help="如 1-425 或 1,3,5-10；默认全书")
    ap.add_argument("--dpi", type=int, default=150)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--bookname", default="", help="给模型的上下文提示（书名）")
    a = ap.parse_args()

    KEY = read_key()
    WS = _WS_ROOT
    WORK = os.path.join(WS, ".work", a.task)
    PAGES = os.path.join(WORK, "pages")
    os.makedirs(PAGES, exist_ok=True)
    out_txt = os.path.join(WORK, "ocr.txt")
    usage_jsonl = os.path.join(WORK, "ocr_usage.jsonl")
    progress = os.path.join(WORK, "ocr_progress.txt")
    cost_json = os.path.join(WORK, "ocr_cost.json")

    doc = fitz.open(a.pdf)
    n = doc.page_count
    # 解析页码范围
    if a.pages:
        wanted = []
        for part in a.pages.split(","):
            if "-" in part:
                s, e = part.split("-")
                wanted += list(range(int(s), int(e) + 1))
            else:
                wanted.append(int(part))
        wanted = [p for p in wanted if 1 <= p <= n]
    else:
        wanted = list(range(1, n + 1))

    print(f"📖 书页数={n}  本次处理={len(wanted)} 页  dpi={a.dpi}  并发={a.workers}")

    # 渲染（跳过已存在）
    todo_render = [p for p in wanted if not os.path.exists(os.path.join(PAGES, f"p{p:04d}.png"))]
    if todo_render:
        print(f"🖼  渲染 {len(todo_render)} 页…")
        for p in todo_render:
            pg = doc[p - 1]
            pix = pg.get_pixmap(dpi=a.dpi)
            pix.save(os.path.join(PAGES, f"p{p:04d}.png"))
    doc.close()

    book = a.bookname or os.path.basename(a.pdf)
    prompt = (
        f"这是中文书《{book}》的一页扫描件。请逐字转写这一页的全部文字："
        "1) 标题（章/节/小节）原样保留；2) 正文全部照抄，不翻译不总结；"
        "3) 表格按行列出，保留表头与全部数据，数字务必精确；"
        "4) 图注与注释原样；5) 页眉页脚跳过；6) 看不清的字用【?】标注。"
    )

    done = set()
    if os.path.exists(progress):
        done = set(open(progress, encoding="utf-8").read().split())
    lock = threading.Lock()
    fout = open(out_txt, "a", encoding="utf-8")
    fprog = open(progress, "a", encoding="utf-8")
    fuse = open(usage_jsonl, "a", encoding="utf-8")
    stat = {"ok": 0, "fail": 0, "pt": 0, "ct": 0}

    def ocr_page(p):
        key = str(p)
        if key in done:
            return
        img = os.path.join(PAGES, f"p{p:04d}.png")
        if not os.path.exists(img):
            return
        b64 = base64.b64encode(open(img, "rb").read()).decode()
        body = {"model": MODEL, "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": "data:image/png;base64," + b64}},
            {"type": "text", "text": prompt}]}], "max_tokens": 4000}
        t0 = time.time()
        text, usage = None, {}
        for _ in range(3):
            try:
                req = urllib.request.Request(
                    "https://api.siliconflow.cn/v1/chat/completions",
                    data=json.dumps(body).encode(),
                    headers={"Content-Type": "application/json", "Authorization": "Bearer " + KEY})
                with urllib.request.urlopen(req, timeout=300) as resp:
                    data = json.loads(resp.read().decode())
                text = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {}) or {}
                break
            except Exception as e:
                print("  retry", p, str(e)[:70], flush=True)
                time.sleep(4)
        dt = time.time() - t0
        with lock:
            if text is None:
                stat["fail"] += 1
                text = "【ERROR】OCR失败"
            else:
                stat["ok"] += 1
                stat["pt"] += usage.get("prompt_tokens", 0)
                stat["ct"] += usage.get("completion_tokens", 0)
            fout.write(f"===== [PAGE {p}] =====\n{text}\n")
            fout.flush()
            fprog.write(key + "\n")
            fprog.flush()
            fuse.write(json.dumps({"page": p, "prompt_tokens": usage.get("prompt_tokens", 0),
                                   "completion_tokens": usage.get("completion_tokens", 0),
                                   "seconds": round(dt, 2),
                                   "ok": text != "【ERROR】OCR失败"}, ensure_ascii=False) + "\n")
            fuse.flush()
            if stat["ok"] % 10 == 0:
                print(f"  进度 {stat['ok'] + stat['fail']}/{len(wanted)}  累计 "
                      f"prompt={stat['pt']} completion={stat['ct']}", flush=True)

    with cf.ThreadPoolExecutor(max_workers=a.workers) as ex:
        list(ex.map(ocr_page, wanted))

    fout.close(); fprog.close(); fuse.close()

    # 汇总（含已有 jsonl 的历史记录，支持续跑）
    tot_pt = tot_ct = cnt = fail = 0
    if os.path.exists(usage_jsonl):
        for line in open(usage_jsonl, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            cnt += 1
            tot_pt += r.get("prompt_tokens", 0)
            tot_ct += r.get("completion_tokens", 0)
            if not r.get("ok"):
                fail += 1
    summary = {"task": a.task, "model": MODEL, "pages_ocr": cnt, "failed": fail,
               "prompt_tokens": tot_pt, "completion_tokens": tot_ct,
               "total_tokens": tot_pt + tot_ct,
               "note": "本账走硅基流动（不经 DSH），成本需按硅基流动单价换算；"
                       "DSH 台账里的成本不含本项"}
    json.dump(summary, open(cost_json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n✅ OCR 完成")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    print(f"\n📄 文本：{out_txt}\n💰 用量：{usage_jsonl}\n📊 汇总：{cost_json}")


if __name__ == "__main__":
    main()
