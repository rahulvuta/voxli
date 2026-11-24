// Okabe-Ito based, tuned for a dark background. Colour is never the only cue: every speaker also has a shape.
export const COLORS = ['#56B4E9', '#E69F00', '#35C99A', '#F0E442', '#CC79A7', '#8C9EFF', '#F26B4B', '#BDBDBD']
export const SHAPES = ['circle', 'square', 'triangle', 'diamond', 'star', 'plus', 'hexagon', 'down'] as const
export type Shape = (typeof SHAPES)[number] | 'ring' | 'dashed'
export interface Look { color: string; shape: Shape }

export function look(s: { id: string; color_index: number } | undefined, mono: boolean): Look {
  if (!s) return { color: '#9AA4AE', shape: 'dashed' }
  if (s.id === 'YOU') return { color: '#FFFFFF', shape: 'ring' }
  if (s.id === 'UNKNOWN') return { color: '#9AA4AE', shape: 'dashed' }
  const i = ((s.color_index % 8) + 8) % 8
  return { color: mono ? '#D5DAE0' : COLORS[i], shape: SHAPES[i] }
}
