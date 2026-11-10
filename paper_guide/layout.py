"""版面：欄位偵測、字排成行、上下標與首字放大的處理。"""
from .model import Line
from .text_rules import normal_ratio


def _rows(words):
    """把字依基線排成行：先用最大字級的字建立各行基線，其他字基線差 < 0.25 字級才併入。
    上下標基線不同，會自成一列，之後由 _attach_scripts 併回最近的行。"""
    rows = []  # [base, size, words]
    for w in sorted(words, key=lambda w: (-w.size, w.base, w.x0)):
        for r in rows:
            if abs(r[0] - w.base) < 0.25 * r[1] and w.size >= r[1] - 0.6:
                r[2].append(w)
                break
        else:
            rows.append([w.base, w.size, [w]])
    return [sorted(r[2], key=lambda w: w.x0) for r in sorted(rows, key=lambda r: r[0])]


def columns(pages, bs):
    """回傳 {'L': (x0, x1), 'R': (x0, x1), 'F': (x0, x1)}；單欄論文只有 F。"""
    body = [w for p in pages for w in p.words if abs(w.size - bs) < 0.6]
    W = pages[0].width
    mid = W / 2
    crossing = sum(1 for w in body if w.x0 < mid - 2 and w.x1 > mid + 2)
    xs0 = sorted(w.x0 for w in body); xs1 = sorted(w.x1 for w in body)
    left, right = xs0[len(xs0) // 100], xs1[-len(xs1) // 100]
    if crossing > 0.02 * len(body):
        return {'F': (left, right)}, None
    lw = [w.x1 for w in body if w.xc < mid]; rw = [w.x0 for w in body if w.xc >= mid]
    lr = sorted(lw)[-len(lw) // 50]; rl = sorted(rw)[len(rw) // 50]
    gutter = (lr + rl) / 2
    return {'L': (left, lr), 'R': (rl, right), 'F': (left, right)}, gutter


def _attach_scripts(rows, bs):
    """全部是小字、字數少的列（上下標）併到上下 5pt 內、水平有重疊的內文列。"""
    big = [r for r in rows if max(w.size for w in r) >= bs - 0.5]
    out = [r for r in big]
    for r in rows:
        if any(r is b for b in big):
            continue
        y0, y1 = min(w.y0 for w in r), max(w.y1 for w in r)
        x0, x1 = min(w.x0 for w in r), max(w.x1 for w in r)
        best = None
        if len(r) <= 8:
            for b in big:
                by0, by1 = min(w.y0 for w in b), max(w.y1 for w in b)
                bx0, bx1 = min(w.x0 for w in b), max(w.x1 for w in b)
                d = max(by0 - y1, y0 - by1, 0)
                if d < 5 and x0 < bx1 + 15 and x1 > bx0 - 15 and (best is None or d < best[0]):
                    best = (d, b)
        if best:
            best[1].extend(r)
        else:
            out.append(r)
    return [sorted(r, key=lambda w: w.x0) for r in sorted(out, key=lambda r: min(w.y0 for w in r))]


def _drop_caps(rows, bs):
    out = [r for r in rows]
    for r in rows:
        if len(r) == 1 and r[0].size > 1.8 * bs and len(r[0].text) <= 2:
            w = r[0]
            tgt = [o for o in out if o is not r and o[0].x0 > w.x0 and abs(min(x.y0 for x in o) - w.y0) < bs]
            if tgt:
                tgt[0].insert(0, w); out.remove(r)
    return out


def build_lines(page, cols, gutter, bs):
    if gutter is None:
        return [Line(r, 'F') for r in _attach_scripts(_rows(page.words), bs)]
    L = [w for w in page.words if w.xc < gutter]
    R = [w for w in page.words if w.xc >= gutter]
    lines = [Line(r, 'L') for r in _drop_caps(_attach_scripts(_rows(L), bs), bs)] + [Line(r, 'R') for r in _drop_caps(_attach_scripts(_rows(R), bs), bs)]
    # 左右兩行垂直重疊、中間空隙小於 6pt → 跨欄行（標題、作者、跨欄圖說）
    ls = [l for l in lines if l.col == 'L']; rs = [l for l in lines if l.col == 'R']
    used = set()
    out = []
    for l in ls:
        hit = None
        for r in rs:
            if id(r) in used: continue
            ov = min(l.y1, r.y1) - max(l.y0, r.y0)
            near = 0 <= r.x0 - l.x1 < max(6, 0.6 * min(l.edge_size('right'), r.edge_size('left')))
            # 置中的跨欄行（作者列中間夾著 ORCID 圖示）：左段不靠左緣、右段不靠右緣、間隙 < 25pt
            centered = (0 <= r.x0 - l.x1 < 25 and l.x0 > cols['L'][0] + 20 and r.x1 < cols['R'][1] - 20
                        and abs((l.x0 + r.x1) / 2 - (cols['L'][0] + cols['R'][1]) / 2) < 5 and normal_ratio(l.words + r.words) > 0.5)
            if ov > 0.5 * min(l.y1 - l.y0, r.y1 - r.y0) and (near or centered):
                hit = r; break
        if hit:
            used.add(id(hit)); out.append(Line(l.words + hit.words, 'F'))
        else:
            out.append(l)
    out += [r for r in rs if id(r) not in used]
    return out
