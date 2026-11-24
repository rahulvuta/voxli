// Mic -> AudioWorklet (public/pcm-worklet.js) -> 16 kHz Int16 interleaved frames.
export interface Mic { stop(): void }
export type MicState = 'on' | 'paused'
export class MicError extends Error {
  kind: 'denied' | 'missing' | 'insecure' | 'other'
  constructor(kind: MicError['kind'], message: string) { super(message); this.kind = kind }
}

interface Opts {
  onFrame(b: ArrayBuffer): void
  onChannels(c: 1 | 2): void
  onState(s: MicState): void
}

const DETECT_CHUNKS = 13 // ~0.5 s of audio decides whether the "stereo" track is really duplicated mono

/** True when L and R are (nearly) identical: iPhone Safari hands out duplicated mono for channelCount:2. */
export function isDuplicatedMono(chunks: Int16Array[]): boolean {
  let diff = 0, sum = 0
  for (const c of chunks) for (let i = 0; i + 1 < c.length; i += 2) { const d = c[i] - c[i + 1]; diff += d * d; sum += c[i] * c[i] + c[i + 1] * c[i + 1] }
  if (sum < 1) return true // digital silence on both: nothing to tell apart, mono is the safe call
  return diff / sum < 1e-5
}

export async function startMic(o: Opts): Promise<Mic> {
  if (!navigator.mediaDevices?.getUserMedia) throw new MicError('insecure', 'The microphone needs a secure (https) page.')
  let stream: MediaStream
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 2, echoCancellation: false, noiseSuppression: false, autoGainControl: true } })
  } catch (e) {
    const n = (e as DOMException).name
    if (n === 'NotAllowedError' || n === 'SecurityError') throw new MicError('denied', 'Microphone permission was blocked.')
    if (n === 'NotFoundError' || n === 'OverconstrainedError') throw new MicError('missing', 'No microphone was found.')
    throw new MicError('other', (e as Error).message)
  }
  const track = stream.getAudioTracks()[0]
  const real = (track.getSettings().channelCount ?? 1) >= 2 ? 2 : 1
  const ctx = new AudioContext({ latencyHint: 'interactive' })
  await ctx.resume()
  await ctx.audioWorklet.addModule('/pcm-worklet.js')
  const src = ctx.createMediaStreamSource(stream)
  const node = new AudioWorkletNode(ctx, 'pcm16', {
    numberOfInputs: 1, numberOfOutputs: 1, outputChannelCount: [1],
    channelCount: real, channelCountMode: 'explicit', channelInterpretation: 'discrete',
    processorOptions: { channels: real, rate: ctx.sampleRate },
  })
  const mute = ctx.createGain()
  mute.gain.value = 0
  src.connect(node).connect(mute).connect(ctx.destination)

  let mode: 'detecting' | 1 | 2 = real === 2 ? 'detecting' : 1
  const held: Int16Array[] = []
  const left = (c: Int16Array) => { const m = new Int16Array(c.length / 2); for (let i = 0; i < m.length; i++) m[i] = c[i * 2]; return m }
  const emit = (c: Int16Array) => o.onFrame(mode === 1 && real === 2 ? left(c).buffer as ArrayBuffer : c.buffer as ArrayBuffer)
  if (mode === 1) o.onChannels(1)

  node.port.onmessage = (ev) => {
    const c = new Int16Array(ev.data as ArrayBuffer)
    if (mode !== 'detecting') { emit(c); return }
    held.push(c)
    if (held.length < DETECT_CHUNKS) return
    mode = isDuplicatedMono(held) ? 1 : 2
    o.onChannels(mode)
    for (const h of held.splice(0)) emit(h)
  }
  const state = () => o.onState(ctx.state === 'running' ? 'on' : 'paused')
  ctx.onstatechange = state
  const wake = () => { if (document.visibilityState === 'visible' && ctx.state !== 'running') void ctx.resume().catch(() => {}) }
  document.addEventListener('visibilitychange', wake)
  track.onended = () => o.onState('paused')

  return {
    stop() {
      document.removeEventListener('visibilitychange', wake)
      ctx.onstatechange = null
      stream.getTracks().forEach((t) => t.stop())
      void ctx.close()
    },
  }
}
