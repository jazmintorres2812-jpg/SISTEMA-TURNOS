import { Component, DestroyRef, OnInit, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { ApiService } from './api.service';
import { SoundService } from './sound.service';

@Component({
  selector: 'app-pantalla',
  standalone: true,
  imports: [RouterLink],
  template: `
    @if (showWelcome()) {
      <div class="overlay">
        <section class="welcome-card">
          <span class="welcome-icon">🔊</span>
          <h1>Bienvenido</h1>
          <button (click)="startWelcome()">Bienvenido</button>
        </section>
      </div>
    }
    <main class="p">
      <a class="kiosk-link" routerLink="/kiosko">← Volver al kiosko</a>
      <section class="desks">
        @for (d of api.state().desks; track d.id) {
          <article class="desk" [class.busy]="d.ticket" [class.flash]="highlight() === d.id">
            <h2>{{ d.name }}</h2>
            @if (d.ticket; as t) {
              <div class="code">{{ t.code }}</div>
              <div class="st">{{ t.status === 'llamado' ? 'Llamado' : 'Atendiendo' }}</div>
            } @else {
              <div class="code free">—</div>
              <div class="st">Libre</div>
            }
          </article>
        }
      </section>
      <aside>
        <h3>En espera ({{ api.state().waiting.length }})</h3>
        <ul>
          @for (t of api.state().waiting; track t.id) { <li>{{ t.code }}</li> }
        </ul>
      </aside>
    </main>`,
  styles: [`
    .overlay { position: fixed; inset: 0; z-index: 10; display: grid; place-items: center; padding: 20px; background: #10091dcc; backdrop-filter: blur(8px); }
    .welcome-card { width: min(440px, 100%); padding: 38px 30px; border: 1px solid #e9d5ff66; border-radius: 28px; background: linear-gradient(145deg, #2e1065, #181226); text-align: center; box-shadow: 0 25px 80px #0009; }
    .welcome-icon { font-size: 3rem; }
    .welcome-card h1 { margin: 12px 0; font-size: 2.4rem; color: #f3e8ff; }
    .welcome-card p { margin: 0 0 24px; color: #ddd6fe; font-size: 1.05rem; }
    .welcome-card button { min-width: 220px; padding: 18px 28px; border-radius: 16px; background: linear-gradient(135deg, #c084fc, #7c3aed); color: white; font-size: 1.3rem; font-weight: 800; }
    .kiosk-link { grid-column: 1 / -1; justify-self: start; color: #ddd6fe; font-weight: 700; text-decoration: none; }
    .kiosk-link:hover { color: white; text-decoration: underline; }
    .p { display: grid; grid-template-columns: 1fr 260px; gap: 24px; padding: 24px; min-height: 100vh; }
    .desks { display: grid; grid-template-columns: repeat(2, 1fr); gap: 20px; }
    .desk { background: #211b35; border-radius: 20px; padding: 20px; text-align: center; border: 4px solid transparent; }
    .desk h2 { margin: 0; font-size: 2rem; color: #94a3b8; }
    .desk.busy { background: #6d28d9; } .desk.busy h2 { color: #f3e8ff; }
    .code { font-size: 6rem; font-weight: 800; } .code.free { color: #475569; }
    .st { font-size: 1.5rem; }
    .desk.flash { border-color: #e9d5ff; animation: blink .7s infinite alternate; }
    @keyframes blink { to { background: #9333ea; } }
    aside { background: #211b35; border-radius: 20px; padding: 20px; }
    aside ul { list-style: none; padding: 0; font-size: 2rem; line-height: 1.6; }
  `],
})
export class PantallaComponent implements OnInit {
  api = inject(ApiService);
  sound = inject(SoundService);
  showWelcome = signal(true);
  highlight = signal<number | null>(null);
  private destroyRef = inject(DestroyRef);

  startWelcome() {
    this.sound.enable(true);
    this.showWelcome.set(false);
  }

  ngOnInit() {
    this.api.connect();
    this.api.calls.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((c) => {
      this.highlight.set(c.desk);
      this.sound.announce(c.ticket.code, c.desk);
      setTimeout(() => this.highlight.set(null), 10000);
    });
  }
}
