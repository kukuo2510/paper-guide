# paper-guide

> 🚧 開發中 / Work in progress

輸入一篇論文 PDF，產生「逐段導讀」網頁：左邊是原文頁面、每段都框起來；右邊是該段的白話說明、重點句翻譯與可批判之處。

Turn a paper PDF into a paragraph-by-paragraph reading guide: the original page on the left with every unit boxed, and on the right a plain-language explanation, key-sentence translation and critique for each unit.

## Pipeline

```
paper.pdf
 ├─ render    PyMuPDF → page images
 ├─ extract   PyMuPDF → characters with coordinates, font size, weight
 ├─ segment   rule-based segmentation into paragraph / equation / figure / table / heading units,
 │            joining paragraphs that span columns and pages            ← core difficulty
 ├─ annotate  LLM (local Ollama; Claude API planned) → JSON cards per unit, schema-validated with retry
 └─ build     HTML viewer (out/<paper>/index.html)
```

## Status

- [x] M1 segmentation — on a hand-labelled 105-unit paper: **B-cubed P 0.901 / R 0.880 / F1 0.890**.
  Most remaining "errors" are places where the hand labels group paragraphs by meaning while the program splits at true paragraph boundaries.
- [~] M2 annotation — local models compared side by side (gemma4:12b vs gpt-oss:20b): completeness, terminology,
  hallucinated symbols; added a terminology table, chunked requests with missing-card resubmission, and post-processing.
- [ ] M3 evaluate on more arXiv papers
- [ ] M4 package as a Claude Code skill

## Usage

```bash
python -m venv .venv && .venv/Scripts/activate
pip install pymupdf                 # PyMuPDF renders the page images too; no external tools needed
python -m paper_guide build paper.pdf -o out/name --llm ollama:gemma4:12b
python -m eval.eval_segment paper.pdf eval/<labels>.json   # segmentation accuracy
python tests/check_regression.py                           # refactor regression check (needs the local PDFs)
```

Papers are not included; public demos use openly licensed arXiv papers only.
