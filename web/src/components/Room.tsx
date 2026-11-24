import { Smartphone } from 'lucide-react'
import { useCtx } from '../ctx'
import { Avatar } from './ui'
import { Empty } from './People'
import { Line } from './Line'

/** Top-down map: the phone at the bottom, people on an arc by direction (-90 left .. +90 right). */
export function Room() {
  const { state, sorted, hidden, name, openSpeaker } = useCtx()
  const list = Object.values(state.speakers).filter((s) => s.epoch === state.epoch && s.id !== 'YOU' && s.id !== 'UNKNOWN')
  const placed = list.filter((s) => s.direction_deg != null)
  const rest = list.filter((s) => s.direction_deg == null)
  const talking = list.find((s) => s.active)
  const last = talking && sorted.filter((u) => u.skey === talking.key && !hidden.has(u.key)).pop()
  if (!list.length) return <Empty hint="People appear here, placed by where their voice comes from." />
  return (
    <div className="room">
      <div className="map" role="group" aria-label="Where people are around the phone">
        <svg viewBox="0 0 100 60" preserveAspectRatio="xMidYMax meet" aria-hidden="true">
          <path d="M6 56a44 44 0 0 1 88 0" className="arc" />
          <path d="M22 56a28 28 0 0 1 56 0" className="arc" />
          <path d="M36 56a14 14 0 0 1 28 0" className="arc" />
        </svg>
        <span className="phone"><Smartphone size={20} aria-hidden="true" /></span>
        {placed.map((s) => {
          const a = (s.direction_deg! * Math.PI) / 180
          return (
            <button key={s.key} type="button" className="pin" style={{ left: `${50 + 36 * Math.sin(a)}%`, bottom: `${(4 + 36 * Math.cos(a)) / 0.6}%` }} onClick={() => openSpeaker(s.key)}
              aria-label={`${name(s.key)}, ${s.active ? 'speaking now, ' : ''}${Math.abs(s.direction_deg!) < 15 ? 'in front' : `to your ${s.direction_deg! < 0 ? 'left' : 'right'}`}. Open history`}>
              <Avatar skey={s.key} size={44} /><span>{name(s.key)}</span>
            </button>
          )
        })}
      </div>
      {rest.length > 0 && (
        <p className="unplaced">Direction unknown: {rest.map((s) => <button key={s.key} type="button" onClick={() => openSpeaker(s.key)}>{name(s.key)}</button>)}</p>
      )}
      <div className="now" aria-live="off">{talking && last ? <><span className="muted">{name(talking.key)}</span><Line u={last} meta={false} /></> : <span className="muted">Nobody is speaking right now</span>}</div>
    </div>
  )
}
