import { Injectable, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Subject, firstValueFrom, timeout } from 'rxjs';
import { CallEvent, State, Ticket } from './models';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private http = inject(HttpClient);
  // En producción la API comparte el dominio de Vercel; en local usa FastAPI:8000.
  private apiRoot = (window as Window & { TURNOS_API_URL?: string }).TURNOS_API_URL?.replace(/\/$/, '')
    || (['localhost', '127.0.0.1'].includes(location.hostname)
      ? `${location.protocol}//${location.hostname}:8000`
      : location.origin);
  private base = `${this.apiRoot}/api`;

  state = signal<State>({ services: [], desks: [], waiting: [] });
  calls = new Subject<CallEvent>();
  connected = signal(false);
  private pollTimer?: number;
  private refreshing = false;
  private hasInitialState = false;

  connect() {
    if (this.pollTimer) return;
    void this.refreshState();
    this.pollTimer = window.setInterval(() => void this.refreshState(), 1500);
  }

  private async refreshState() {
    if (this.refreshing) return;
    this.refreshing = true;
    try {
      const next = await firstValueFrom(this.http.get<State>(`${this.base}/state`).pipe(timeout(7000)));
      const previous = this.state();
      this.state.set(next);
      this.connected.set(true);

      if (this.hasInitialState) {
        for (const desk of next.desks) {
          const ticket = desk.ticket;
          const oldTicket = previous.desks.find(item => item.id === desk.id)?.ticket;
          if (ticket?.status === 'llamado' && (ticket.id !== oldTicket?.id || ticket.called_at !== oldTicket?.called_at)) {
            this.calls.next({ desk: desk.id, ticket });
          }
        }
      }
      this.hasInitialState = true;
    } catch {
      this.connected.set(false);
    } finally {
      this.refreshing = false;
    }
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
