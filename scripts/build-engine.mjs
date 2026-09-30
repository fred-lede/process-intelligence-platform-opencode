#!/usr/bin/env node
/**
 * Build the Python analysis engine into a self-contained, frozen executable
 * and stage it for the Tauri bundler.
 *
 * Why this exists
 * ---------------
 * The Tauri shell spawns the engine as a child process. On a developer
 * machine it can point at `engine/.venv/`, but an installed app has no repo
 * checkout, no virtualenv and (usually) no Python at all. This script freezes
 * the engine with PyInstaller and copies the result to
 * `src-tauri/resources/engine/`, which `tauri.conf.json` ships via
 * `bundle.resources`. At runtime the Rust side resolves that directory from
 * `resource_dir()` — see `src-tauri/src/engine/mod.rs`.
 *
 * Usage (from the repository root)
 * --------------------------------
 *   node scripts/build-engine.mjs                  # base bundle (no DL stack)
 *   node scripts/build-engine.mjs --with-dl        # + torch / pytorch-forecasting
 *   node scripts/build-engine.mjs --with-tensorflow
 *   node scripts/build-engine.mjs --with-cuda      # + CUDA runtime libs (~450 MB)
 *   node scripts/build-engine.mjs --skip-smoke     # skip the engine/ping check
 *
 * CPU vs CUDA
 * -----------
 * The default bundle is CPU-only and drops the `nvidia-*` CUDA runtime wheels
 * that xgboost pulls in on Linux; they are ~450 MB, about a third of the whole
 * bundle, for a path that is off by default and additionally needs a system
 * CUDA toolkit and an NVIDIA GPU. Build with `--with-cuda` when a GPU machine
 * actually needs them. (The CPU bundle runs on GPU machines too -- it simply
 * trains on the CPU.)
 *
 * PyInstaller cannot cross-compile: run this on each target OS (CI does).
 */

import { spawn, spawnSync } from 'node:child_process'
import { cpSync, existsSync, mkdirSync, readdirSync, rmSync, statSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const engineDir = join(repoRoot, 'engine')
const specFile = join(engineDir, 'process-intelligence-engine.spec')
const buildDir = join(engineDir, 'build')
const distDir = join(buildDir, 'dist')
const workDir = join(buildDir, 'work')
const stageDir = join(repoRoot, 'src-tauri', 'resources', 'engine')

const flags = new Set(process.argv.slice(2))
const withDl = flags.has('--with-dl')
const withTensorflow = flags.has('--with-tensorflow')
const withCuda = flags.has('--with-cuda')
const skipSmoke = flags.has('--skip-smoke')

// How long the frozen engine gets to answer engine/ping. Overridable because a cold
// first launch on macOS (Gatekeeper evaluating a binary it has not seen before) can
// take far longer than a warm one, and a hard 120s made that look like a hang.
const smokeTimeoutMs = Number(process.env.SMOKE_TIMEOUT_MS ?? 120_000)

const isWindows = process.platform === 'win32'
const exeName = isWindows ? 'process-intelligence-engine.exe' : 'process-intelligence-engine'
const venvPython = join(engineDir, '.venv', isWindows ? 'Scripts' : 'bin', isWindows ? 'python.exe' : 'python')

function run(command, args, options = {}) {
  const printable = [command, ...args].join(' ')
  console.log(`\n$ ${printable}`)
  const result = spawnSync(command, args, {
    stdio: 'inherit',
    cwd: options.cwd ?? repoRoot,
    env: { ...process.env, ...(options.env ?? {}) },
  })
  if (result.error) throw result.error
  if (result.status !== 0) {
    throw new Error(`command failed (exit ${result.status}): ${printable}`)
  }
}

function uv(args, options = {}) {
  run('uv', args, options)
}

function ensureVenv() {
  if (!existsSync(venvPython)) {
    console.log(`creating engine virtualenv (python 3.12) at ${venvPython}`)
    uv(['venv', '--python', '3.12', '--directory', engineDir])
  } else {
    console.log(`reusing engine virtualenv at ${venvPython}`)
  }
}

function installBuildDeps() {
  // Runtime, dev and build-only dependencies all come from the locked
  // environment, so the frozen engine cannot drift from what the tests ran
  // against. PyInstaller is declared in the `bundle` extra for that reason.
  if (existsSync(join(engineDir, 'uv.lock'))) {
    uv(['sync', '--project', engineDir, '--extra', 'dev', '--extra', 'bundle'])
  } else {
    uv(['pip', 'install', '--python', venvPython, '-e', engineDir])
    uv(['pip', 'install', '--python', venvPython, 'pyinstaller'])
  }
}

function buildFrozenEngine() {
  rmSync(distDir, { recursive: true, force: true })
  rmSync(workDir, { recursive: true, force: true })
  run(
    venvPython,
    [
      '-m',
      'PyInstaller',
      '--clean',
      '--noconfirm',
      '--distpath',
      distDir,
      '--workpath',
      workDir,
      specFile,
    ],
    {
      cwd: engineDir,
      env: {
        PIE_WITH_DL: withDl ? '1' : '0',
        PIE_WITH_TENSORFLOW: withTensorflow ? '1' : '0',
        PIE_WITH_CUDA: withCuda ? '1' : '0',
      },
    },
  )
}

function stageForTauri() {
  const built = join(distDir, 'process-intelligence-engine')
  if (!existsSync(built)) {
    throw new Error(`PyInstaller did not produce ${built}`)
  }
  // Wipe first so a shrinking bundle never leaves stale files behind.
  rmSync(stageDir, { recursive: true, force: true })
  mkdirSync(dirname(stageDir), { recursive: true })
  cpSync(built, stageDir, { recursive: true })
  // The staging tree is gitignored; restore the tracked placeholder that the
  // wipe above removed so a fresh clone still has the directory Tauri needs.
  writeFileSync(
    join(stageDir, '.gitkeep'),
    [
      '# The frozen analysis engine is staged here by scripts/build-engine.mjs and',
      '# shipped by Tauri via `bundle.resources` in tauri.conf.json',
      '# (source "resources/engine/" -> target "$RESOURCE/engine/").',
      '#',
      '# Contents are gitignored. Release builds always regenerate them; see',
      '# .github/workflows/release.yml.',
      '',
    ].join('\n'),
  )
  console.log(`\nstaged engine -> ${stageDir}`)
}

function dirSize(path) {
  let total = 0
  for (const entry of readdirSync(path, { withFileTypes: true })) {
    const child = join(path, entry.name)
    total += entry.isDirectory() ? dirSize(child) : statSync(child).size
  }
  return total
}

export function smokeTest(exeOverride) {
  const exe = exeOverride ?? join(stageDir, exeName)
  if (!existsSync(exe)) throw new Error(`staged executable missing: ${exe}`)

  console.log('\nsmoke test: engine/ping against the frozen engine')
  return new Promise((resolvePromise, rejectPromise) => {
    const child = spawn(exe, [], { stdio: ['pipe', 'pipe', 'pipe'], cwd: stageDir })
    let stdout = ''
    let stderr = ''
    let settled = false

    const finish = (error) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      try {
        child.kill()
      } catch {
        /* already gone */
      }
      if (error) rejectPromise(error)
      else resolvePromise()
    }

    const timer = setTimeout(
      () =>
        finish(
          new Error(
            `engine did not answer engine/ping within ${Math.round(smokeTimeoutMs / 1000)}s` +
              ` (raise it with SMOKE_TIMEOUT_MS)` +
              `\n--- stderr ---\n${
                stderr.slice(-4000) ||
                '(empty -- the process produced no stderr, which points to a process that is alive but not answering, rather than one crashing with a traceback)'
              }`,
          ),
        ),
      smokeTimeoutMs,
    )

    child.on('error', (e) => finish(e))
    // Report an early death as an early death. Without this handler a binary killed at
    // startup -- Gatekeeper quarantine on a freshly rebuilt executable, a missing
    // dylib, an architecture mismatch -- was indistinguishable from a slow one: the
    // script waited out the entire timeout and then blamed a lack of response, with an
    // empty stderr and no exit code to go on.
    child.on('exit', (code, signal) => {
      if (settled) return
      finish(
        new Error(
          `engine exited before answering engine/ping (code ${code ?? 'null'}, signal ${signal ?? 'none'})` +
            `\n--- stderr ---\n${stderr.slice(-4000) || '(empty)'}`,
        ),
      )
    })
    child.stderr.on('data', (chunk) => {
      stderr += chunk.toString()
    })
    child.stdout.on('data', (chunk) => {
      stdout += chunk.toString()
      const line = stdout.split('\n').find((l) => l.trim().length > 0)
      if (!line) return
      let parsed
      try {
        parsed = JSON.parse(line)
      } catch {
        return // partial line; wait for more
      }
      if (parsed?.error) {
        finish(new Error(`engine returned an error to engine/ping: ${JSON.stringify(parsed.error)}`))
        return
      }
      if (parsed?.result?.pong === true) {
        console.log(`smoke test passed (engine version ${parsed.result.version ?? 'unknown'})`)
        finish()
        return
      }
      finish(new Error(`unexpected engine/ping response: ${line}`))
    })

    // A child that dies before it reads stdin makes this pipe raise EPIPE, and an
    // unhandled 'error' event on a stream takes the whole process down with a stack
    // trace -- hiding the exit that actually happened. Swallow it here; the child's
    // 'exit' handler is what reports the news.
    child.stdin.on('error', () => {})
    child.stdin.write(`${JSON.stringify({ id: '1', method: 'engine/ping', params: {} })}\n`)
  })
}

async function main() {
  if (!existsSync(specFile)) throw new Error(`spec not found: ${specFile}`)

  console.log(`building frozen engine for ${process.platform}/${process.arch}`)
  console.log(`  with DL stack: ${withDl ? 'yes' : 'no'}   with tensorflow: ${withTensorflow ? 'yes' : 'no'}   with CUDA: ${withCuda ? 'yes' : 'no'}`)

  ensureVenv()
  installBuildDeps()
  buildFrozenEngine()
  stageForTauri()
  if (!skipSmoke) await smokeTest()

  const mb = (dirSize(stageDir) / (1024 * 1024)).toFixed(1)
  console.log(`\ndone: ${stageDir} (${mb} MB)`)
  console.log('tauri.conf.json ships src-tauri/resources/engine/ via bundle.resources')
}

// Only run the build when invoked directly: importing this module (from a test, say)
// must not kick off a full PyInstaller build as a side effect.
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch((error) => {
    console.error(`\nbuild-engine failed: ${error.message}`)
    process.exit(1)
  })
}
