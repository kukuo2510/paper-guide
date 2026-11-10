"""paper-guide 指令列。

  python -m paper_guide build paper.pdf -o out/paper
"""
import argparse
import os
import sys

from .build import build


def main(argv=None):
    ap = argparse.ArgumentParser(prog='paper_guide', description='論文逐段導讀產生器')
    sub = ap.add_subparsers(dest='cmd', required=True)
    b = sub.add_parser('build', help='切段落並輸出導讀網頁')
    b.add_argument('pdf')
    b.add_argument('-o', '--out', help='輸出資料夾（預設 out/<檔名>）')
    b.add_argument('--dpi', type=int, default=150)
    b.add_argument('--llm', help='產生說明卡用的模型，例如 ollama:gemma4:12b')
    b.add_argument('--chunk', type=int, help='一次最多送幾個單位給模型，預設整頁')
    b.add_argument('--pages', help='只標註這些頁（從 1 起算，逗號分隔），預設全部')
    a = ap.parse_args(argv)
    if a.cmd == 'build':
        out = a.out or os.path.join('out', os.path.splitext(os.path.basename(a.pdf))[0])
        pages = {int(x) for x in a.pages.split(',')} if a.pages else None
        data = build(a.pdf, out, a.dpi, a.llm, pages, chunk=a.chunk)
        n = sum(len(p['units']) for p in data['pages'])
        print(f'{len(data["pages"])} 頁、{n} 個單位 → {os.path.join(out, "index.html")}')


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf8')
    main()
