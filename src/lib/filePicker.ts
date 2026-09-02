import { open } from '@tauri-apps/plugin-dialog'

const DATA_FILE_FILTER = [
  { name: 'Data Files', extensions: ['csv', 'xlsx', 'xls'] },
  { name: 'CSV', extensions: ['csv'] },
  { name: 'Excel', extensions: ['xlsx', 'xls'] },
]

/**
 * Open a native file dialog restricted to Excel/CSV files.
 * Returns the selected path or null if cancelled.
 */
export async function pickDataFile(): Promise<string | null> {
  const selected = await open({
    multiple: false,
    directory: false,
    filters: DATA_FILE_FILTER,
  })
  if (typeof selected === 'string') return selected
  return null
}