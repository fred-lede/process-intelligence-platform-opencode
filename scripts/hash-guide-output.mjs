// Hash every page x locale x field of the guide so a refactor can be proven inert.
// Usage: node scripts/hash-guide-output.mjs [outfile]
import { writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';

const repoRoot = new URL('..', import.meta.url)
const { getGuideSection } = await import(new URL('src/components/guide/guideContent.ts', repoRoot).href)

const PAGES = ['modelCenter', 'spc', 'monteCarlo', 'copula', 'validation', 'settings', 'reports',
  'dataImport', 'processDefine', 'project', 'processFlow', 'dataAssets', 'approval',
  'distribution', 'trend', 'timeseries', 'grr', 'prediction',
  'exploration', 'data-assets', 'model-center', 'report']
const FIELDS = ['title', 'purpose', 'principle', 'formula', 'interpretation', 'limits', 'recommendation', 'steps']
const LOCALES = ['zh-TW', 'en', 'es-MX']

const out = {}
let cells = 0
for (const p of PAGES) {
  for (const l of LOCALES) {
    const s = getGuideSection(p, undefined, l)
    for (const f of FIELDS) {
      out[`${p}|${l}|${f}`] = createHash('sha256').update(String(s[f] ?? '')).digest('hex').slice(0, 16)
      cells++
    }
  }
}
const dest = process.argv[2]
writeFileSync(dest, JSON.stringify(out, null, 0))
console.log(`${cells} cells hashed -> ${dest}`)
