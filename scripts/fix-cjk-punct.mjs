// Repair full-width CJK punctuation that leaked into the non-Chinese guide locales.
//
// Why a script and not a find/replace: the guide strings for all three locales live
// side by side (often on one line), and full-width punctuation is *correct* inside the
// zh-TW text. So the only safe rule is per string literal: a literal containing no CJK
// ideograph is an en/es literal, and full-width punctuation in it is a defect.
// The script is atomic: it writes only if the leftover guard passes.

import { readFileSync, writeFileSync } from 'node:fs';

const FILE = new URL('../src/components/guide/guideContent.ts', import.meta.url);
const IDE0 = 0x4e00, IDE1 = 0x9fff;
const orig = readFileSync(FILE, 'utf8');

const hasIdeograph = (s) => [...s].some((c) => { const n = c.codePointAt(0); return n >= IDE0 && n <= IDE1; });

// Full-width / CJK-form punctuation -> its ASCII equivalent.
const MAP = {
  '。': '.', '，': ', ', '、': ', ', '；': '; ', '：': ': ',
  '！': '! ', '？': '? ', '／': '/', '｜': ' | ', '＼': '\\',
  '（': '(', '）': ')', '％': '%', '－': '-', '～': '~', '〜': '~',
  '「': '"', '」': '"', '『': '"', '』': '"', '　': ' ',
  '〔': '[', '〕': ']', '【': '[', '】': ']', '《': '<', '》': '>',
  '＋': '+', '＝': '=', '＜': '<', '＞': '>', '＆': '&', '＊': '*', '＃': '#', '＠': '@',
};

// Single-quoted TS literals, honouring backslash escapes.
const LITERAL = /'(?:\\[\s\S]|[^'\\])*'/g;
const FULL = /[\u3000-\u303F\uFF00-\uFFEF]/;

let candidates = 0, changed = 0, skippedZh = 0;
const samples = [];

const out = orig.replace(LITERAL, (lit) => {
  if (!FULL.test(lit)) return lit;                      // nothing full-width
  if (hasIdeograph(lit)) { skippedZh++; return lit; }   // zh-TW: correct as written
  candidates++;
  let fixed = lit.replace(/[\u3000-\u303F\uFF00-\uFFEF]/g, (ch) => (ch in MAP ? MAP[ch] : ch));
  // Tidy only the whitespace our own substitutions can introduce.
  fixed = fixed.replace(/ {2,}/g, ' ').replace(/ ([.,;:!?)\]])/g, '$1');
  if (fixed === lit) return lit;
  changed++;
  if (samples.length < 18) samples.push(lit.slice(0, 74) + '\n   -> ' + fixed.slice(0, 74));
  return fixed;
});

console.log('literals with full-width punctuation, no ideograph :', candidates);
console.log('literals corrected                                  :', changed);
console.log('zh-TW literals deliberately skipped                 :', skippedZh);
console.log('---');
for (const s of samples) console.log(s);

// Guard: a remaining en/es literal with full-width punctuation means a code point is unmapped.
const leftovers = [...out.matchAll(LITERAL)].filter((m) => FULL.test(m[0]) && !hasIdeograph(m[0]));
if (leftovers.length) {
  console.error('\nABORT: ' + leftovers.length + ' en/es literal(s) still contain full-width punctuation');
  for (const m of leftovers.slice(0, 8)) console.error('  ' + m[0].slice(0, 95));
  process.exit(1);
}
if (changed === 0) { console.error('ABORT: nothing changed'); process.exit(1); }

writeFileSync(FILE, out);
console.log('\nwritten:', FILE.pathname);
