import { Injectable, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Subject, firstValueFrom } from 'rxjs';
import { CallEvent, State, Ticket } from './models';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private http = inject(HttpClient);
  // Configurable en public/api-config.js para apuntar al backend publicado.
  private apiRoot = (window as Window & { TURNOS_API_URL?: string }).TURNOS_API_URL?.replace(/\/$/, '')
    || `${location.protocol}//${location.hostname}:8000`;
  private base = `${this.apiRoot}/api`;

  state = signal<State>({ services: [], desks: [], waiting: [] });
  calls = new Subject<CallEvent>();
  connected = signal(false);
  private ws?: WebSocket;

  connect() {
    if (this.ws && this.ws.readyState <= 1) return;
    const wsRoot = this.apiRoot.replace(/^http/, 'ws');
    this.ws = new WebSocket(`${wsRoot}/ws`);
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
