import { readFile, writeFile } from 'node:fs/promises'

const version = (await readFile('VERSION', 'utf8')).trim()
if (!/^\d+\.\d+\.\d+$/.test(version)) throw new Error(`Invalid VERSION: ${version}`)

const replacements = [
  ['package.json', /("version"\s*:\s*")\d+\.\d+\.\d+(")/, `$1${version}$2`],
  ['package-lock.json', /("version"\s*:\s*")\d+\.\d+\.\d+(")/g, `$1${version}$2`],
  ['src-tauri/Cargo.toml', /(^version\s*=\s*")\d+\.\d+\.\d+(")/m, `$1${version}$2`],
  ['src-tauri/tauri.conf.json', /("version"\s*:\s*")\d+\.\d+\.\d+(")/, `$1${version}$2`],
  ['engine/src/process_intelligence_engine/__init__.py', /(__version__\s*=\s*")\d+\.\d+\.\d+(")/, `$1${version}$2`],
]
for (const [path, pattern, replacement] of replacements) {
  const source = await readFile(path, 'utf8')
  await writeFile(path, source.replace(pattern, replacement))
}
console.log(`Synchronized project version to ${version}`)
