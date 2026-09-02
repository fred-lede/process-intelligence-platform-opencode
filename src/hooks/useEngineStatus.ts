import { useCallback, useEffect, useState } from 'react'
import { engineHealth, enginePing, type EngineHealth } from '../lib/engine'

export type EngineStatus =
  | { state: 'checking' }
  | { state: 'online'; health: EngineHealth }
  | { state: 'offline'; error: string }

/**
 * Monitors the Python engine's health. Polls on an interval so the UI
 * reflects engine restarts automatically.
 */
export function useEngineStatus(refreshMs = 5000): {
  status: EngineStatus
  refresh: () => Promise<void>
} {
  const [status, setStatus] = useState<EngineStatus>({ state: 'checking' })

  const refresh = useCallback(async () => {
    try {
      await enginePing()
      const health = await engineHealth()
      setStatus({ state: 'online', health })
    } catch (err) {
      setStatus({
        state: 'offline',
        error: err instanceof Error ? err.message : String(err),
      })
    }
  }, [])

  useEffect(() => {
    void refresh()
    const timer = setInterval(() => void refresh(), refreshMs)
    return () => clearInterval(timer)
  }, [refresh, refreshMs])

  return { status, refresh }
}