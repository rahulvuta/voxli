import { useCallback, useEffect, useState } from 'react'

export interface Settings {
  size: number // index into SIZES
  contrast: boolean
  palette: 'standard' | 'mono'
  reduceMotion: boolean
  voiceMemory: boolean
  phrases: string[] // custom quick phrases
}
export const SIZES = [
  { label: 'S', px: 17 }, { label: 'M', px: 20 }, { label: 'L', px: 24 }, { label: 'XL', px: 29 }, { label: 'XXL', px: 35 },
]
const KEY = 'voxli.settings.v1'

function load(): Settings {
  const sysReduce = typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches
  const base: Settings = { size: 1, contrast: false, palette: 'standard', reduceMotion: sysReduce, voiceMemory: false, phrases: [] }
  try {
    return { ...base, ...JSON.parse(localStorage.getItem(KEY) ?? '{}') }
  } catch { return base }
}

export function useSettings(): [Settings, (p: Partial<Settings>) => void] {
  const [s, setS] = useState(load)
  const update = useCallback((p: Partial<Settings>) => setS((cur) => ({ ...cur, ...p })), [])
  useEffect(() => {
    try { localStorage.setItem(KEY, JSON.stringify(s)) } catch { /* private mode: settings just don't persist */ }
    const r = document.documentElement
    r.style.setProperty('--cap', `${SIZES[s.size]?.px ?? 20}px`)
    r.dataset.contrast = s.contrast ? 'high' : 'normal'
    r.dataset.reduce = s.reduceMotion ? '1' : '0'
  }, [s])
  return [s, update]
}
