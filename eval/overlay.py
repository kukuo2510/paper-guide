"""除錯用：把預測框（彩色實線）和標準答案框（灰色虛線）畫在頁面上，輸出 PNG。

用法：python -m eval.overlay data/rl-adapter.pdf eval/rl-adapter.boxes.raw.json out/overlay 2 3
"""
import json
import os
import sys

import pymupdf

from paper_guide.extract import load
from paper_guide.segment import segment

COLORS = {'text': (0, 0.45, 0.4), 'math': (0.75, 0.2, 0), 'figure': (0.2, 0.3, 0.8), 'table': (0.5, 0.1, 0.6), 'heading': (0.8, 0.6, 0), 'algorithm': (0.3, 0.5, 0.1)}


def main(pdf, gt_path, out, pages_wanted):
    os.makedirs(out, exist_ok=True)
    raw = json.load(open(gt_path, encoding='utf8')) if gt_path != '-' else []
    units, cols = segment(load(pdf))
    doc = pymupdf.open(pdf)
    for pn in pages_wanted:
        p = doc[pn - 1]
        if pn - 1 < len(raw):
            for it in raw[pn - 1]:
                for xr, y0, y1 in it['b']:
                    p.draw_rect(pymupdf.Rect(xr[0], y0, xr[1], y1), color=(0.5, 0.5, 0.5), dashes='[3] 0', width=0.8)
        k = 0
        for u in units:
            if u.page != pn - 1:
                continue
            k += 1
            for j, b in enumerate(u.boxes(cols)):
                r = pymupdf.Rect(*b)
                p.draw_rect(r, color=COLORS[u.kind], width=1.2)
                label = f'{k}{"abcd"[j] if len(u.parts) > 1 else ""}{"+" if u.cont else ""}'
                p.insert_text((r.x0 - 9, r.y0 + 7), label, fontsize=7, color=COLORS[u.kind])
        p.get_pixmap(dpi=110).save(f'{out}/ov-{pn:02d}.png')


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], sys.argv[3], [int(x) for x in sys.argv[4:]])
