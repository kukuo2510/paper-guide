"""文字規則：字是否像正常英文、行是公式還是內文、是不是標題。"""
import re

EQ_NO = re.compile(r'^\(\d+[a-z]?\)$')
NUM_HEAD = re.compile(r'^(\d+(\.\d+)*\.?|[A-Z]\.?(\d+)*)$')
HEADING = re.compile(r'^([IVX]+\.|[A-H]\.|[1-9]\)|APPENDIX|REFERENCES|Appendix|Abstract|Index|Proof|Theorem|Lemma|Algorithm)')

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
