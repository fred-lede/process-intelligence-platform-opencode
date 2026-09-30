// Exercises the real smokeTest() from build-engine.mjs against stub executables.
//
// Written because the smoke test used to have no child.on('exit') handler, so a frozen
// engine that died at startup was reported as "did not answer within 120s" with an empty
// stderr -- the exit code was thrown away, which is exactly the information needed to
// tell a Gatekeeper kill from a slow start.
//
// Run with a short timeout so the hang case does not take 120s:
//   SMOKE_TIMEOUT_MS=1500 node scripts/test-smoke-timeout.mjs

import { chmodSync, mkdtempSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { smokeTest } from './build-engine.mjs'

const dir = mkdtempSync(join(tmpdir(), 'smoke-'))
const stub = (name, body) => {
  const p = join(dir, name)
  writeFileSync(p, `#!/bin/sh\n${body}\n`)
  chmodSync(p, 0o755)
  return p
}

const run = async (name, exe) => {
  const started = Date.now()
  try {
    await smokeTest(exe)
    return { name, ms: Date.now() - started, error: null, full: '' }
  } catch (e) {
    return { name, ms: Date.now() - started, error: e.message.split('\n')[0], full: e.message }
  }
}

const cases = [
  await run('dies-at-startup', stub('dies', 'exit 3')),
  await run('answers-pong', stub('pong', `printf '%s\\n' '{"id":"1","result":{"pong":true,"version":"test"}}'`)),
  await run('silent-hang', stub('hang', 'sleep 30')),
]

const budget = Number(process.env.SMOKE_TIMEOUT_MS ?? 120_000)
let failures = 0

for (const c of cases) {
  const line = `  ${c.name.padEnd(18)} ${String(c.ms).padStart(5)}ms  ${c.error ?? 'resolved OK'}`
  console.log(line)

  if (c.name === 'dies-at-startup') {
    // Must be reported as an exit, must name the code, and must not wait out the timer.
    if (!c.error || !/exited before answering/.test(c.error) || !/code 3/.test(c.error)) {
      console.log('    FAIL: expected an exit report naming code 3')
      failures++
    } else if (c.ms > budget / 2) {
      console.log(`    FAIL: took ${c.ms}ms -- it waited for the timer instead of reporting the exit`)
      failures++
    }
  }
  if (c.name === 'answers-pong' && c.error) {
    console.log('    FAIL: a valid pong response should resolve, not error')
    failures++
  }
  if (c.name === 'silent-hang') {
    if (!c.error || !/did not answer/.test(c.error)) {
      console.log('    FAIL: expected the timeout message for a silent hang')
      failures++
    } else if (!/no stderr/.test(c.full)) {
      console.log('    FAIL: the timeout message should explain that stderr was empty')
      failures++
    }
  }
}

console.log(failures ? `\n${failures} smoke-test assertion(s) failed` : '\nall smoke-test assertions passed')
process.exit(failures ? 1 : 0)
