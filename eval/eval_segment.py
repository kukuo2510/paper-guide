"""切段準確率評估（字層級 B-cubed）。

標準答案：手工框好的單位（每個單位可以有多個框）。每個字依中心點落在哪個框，決定它屬於哪個標準單位；
同理得到預測單位。對每個字算：
  precision = 它所在預測單位裡，有多少比例的字跟它同一個標準單位（切太粗會降低）
  recall    = 它所在標準單位裡，有多少比例的字跟它同一個預測單位（切太細會降低）
另外列出「合併錯誤」：預測單位跨到兩個以上標準單位（這種錯最嚴重，說明會混在一起）。

用法：python -m eval.eval_segment data/rl-adapter.pdf eval/rl-adapter.boxes.raw.json
"""
import json
import sys
from collections import Counter, defaultdict

from paper_guide.extract import load
from paper_guide.segment import segment


def gt_units(raw):
    """raw[頁][單位] = {'b': [[[x0, x1], y0, y1], ...], 't': 標題}"""
    out = []
    for p, items in enumerate(raw):
        for i, it in enumerate(items):
            out.append({'page': p, 'id': f'{p + 1}-{i + 1}', 't': it['t'],
                        'boxes': [[xr[0], y0, xr[1], y1] for xr, y0, y1 in it['b']]})
    return out


def inside(w, b):
    return b[0] <= w.xc <= b[2] and b[1] <= w.yc <= b[3]


def main(pdf, gt_path, verbose=True):
    raw = json.load(open(gt_path, encoding='utf8'))
    gts = gt_units(raw)
    pages = load(pdf)
    units, cols = segment(pages)
    npages = len(raw)
    pred_of, gt_of = {}, {}
    for k, u in enumerate(units):
        for w in u.words():
            if w.text:
                pred_of[id(w)] = k
    words = [w for p in pages[:npages] for w in p.words]
    page_of = {id(w): p.no for p in pages[:npages] for w in p.words}
    for w in words:
        for g in gts:
            if g['page'] == page_of[id(w)] and any(inside(w, b) for b in g['boxes']):
                gt_of[id(w)] = g['id']; break
    ws = [w for w in words if id(w) in gt_of and id(w) in pred_of]
    missed = [w for w in words if id(w) in gt_of and id(w) not in pred_of]
    by_pred = defaultdict(Counter); by_gt = defaultdict(Counter)
    for w in ws:
        by_pred[pred_of[id(w)]][gt_of[id(w)]] += 1
        by_gt[gt_of[id(w)]][pred_of[id(w)]] += 1
    P = sum(by_pred[pred_of[id(w)]][gt_of[id(w)]] / sum(by_pred[pred_of[id(w)]].values()) for w in ws) / len(ws)
    R = sum(by_gt[gt_of[id(w)]][pred_of[id(w)]] / sum(by_gt[gt_of[id(w)]].values()) for w in ws) / len(ws)
    F = 2 * P * R / (P + R)
    merges = []
    for k, c in by_pred.items():
        big = [g for g, n in c.items() if n >= 3]
        if len(big) > 1:
            merges.append((k, big))
    exact = sum(1 for g, c in by_gt.items() if len(c) == 1 and len(by_pred[next(iter(c))]) == 1)
    nu = len([u for u in units if u.page < npages])
    print(f'標準單位 {len(gts)}，預測單位 {nu}')
    print(f'B-cubed  P={P:.3f}  R={R:.3f}  F1={F:.3f}')
    print(f'完全一致的單位：{exact}/{len(gts)} = {exact / len(gts):.1%}')
    print(f'合併錯誤（一個預測單位混到多個標準單位）：{len(merges)}')
    print(f'沒被任何預測單位涵蓋的字：{len(missed)}')
    if verbose:
        tt = {g['id']: g['t'] for g in gts}
        for k, big in merges:
            u = units[k]
            print(f'  p{u.page + 1} [{u.kind}] 混到：' + '、'.join(f'{g} {tt[g]}' for g in big))
        split = [(g, c) for g, c in by_gt.items() if len(c) > 1]
        print(f'被切開的標準單位：{len(split)}')
        for g, c in sorted(split, key=lambda x: [int(v) for v in x[0].split('-')]):
            print(f'  {g} {tt[g]} → {len(c)} 塊 ' + ' '.join(units[k].kind for k in c))
    return P, R, F


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf8')
    main(sys.argv[1], sys.argv[2])
