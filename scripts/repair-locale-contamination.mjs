#!/usr/bin/env node
// Repair full-width CJK punctuation that leaked into non-Chinese locale strings.
//
// Why a script and not a find/replace: the locales usually sit side by side
// (often on one line, in one ternary), and full-width punctuation is CORRECT
// inside the CJK locale. So the only safe scope is the string literal: a literal
// with no ideograph is a non-CJK literal, and full-width punctuation in it is a
// defect. Literals that do contain an ideograph are left untouched.
//
// Atomic by construction: the transform happens in memory and the file is only
// written if the leftover guard passes. Expect the first run to ABORT having
// changed nothing on disk -- that is the design working, and it is why a
// half-applied repair never lands. The abort lists the leftovers; extend MAP
// from that list and re-run.
//
// Usage: node scripts/repair-locale-contamination.mjs [path/to/content.ts]
// Then keep scripts/verify-guide-content.mjs (check 4) in CI so it cannot recur.

import { readFileSync, writeFileSync } from 'node:fs';

const FILE = process.argv[2] ?? 'src/components/guide/guideContent.ts';
const IDE0 = 0x4e00, IDE1 = 0x9fff;

// Full-width / CJK-form punctuation -> ASCII. Extend when the guard names more.
const MAP = {
  '\u3002': '.', '\uFF0C': ', ', '\u3001': ', ', '\uFF1B': '; ', '\uFF1A': ': ',
  '\uFF01': '! ', '\uFF1F': '? ', '\uFF0F': '/', '\uFF5C': ' | ', '\uFF3C': '\\',
  '\uFF08': '(', '\uFF09': ')', '\uFF05': '%', '\uFF0D': '-', '\uFF5E': '~', '\u301C': '~',
  '\u300C': '"', '\u300D': '"', '\u300E': '"', '\u300F': '"', '\u3000': ' ',
  '\u3014': '[', '\u3015': ']', '\u3010': '[', '\u3011': ']', '\u300A': '<', '\u300B': '>',
  '\uFF0B': '+', '\uFF1D': '=', '\uFF1C': '<', '\uFF1E': '>', '\uFF06': '&', '\uFF0A': '*', '\uFF03': '#', '\uFF20': '@',
};

const FULL = /[\u3000-\u303F\uFF00-\uFFEF]/;
// Single-quoted TS literals, honouring backslash escapes.
const LITERAL = /'(?:\\[\s\S]|[^'\\])*'/g;
const hasIdeograph = (s) =>
  [...s].some((c) => { const n = c.codePointAt(0); return n >= IDE0 && n <= IDE1; });

const orig = readFileSync(FILE, 'utf8');
let candidates = 0, changed = 0, skippedCjk = 0;
const samples = [];

const out = orig.replace(LITERAL, (lit) => {
  if (!FULL.test(lit)) return lit;                       // nothing full-width
  if (hasIdeograph(lit)) { skippedCjk++; return lit; }   // CJK locale: correct as written
  candidates++;
  let fixed = lit.replace(/[\u3000-\u303F\uFF00-\uFFEF]/g, (ch) => (ch in MAP ? MAP[ch] : ch));
  // Tidy only the whitespace our own substitutions can introduce: collapse runs
  // of spaces, and drop a space that now sits before closing punctuation.
  fixed = fixed.replace(/ {2,}/g, ' ').replace(/ ([.,;:!?)\]])/g, '$1');
  if (fixed === lit) return lit;
  changed++;
  if (samples.length < 18) samples.push(lit.slice(0, 74) + '\n   -> ' + fixed.slice(0, 74));
  return fixed;
});

console.log('literals with full-width punctuation, no ideograph :', candidates);
console.log('literals corrected                                  :', changed);
console.log('CJK literals deliberately skipped                   :', skippedCjk);
console.log('---');
for (const s of samples) console.log(s);

const leftovers = [...out.matchAll(LITERAL)].filter((m) => FULL.test(m[0]) && !hasIdeograph(m[0]));
if (leftovers.length) {
  console.error(`\nABORT: ${leftovers.length} non-CJK literal(s) still contain full-width punctuation -- nothing written.`);
  for (const m of leftovers.slice(0, 8)) console.error('  ' + m[0].slice(0, 95));
  console.error('Extend MAP with the characters above and re-run.');
  process.exit(1);
}
if (changed === 0) {
  console.error('ABORT: nothing changed -- already repaired, or the pattern moved. Nothing written.');
  process.exit(1);
}

writeFileSync(FILE, out);
console.log('\nwritten:', FILE);
