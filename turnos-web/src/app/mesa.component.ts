import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { ApiService } from './api.service';

@Component({
  selector: 'app-mesa',
  standalone: true,
  imports: [RouterLink],
  template: `
    <main class="m">
      <a routerLink="/">← Inicio</a>
      <h1>Mesa {{ id }}</h1>
      <p class="wait">En espera: <b>{{ api.state().waiting.length }}</b></p>

      <section class="card">
        @if (ticket(); as t) {
          <div class="code">{{ t.code }}</div>
          <p>{{ t.status === 'llamado' ? 'Llamado: tiene 1 minuto para presentarse' : 'Atendiendo · máximo 1 minuto' }}</p>
        } @else {
          <div class="code free">Libre</div>
        }
      </section>

      <div class="actions">
        <button [disabled]="!!ticket() || !api.state().waiting.length" (click)="run('call-next')">Llamar siguiente</button>
        <button class="sec" [disabled]="!ticket()" (click)="run('recall')">🔔 Volver a llamar</button>
        <button class="ok" [disabled]="ticket()?.status !== 'llamado'" (click)="run('start')">Paciente llegó</button>
        <button class="ok" [disabled]="!ticket()" (click)="run('finish')">Finalizar</button>
        <button class="warn" [disabled]="ticket()?.status !== 'llamado'" (click)="run('no-show')">No se presentó</button>
      </div>
      @if (error()) { <p class="err">{{ error() }}</p> }
    </main>`,
  styles: [`
    .m { max-width: 700px; margin: 0 auto; padding: 24px; text-align: center; }
    .card { background: #211b35; border-radius: 20px; padding: 30px; margin: 20px 0; }
    .code { font-size: 6rem; font-weight: 800; color: #c084fc; } .code.free { color: #64748b; font-size: 3rem; }
    .actions { display: grid; gap: 12px; } .err { color: #fca5a5; } .wait { font-size: 1.3rem; }
  `],
})
export class MesaComponent implements OnInit {
  api = inject(ApiService);
  id = Number(inject(ActivatedRoute).snapshot.paramMap.get('id'));
  ticket = computed(() => this.api.state().desks.find((d) => d.id === this.id)?.ticket ?? null);
  error = signal('');

  ngOnInit() { this.api.connect(); }

  async run(action: string) {
    this.error.set(await this.api.deskAction(this.id, action));
  }
}
