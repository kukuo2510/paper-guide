"""圖表（含演算法框）的偵測。"""
import re

from .text_rules import classify

CAPTION = re.compile(r'^(Fig\.|Figure|FIG\.|TABLE|Table)$')
CAP_NO = re.compile(r'^([0-9]+|[IVX]+)[:.]?$')


def is_caption(m, bs):
    """圖表說明行：「Fig. / TABLE」開頭，且字級比內文小，或後面接「編號:」。"""
    ws = sorted(m.words, key=lambda w: w.x0)
    if not CAPTION.match(ws[0].text):
        return False
    return m.size < bs - 0.5 or (len(ws) > 1 and CAP_NO.match(ws[1].text) and ws[1].text[-1:] in ':.')


def find_floats(page, lines, bs, cols):
    """找圖表：回傳 [(kind, col, lines, graphics_bbox)]，被吃掉的行從 lines 移除。"""
    floats = []
    taken = set()
    small = lambda l: l.size < bs - 0.5

    # 演算法框：「Algorithm N」開頭、上方 15pt 內有水平線；範圍到標題下方第二條水平線
    for l in lines:
        ws = l.words
        if id(l) in taken or len(ws) < 2 or ws[0].text != 'Algorithm' or not ws[1].text.rstrip(':.').isdigit():
            continue
        cx0, cx1 = cols[l.col]
        rs = sorted(r[1] for r in page.rules if r[0] < cx0 + 10 and r[2] > cx1 - 10)
        above = [y for y in rs if l.y0 - 15 <= y <= l.y0]
        below = [y for y in rs if y > l.y1]
        if not above or len(below) < 2:
            continue
        top, bottom = above[-1], below[1]
        group = [m for m in lines if m.col == l.col and top - 1 <= m.y0 and m.y1 <= bottom + 1 and id(m) not in taken]
        for m in group:
            taken.add(id(m))
        floats.append(('algorithm', l.col, group, [cx0, top, cx1, bottom]))
    for i, l in enumerate(lines):
        if id(l) in taken or not is_caption(l, bs):
            continue
        kind = 'table' if l.words[0].text.upper().startswith('TABLE') else 'figure'
        col = l.col
        same = sorted([m for m in lines if (m.col == col or col == 'F' or m.col == 'F') and id(m) not in taken], key=lambda m: m.y0)
        idx = same.index(l)
        cap = [l]
        # 說明文字往下延伸：同為小字、行距小
        j = idx + 1
        while (j < len(same) and same[j].y0 - cap[-1].y1 < 4 and not is_caption(same[j], bs)
               and (small(same[j]) or (not small(l) and abs(same[j].size - l.size) < 0.6 and classify(same[j], bs, cols) == 'text'))):
            cap.append(same[j]); j += 1
        cx0, cx1 = (cols[col] if col != 'F' else cols['F'])
        if kind == 'figure':
            # 往上找到前一個內文行為止
            top = 0
            for m in reversed(same[:idx]):
                if not small(m) and classify(m, bs, cols) == 'text' and len(m.words) > 4 and m.x1 - m.x0 > 0.6 * (cx1 - cx0):
                    top = m.y1; break
            gs = [g for g in page.graphics if g[1] >= top - 2 and g[3] <= l.y0 + 2 and g[0] < cx1 and g[2] > cx0]
            if not gs:
                continue
            gy0 = min(g[1] for g in gs)
            body = [m for m in same[:idx] if m.y0 >= gy0 - 2]
            if any(g[0] < cols.get('L', cols['F'])[1] - 10 for g in gs) and any(g[2] > cols.get('R', cols['F'])[0] + 10 for g in gs):
                col = 'F'
        else:
            # 表：說明在上，往下吃到下一個內文大小的寬行為止
            # 先找說明正下方 40pt 內開始的圖形（表格框線），表格範圍到圖形底部
            capy = cap[-1].y1
            gs = [g for g in page.graphics if capy - 2 <= g[1] <= capy + 40 and g[0] < cx1 and g[2] > cx0]
            if gs:
                bottom = max(g[3] for g in gs) + 3
                body = [m for m in same[j:] if m.y0 >= capy - 1 and m.y1 <= bottom + 6 and not CAPTION.match(m.words[0].text)]
            else:
                body = []
                k = j
                while k < len(same):
                    m = same[k]
                    if not small(m) and len(m.words) > 6 and classify(m, bs, cols) == 'text':
                        break
                    if CAPTION.match(m.words[0].text) and small(m):
                        break
                    body.append(m); k += 1
        group = body + cap
        for m in group:
            taken.add(id(m))
        gb = None
        if gs:
            gb = [min(g[0] for g in gs), min(g[1] for g in gs), max(g[2] for g in gs), max(g[3] for g in gs)]
        floats.append((kind, col, group, gb))
    rest = [l for l in lines if id(l) not in taken]
    return floats, rest
