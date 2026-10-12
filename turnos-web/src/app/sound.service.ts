import { Injectable, signal } from '@angular/core';

@Injectable({ providedIn: 'root' })
export class SoundService {
  enabled = signal(false);
  private ctx?: AudioContext;

  /** Activa el audio después de la pulsación del usuario. */
  enable(playWelcome = false) {
    if (typeof AudioContext === 'undefined') return;
    try {
      this.ctx ??= new AudioContext();
      void this.ctx.resume().then(() => {
        this.enabled.set(true);
        if (playWelcome) {
          this.chime();
          this.speakWelcome();
        }
      }).catch(() => this.enabled.set(false));
    } catch {
      this.enabled.set(false);
    }
  }

  private tone(freq: number, start: number, dur: number) {
    if (!this.ctx) return;
    const o = this.ctx.createOscillator();
    const g = this.ctx.createGain();
    o.type = 'sine';
    o.frequency.value = freq;
    g.gain.setValueAtTime(0.0001, this.ctx.currentTime + start);
    g.gain.exponentialRampToValueAtTime(0.4, this.ctx.currentTime + start + 0.02);
    g.gain.exponentialRampToValueAtTime(0.0001, this.ctx.currentTime + start + dur);
    o.connect(g).connect(this.ctx.destination);
    o.start(this.ctx.currentTime + start);
    o.stop(this.ctx.currentTime + start + dur);
  }

  chime() {
    this.tone(880, 0, 0.5);
    this.tone(660, 0.45, 0.7);
  }

  private speakWelcome() {
    if (typeof speechSynthesis === 'undefined') return;
    const u = new SpeechSynthesisUtterance('Bienvenido');
    u.lang = 'es-MX';
    u.rate = 0.9;
    speechSynthesis.speak(u);
  }

  announce(_code: string, _desk: number) {
    if (!this.enabled()) return;
    this.chime();
    setTimeout(() => this.speakWelcome(), 1200);
  }

}
