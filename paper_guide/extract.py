"""從 PDF 抽出每頁的文字（含字級）與圖形區域。"""
from collections import Counter
from dataclasses import dataclass, field

import pymupdf


@dataclass
class Word:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    size: float  # 字級
    base: float = 0  # 基線 y（同一行的字基線相同，上下標不同）
    bold: bool = False

    @property
    def xc(self):
        return (self.x0 + self.x1) / 2

    @property
    def yc(self):
        return (self.y0 + self.y1) / 2


@dataclass
class Page:
    no: int  # 從 0 開始
    width: float
    height: float
    words: list
    graphics: list = field(default_factory=list)  # 圖形叢集 [x0, y0, x1, y1]
    rules: list = field(default_factory=list)  # 水平線 [x0, y, x1]（演算法框、表格線）


def _words_from_rawdict(page):
    """逐字元組字：遇到空白或字級改變就斷字。比 get_text('words') 多了正確的字級與基線。"""
    words = []
    for b in page.get_text('rawdict')['blocks']:
        for l in b.get('lines', []):
            for sp in l['spans']:
                cur = []
                def flush():
                    if cur:
                        xs0 = min(c['bbox'][0] for c in cur); xs1 = max(c['bbox'][2] for c in cur)
                        ys0 = min(c['bbox'][1] for c in cur); ys1 = max(c['bbox'][3] for c in cur)
                        words.append(Word(xs0, ys0, xs1, ys1, ''.join(c['c'] for c in cur), round(sp['size'], 1), cur[0]['origin'][1],
                                          bool(sp['flags'] & 16) or 'Bold' in sp['font'] or '.B' in sp['font']))
                        cur.clear()
                for c in sp['chars']:
                    if c['c'].isspace():
                        flush()
                    else:
                        cur.append(c)
                flush()
    # 同字級、同基線、緊鄰（間隙 < 0.5pt）的片段合成一個字（PDF 常把一個字拆成好幾個 span）
    words.sort(key=lambda w: (round(w.base, 1), w.x0))
    out = []
    for w in words:
        if out and abs(out[-1].base - w.base) < 0.3 and 0 <= w.x0 - out[-1].x1 < 0.5 and out[-1].size == w.size:
            o = out[-1]
            out[-1] = Word(o.x0, min(o.y0, w.y0), w.x1, max(o.y1, w.y1), o.text + w.text, o.size, o.base, o.bold)
        else:
            out.append(w)
    return out


def load(path):
    doc = pymupdf.open(path)
    pages = []
    for p in doc:
        words = _words_from_rawdict(p)
        graphics = [list(r) for r in p.cluster_drawings()]
        graphics += [list(i['bbox']) for i in p.get_image_info() if (i['bbox'][2] - i['bbox'][0]) * (i['bbox'][3] - i['bbox'][1]) > 4]
        rules = []
        for d in p.get_drawings():
            r = d['rect']
            if r.height < 1.5 and r.width > 40:
                rules.append([r.x0, (r.y0 + r.y1) / 2, r.x1])
        pages.append(Page(p.number, p.rect.width, p.rect.height, words, graphics, rules))
    return pages


def body_size(pages):
    """內文字級 = 出現最多次的字級。"""
    c = Counter(w.size for p in pages for w in p.words if w.text.isalpha() and len(w.text) > 2)
    return c.most_common(1)[0][0]


def render_pages(path, out_dir, dpi=150):
    doc = pymupdf.open(path)
    names = []
    for p in doc:
        name = f'p-{p.number + 1:02d}.png'
        p.get_pixmap(dpi=dpi).save(f'{out_dir}/{name}')
        names.append(name)
    return names
