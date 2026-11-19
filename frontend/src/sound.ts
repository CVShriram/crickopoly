/** Tiny WebAudio sound engine — no external audio assets required. */

type SoundName =
  | 'click' | 'dice' | 'move' | 'buy' | 'money' | 'runs' | 'boundary'
  | 'sixer' | 'wicket' | 'out' | 'eliminated' | 'victory' | 'card'

const PRESETS: Record<SoundName, Array<[number, number, number]>> = {
  click: [[440, 0.04, 0.06]],
  dice: [[180, 0.05, 0.08], [260, 0.06, 0.08], [140, 0.07, 0.08]],
  move: [[320, 0.05, 0.05]],
  buy: [[523, 0.09, 0.08], [784, 0.14, 0.08]],
  money: [[880, 0.07, 0.06], [1174, 0.12, 0.06]],
  runs: [[660, 0.08, 0.07], [880, 0.12, 0.07]],
  boundary: [[523, 0.09, 0.08], [659, 0.13, 0.08], [784, 0.18, 0.08]],
  sixer: [[587, 0.09, 0.09], [784, 0.14, 0.09], [1175, 0.2, 0.09]],
  wicket: [[220, 0.1, 0.12], [110, 0.18, 0.12]],
  out: [[196, 0.14, 0.13], [98, 0.26, 0.13]],
  eliminated: [[330, 0.12, 0.1], [247, 0.2, 0.1], [165, 0.3, 0.1]],
  victory: [[523, 0.12, 0.09], [659, 0.2, 0.09], [784, 0.28, 0.09], [1047, 0.4, 0.1]],
  card: [[700, 0.06, 0.05]],
}

class SoundEngine {
  muted = localStorage.getItem('cm-muted') === '1'
  volume = Number(localStorage.getItem('cm-volume') ?? 0.5)
  private ctx: AudioContext | null = null

  setMuted(value: boolean) {
    this.muted = value
    localStorage.setItem('cm-muted', value ? '1' : '0')
  }

  setVolume(value: number) {
    this.volume = Math.max(0, Math.min(1, value))
    localStorage.setItem('cm-volume', String(this.volume))
  }

  play(name: SoundName) {
    if (this.muted || this.volume === 0) return
    try {
      this.ctx ??= new AudioContext()
      const ctx = this.ctx
      const notes = PRESETS[name] || PRESETS.click
      let offset = 0
      for (const [freq, duration, gain] of notes) {
        const osc = ctx.createOscillator()
        const volume = ctx.createGain()
        osc.type = name === 'wicket' || name === 'out' ? 'sawtooth' : 'sine'
        osc.frequency.setValueAtTime(freq, ctx.currentTime + offset)
        volume.gain.setValueAtTime(0.0001, ctx.currentTime + offset)
        volume.gain.exponentialRampToValueAtTime(gain * this.volume, ctx.currentTime + offset + 0.01)
        volume.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + offset + duration)
        osc.connect(volume).connect(ctx.destination)
        osc.start(ctx.currentTime + offset)
        osc.stop(ctx.currentTime + offset + duration + 0.02)
        offset += duration * 0.55
      }
    } catch { /* audio is optional */ }
  }
}

export const sound = new SoundEngine()
