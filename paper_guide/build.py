"""把切好的單位輸出成導讀網頁：out_dir/index.html + pages/*.png + data.js。"""
import json
import os
import re
import shutil

import pymupdf

from .annotate import annotate_page
from .extract import load, render_pages
from .segment import segment

TEMPLATE = os.path.join(os.path.dirname(__file__), 'template.html')


def unit_text(u):
    """依原本的行序把字接回文字；行尾連字號接起來。"""
    lines = {}
    for col, ws in u.parts:
        for w in ws:
            if w.text:
                lines.setdefault((col, round(w.base)), []).append(w)
    out = []
    for key in sorted(lines, key=lambda k: ({'F': 0, 'L': 1, 'R': 2}[k[0]], k[1])):
        out.append(' '.join(w.text for w in sorted(lines[key], key=lambda w: w.x0)))
    text = '\n'.join(out)
    text = re.sub(r'(\w)-\n(\w)', r'\1\2', text)
    return text.replace('\n', ' ')


def segment_pdf(pdf):
    pages = load(pdf)
    units, cols = segment(pages)
    return pages, units, cols


def build(pdf, out_dir, dpi=150, llm=None, pages_to_annotate=None, log=print, chunk=None):
    """llm 有給就逐頁產生說明卡（pages_to_annotate 是從 1 起算的頁碼，None 表示全部）；沒給就只顯示原文。"""
    os.makedirs(os.path.join(out_dir, 'pages'), exist_ok=True)
    pages, units, cols = segment_pdf(pdf)
    names = render_pages(pdf, os.path.join(out_dir, 'pages'), dpi)
    title = pymupdf.open(pdf).metadata.get('title') or os.path.splitext(os.path.basename(pdf))[0]
    stats = []
    data = {'id': os.path.basename(os.path.abspath(out_dir)), 'title': title, 'pages': []}
    for p, name in zip(pages, names):
        pu = [u for u in units if u.page == p.no]
        items = []
        for i, u in enumerate(pu):
            item = {'kind': u.kind, 'boxes': u.boxes(cols), 'text': unit_text(u), 'cont': u.cont}
            items.append(item)
        if llm and items and (pages_to_annotate is None or p.no + 1 in pages_to_annotate):
            log(f'第 {p.no + 1} 頁：{len(items)} 個單位，送 {llm} …')
            cards, st = annotate_page(llm, title, p.no, items, log, chunk)
            for i, c in cards.items():
                items[i]['card'] = c
            st['page'] = p.no + 1
            stats.append(st)
            log(f'  {st["seconds"]} 秒、{st["calls"]} 次呼叫，輸出 {st["output_tokens"]} tokens，用語替換 {st["term_fixes"]}' + (f'，問題：{st["problems"]}' if st['problems'] else ''))
        data['pages'].append({'img': f'pages/{name}', 'w': p.width, 'h': p.height, 'units': items})
    with open(os.path.join(out_dir, 'data.js'), 'w', encoding='utf8') as f:
        f.write('const DATA = ' + json.dumps(data, ensure_ascii=False) + ';\n')
    if stats:
        with open(os.path.join(out_dir, 'llm_stats.json'), 'w', encoding='utf8') as f:
            json.dump(stats, f, ensure_ascii=False, indent=1)
    data['llm_stats'] = stats
    shutil.copy(TEMPLATE, os.path.join(out_dir, 'index.html'))
    return data
