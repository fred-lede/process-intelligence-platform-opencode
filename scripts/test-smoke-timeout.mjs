// Exercises the real smokeTest() from build-engine.mjs against stub executables.
//
// Written because the smoke test used to have no child.on('exit') handler, so a frozen
// engine that died at startup was reported as "did not answer within 120s" with an empty
// stderr -- the exit code was thrown away, which is exactly the information needed to
// tell a Gatekeeper kill from a slow start.
//
// Extended for the DL probe: engine/ping alone passed a bundle whose torch could not
// import, because torch is imported lazily. The probe cases below answer ping and then
// either fail or succeed the device probe, and assert the smoke test reacts to each.
//
// POSIX-only: the stubs are #!/bin/sh scripts.
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

const PONG = JSON.stringify({ id: 'ping', result: { pong: true, version: 'test' } })
const PROBE_OK = JSON.stringify({
  id: 'probe',
  result: {
    torch: {
      installed: true,
      import_ok: true,
      cuda_available: false,
      version: '2.14.1+cu132',
      reason: 'torch.cuda.is_available() is False',
    },
  },
})
const PROBE_BROKEN = JSON.stringify({
  id: 'probe',
  result: {
    torch: {
      installed: true,
      import_ok: false,
      cuda_available: false,
      reason: "import failed: ModuleNotFoundError: No module named 'torchgen'",
    },
  },
})

// Answers each request line by line; the engine keeps stdin open, so the loop blocks
// after the last reply until the smoke test kills the child.
const responder = (pong, probe) =>
  `while IFS= read -r line; do
  case "$line" in
    *engine/ping*) printf '%s\\n' '${pong}' ;;
    *system/device_probe*) printf '%s\\n' '${probe}' ;;
  esac
done`

const run = async (name, exe, opts) => {
  const started = Date.now()
  try {
    await smokeTest(exe, opts)
    return { name, ms: Date.now() - started, error: null, full: '' }
  } catch (e) {
    return { name, ms: Date.now() - started, error: e.message.split('\n')[0], full: e.message }
  }
}

const cases = [
  await run('dies-at-startup', stub('dies', 'exit 3')),
  await run('answers-pong', stub('pong', responder(PONG, PROBE_OK))),
  await run('silent-hang', stub('hang', 'sleep 30')),
  await run('dl-import-ok', stub('dlok', responder(PONG, PROBE_OK)), { probe: true }),
  await run('dl-import-broken', stub('dlbad', responder(PONG, PROBE_BROKEN)), { probe: true }),
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
  if (c.name === 'dl-import-ok' && c.error) {
    console.log('    FAIL: a probe with torch.import_ok=true should resolve, not error')
    failures++
  }
  if (c.name === 'dl-import-broken') {
    if (!c.error || !/torch does not import/.test(c.error)) {
      console.log('    FAIL: a probe with torch.import_ok=false must fail the build')
      failures++
    }
  }
}

console.log(failures ? `\n${failures} smoke-test assertion(s) failed` : '\nall smoke-test assertions passed')
process.exit(failures ? 1 : 0)
