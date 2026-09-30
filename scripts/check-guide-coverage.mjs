#!/usr/bin/env node
/**
 * Verify that the in-app user guide actually covers every page and function.
 *
 * Why this exists: the guide's content is split between a `topics` data object
 * and ~15 language ternaries in code, and `topics` is typed with `Partial` at
 * every level -- so a missing page, a missing locale, or a missing field is
 * invisible to the compiler, and a page with no entry silently renders the
 * generic boilerplate instead of failing. That made "is the guide complete?"
 * unanswerable by reading either the data or the code alone.
 *
 * This calls the real `getGuideSection()` (the single entry point the modal
 * uses) for every page x locale and asserts:
 *   1. all eight GuideSection fields are non-empty;
 *   2. the page is not pure boilerplate. An unknown page returns exactly the
 *      generic text, so calling with a bogus key gives us the baseline to
 *      compare against without exporting `common`.
 *
 * The page list is read from the AppTab union in src/types, so adding a page to
 * the app fails this check until its guide exists.
 *
 * Run: node --experimental-strip-types scripts/check-guide-coverage.mjs
 */
import { readFileSync } from 'node:fs'

// Resolve everything from this script's location so the check works from any cwd.
const repoRoot = new URL('..', import.meta.url)
const GUIDE = new URL('src/components/guide/guideContent.ts', repoRoot).href
const { getGuideSection } = await import(GUIDE)

const LOCALES = ['zh-TW', 'en', 'es-MX']
const REQUIRED = ['title', 'purpose', 'principle', 'formula', 'interpretation', 'limits', 'recommendation', 'steps']
// Compared against the generic baseline: at least one of these must be specific.
const BESPOKE = ['purpose', 'principle', 'interpretation', 'formula', 'limits', 'recommendation']
// Full-width punctuation, CJK symbols and CJK ideographs. A non-Chinese locale
// must contain none of these: they leak in when text is copied from the zh-TW
// entry, and neither the compiler nor check-i18n-parity (which only compares key
// sets) can see it. Legitimate maths glyphs such as U+2212 minus and U+00D7
// multiply are deliberately outside these ranges.
const FORBIDDEN_IN_NON_ZH = /[\u3000-\u303F\uFF00-\uFFEF\u4E00-\u9FFF]/

// Pages the app exposes, straight from the AppTab union: take the declaration
// up to the first blank line and collect its quoted members.
const typesSrc = readFileSync(new URL('src/types/index.ts', repoRoot), 'utf8')
const unionStart = typesSrc.indexOf('export type AppTab')
const unionBlock = typesSrc.slice(unionStart, typesSrc.indexOf('\n\n', unionStart))
const appTabs = [...unionBlock.matchAll(/'([a-zA-Z]+)'/g)].map((m) => m[1])
if (appTabs.length < 10) {
  console.error(`could not parse AppTab (found ${appTabs.length} entries) -- update this script`)
  process.exit(1)
}

// Sub-tabs of the exploration page (from the tab items in Exploration.tsx).
const EXPLORATION_SUBTABS = ['distribution', 'trend', 'timeseries', 'grr']

const targets = []
for (const tab of appTabs) {
  if (tab === 'exploration') {
    for (const sub of EXPLORATION_SUBTABS) targets.push({ label: `exploration/${sub}`, tab, sub })
    targets.push({ label: 'exploration (default sub-tab)', tab, sub: undefined })
  } else {
    targets.push({ label: tab, tab, sub: undefined })
  }
}

let failures = 0
const genericField = (section) => section.title === '' && section.steps === ''

for (const { label, tab, sub } of targets) {
  for (const lang of LOCALES) {
    const section = getGuideSection(tab, sub, lang)
    const base = getGuideSection('__not_a_real_page__', undefined, lang)

    const empty = REQUIRED.filter((f) => !String(section[f] ?? '').trim())
    // `title` is synthesised by the modal from nav.<tab>; it is allowed to be blank.
    const emptyMeaningful = empty.filter((f) => f !== 'title')
    if (emptyMeaningful.length) {
      console.log(`  ${label} [${lang}]: empty ${emptyMeaningful.join(', ')}`)
      failures++
      continue
    }
    const isBoilerplate = BESPOKE.every((f) => section[f] === base[f])
    if (isBoilerplate) {
      console.log(`  ${label} [${lang}]: renders only the generic boilerplate (no guide entry?)`)
      failures++
      continue
    }
    // `contract` is rendered by the modal as well, but only when a page defines one
    // (today only dataImport). It is not in REQUIRED, so an empty contract would ship
    // silently as a blank section -- assert it whenever the page provides one.
    if (section.contract !== undefined && !String(section.contract).trim()) {
      console.log(`  ${label} [${lang}]: defined but empty contract`)
      failures++
      continue
    }
    // Locale integrity: a non-Chinese locale must carry no full-width or CJK
    // character at all. This is the check that would have caught the en/es
    // strings shipping '%GRR=GRR variation／total variation×100%；...' for so
    // long: the text rendered, so nothing else flagged it.
    if (lang !== 'zh-TW') {
      const dirty = [...REQUIRED, 'contract'].filter((f) => FORBIDDEN_IN_NON_ZH.test(String(section[f] ?? '')))
      if (dirty.length) {
        const hit = String(section[dirty[0]]).match(FORBIDDEN_IN_NON_ZH)[0]
        console.log(`  ${label} [${lang}]: full-width/CJK char ${JSON.stringify(hit)} in ${dirty.join(', ')}`)
        failures++
      }
    }
  }
}

// Structural parity: sentence counts per field, across locales. This is the sound
// completeness signal -- character ratios are not (a zh/en ratio of 0.25-0.5 is
// normal, since Chinese carries far more meaning per character and a full-width
// glyph is counted once while its English phrase takes many). Counted as a flag, not
// as proof: read the fields before calling a divergence a content gap.
// Sentence counter, deliberately conservative about ASCII periods. Splitting on every
// '.' counts the '.' in a decimal, in an ellipsis and in a step number as sentence ends,
// which flagged eight pages spuriously: '99.73%' split after '99.', 'F(x1,...,xp)'
// split three times, and '1. Select' split once per step. A CJK terminator always ends a
// sentence; an ASCII period only does when whitespace follows and the next character
// starts a sentence (capital or opening bracket).
const countSentences = (s) =>
  String(s ?? '')
    .split(/(?<=[。！？!?])\s*|(?<=\.)\s+(?=[A-Z(["'])/)
    .filter((x) => x.trim().length > 3).length

const PARITY_FIELDS = ['purpose', 'principle', 'formula', 'interpretation', 'limits', 'recommendation', 'steps']
let parityNotes = 0
for (const { label, tab, sub } of targets) {
  const counts = LOCALES.map((lang) => {
    const section = getGuideSection(tab, sub, lang)
    return [lang, PARITY_FIELDS.reduce((a, f) => a + countSentences(section[f]), 0)]
  })
  if (new Set(counts.map(([, n]) => n)).size > 1) {
    parityNotes++
    console.log(`  NOTE ${label}: sentence counts differ -- ${counts.map(([l, n]) => `${l}=${n}`).join(' ')}`)
  }
}

console.log(`checked ${targets.length} page(s) x ${LOCALES.length} locales`)
if (parityNotes) console.log(`${parityNotes} page(s) flagged for sentence-count divergence (informational, not a failure)`)
if (failures) {
  console.error(`\n${failures} guide gap(s) -- users would see missing or generic text on these pages.`)
  process.exit(1)
}
console.log('Every page has specific guide content in all three locales.')
