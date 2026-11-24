import { useCallback, useEffect, useState } from 'react'

export interface Settings {
  size: number // index into SIZES
  theme: 'system' | 'light' | 'dark'
  contrast: boolean
  palette: 'standard' | 'mono'
  reduceMotion: boolean
  voiceMemory: boolean
  phrases: string[] // custom quick phrases
  voice: string | null // Aura voice id; null = server default
}
export const SIZES = [
  { label: 'S', px: 18 }, { label: 'M', px: 22 }, { label: 'L', px: 26 }, { label: 'XL', px: 31 }, { label: 'XXL', px: 37 },
]
const KEY = 'voxli.settings.v1'

function load(): Settings {
  const sysReduce = typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches
  const base: Settings = { size: 1, theme: 'system', contrast: false, palette: 'standard', reduceMotion: sysReduce, voiceMemory: false, phrases: [], voice: null }
  try {
    return { ...base, ...JSON.parse(localStorage.getItem(KEY) ?? '{}') }
  } catch { return base }
}

const dark = matchMedia('(prefers-color-scheme: dark)')

export function useSettings(): [Settings, (p: Partial<Settings>) => void] {
  const [s, setS] = useState(load)
  const [sysDark, setSysDark] = useState(dark.matches)
  const update = useCallback((p: Partial<Settings>) => setS((cur) => ({ ...cur, ...p })), [])
  useEffect(() => {
    const f = () => setSysDark(dark.matches)
    dark.addEventListener('change', f)
    return () => dark.removeEventListener('change', f)
  }, [])
  useEffect(() => {
    try { localStorage.setItem(KEY, JSON.stringify(s)) } catch { /* private mode: settings just don't persist */ }
    const r = document.documentElement
    const theme = s.theme === 'system' ? (sysDark ? 'dark' : 'light') : s.theme
    r.style.setProperty('--cap', `${SIZES[s.size]?.px ?? 22}px`)
    r.dataset.theme = theme
    r.dataset.contrast = s.contrast ? 'high' : 'normal'
    r.dataset.reduce = s.reduceMotion ? '1' : '0'
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', getComputedStyle(r).getPropertyValue('--bg').trim())
  }, [s, sysDark])
  return [s, update]
}
