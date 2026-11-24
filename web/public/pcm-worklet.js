// Mic -> 16 kHz Int16 interleaved frames (~40 ms). Area-average resampler (cheap low-pass) from the context rate.
class Pcm16 extends AudioWorkletProcessor {
  constructor(o) {
    super()
    const { channels, rate } = o.processorOptions
    this.ch = channels
    this.ratio = rate / 16000
    this.acc = new Float64Array(channels)
    this.fill = 0
    this.out = new Int16Array(640 * channels)
    this.n = 0
  }
  process(inputs) {
    const inp = inputs[0]
    if (!inp || !inp[0]) return true
    const len = inp[0].length
    for (let i = 0; i < len; i++) {
      let w = 1
      while (w > 1e-9) {
        const take = Math.min(w, this.ratio - this.fill)
        for (let c = 0; c < this.ch; c++) this.acc[c] += (inp[c] ? inp[c][i] : inp[0][i]) * take
        this.fill += take
        w -= take
        if (this.fill >= this.ratio - 1e-9) {
          for (let c = 0; c < this.ch; c++) {
            const v = Math.max(-1, Math.min(1, this.acc[c] / this.ratio))
            this.out[this.n * this.ch + c] = v < 0 ? v * 32768 : v * 32767
            this.acc[c] = 0
          }
          this.fill = 0
          if (++this.n === 640) {
            const buf = this.out.buffer
            this.port.postMessage(buf, [buf])
            this.out = new Int16Array(640 * this.ch)
            this.n = 0
          }
        }
      }
    }
    return true
  }
}
registerProcessor('pcm16', Pcm16)
