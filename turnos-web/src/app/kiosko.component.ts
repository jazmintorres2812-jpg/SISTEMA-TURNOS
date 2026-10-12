import { Component, OnInit, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { ApiService } from './api.service';
import { Ticket } from './models';

@Component({
  selector: 'app-kiosko',
  standalone: true,
  template: `
    <main class="k">
      <header class="brand"><span class="brand-mark">T</span><span>Atención al paciente</span></header>
      <section class="intro"><p class="eyebrow">SISTEMA DE TURNOS</p><h1>Bienvenido</h1><p class="subtitle">Seleccione el servicio para obtener su turno</p></section>
      @if (ticket()) {
        <section class="ticket">
          <span class="ticket-label">TURNO ASIGNADO</span>
          <h2>{{ ticket()!.code }}</h2>
          @if (ticket()!.desk) {
            <p class="ticket-wait">Pase a la Mesa {{ ticket()!.desk }}</p>
          } @else {
            <p class="ticket-wait">Está en la fila de espera</p>
            <p class="ticket-note">Le asignaremos una mesa cuando quede libre.</p>
          }
        </section>
      } @else {
        <p class="hint">¿Qué servicio necesita?</p>
        <div class="btns">
          @for (s of api.state().services; track s.prefix) {
            <button [disabled]="busy()" (click)="take(s.prefix)">{{ s.name }}</button>
          }
        </div>
      }
    </main>`,
  styles: [`
    .k { min-height: 100vh; padding: 40px 24px; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; gap: 28px; background: radial-gradient(ellipse at 50% 20%, #4c1d95 0, #211235 46%, #0b1220 100%); }
    .brand { position: absolute; top: 28px; left: 32px; display: flex; align-items: center; gap: 12px; font-size: 1rem; font-weight: 650; color: #cbd5e1; }
    .brand-mark { width: 38px; height: 38px; display: grid; place-items: center; border-radius: 12px; background: #c084fc; color: #3b0764; font-size: 1.2rem; font-weight: 900; }
    .intro { display: grid; gap: 10px; } .eyebrow { margin: 0; color: #d8b4fe; letter-spacing: .2em; font-size: .85rem; font-weight: 800; }
    h1 { font-size: clamp(2.5rem, 7vw, 4.5rem); margin: 0; letter-spacing: -.04em; } .subtitle, .hint { color: #cbd5e1; font-size: 1.2rem; margin: 0; }
    .btns { width: min(780px, 100%); display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 18px; }
    .btns button { min-height: 130px; padding: 24px; border-radius: 22px; background: linear-gradient(145deg, #c084fc, #7c3aed); box-shadow: 0 14px 35px #02061766; font-size: 1.5rem; transition: transform .18s, box-shadow .18s; }
    .btns button:hover { transform: translateY(-4px); box-shadow: 0 18px 40px #02061799; }
    .ticket { width: min(560px, 100%); padding: 38px 28px; border: 1px solid #ffffff30; border-radius: 28px; background: #f8fafc; color: #0f172a; box-shadow: 0 24px 80px #02061780; animation: appear .35s ease-out; }
    .ticket-label { display: inline-block; color: #475569; font-size: .9rem; font-weight: 800; letter-spacing: .16em; }
    .ticket h2 { font-size: clamp(6rem, 18vw, 9rem); line-height: 1; margin: 18px 0; color: #7c3aed; }
    .ticket-wait { margin: 0; font-size: 1.35rem; font-weight: 750; } .ticket-note { margin: 10px 0 0; color: #64748b; font-size: 1rem; }
    @keyframes appear { from { opacity: 0; transform: translateY(12px) scale(.98); } to { opacity: 1; transform: translateY(0) scale(1); } }
    @media (max-width: 600px) { .brand { position: static; align-self: flex-start; } .btns { grid-template-columns: 1fr; } .btns button { min-height: 100px; } }
  `],
})
export class KioskoComponent implements OnInit {
  api = inject(ApiService);
  private router = inject(Router);
  ticket = signal<Ticket | null>(null);
  busy = signal(false);

  ngOnInit() { this.api.connect(); }

  async take(service: string) {
    if (this.busy()) return;          // evita doble clic
    this.busy.set(true);
    try {
      this.ticket.set(await this.api.takeTicket(service));
      setTimeout(() => this.router.navigateByUrl('/pantalla'), 5000);
    } finally {
      this.busy.set(false);
    }
  }
}
