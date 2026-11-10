"""頁首頁尾（重複出現在頁面上下緣的行）的移除。"""
import re
from collections import Counter

from .layout import _rows


def _norm(s):
    return re.sub(r'\d+', '#', s.lower()).strip()


def strip_furniture(pages):
    """頁首頁尾：出現在頁面上下 8% 範圍、且（數字換成 #）文字在超過一半頁面重複的行。"""
    bands = []
    for p in pages:
        top = [w for w in p.words if w.y1 < p.height * 0.08]
        bot = [w for w in p.words if w.y0 > p.height * 0.92]
        bands.append((top, bot))
    cnt = Counter()
    for top, bot in bands:
        for ws in (top, bot):
            for ln in _rows(ws):
                cnt[_norm(' '.join(w.text for w in ln))] += 1
    rep = {k for k, v in cnt.items() if v >= max(2, len(pages) // 2)}
    for p, (top, bot) in zip(pages, bands):
        drop = set()
        for ws in (top, bot):
            for ln in _rows(ws):
                if _norm(' '.join(w.text for w in ln)) in rep or (len(ln) == 1 and ln[0].text.isdigit()):
                    drop.update(id(w) for w in ln)
        p.words = [w for w in p.words if id(w) not in drop]
