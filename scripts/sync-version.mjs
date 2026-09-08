import { readFile, writeFile } from 'node:fs/promises'
const version = (await readFile('VERSION', 'utf8')).trim()
if (!/^\d+\.\d+\.\d+$/.test(version)) throw new Error(`Invalid VERSION: ${version}`)
const files = [
  ['package.json', /("version"\s*:\s*")\d+\.\d+\.\d+(")/],
  ['package-lock.json', /("version"\s*:\s*")\d+\.\d+\.\d+(")/],
  ['src-tauri/Cargo.toml', /(^version\s*=\s*")\d+\.\d+\.\d+(")/m],
  ['src-tauri/tauri.conf.json', /("version"\s*:\s*")\d+\.\d+\.\d+(")/],
  ['engine/src/process_intelligence_engine/__init__.py', /(__version__\s*=\s*")\d+\.\d+\.\d+(")/],
]
for (const [path, pattern] of files) {
  const source = await readFile(path, 'utf8')
  await writeFile(path, source.replace(pattern, `$1${version}$2`))
}
console.log(`Synchronized project version to ${version}`)
