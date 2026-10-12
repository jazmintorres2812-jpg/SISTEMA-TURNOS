export interface Ticket {
  id: number; prefix: string; number: number; code: string;
  status: 'espera' | 'llamado' | 'atendiendo' | 'finalizado' | 'ausente';
  desk: number | null;
  called_at?: string | null; started_at?: string | null;
}
export interface Desk { id: number; name: string; ticket: Ticket | null; }
export interface Service { prefix: string; name: string; }
export interface State { services: Service[]; desks: Desk[]; waiting: Ticket[]; }
export interface CallEvent { desk: number; ticket: Ticket; }
