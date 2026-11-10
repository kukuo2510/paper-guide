// 從手工導讀 guide.html 取出 PAGES 陣列，輸出 JSON（給 compare_llm.py 當基準）
// 用法：node eval/handmade_cards.js <guide.html> > out.json
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');
const js = src.slice(src.indexOf('const L ='), src.indexOf('\n];', src.indexOf('const PAGES')) + 3);
const PAGES = new Function(js + '\nreturn PAGES;')();
console.log(JSON.stringify(PAGES.map((p) => ({ tab: p.tab, items: p.items.map((it) => ({ b: it.b, k: it.k, t: it.t, h: it.h })) }))));
