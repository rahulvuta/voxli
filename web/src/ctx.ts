import { createContext, useContext } from 'react'
import type { Look } from './palette'
import type { Settings } from './settings'
import type { State, Utt } from './store'

export interface Ctx {
  state: State
  settings: Settings
  groups: Map<string, Utt[]>
  hidden: Set<string>
  sorted: Utt[]
  look(skey: string): Look
  name(skey: string): string
  jump(ukey: string): void
  openSpeaker(skey: string): void
}
export const C = createContext<Ctx | null>(null)
export const useCtx = () => useContext(C)!
