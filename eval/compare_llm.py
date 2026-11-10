"""同一頁、不同模型產生的說明卡並排比較，加上手工版當基準。

  python -m eval.compare_llm <頁碼> <手工json> <輸出html> <out/模型A> <out/模型B> ...

量化指標（每個模型）：
- 簡體字／中國用語出現次數（要求是繁體台灣用語）
- quote_en 是否真的出現在原文（小模型常改寫或捏造）
- 全文翻譯字數 / 原文字數（太低代表省略）
- 空欄位、缺卡
"""
import html
import json
import os
import re
import sys

# 常見的簡體字（跟繁體不同形的），出現就算錯
SIMPLIFIED = set('这们说时为个来对会发实现进过还产经动与务处问题应网络预测优计数据视频软质级习学种'
                 '图块层输长将该实际电价负结构损训练样标设变维误项约条确认关键')
# 不在上面但台灣不用的詞
CN_TERMS = ['信息', '數據', '質量', '優化', '默認', '網絡', '軟件', '硬件', '視頻', '模塊', '算子', '魯棒', '調度', '計劃', '算法']


def load_data(out_dir):
    with open(os.path.join(out_dir, 'data.js'), encoding='utf8') as f:
        return json.loads(f.read().removeprefix('const DATA = ').rstrip().rstrip(';'))


def norm(s):
    return re.sub(r'[^a-z0-9]', '', s.lower())


def iou(a, b):
    x0, y0, x1, y1 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, x1 - x0) * max(0, y1 - y0)
    area = lambda r: (r[2] - r[0]) * (r[3] - r[1])
    return inter / (area(a) + area(b) - inter or 1)


def metrics(units):
    zh = ''.join(c['card'].get(k, '') for c in units if 'card' in c
                 for k in ('title', 'what', 'quote_zh', 'note', 'critique', 'translation'))
    simp = sorted({ch for ch in zh if ch in SIMPLIFIED})
    terms = [t for t in CN_TERMS if t in zh]
    quotes = [(u['card']['quote_en'], u['text']) for u in units if u.get('card', {}).get('quote_en')]
    verbatim = sum(norm(q) in norm(t) for q, t in quotes)
    src = sum(len(u['text']) for u in units if 'card' in u)
    tr = sum(len(u['card']['translation']) for u in units if 'card' in u)
    return {
        'cards': sum('card' in u for u in units), 'units': len(units),
        'simplified': simp, 'cn_terms': terms,
        'quote_ok': f'{verbatim}/{len(quotes)}',
        # 英文→中文字數大約 1:0.3～0.4；低於 0.2 多半是省略
        'tr_ratio': round(tr / src, 2) if src else 0,
        'empty_what': sum(1 for u in units if 'card' in u and not u['card']['what'].strip()),
        'critiques': sum(1 for u in units if u.get('card', {}).get('critique')),
        'key': sum(1 for u in units if u.get('card', {}).get('key')),
    }


def card_html(c):
    if not c:
        return '<p class="miss">（沒有產生卡片）</p>'
    e = html.escape
    return (f'<h4>{e(c["title"])} <span class="tag">{"重點" if c["key"] else "帶過"}</span></h4>'
            f'<p><b>這段在講</b>：{e(c["what"])}</p>'
            + (f'<p class="q">“{e(c["quote_en"])}”<br>→ {e(c["quote_zh"])}</p>' if c['quote_en'] else '')
            + (f'<p class="ex">{e(c["note"])}</p>' if c['note'] else '')
            + (f'<p class="warn">可以批判：{e(c["critique"])}</p>' if c['critique'] else '')
            + f'<details><summary>全文翻譯</summary>{e(c["translation"])}</details>')


def main(page, hand_json, out_html, *dirs):
    page_i = int(page) - 1
    runs = []
    for d in dirs:
        data = load_data(d)
        with open(os.path.join(d, 'llm_stats.json'), encoding='utf8') as f:
            st = next(s for s in json.load(f) if s['page'] == page_i + 1)
        runs.append((st['model'], data['pages'][page_i]['units'], st))
    with open(hand_json, encoding='utf8') as f:
        hand = json.load(f)[page_i]['items']
    hand_boxes = [[x[0][0], x[1], x[0][1], x[2]] for it in hand for x in it['b'][:1]]

    rows = []
    base = runs[0][1]
    for i, u in enumerate(base):
        best = max(range(len(hand)), key=lambda j: iou(u['boxes'][0], hand_boxes[j]))
        h = hand[best] if iou(u['boxes'][0], hand_boxes[best]) > 0.3 else None
        cells = ''.join(f'<td>{card_html(r[1][i].get("card"))}</td>' for r in runs)
        hc = f'<h4>{html.escape(h["t"])}</h4>{h["h"]}' if h else '<p class="miss">（手工版這段沒對上）</p>'
        rows.append(f'<tr><th>{i + 1}<br><small>{u["kind"]}</small><details><summary>原文</summary>'
                    f'{html.escape(u["text"])}</details></th>{cells}<td class="hand">{hc}</td></tr>')

    ms = [(r[0], metrics(r[1]), r[2]) for r in runs]
    head = ''.join(f'<th>{html.escape(m)}</th>' for m, _, _ in ms)
    def row(label, f):
        return f'<tr><th>{label}</th>' + ''.join(f'<td>{f(m, s)}</td>' for _, m, s in ms) + '</tr>'
    summary = ''.join([
        row('花費時間', lambda m, s: f'{s["seconds"]} 秒（{s.get("calls", s.get("attempts"))} 次呼叫）'),
        row('輸出 tokens', lambda m, s: s['output_tokens']),
        row('卡片數', lambda m, s: f'{m["cards"]}/{m["units"]}' + (f'<br>{s["problems"]}' if s['problems'] else '')),
        row('簡體字', lambda m, s: '、'.join(m['simplified']) or '無'),
        row('中國用語（最終）', lambda m, s: '、'.join(m['cn_terms']) or '無'),
        row('後處理替換', lambda m, s: '、'.join(f'{k}×{v}' for k, v in s.get('term_fixes', {}).items()) or '無'),
        row('重點句照抄原文', lambda m, s: m['quote_ok']),
        row('翻譯長度／原文', lambda m, s: m['tr_ratio']),
        row('有批判的卡', lambda m, s: m['critiques']),
        row('標成重點的卡', lambda m, s: m['key']),
    ])
    doc = f'''<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><title>模型比較 第 {page} 頁</title>
<style>
body {{ font-family: "Microsoft JhengHei", sans-serif; margin: 16px; background: #f8fafc; color: #0f172a; }}
table {{ border-collapse: collapse; width: 100%; background: #fff; }}
th, td {{ border: 1px solid #cbd5e1; padding: 8px 10px; vertical-align: top; font-size: 14px; line-height: 1.7; }}
.cmp td {{ width: 30%; }} .cmp th {{ width: 7%; }} td.hand {{ background: #f0fdf4; }}
h4 {{ margin: 0 0 4px; font-size: 15px; }} .tag {{ font-size: 12px; color: #c2410c; }}
.q {{ background: #fff7ed; padding: 4px 8px; }} .ex {{ color: #334155; }} .warn {{ background: #fef2f2; padding: 4px 8px; }}
.miss {{ color: #94a3b8; }} details {{ font-size: 13px; color: #475569; }}
.sum {{ width: auto; margin-bottom: 20px; }} .sum td {{ min-width: 220px; }}
</style>
<h2>第 {page} 頁：本機模型產生的說明卡比較</h2>
<table class="sum"><tr><th></th>{head}</tr>{summary}</table>
<table class="cmp"><tr><th>單位</th>{head}<th>手工版（Claude，基準）</th></tr>{''.join(rows)}</table></html>'''
    with open(out_html, 'w', encoding='utf8') as f:
        f.write(doc)
    for m, x, s in ms:
        print(m, s['seconds'], 's', x)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf8')
    main(*sys.argv[1:])
