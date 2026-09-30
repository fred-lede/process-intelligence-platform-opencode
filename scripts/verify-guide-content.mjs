#!/usr/bin/env node
// Structural probe for localized in-app guide content.
//
// Usage (from the repo root, against the real module — never a copy):
//   node --experimental-strip-types scripts/verify-guide-content.mjs <page-id> [...]
//   GUIDE_MODULE=src/components/guide/guideContent.ts \
//   LOCALES=zh-TW,en,es-MX \
//   REQUIRED='LSL,LCL,Cpk' \
//   node --experimental-strip-types scripts/verify-guide-content.mjs processDefine
//
// What it checks, and why each check exists:
//   1. key-set parity across locales  — CI guard parity; a locale missing a field
//      ships a blank section.
//   2. sentence-count parity per field — the ONLY sound completeness signal.
//      Character counts are worthless here: zh/en ratios of 0.25-0.5 are normal.
//   3. required-token presence per locale — proves the enumeration actually landed
//      in every locale (a key can exist and be empty).
//   4. locale integrity — a non-Chinese locale must contain no full-width/CJK
//      character at all. Checks 1-3 all pass on contaminated text, and so does a
//      key-parity CI guard, because no key is missing.

const MODULE = process.env.GUIDE_MODULE ?? 'src/components/guide/guideContent.ts';
const LOCALES = (process.env.LOCALES ?? 'zh-TW,en,es-MX').split(',').map((s) => s.trim());
const REQUIRED = (process.env.REQUIRED ?? '').split(',').map((s) => s.trim()).filter(Boolean);

const FIELDS = [
  'purpose', 'principle', 'formula', 'interpretation',
  'limits', 'recommendation', 'steps',
];

const pages = process.argv.slice(2);
if (pages.length === 0) {
  console.error('usage: node scripts/verify-guide-content.mjs <page-id> [<page-id> ...]');
  console.error('  env: GUIDE_MODULE, LOCALES, REQUIRED');
  process.exit(2);
}

// Sentence counter: split on terminal punctuation of ANY script. Used for
// structural comparison, so it must not assume Latin punctuation.
const sentences = (s) =>
  String(s ?? '')
    .split(/(?<=[.。！？!?])\s*/)
    .filter((x) => x.trim().length > 3).length;

const url = new URL(MODULE, new URL('file://' + process.cwd() + '/'));
const mod = await import(url.href);
if (typeof mod.getGuideSection !== 'function') {
  console.error(`error: ${MODULE} does not export getGuideSection()`);
  process.exit(2);
}

let failures = 0;

for (const page of pages) {
  const sections = Object.fromEntries(
    LOCALES.map((l) => [l, mod.getGuideSection(page, undefined, l)]),
  );

  // 1. key-set parity: compare the set of fields that actually carry content.
  const keysets = Object.fromEntries(
    LOCALES.map((l) => {
      const s = sections[l] ?? {};
      return [l, Object.keys(s).filter((k) => String(s[k] ?? '').trim()).sort().join('|')];
    }),
  );
  if (new Set(Object.values(keysets)).size > 1) {
    failures++;
    console.log(`FAIL ${page}: key sets differ across locales`);
    for (const l of LOCALES) {
      console.log(`       ${l.padEnd(6)} ${keysets[l].split('|').length} populated keys`);
    }
  }

  // 2 + 3. per-field structure and required tokens.
  const rows = LOCALES.map((l) => {
    const s = sections[l] ?? {};
    return {
      l,
      chars: FIELDS.reduce((a, f) => a + String(s[f] ?? '').length, 0),
      sents: FIELDS.reduce((a, f) => a + sentences(s[f]), 0),
    };
  });

  const en = rows.find((r) => r.l === 'en') ?? rows[0];
  console.log(`\n${page}`);
  for (const r of rows) {
    const ratio = en.chars ? (r.chars / en.chars).toFixed(2) : 'n/a';
    console.log(
      `  ${r.l.padEnd(6)} ${String(r.chars).padStart(5)} chars  ` +
      `${String(r.sents).padStart(3)} sentences  ratio=${ratio} (informational only)`,
    );
  }

  // Sentence-count divergence is the real defect signal. Even then: read the
  // fields before declaring a gap. Counting is a flag, not proof.
  if (new Set(rows.map((r) => r.sents)).size > 1) {
    console.log(`  NOTE sentence counts differ: ` + rows.map((r) => `${r.l}=${r.sents}`).join(' '));
    console.log(`       Read the fields before calling it a gap.`);
  }

  for (const token of REQUIRED) {
    const missing = LOCALES.filter(
      (l) => !FIELDS.map((f) => (sections[l] ?? {})[f] ?? '').join(' ').includes(token),
    );
    if (missing.length) {
      failures++;
      console.log(`  FAIL token ${JSON.stringify(token)} absent in: ${missing.join(', ')}`);
      console.log(`       Confirm the literal form first — a localized or inflected string`);
      console.log(`       ("Apéndice" for "Appendix") is a probe false negative, not a bug.`);
    } else {
      console.log(`  ok   token ${JSON.stringify(token)} present in all ${LOCALES.length} locales`);
    }
  }

  // 4. locale integrity. This is the one class of defect the checks above cannot
  // reach: the key exists, the sentence count matches, the token is present, and
  // the text renders — it is simply the wrong alphabet's punctuation. It shipped
  // for months as '%GRR=GRR variation／total variation×100%；...' in English.
  // Legitimate maths glyphs (U+2212 minus, U+00D7 multiply, Greek letters) sit
  // outside these ranges and are unaffected.
  const FORBIDDEN_IN_NON_ZH = /[\u3000-\u303F\uFF00-\uFFEF\u4E00-\u9FFF]/;
  for (const l of LOCALES) {
    if (l === 'zh-TW') continue;
    const s = sections[l] ?? {};
    const dirty = FIELDS.filter((f) => FORBIDDEN_IN_NON_ZH.test(String(s[f] ?? '')));
    if (dirty.length) {
      failures++;
      const hit = String(s[dirty[0]]).match(FORBIDDEN_IN_NON_ZH)[0];
      console.log(`  FAIL ${l}: full-width/CJK char ${JSON.stringify(hit)} in ${dirty.join(', ')}`);
      console.log(`       Repair with scripts/repair-locale-contamination.mjs.`);
    }
  }
}

console.log('');
if (failures) {
  console.log(`${failures} check(s) failed.`);
  process.exit(1);
}
console.log('All structural checks passed.');
