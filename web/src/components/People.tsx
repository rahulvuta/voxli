import { useMemo } from 'react'
import { useCtx } from '../ctx'
import { Line } from './Line'
import { Avatar } from './ui'

export function Empty({ hint }: { hint: string }) {
  return <div className="empty"><p>Waiting for the first words…</p><p>{hint}</p></div>
}

/** First-appearance order of everyone who has spoken (YOU excluded: your own lines sit under the grid). */
function useOrder() {
  const { state, sorted, hidden } = useCtx()
  return useMemo(() => {
    const first = new Map<string, number>()
    for (const u of sorted) if (!hidden.has(u.key) && u.skey !== 'YOU' && !first.has(u.skey)) first.set(u.skey, u.epoch * 1e6 + u.start)
    return [...first.keys()].filter((k) => state.speakers[k]).sort((x, y) => first.get(x)! - first.get(y)!)
  }, [sorted, hidden, state.speakers])
}

const PREV = 3

function Card({ skey }: { skey: string }) {
  const { state, sorted, hidden, name, look, openSpeaker } = useCtx()
  const s = state.speakers[skey]
  const mine = useMemo(() => sorted.filter((u) => u.skey === skey && !hidden.has(u.key)), [sorted, hidden, skey])
  const latest = mine[mine.length - 1]
  const prev = mine.slice(Math.max(0, mine.length - 1 - PREV), -1).reverse()
  const old = s.epoch !== state.epoch
  const open = (e: React.MouseEvent) => { if (!(e.target as HTMLElement).closest('button')) openSpeaker(skey) }
  return (
    <section className={`card${s.active ? ' active' : ''}${old ? ' old' : ''}`} style={{ '--c': look(skey).color } as React.CSSProperties} aria-label={`${name(skey)}${s.active ? ', speaking' : ''}`}>
      <button type="button" className="card-head" onClick={() => openSpeaker(skey)} aria-label={`${name(skey)}${s.name_source === 'suggested' ? ' (suggested name)' : ''}. Open history, rename or merge`}>
        <Avatar skey={skey} size={32} />
        <span className="ptext">
          <span className="pname">{name(skey)}</span>
          {(s.active || old) && <span className="pstate">{s.active ? 'Speaking' : 'Earlier'}</span>}
        </span>
      </button>
      <div className="card-body" onClick={open}>
        {latest && <div className="latest"><Line u={latest} same /></div>}
        {prev.length > 0 && <div className="prev">{prev.map((u) => <Line key={u.key} u={u} size="sm" meta={false} />)}</div>}
      </div>
    </section>
  )
}

export function People() {
  const { sorted, openSpeaker, look, name } = useCtx()
  const keys = useOrder()
  const me = useMemo(() => sorted.filter((u) => u.skey === 'YOU').pop(), [sorted])
  if (!keys.length && !me) return <Empty hint="Captions appear here, one card per person." />
  return (
    <div className="people">
      <div className={`grid ${keys.length <= 4 ? `n${keys.length}` : 'many'}`}>{keys.map((k) => <Card key={k} skey={k} />)}</div>
      {me && (
        <button type="button" className="you" style={{ '--c': look('YOU').color } as React.CSSProperties} onClick={() => openSpeaker('YOU')} aria-label={`${name('YOU')}, last thing you said: ${me.text}. Open history`}>
          <Avatar skey="YOU" size={24} /><span className="you-text">{me.text}</span>
        </button>
      )}
    </div>
  )
}
