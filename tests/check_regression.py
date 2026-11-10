"""重構回歸檢查：重算 eval 輸出、各 PDF 的 data.js 與 segment() 傾印，和黃金值比對。

  python tests/check_regression.py            比對（失敗時 exit 1）
  python tests/check_regression.py --update   重新產生黃金值（要在確定行為正確的程式碼上跑；會先跑兩次驗證可重現）

黃金值：
  tests/golden.json  只存 sha256 與 eval 數字（可進版控，不含 PDF 文字）
  out/golden/        含文字的完整黃金檔（git 忽略，僅供比對失敗時看差異）
不呼叫 LLM。
"""
import hashlib
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
DATA = os.environ.get('PAPER_GUIDE_DATA', r'D:\workspace\project\paper-guide\data')
RL = os.path.join(DATA, 'rl-adapter.pdf')
GT = os.path.join(ROOT, 'eval', 'rl-adapter.boxes.raw.json')
PDFS = [RL] + sorted(os.path.join(DATA, 'arxiv', f) for f in os.listdir(os.path.join(DATA, 'arxiv')) if f.endswith('.pdf'))
GOLDEN_JSON = os.path.join(ROOT, 'tests', 'golden.json')
GOLDEN_DIR = os.path.join(ROOT, 'out', 'golden')
WORK = os.path.join(ROOT, 'out', 'regress')
EXPECT_EVAL = 'B-cubed  P=0.901  R=0.880  F1=0.890'


def sha(b):
    return hashlib.sha256(b).hexdigest()


def name_of(pdf):
    return os.path.splitext(os.path.basename(pdf))[0]


def run_eval():
    env = dict(os.environ, PYTHONIOENCODING='utf8')
    r = subprocess.run([sys.executable, '-m', 'eval.eval_segment', RL, GT], cwd=ROOT, env=env, capture_output=True, check=True)
    return r.stdout


def dump_segment(pdf):
    from paper_guide.extract import load
    from paper_guide.segment import segment
    pages = load(pdf)
    units, cols = segment(pages)
    out = {'cols': cols,
           'pages_words_after': [[p.no, len(p.words), sha('\n'.join(w.text for w in p.words).encode('utf8'))] for p in pages],
           'units': [{'kind': u.kind, 'page': u.page, 'cont': u.cont,
                      'parts': [[c, len(ws)] for c, ws in u.parts],
                      'boxes': u.boxes(cols),
                      'words': [w.text for w in u.words()]} for u in units]}
    return json.dumps(out, ensure_ascii=False, indent=1).encode('utf8')


def run_build(pdf):
    out = os.path.join(WORK, name_of(pdf))
    env = dict(os.environ, PYTHONIOENCODING='utf8')
    subprocess.run([sys.executable, '-m', 'paper_guide', 'build', pdf, '-o', out, '--dpi', '30'], cwd=ROOT, env=env, capture_output=True, check=True)
    with open(os.path.join(out, 'data.js'), 'rb') as f:
        return f.read()


def compute():
    res = {'eval.txt': run_eval()}
    for pdf in PDFS:
        n = name_of(pdf)
        res[n + '/data.js'] = run_build(pdf)
        res[n + '/segment.json'] = dump_segment(pdf)
    return res


def main():
    update = '--update' in sys.argv
    a = compute()
    ok = True
    if update:
        b = compute()
        if a != b:
            print('非決定性：兩次結果不同', [k for k in a if a[k] != b[k]])
            return 1
        print('兩次執行結果一致（可重現）')
        for k, v in a.items():
            p = os.path.join(GOLDEN_DIR, k)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, 'wb') as f:
                f.write(v)
        if EXPECT_EVAL not in a['eval.txt'].decode('utf8'):
            print('eval 數字不是預期的', EXPECT_EVAL)
            return 1
        with open(GOLDEN_JSON, 'w', encoding='utf8') as f:
            json.dump({'eval_line': EXPECT_EVAL, 'sha256': {k: sha(v) for k, v in a.items()}}, f, indent=1, sort_keys=True)
        print('已更新黃金值', len(a), '個檔')
        return 0
    g = json.load(open(GOLDEN_JSON, encoding='utf8'))
    if g['eval_line'] not in a['eval.txt'].decode('utf8'):
        print('FAIL eval 數字不符', g['eval_line']); ok = False
    for k, h in g['sha256'].items():
        if k not in a or sha(a[k]) != h:
            print('FAIL', k, '與黃金值不同' + ('（out/golden 有完整檔可 diff）' if os.path.exists(os.path.join(GOLDEN_DIR, k)) else ''))
            ok = False
            if os.path.exists(os.path.join(GOLDEN_DIR, k)):
                os.makedirs(os.path.join(WORK, 'fail', os.path.dirname(k)), exist_ok=True)
                open(os.path.join(WORK, 'fail', k), 'wb').write(a[k])
    print('PASS' if ok else 'FAILED', f'({len(g["sha256"])} 項)')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
