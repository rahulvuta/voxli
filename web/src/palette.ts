// Colours live in CSS (--spk0..7, tuned per theme). Colour is never the only cue: every speaker also has a shape and an initial.
export const SHAPES = ['circle', 'square', 'hexagon', 'diamond', 'octagon', 'pentagon', 'shield', 'triangle'] as const
export type Shape = (typeof SHAPES)[number]
export interface Look { color: string; shape: Shape; letter: string }

export function look(s: { id: string; color_index: number } | undefined, display: string, mono: boolean): Look {
  if (!s || s.id === 'UNKNOWN') return { color: 'var(--spk-neutral)', shape: 'circle', letter: '?' }
  if (s.id === 'YOU') return { color: 'var(--accent)', shape: 'circle', letter: 'Y' }
  const i = ((s.color_index % 8) + 8) % 8
  return { color: mono ? 'var(--spk-neutral)' : `var(--spk${i})`, shape: SHAPES[i], letter: (display.replace(/^Speaker /, '').charAt(0) || '?').toUpperCase() }
}
