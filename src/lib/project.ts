import { save, open } from '@tauri-apps/plugin-dialog'
import { readTextFile, writeTextFile, exists } from '@tauri-apps/plugin-fs'
import type { FieldAssignment, SpecConfiguration } from '../stores/dataPipelineStore'
import type { QualityReport } from './engine'

export const PROJECT_FORMAT_VERSION = 1

export interface ProjectFile {
  version: number
  app: string
  savedAt: string
  import: {
    file_path: string
  }
  fields: FieldAssignment[] | null
  quality: QualityReport | null
  spec: SpecConfiguration | null
}

const PROJECT_FILTER = [{ name: 'Project', extensions: ['piproj.json'] }]

export function buildProjectFile(
  filePath: string,
  fields: FieldAssignment[],
  quality: QualityReport | null,
  spec: SpecConfiguration | null,
): ProjectFile {
  return {
    version: PROJECT_FORMAT_VERSION,
    app: 'process-intelligence-platform',
    savedAt: new Date().toISOString(),
    import: { file_path: filePath },
    fields: fields.length ? fields : null,
    quality,
    spec,
  }
}

export async function saveProjectFile(data: ProjectFile): Promise<string | null> {
  const target = await save({
    title: 'Save Project',
    defaultPath: `process-project.piproj.json`,
    filters: PROJECT_FILTER,
  })
  if (typeof target !== 'string') return null

  const serialized = JSON.stringify(data, null, 2)
  await writeTextFile(target, serialized)
  return target
}

export async function loadProjectFile(): Promise<ProjectFile | null> {
  const selected = await open({
    multiple: false,
    directory: false,
    filters: PROJECT_FILTER,
  })
  if (typeof selected !== 'string') return null
  if (!(await exists(selected))) {
    throw new Error(`Project file not found: ${selected}`)
  }
  const raw = await readTextFile(selected)
  const parsed = JSON.parse(raw) as ProjectFile
  if (parsed.app !== 'process-intelligence-platform') {
    throw new Error('Not a Process Intelligence Platform project file.')
  }
  if (parsed.version > PROJECT_FORMAT_VERSION) {
    throw new Error(
      `Project version ${parsed.version} is newer than supported (${PROJECT_FORMAT_VERSION}).`,
    )
  }
  return parsed
}