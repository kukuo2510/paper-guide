"""資料結構：行（Line）與導讀單位（Unit）。"""
from dataclasses import dataclass, field

BULLETS = {'•', '◦', '–', '▪', '∙'}
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
