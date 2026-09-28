#!/usr/bin/env node
/**
 * Fail if the three locale files do not expose exactly the same key set.
 *
 * A missing key does not throw at runtime -- i18next renders the raw key or
 * falls back to English -- so drift is invisible until a user reports a
 * half-translated screen. That is exactly what happened here: es-MX was
 * missing the six `settings.lightgbmDevice*` keys, so the LightGBM device
 * selector showed raw keys in Spanish, and en/zh-TW disagreed on the name of
 * the (already dead) exploration guide block.
 *
 * Run from the repository root. Exits non-zero with the offending keys.
 */
import { readFileSync } from 'node:fs'

const LOCALES = ['en', 'zh-TW', 'es-MX']
const DIR = 'src/i18n'

function flatten(value, prefix = '') {
  const keys = new Set()
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    for (const [k, v] of Object.entries(value)) {
      for (const nested of flatten(v, prefix ? `${prefix}.${k}` : k)) keys.add(nested)
    }
  } else {
    keys.add(prefix)
  }
  return keys
}

const sets = {}
for (const locale of LOCALES) {
  sets[locale] = flatten(JSON.parse(readFileSync(`${DIR}/${locale}.json`, 'utf8')))
}

const union = new Set(Object.values(sets).flatMap((s) => [...s]))
const problems = []
for (const key of [...union].sort()) {
  const missing = LOCALES.filter((l) => !sets[l].has(key))
  if (missing.length) problems.push(`  ${key}  missing from: ${missing.join(', ')}`)
}

for (const locale of LOCALES) {
  console.log(`${locale.padEnd(6)} ${sets[locale].size} keys`)
}

if (problems.length) {
  console.error(`\ni18n key sets diverge (${problems.length} key(s)):\n${problems.join('\n')}`)
  process.exit(1)
}
console.log('\nAll locales expose the same key set.')
