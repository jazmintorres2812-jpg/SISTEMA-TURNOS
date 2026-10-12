# Sistema de turnos

Aplicación web para emitir turnos, mostrar la fila de espera y atender pacientes desde mesas. Incluye backend FastAPI y frontend Angular.

## Estructura

- `backend/`: API FastAPI, WebSocket y almacenamiento SQLite local.
- `turnos-web/`: aplicación Angular activa.
- `frontend/`: fuentes frontend de la versión inicial del proyecto.

## Requisitos

- Python 3.10 o superior
- Node.js y npm

## Iniciar el backend (Windows PowerShell)

```powershell
cd backend
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

La base de datos `turnos.db` se crea localmente al iniciar el backend y no se sube al repositorio.

## Iniciar el frontend

En otra terminal:

```powershell
cd turnos-web
npm install
npx ng serve --host 0.0.0.0
```

Abre `http://localhost:4200`. La ruta inicial abre el kiosco. Las pantallas disponibles son:

- `/kiosko`: emitir un turno.
- `/pantalla`: tablero de espera y mesas.
- `/mesa/1` a `/mesa/4`: controles del operador.
- `/inicio`: menú de navegación.

El backend escucha en el puerto `8000`. Para usar otros equipos en la red local, abre el frontend con la IP del equipo servidor.

## Publicar la interfaz en Vercel

El frontend Angular se despliega desde GitHub como proyecto separado. En Vercel importa este repositorio y configura **Root Directory** como `turnos-web`; el archivo `vercel.json` fija el comando de compilación y el directorio de salida, y mantiene operativas las rutas Angular.

Antes de desplegar, configura `turnos-web/public/api-config.js` con la URL HTTPS del backend en `window.TURNOS_API_URL`. En la API hay que permitir en CORS el dominio de Vercel. La API actual usa WebSocket, SQLite local y temporizadores en memoria; no puede publicarse en Vercel Functions tal cual. Debe alojarse en un servicio persistente con WebSockets y base de datos persistente, o adaptarse a un backend administrado compatible.
