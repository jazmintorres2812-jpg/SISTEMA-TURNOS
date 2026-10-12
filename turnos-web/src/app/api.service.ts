import { Injectable, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Subject, firstValueFrom } from 'rxjs';
import { CallEvent, State, Ticket } from './models';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private http = inject(HttpClient);
  // Usa el mismo host desde el que se abre la página (funciona en red local)
  private host = location.hostname + ':8000';
  private base = `http://${this.host}/api`;

  state = signal<State>({ services: [], desks: [], waiting: [] });
  calls = new Subject<CallEvent>();
  connected = signal(false);
  private ws?: WebSocket;

  connect() {
    if (this.ws && this.ws.readyState <= 1) return;
    this.ws = new WebSocket(`ws://${this.host}/ws`);
    this.ws.onopen = () => this.connected.set(true);
    this.ws.onmessage = (e) => {
      const msg = JSON.parse(e.data);
      if (msg.type === 'state') this.state.set(msg.state);
      if (msg.type === 'call') this.calls.next({ desk: msg.desk, ticket: msg.ticket });
    };
    this.ws.onclose = () => {
      this.connected.set(false);
      setTimeout(() => this.connect(), 2000); // reconexión automática
    };
  }

  takeTicket(service: string): Promise<Ticket> {
    return firstValueFrom(this.http.post<Ticket>(`${this.base}/tickets`, { service }));
  }

  /** action: call-next | recall | start | finish | no-show */
  async deskAction(desk: number, action: string): Promise<string> {
    try {
      await firstValueFrom(this.http.post(`${this.base}/desks/${desk}/${action}`, {}));
      return '';
    } catch (e: any) {
      return e?.error?.detail ?? 'Error de conexión';
    }
  }
}
