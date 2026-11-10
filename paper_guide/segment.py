"""把每頁的字切成「導讀單位」：段落、公式、圖、表、標題＋段落。

流程：
1. 去掉每頁重複的頁首頁尾
2. 判斷雙欄，把字分到左欄 / 右欄，再排成一行一行（左右兩行靠很近就合成跨欄行）
3. 找圖表說明（Fig. / TABLE 開頭、字級比內文小），往上（圖）或往下（表）圈出整個圖表
4. 剩下的行分類成 標題 / 公式 / 內文，依縮排、行距、公式切成單位
5. 同一頁左欄底部接右欄頂端的段落合成同一單位；跨頁的標記 cont
"""
import re

from .extract import Word, body_size
from .floats import CAP_NO, CAPTION, find_floats, is_caption  # noqa: F401
from .furniture import _norm, strip_furniture  # noqa: F401
from .layout import _attach_scripts, _drop_caps, _rows, build_lines, columns  # noqa: F401
from .model import BULLETS, COL_ORDER, Line, Unit  # noqa: F401
from .text_rules import EQ_NO, HEADING, NUM_HEAD, WORDLIKE, classify, is_heading, normal_ratio  # noqa: F401

SENT_END = re.compile(r'[.:;?!]["”)\]]?$')


def segment(pages):
    bs = body_size(pages)
    strip_furniture(pages)
    cols, gutter = columns(pages, bs)
    units = []
    for page in pages:
        lines = build_lines(page, cols, gutter, bs)
        floats, lines = find_floats(page, lines, bs, cols)
        page_units = []
        for kind, col, group, gb in floats:
            ws = [w for m in group for w in m.words]
            if gb:  # 用不可見的「字」把圖形範圍帶進方框
                ws = ws + [Word(gb[0], gb[1], gb[2], gb[3], '', 0)]
            page_units.append(Unit(page.no, kind, [(col, ws)]))
        # 跨欄行（標題）先放，再左欄、右欄；同欄依 y
        lines.sort(key=lambda l: (COL_ORDER[l.col] if l.col != 'F' else 0, l.y0) if gutter else l.y0)
        # 跨欄行如果在頁面中間，依 y 排在左欄前面即可（雙欄論文少見）
        lead = _leading(lines, bs)
        kinds = ['text' if is_heading(l, bs, cols) else classify(l, bs, cols) for l in lines]
        # 置中的短行如果緊鄰公式行，也算公式（例如 min C = ∑ 這種有幾個英文字的行）
        for i, l in enumerate(lines):
            if kinds[i] == 'text' and len(l.words) <= 8 and l.x0 > cols[l.col][0] + 15:
                nb = [j for j in (i - 1, i + 1) if 0 <= j < len(lines) and lines[j].col == l.col]
                if any(kinds[j] == 'math' and (lines[j].y0 - l.y1 < 6 and l.y0 - lines[j].y1 < 6) for j in nb):
                    kinds[i] = 'math'
        cur, prev, glue = None, None, False
        for l, kind in zip(lines, kinds):
            head = kind == 'text' and is_heading(l, bs, cols)
            new = False
            if cur is None or l.col != prev.col:
                new = True
            else:
                gap = l.y0 - prev.y1
                # 置中的行（標題、作者）不看縮排
                centered = l.x0 > cols[l.col][0] + 20 and l.x1 < cols[l.col][1] - 20 and prev.x0 > cols[l.col][0] + 5
                indent = l.x0 - cols[l.col][0] > 5 and kind == 'text' and not centered
                rel_indent = kind == 'text' and l.tx0 - prev.tx0 > 5 and not centered
                if head or (kind == 'text' and l.bullet):
                    new = True
                elif glue:
                    new = False
                elif kind == 'text' and rel_indent and prev.kind != 'math':
                    new = True
                elif (kind == 'text' and prev.kind == 'text' and prev.x1 < cols[prev.col][1] - 20 and not centered
                      and SENT_END.search(prev.text) and l.words[0].text[:1].isupper()):
                    new = True  # 上一行沒寫滿且句子結束 → 段落結束
                elif kind == 'text' and indent and prev.kind == 'math' and (l.words[0].text[:1].isupper() or l.words[0].text[:1].isdigit()):
                    new = True
                elif gap > lead + 0.35 * bs and not (kind == 'math' or prev.kind == 'math'):
                    new = True
                elif abs(l.size - prev.size) > 1.5 and kind == 'text' and prev.kind == 'text':
                    new = True
            l.kind = kind
            if new:
                cur = Unit(page.no, 'heading' if head else kind, [(l.col, [])])
                page_units.append(cur)
                glue = head
            elif glue and not head:
                glue = False
                cur.kind = 'text'
            if kind == 'math' and cur.kind == 'text' and not cur.words():
                cur.kind = 'math'
            cur.parts[-1][1].extend(l.words)
            prev = l
        # 同頁跨欄接續：右欄第一個內文單位如果第一行沒縮排、不是標題 → 併到左欄最後一個內文單位
        if gutter:
            lt = [u for u in page_units if u.parts[0][0] == 'L' and u.kind in ('text', 'math')]
            rt = [u for u in page_units if u.parts[0][0] == 'R' and u.kind in ('text', 'math')]
            if lt and rt:
                a = max(lt, key=lambda u: max(w.y1 for w in u.words()))
                b = min(rt, key=lambda u: min(w.y0 for w in u.words()))
                fw = min(b.words(), key=lambda w: (round(w.y0), w.x0))
                last = max(a.words(), key=lambda w: (round(w.y1), w.x1))
                if fw.x0 - cols['R'][0] <= 5 and not SENT_END.search(last.text):
                    a.parts.append(b.parts[0]); page_units.remove(b)
        # 排序：依第一個框的欄位、y
        def key(u):
            col, ws = u.parts[0]
            return (COL_ORDER[col] if gutter else 0, min(w.y0 for w in ws))
        page_units.sort(key=key)
        units.extend(page_units)
    # 跨頁接續標記
    for a, b in zip(units, units[1:]):
        if b.page == a.page + 1 and b.kind == 'text' and a.kind == 'text':
            first = min(b.words(), key=lambda w: (round(w.y0), w.x0))
            col = b.parts[0][0]
            if first.x0 - cols[col][0] <= 5:
                b.cont = True
    return units, cols


def _leading(lines, bs):
    """同欄相鄰兩個內文行之間的正常空白（上一行底到下一行頂）。"""
    d = []
    for col in ('L', 'R', 'F'):
        ls = sorted((l for l in lines if l.col == col and abs(l.size - bs) < 0.6), key=lambda l: l.y0)
        d += [b.y0 - a.y1 for a, b in zip(ls, ls[1:]) if 0 <= b.y0 - a.y1 < bs]
    return sorted(d)[len(d) // 2] if d else bs * 0.3
