import { Mic } from 'lucide-react'

/** Phone in the middle of a table, with a caption card in front of each person. */
function Illustration() {
  const card = (x: number, y: number, c: string, shape: React.ReactNode, w1: number, w2: number) => (
    <g transform={`translate(${x} ${y})`}>
      <rect width="92" height="50" rx="10" fill="var(--s2)" />
      <rect x="0" y="8" width="3" height="34" rx="1.5" fill={c} />
      <g transform="translate(12 10)">{shape}</g>
      <rect x="38" y="13" width={w1} height="5" rx="2.5" fill="var(--text)" opacity=".85" />
      <rect x="12" y="32" width={w2} height="5" rx="2.5" fill="var(--muted)" opacity=".6" />
    </g>
  )
  return (
    <svg className="hero" viewBox="0 0 320 200" role="img" aria-label="A phone lies in the middle of a table. Around it, four caption cards show what each person is saying.">
      <rect x="38" y="46" width="244" height="110" rx="55" fill="var(--s2)" />
      <rect x="140" y="68" width="40" height="66" rx="9" fill="var(--bg)" stroke="var(--accent)" strokeWidth="3" />
      <path d="M150 94h20M150 102h14M150 110h18" stroke="var(--accent)" strokeWidth="3" strokeLinecap="round" />
      {card(8, 8, 'var(--spk0)', <circle cx="10" cy="10" r="10" fill="var(--spk0)" />, 40, 62)}
      {card(220, 8, 'var(--spk1)', <rect width="20" height="20" rx="5" fill="var(--spk1)" />, 34, 50)}
      {card(8, 142, 'var(--spk2)', <path d="M10 0l10 5.5v9L10 20 0 14.5v-9z" fill="var(--spk2)" />, 38, 56)}
      {card(220, 142, 'var(--spk4)', <path d="M10 0l10 10-10 10L0 10z" fill="var(--spk4)" />, 30, 66)}
    </svg>
  )
}

export function Start({ onStart }: { onStart(): void }) {
  return (
    <main className="start">
      <div className="start-in">
        <h1 className="brand big">Voxli</h1>
        <Illustration />
        <h2>See who is saying what</h2>
        <ol className="steps">
          <li><span>1</span>Put your phone flat in the middle of the table.</li>
          <li><span>2</span>Tap Start and allow the microphone.</li>
          <li><span>3</span>Read each person’s words. Type to reply.</li>
        </ol>
        <button className="start-btn" onClick={onStart} autoFocus><Mic size={22} aria-hidden="true" />Start listening</button>
        <p className="privacy">Your audio is sent to the Voxli server to make captions. Nothing is saved unless you turn on voice memory.</p>
        <details className="learn">
          <summary>Learn more</summary>
          <p>The server may pass audio to a speech-recognition service to turn it into text, and to an AI model to suggest names, summaries and replies. Recordings are never stored. Voice memory is off until you switch it on in Settings, and you can delete everything there at any time.</p>
        </details>
        <p className="demo"><a href="?mock=1">Try the demo without a microphone</a></p>
      </div>
    </main>
  )
}
