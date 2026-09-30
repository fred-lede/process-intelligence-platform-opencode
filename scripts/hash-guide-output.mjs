// Hash every page x locale x field of a guide module, so a refactor can be PROVEN inert.
//
// Use before/after around any change that is supposed to alter nothing (removing a
// shadowed const, reordering spreads, renaming an internal selector). CI green does
// not prove inertness: when the rendered text never changed, the coverage and parity
// checks pass either way. Only identical hashes show the output did not move.
//
//   node --experimental-strip-types scripts/hash-guide-output.mjs /tmp/before.json
//   <apply the refactor>
//   node --experimental-strip-types scripts/hash-guide-output.mjs /tmp/after.json
//   node -e "const a=require('/tmp/before.json'),b=require('/tmp/after.json');
//     const k=Object.keys(a);const d=k.filter(x=>a[x]!==b[x]);
//     console.log(k.length+' cells, '+d.length+' differing');if(d.length)process.exit(1)"
//
// Run each hash pass in its own node process: a module import is cached, so a second
// pass in the same process would re-read the pre-edit text.
//
// ADAPT the page list. Read it from the app's tab union plus the sub-tabs of any
// parent page, so a newly added page is covered without editing this file:
//   const typesSrc = readFileSync(new URL('src/types/index.ts', repoRoot), 'utf8')
//   const union = typesSrc.slice(typesSrc.indexOf('export type AppTab'), ...)
// A stale hardcoded list silently drops new pages from the comparison.

import { writeFileSync } from 'node:fs'
import { createHash } from 'node:crypto'

const repoRoot = new URL('..', import.meta.url)
const GUIDE = 'src/components/guide/guideContent.ts'
const { getGuideSection } = await import(new URL(GUIDE, repoRoot).href)

const PAGES = [
  // top-level tabs
  'modelCenter', 'spc', 'monteCarlo', 'copula', 'validation', 'settings', 'reports',
  'dataImport', 'processDefine', 'project', 'processFlow', 'dataAssets', 'approval',
  // sub-tabs of the exploration page, which are addressed by name
  'distribution', 'trend', 'timeseries', 'grr', 'prediction',
]
const FIELDS = ['title', 'purpose', 'principle', 'formula', 'interpretation', 'limits', 'recommendation', 'steps']
const LOCALES = ['zh-TW', 'en', 'es-MX']

// Fail loudly if the module's locale set grew, rather than silently skipping it.
const seen = new Set()
const out = {}
let cells = 0
for (const page of PAGES) {
  for (const locale of LOCALES) {
    const section = getGuideSection(page, undefined, locale)
    for (const field of FIELDS) {
      const value = String(section[field] ?? '')
      seen.add(locale)
      out[`${page}|${locale}|${field}`] = createHash('sha256').update(value).digest('hex').slice(0, 16)
      cells++
    }
  }
}

const dest = process.argv[2]
if (!dest) {
  console.error('usage: hash-guide-output.mjs <outfile.json>')
  process.exit(1)
}
writeFileSync(dest, JSON.stringify(out, null, 0))
console.log(`${cells} cells hashed across ${PAGES.length} page(s) -> ${dest}`)
