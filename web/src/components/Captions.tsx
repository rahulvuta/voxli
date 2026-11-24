import { Fragment, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useCtx } from '../ctx'
import type { Utt } from '../store'
import { Glyph } from './ui'

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
    ro.observe(el) // lane height changes (the active lane grows) must re-pin too
    el.scrollTop = el.scrollHeight
    return () => ro.disconnect()
  }, [])
  return { ref, away, toEnd, bind: { onScroll, onWheel: mark, onTouchStart: mark, onTouchMove: mark, onTouchEnd: mark, onPointerDown: mark, onKeyDown: mark } }
}

function Words({ u }: { u: Utt }) {
  const toks = u.text.split(/\s+/).filter(Boolean)
  if (u.words.length && toks.length === u.words.length)
    return <>{toks.map((t, i) => <Fragment key={i}>{i > 0 && ' '}<span className={u.words[i].conf < 0.6 ? 'lc' : undefined}>{t}</span></Fragment>)}</>
  return <>{u.text}</>
}

const snip = (t: string) => { const w = t.split(/\s+/); return w.slice(0, 5).join(' ') + (w.length > 5 ? '…' : '') }

function Utterance({ u, who }: { u: Utt; who?: boolean }) {
  const { state, groups, look, name, jump, openSpeaker } = useCtx()
  const a = state.ann[u.key]
  const reply = a?.reply_to ? state.utts[a.reply_to] : undefined
  const cut = a?.interrupts ? state.utts[a.interrupts] : undefined
  const partners = u.gkey ? (groups.get(u.gkey) ?? []).filter((x) => x.key !== u.key) : []
  const l = look(u.skey)
  return (
    <article id={`u-${u.key}`} className={`utt ${u.is_final ? 'final' : 'interim'} ${partners.length ? 'ov' : ''} ${u.source === 'you' ? 'mine' : ''}`}>
      {who && (
        <button type="button" className="who" onClick={() => openSpeaker(u.skey)}>
          <Glyph shape={l.shape} color={l.color} size={16} />{name(u.skey)}
        </button>
      )}
      {(reply || cut || partners.length > 0) && (
        <div className="rel">
          {reply && <button type="button" className="chip rep" onClick={() => jump(reply.key)} aria-label={`Replying to ${name(reply.skey)}: ${snip(reply.text)}. Jump to it`}><span aria-hidden="true">↩</span> {name(reply.skey)} <q>{snip(reply.text)}</q></button>}
          {cut && <button type="button" className="chip cut" onClick={() => jump(cut.key)} aria-label={`Interrupted ${name(cut.skey)}. Jump to it`}><span aria-hidden="true">✂︎</span> cut in on {name(cut.skey)}</button>}
          {partners.length > 0 && <span className="chip same"><span aria-hidden="true">‖</span> at the same time as {partners.map((p) => name(p.skey)).join(', ')}</span>}
        </div>
      )}
      <p className="text">
        <Words u={u} />
        {a?.incomplete && <span className="tag cutoff"> cut off</span>}
        {!u.is_final && <span className="sr-only"> (still being heard)</span>}
        {u.speaker_uncertain && u.speaker_id !== 'UNKNOWN' && <span className="unsure" title="Not sure who said this"><b aria-hidden="true">?</b> unsure who<span className="sr-only"> said this</span></span>}
      </p>
    </article>
  )
}

function Lane({ skey }: { skey: string }) {
  const { state, sorted, hidden, look, name, openSpeaker } = useCtx()
  const s = state.speakers[skey]
  const mine = useMemo(() => sorted.filter((u) => u.skey === skey && !hidden.has(u.key)), [sorted, hidden, skey])
  const { ref, bind, away, toEnd } = useStick()
  const l = look(skey)
  const old = skey !== 'YOU' && s.epoch !== state.epoch
  return (
    <section className={`lane ${s.active ? 'active' : ''} ${old ? 'old' : ''} ${skey === 'YOU' ? 'me' : ''}`} style={{ '--c': l.color } as React.CSSProperties} aria-label={`${name(skey)} lane`}>
      <button type="button" className="lane-head" onClick={() => openSpeaker(skey)} aria-label={`${name(skey)}${s.name_source === 'suggested' ? ' (suggested name)' : ''}. Rename or merge`}>
        <Glyph shape={l.shape} color={l.color} size={20} />
        <span className="lane-name">{name(skey)}</span>
        {s.name && <span className="lane-label">{s.label}</span>}
        {old && <span className="tag" title="From before the connection restarted">earlier</span>}
        {s.active && <span className="tag live">speaking</span>}
      </button>
      <div className="lane-scroll" ref={ref} {...bind} tabIndex={0} role="group" aria-label={`${name(skey)} captions`}>
        <div className="lane-inner">{mine.map((u) => <Utterance key={u.key} u={u} />)}</div>
      </div>
      {away && <button type="button" className="btn toend" onClick={toEnd}>↓ Latest</button>}
    </section>
  )
}

export function Lanes() {
  const { state, sorted, hidden } = useCtx()
  const keys = useMemo(() => {
    const first = new Map<string, number>()
    for (const u of sorted) if (!hidden.has(u.key) && !first.has(u.skey)) first.set(u.skey, u.epoch * 1e6 + u.start)
    const rank = (k: string) => (k === 'YOU' ? Infinity : first.get(k)!)
    return [...first.keys()].filter((k) => state.speakers[k]).sort((x, y) => rank(x) - rank(y))
  }, [sorted, hidden, state.speakers])
  if (!keys.length) return <Empty />
  return <div className={`lanes n${Math.min(keys.length, 4)}`}>{keys.map((k) => <Lane key={k} skey={k} />)}</div>
}

function Empty() {
  return <div className="empty"><p>Waiting for the first words…</p><p className="muted">Captions appear here, one lane per person.</p></div>
}

export function Timeline() {
  const { sorted, groups, hidden, look } = useCtx()
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
  if (!rows.length) return <Empty />
  let epoch = rows[0] instanceof Array ? rows[0][0].epoch : rows[0].epoch
  return (
    <div className="timeline-wrap">
      <div className="timeline" ref={ref} {...bind} tabIndex={0} role="group" aria-label="Conversation timeline">
        <div className="timeline-inner">
          {rows.map((r) => {
            const first = r instanceof Array ? r[0] : r
            const divider = first.epoch !== epoch
            epoch = first.epoch
            return (
              <Fragment key={first.key}>
                {divider && <p className="divider">Connection restarted: speakers may be relabelled</p>}
                {r instanceof Array ? (
                  <div className="ovgrp" role="group" aria-label="People speaking at the same time">
                    <p className="ovlabel"><span aria-hidden="true">‖</span> At the same time</p>
                    <div className="ovcols">
                      {r.map((u) => {
                        const l = look(u.skey)
                        return <div key={u.key} className="ovcol" style={{ '--c': l.color } as React.CSSProperties}><Utterance u={u} who /></div>
                      })}
                    </div>
                  </div>
                ) : (
                  <div className="trow" style={{ '--c': look(r.skey).color } as React.CSSProperties}><Utterance u={r} who /></div>
                )}
              </Fragment>
            )
          })}
        </div>
      </div>
      {away && <button type="button" className="btn toend" onClick={toEnd}>↓ Latest</button>}
    </div>
  )
}

/** Polite, batched screen-reader announcements of finished captions (the visual lanes are not live regions). */
export function Announcer() {
  const { sorted, name } = useCtx()
  const [text, setText] = useState('')
  const said = useRef(new Set<string>())
  const queue = useRef<string[]>([])
  useEffect(() => {
    for (const u of sorted) if (u.is_final && u.source !== 'you' && !said.current.has(u.key)) { said.current.add(u.key); queue.current.push(`${name(u.skey)}: ${u.text}`) }
  }, [sorted, name])
  useEffect(() => {
    const t = window.setInterval(() => { if (queue.current.length) setText(queue.current.splice(0).slice(-3).join(' ')) }, 2500)
    return () => clearInterval(t)
  }, [])
  return <div className="sr-only" aria-live="polite" aria-atomic="true">{text}</div>
}
