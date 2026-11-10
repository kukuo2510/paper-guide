"""標準答案（手工框的單位）的讀取，eval_segment 與 overlay 共用。"""
import json


def load_raw(path):
    with open(path, encoding='utf8') as f:
        return json.load(f)


def gt_units(raw):
    """raw[頁][單位] = {'b': [[[x0, x1], y0, y1], ...], 't': 標題}"""
    out = []
    for p, items in enumerate(raw):
        for i, it in enumerate(items):
            out.append({'page': p, 'id': f'{p + 1}-{i + 1}', 't': it['t'],
                        'boxes': [[xr[0], y0, xr[1], y1] for xr, y0, y1 in it['b']]})
    return out
