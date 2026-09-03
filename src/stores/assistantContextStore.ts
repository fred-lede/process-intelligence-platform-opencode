import { create } from 'zustand'
import type { AppTab } from '../types'

/**
 * Holds a concise text summary of the real data/charts currently shown on each
 * analysis page. Feature pages call `setContext` whenever they have meaningful
 * computed results; the AI assistant reads it to interpret the actual data
 * instead of only describing the page's features.
 */
interface AssistantContextState {
  context: Partial<Record<AppTab, string>>
  setContext: (tab: AppTab, summary: string) => void
}

export const useAssistantContextStore = create<AssistantContextState>((set) => ({
  context: {},
  setContext: (tab, summary) =>
    set((state) => ({ context: { ...state.context, [tab]: summary } })),
}))
