import { create } from 'zustand'

interface GuideContextState { subtab?: string; setSubtab: (subtab?: string) => void }
export const useGuideContextStore = create<GuideContextState>((set) => ({ subtab: undefined, setSubtab: (subtab) => set({ subtab }) }))
