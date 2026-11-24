import { ChevronsDown } from 'lucide-react'
import { Fragment, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useCtx } from '../ctx'
import { clock, type Utt } from '../store'
import { Line } from './Line'
import { Empty } from './People'
import { Avatar } from './ui'

/** Keeps a scroller pinned to the newest caption unless the reader scrolled up (only real user input un-pins it). */
function useStick() {
  const ref = useRef<HTMLDivElement>(null)
  const stuck = useRef(true)
  const lastInput = useRef(0)
  const [away, setAway] = useState(false)
  const mark = () => { lastInput.current = performance.now() }
  const onScroll = () => {
    const el = ref.current
    if (!el) return
    if (el.scrollHeight - el.scrollTop - el.clientHeight < 48) { stuck.current = true; setAway(false) }
    else if (performance.now() - lastInput.current < 1500) { stuck.current = false; setAway(true) }
  }
  const toEnd = () => { const el = ref.current; if (el) { el.scrollTop = el.scrollHeight; stuck.current = true; setAway(false) } }
  useLayoutEffect(() => {
    const el = ref.current
    if (!el || !el.firstElementChild) return
    const ro = new ResizeObserver(() => { if (stuck.current) el.scrollTop = el.scrollHeight })
    ro.observe(el.firstElementChild)
    ro.observe(el)
    el.scrollTop = el.scrollHeight
    return () => ro.disconnect()
  }, [])
  return { ref, away, toEnd, bind: { onScroll, onWheel: mark, onTouchStart: mark, onTouchMove: mark, onTouchEnd: mark, onPointerDown: mark, onKeyDown: mark } }
}

function Turn({ u, lead }: { u: Utt; lead: boolean }) {
  const { name, look, openSpeaker } = useCtx()
  const mine = u.skey === 'YOU'
  return (
    <div className={`turn${mine ? ' mine' : ''}${lead ? ' lead' : ''}`} style={{ '--c': look(u.skey).color } as React.CSSProperties}>
      <div className="turn-av">{lead && <button type="button" onClick={() => openSpeaker(u.skey)} aria-label={`${name(u.skey)}. Open history, rename or merge`}><Avatar skey={u.skey} size={36} /></button>}</div>
      <div className="turn-main">
        {lead && <div className="turn-head"><button type="button" onClick={() => openSpeaker(u.skey)}>{name(u.skey)}</button><time>{clock(u.start)}</time></div>}
        <Line u={u} />
      </div>
    </div>
  )
}

export function Conversation() {
  const { sorted, groups, hidden } = useCtx()
  const { ref, bind, away, toEnd } = useStick()
  const rows = useMemo(() => {
    const seen = new Set<string>()
    const out: (Utt | Utt[])[] = []
    for (const u of sorted) {
      if (hidden.has(u.key)) continue
      const g = u.gkey ? groups.get(u.gkey) : undefined
      if (!g) { out.push(u); continue }
      if (!seen.has(u.gkey!)) { seen.add(u.gkey!); out.push(g) }
    }
    return out
  }, [sorted, groups, hidden])
  if (!rows.length) return <Empty hint="The conversation appears here as it happens." />
  let epoch = rows[0] instanceof Array ? rows[0][0].epoch : rows[0].epoch
  let prevSkey = ''
  return (
    <div className="feed-wrap">
      <div className="feed" ref={ref} {...bind} tabIndex={0} role="group" aria-label="Conversation">
        <div className="feed-inner">
          {rows.map((r) => {
            const first = r instanceof Array ? r[0] : r
            const divider = first.epoch !== epoch
            epoch = first.epoch
            const lead = divider || r instanceof Array || first.skey !== prevSkey
            prevSkey = r instanceof Array ? '' : first.skey
            return (
              <Fragment key={first.key}>
                {divider && <p className="divider">Connection restarted: speakers may be relabelled</p>}
                {r instanceof Array ? (
                  <div className="ovg" role="group" aria-label="People speaking at the same time">
                    <p className="ovlabel">at the same time</p>
                    {r.map((u) => <Turn key={u.key} u={u} lead />)}
                  </div>
                ) : <Turn u={r} lead={lead} />}
              </Fragment>
            )
          })}
        </div>
      </div>
      {away && <button type="button" className="latest-bar" onClick={toEnd}><ChevronsDown size={18} aria-hidden="true" />Jump to latest</button>}
    </div>
  )
}
