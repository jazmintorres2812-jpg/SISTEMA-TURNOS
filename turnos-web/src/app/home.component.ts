import { Component, inject } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ApiService } from './api.service';

@Component({
  selector: 'app-home',
  standalone: true,
  imports: [RouterLink],
  template: `
    <main style="max-width:600px;margin:40px auto;padding:20px">
      <h1>Sistema de turnos</h1>
      <ul style="line-height:2.4;font-size:1.2rem">
        <li><a routerLink="/kiosko">Kiosko (tomar turno)</a></li>
        <li><a routerLink="/pantalla">Pantalla de sala de espera</a></li>
        @for (d of desks; track d) {
          <li><a [routerLink]="['/mesa', d]">Mesa {{ d }} (operador)</a></li>
        }
      </ul>
    </main>`,
})
export class HomeComponent {
  desks = [1, 2, 3, 4]; // debe coincidir con DESKS del backend
}
