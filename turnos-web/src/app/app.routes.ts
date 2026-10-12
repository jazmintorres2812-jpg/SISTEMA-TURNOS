import { Routes } from '@angular/router';
import { HomeComponent } from './home.component';
import { KioskoComponent } from './kiosko.component';
import { MesaComponent } from './mesa.component';
import { PantallaComponent } from './pantalla.component';

export const routes: Routes = [
  { path: '', redirectTo: 'kiosko', pathMatch: 'full' },
  { path: 'inicio', component: HomeComponent },
  { path: 'kiosko', component: KioskoComponent },
  { path: 'mesa/:id', component: MesaComponent },
  { path: 'pantalla', component: PantallaComponent },
  { path: '**', redirectTo: '' },
];
