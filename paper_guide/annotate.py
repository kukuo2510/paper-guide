"""第 4 步：LLM 逐頁產生說明卡。一頁呼叫一次，回傳該頁每個單位的 card。

目前只有 Ollama（--llm ollama:<模型>）；Claude 等使用者有 API key 再接。
"""
import json
import time
import urllib.request

OLLAMA = 'http://localhost:11434/api/chat'

CARD_FIELDS = {
    'i': {'type': 'integer'},
    'title': {'type': 'string'},
    'what': {'type': 'string'},
    'quote_en': {'type': 'string'},
    'quote_zh': {'type': 'string'},
    'note': {'type': 'string'},
    'critique': {'type': 'string'},
    'key': {'type': 'boolean'},
    'translation': {'type': 'string'},
}
SCHEMA = {
    'type': 'object',
    'properties': {'cards': {'type': 'array', 'items': {
        'type': 'object', 'properties': CARD_FIELDS, 'required': list(CARD_FIELDS)}}},
    'required': ['cards'],
}

SYSTEM = """你是幫研究所學生讀英文論文的助教。使用者會給你論文其中一頁，已經切成編號的單位（段落、公式、圖、表、標題）。
請為每個單位各產生一張說明卡，全部用繁體中文、台灣用語（不要用簡體字，也不要用「質量」「信息」「數據」這類中國用語，要用「品質」「資訊」「資料」）。

每張卡的欄位：
- i：單位編號（照輸入的編號）
- title：6～14 字的小標，講這段的重點
- what：一兩句白話說明這段在講什麼，讓沒讀過的人也懂
- quote_en：從原文挑一句最關鍵的句子，一字不改照抄；標題或沒有重點句就給空字串
- quote_zh：quote_en 的中文翻譯；quote_en 是空字串就也給空字串
- note：補充說明（名詞解釋、公式每個符號的意思、跟前文的關係），沒有就給空字串
- critique：這段真的有問題才寫（假設太強、實驗不公平、數字前後不一致、沒交代清楚的關鍵細節）。
  寧缺勿濫：大多數段落應該給空字串。「只是定義」「需要看附錄」「公式很複雜」這種不算批判，不要寫
- key：這段是不是理解全文必讀的重點（true/false）。一頁裡最多一半標 true；標題、圖說、符號定義、過場段落給 false
- translation：整段的完整中文翻譯，不要省略；公式保留原本的符號

公式和符號：如果原文的數學式亂掉了，請在 note 裡逐一說明每個符號代表什麼（例如「ŷ 是預測值、y 是實際值」），不要只寫「定義了某某函數」。

用語一律用台灣學術界的說法：
排程（不要用調度）、最佳化（不要用優化）、計畫（不要用計劃）、演算法（不要用算法）、
資料（不要用數據）、資訊（不要用信息）、網路（不要用網絡）、模組（不要用模塊）、預設（不要用默認）、品質（不要用質量）

只輸出 JSON，格式：{"cards": [ ... ]}，輸入的每個單位剛好一張卡，i 用輸入的編號。"""

# 模型還是寫錯就直接換掉，替換次數記進 stats，比較時看得到
TERM_FIX = {'調度': '排程', '優化': '最佳化', '計劃': '計畫', '算法': '演算法', '數據': '資料',
            '信息': '資訊', '網絡': '網路', '模塊': '模組', '默認': '預設', '質量': '品質'}

KIND_ZH = {'text': '段落', 'math': '公式', 'figure': '圖', 'table': '表', 'heading': '標題', 'algorithm': '演算法'}


def page_prompt(title, page_no, units, idx):
    lines = [f'論文：{title}', f'第 {page_no + 1} 頁，這次給你 {len(idx)} 個單位：', '']
    for i in idx:
        lines.append(f'[{i}] （{KIND_ZH.get(units[i]["kind"], units[i]["kind"])}）{units[i]["text"]}')
    return '\n'.join(lines)


def call_ollama(model, system, user, num_ctx=16384):
    body = json.dumps({
        'model': model, 'stream': False, 'format': SCHEMA,
        'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}],
        'options': {'temperature': 0.2, 'num_ctx': num_ctx},
    }).encode('utf8')
    req = urllib.request.Request(OLLAMA, body, {'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=1800) as r:
        res = json.loads(r.read())
    return res['message']['content'], res


def validate(raw, idx):
    """回傳 ({單位序號: card}, 問題清單)。JSON 壞掉直接丟例外讓呼叫端重試。"""
    cards = json.loads(raw)['cards']
    out, problems = {}, []
    for c in cards:
        i = c.get('i')
        if i not in idx:
            problems.append(f'編號不在這批：{i}')
            continue
        if i in out:
            problems.append(f'編號重複：{i}')
        out[i] = {k: c.get(k, '' if k != 'key' else False) for k in CARD_FIELDS if k != 'i'}
    return out, problems


def fix_terms(card, counts):
    for k, v in card.items():
        if isinstance(v, str):
            for bad, good in TERM_FIX.items():
                if bad in v:
                    counts[bad] = counts.get(bad, 0) + v.count(bad)
                    v = v.replace(bad, good)
            card[k] = v


def annotate_page(llm, title, page_no, units, log=print, chunk=None):
    """llm 形如 'ollama:gemma4:12b'；chunk 是一次最多送幾個單位（None 表示整頁）。
    缺卡的單位會再補送一次。回傳 (cards, stats)。"""
    backend, _, model = llm.partition(':')
    if backend != 'ollama':
        raise ValueError(f'還不支援 {backend}，目前只有 ollama:<模型>')
    all_idx = list(range(len(units)))
    size = chunk or len(units)
    batches = [all_idx[k:k + size] for k in range(0, len(all_idx), size)]
    cards, problems = {}, []
    st = {'model': model, 'seconds': 0, 'calls': 0, 'prompt_tokens': 0, 'output_tokens': 0}

    def run(idx):
        for attempt in (1, 2):
            t0 = time.time()
            raw, res = call_ollama(model, SYSTEM, page_prompt(title, page_no, units, idx))
            st['seconds'] += time.time() - t0
            st['calls'] += 1
            st['prompt_tokens'] += res.get('prompt_eval_count') or 0
            st['output_tokens'] += res.get('eval_count') or 0
            try:
                got, probs = validate(raw, idx)
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                log(f'  回傳格式錯誤（{e}），{"重試" if attempt == 1 else "放棄這批"}')
                continue
            problems.extend(probs)
            cards.update(got)
            return

    for idx in batches:
        run(idx)
    missing = [i for i in all_idx if i not in cards]
    if missing:
        log(f'  缺 {missing}，補送一次')
        problems.append(f'第一輪缺少：{missing}')
        run(missing)
        still = [i for i in all_idx if i not in cards]
        if still:
            problems.append(f'補送後仍缺：{still}')
    terms = {}
    for c in cards.values():
        fix_terms(c, terms)
    st.update(seconds=round(st['seconds'], 1), problems=problems, term_fixes=terms)
    return cards, st
