"""把每頁的字切成「導讀單位」：段落、公式、圖、表、標題＋段落。

流程：
1. 去掉每頁重複的頁首頁尾
2. 判斷雙欄，把字分到左欄 / 右欄，再排成一行一行（左右兩行靠很近就合成跨欄行）
3. 找圖表說明（Fig. / TABLE 開頭、字級比內文小），往上（圖）或往下（表）圈出整個圖表
4. 剩下的行分類成 標題 / 公式 / 內文，依縮排、行距、公式切成單位
5. 同一頁左欄底部接右欄頂端的段落合成同一單位；跨頁的標記 cont
"""
import re
from collections import Counter
from dataclasses import dataclass, field

from .extract import Word, body_size

EQ_NO = re.compile(r'^\(\d+[a-z]?\)$')
CAPTION = re.compile(r'^(Fig\.|Figure|FIG\.|TABLE|Table)$')
CAP_NO = re.compile(r'^([0-9]+|[IVX]+)[:.]?$')
NUM_HEAD = re.compile(r'^(\d+(\.\d+)*\.?|[A-Z]\.?(\d+)*)$')
HEADING = re.compile(r'^([IVX]+\.|[A-H]\.|[1-9]\)|APPENDIX|REFERENCES|Appendix|Abstract|Index|Proof|Theorem|Lemma|Algorithm)')
BULLETS = {'•', '◦', '–', '▪', '∙'}
SENT_END = re.compile(r'[.:;?!]["”)\]]?$')
COL_ORDER = {'F': 0, 'L': 1, 'R': 2}  # 跨欄行先、再左欄、右欄


@dataclass
class Line:
    words: list
    col: str  # 'L' / 'R' / 'F'
    kind: str = 'text'

    @property
    def x0(self): return min(w.x0 for w in self.words)
    @property
    def x1(self): return max(w.x1 for w in self.words)
    @property
    def y0(self): return min(w.y0 for w in self.words)
    @property
    def y1(self): return max(w.y1 for w in self.words)
    @property
    def size(self): return max(w.size for w in self.words)
    @property
    def tx0(self):
        ws = sorted(self.words, key=lambda w: w.x0)
        return ws[1].x0 if len(ws) > 1 and ws[0].text in BULLETS else ws[0].x0
    def edge_size(self, side):
        ws = sorted(self.words, key=lambda w: w.x0)
        return (ws[-1] if side == 'right' else ws[0]).size
    @property
    def bullet(self):
        return min(self.words, key=lambda w: w.x0).text in BULLETS
    @property
    def text(self): return ' '.join(w.text for w in sorted(self.words, key=lambda w: w.x0))


@dataclass
class Unit:
    page: int
    kind: str  # text / math / figure / table / heading
    parts: list = field(default_factory=list)  # [(col, [lines or words])]
    cont: bool = False  # 接續上一頁

    def words(self):
        return [w for _, ws in self.parts for w in ws]

    def boxes(self, cols):
        out = []
        for col, ws in self.parts:
            x0, x1 = cols[col]
            x0 = min(x0, min(w.x0 for w in ws)); x1 = max(x1, max(w.x1 for w in ws))
            out.append([round(x0 - 3, 1), round(min(w.y0 for w in ws) - 2, 1),
                        round(x1 + 3, 1), round(max(w.y1 for w in ws) + 2, 1)])
        return out


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


WORDLIKE = re.compile(r"^([\[(]?[A-Za-z][a-z\-’']{2,}[\])]?[.,;:]?|\[\d+\][,.;]?|\d+(\.\d+)?%?[.,;)]?|[A-Z]{2,}[a-z]?[.,;:)]?)$")


def normal_ratio(ws):
    return sum(1 for w in ws if WORDLIKE.match(w.text)) / len(ws)


def classify(line, bs, cols):
    ws = line.words
    x0, x1 = cols[line.col]
    if EQ_NO.match(ws[-1].text) and ws[-1].x1 > x1 - 25:
        return 'math'
    r = normal_ratio(ws)
    centered = line.x0 > x0 + 15 and line.x1 < x1 - 15
    if r < 0.25 or (centered and r < 0.5):
        return 'math'
    return 'text'


def is_heading(line, bs, cols):
    t = line.text
    ws = sorted(line.words, key=lambda w: w.x0)
    # 「2.3 Transfer Learning」「3 BERT」：編號開頭、粗體或字比內文大、短
    if (len(ws) >= 2 and len(ws) <= 12 and NUM_HEAD.match(ws[0].text) and ws[1].text[:1].isupper()
            and (all(w.bold for w in ws if w.text.isalpha()) or line.size > bs + 0.5)):
        return True
    if len(line.words) > 12 or not HEADING.match(t):
        return False
    if t.startswith(('Abstract', 'Index')):
        return False  # IEEE 摘要、關鍵字是段落開頭，不是獨立標題
    return line.x1 < cols[line.col][1] - 20 or line.text.isupper()


def find_floats(page, lines, bs, cols):
    """找圖表：回傳 [(kind, col, lines, graphics_bbox)]，被吃掉的行從 lines 移除。"""
    floats = []
    taken = set()
    small = lambda l: l.size < bs - 0.5

    def is_caption(m):
        ws = sorted(m.words, key=lambda w: w.x0)
        if not CAPTION.match(ws[0].text):
            return False
        return small(m) or (len(ws) > 1 and CAP_NO.match(ws[1].text) and ws[1].text[-1:] in ':.')
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
        if id(l) in taken or not is_caption(l):
            continue
        kind = 'table' if l.words[0].text.upper().startswith('TABLE') else 'figure'
        col = l.col
        same = sorted([m for m in lines if (m.col == col or col == 'F' or m.col == 'F') and id(m) not in taken], key=lambda m: m.y0)
        idx = same.index(l)
        cap = [l]
        # 說明文字往下延伸：同為小字、行距小
        j = idx + 1
        while (j < len(same) and same[j].y0 - cap[-1].y1 < 4 and not is_caption(same[j])
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
