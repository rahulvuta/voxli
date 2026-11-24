import { CornerUpLeft, Equal, HelpCircle } from 'lucide-react'
import { Fragment } from 'react'
import { useCtx } from '../ctx'
import type { Utt } from '../store'

/** Verbatim words; low-confidence ones get a dotted underline, and words arriving live fade in. */
function Words({ u }: { u: Utt }) {
  const toks = u.text.split(/\s+/).filter(Boolean)
  const cls = (i: number) => [u.words[i] && u.words[i].conf < 0.6 ? 'lc' : '', u.is_final ? '' : 'w-in'].filter(Boolean).join(' ') || undefined
  if (u.words.length && toks.length === u.words.length || !u.is_final)
    return <>{toks.map((t, i) => <Fragment key={i}>{i > 0 && ' '}<span className={cls(i)}>{t}</span></Fragment>)}</>
  return <>{u.text}</>
}

/** One caption line plus its quiet relationship notes: reply target, interruption, overlap, unsure speaker. */
export function Line({ u, size = 'lg', meta = true, same = false }: { u: Utt; size?: 'lg' | 'sm'; meta?: boolean; same?: boolean }) {
  const { state, groups, interruptedBy, name, jump, openSpeaker } = useCtx()
  const a = state.ann[u.key]
  const reply = a?.reply_to ? state.utts[a.reply_to] : undefined
  const cut = a?.interrupts ? state.utts[a.interrupts] : undefined
  const by = interruptedBy.has(u.key) ? state.utts[interruptedBy.get(u.key)!] : undefined
  const partners = same && u.gkey ? (groups.get(u.gkey) ?? []).filter((x) => x.key !== u.key) : []
  const unsure = u.speaker_uncertain && u.speaker_id !== 'UNKNOWN'
  const stop = (e: React.MouseEvent) => e.stopPropagation()
  return (
    <div className={`line ${size} ${u.is_final ? 'final' : 'interim'}`} data-u={u.key}>
      {meta && (reply || cut || partners.length > 0) && (
        <div className="rel">
          {reply && <button type="button" onClick={(e) => { stop(e); jump(reply.key) }} aria-label={`Replying to ${name(reply.skey)}. Jump to that line`}><CornerUpLeft size={14} aria-hidden="true" />to {name(reply.skey)}</button>}
          {cut && <button type="button" onClick={(e) => { stop(e); jump(cut.key) }} aria-label={`Interrupted ${name(cut.skey)}. Jump to that line`}><CornerUpLeft size={14} aria-hidden="true" />cut in on {name(cut.skey)}</button>}
          {partners.length > 0 && <span><Equal size={14} aria-hidden="true" />at the same time as {partners.map((p) => name(p.skey)).join(', ')}</span>}
        </div>
      )}
      <p className="txt">
        <Words u={u} />
        {a?.incomplete && <span aria-label=", interrupted"> —</span>}
        {!u.is_final && <span className="sr-only"> (still being heard)</span>}
      </p>
      {meta && (by || unsure) && (
        <div className="rel notes">
          {by && <button type="button" onClick={(e) => { stop(e); jump(by.key) }}>interrupted by {name(by.skey)}</button>}
          {unsure && <button type="button" className="unsure" onClick={(e) => { stop(e); openSpeaker(u.skey) }}><HelpCircle size={14} aria-hidden="true" />Unsure who<span className="sr-only"> said this. Tap to name this person</span></button>}
        </div>
      )}
    </div>
  )
}
