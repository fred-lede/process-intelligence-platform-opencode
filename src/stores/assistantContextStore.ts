import { create } from 'zustand'
import type { AppTab } from '../types'
import type { AssistantContext } from '../lib/engine'

/**
 * Holds a concise text summary of the real data/charts currently shown on each
 * analysis page. Feature pages call `setContext` whenever they have meaningful
 * computed results; the AI assistant reads it to interpret the actual data
 * instead of only describing the page's features.
 */
interface AssistantContextState {
  context: Partial<Record<AppTab, string>>
  setContext: (tab: AppTab, summary: string) => void
  activeProjectId: string | null
  setActiveProjectId: (projectId: string | null) => void
  getCurrentContext: (tab: AppTab) => AssistantContext
}

export const useAssistantContextStore = create<AssistantContextState>((set, get) => ({
  context: {},
  activeProjectId: null,
  setActiveProjectId: (activeProjectId) => set((state) => ({
    activeProjectId,
    context: state.activeProjectId === activeProjectId ? state.context : {},
  })),
  getCurrentContext: (tab) => ({
    tab,
    summary: get().activeProjectId ? get().context[tab] ?? '' : '',
    project_id: get().activeProjectId,
  }),
  setContext: (tab, summary) =>
    set((state) => ({ context: { ...state.context, [tab]: summary } })),
}))
