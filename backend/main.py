"""Sistema de turnos para laboratorio (tipo banco).
Ejecutar:  uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""
import asyncio
import sqlite3
from datetime import date, datetime

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ---------- Configuración ----------
SERVICES = {                       # prefijo -> nombre del servicio
    "A": "Toma de muestras",
    "B": "Entrega de resultados",
}
DESKS = [1, 2, 3, 4]               # mesas disponibles
CALL_TIMEOUT_SECONDS = 60          # tiempo máximo para presentarse tras el llamado
ATTENDING_TIMEOUT_SECONDS = 60     # duración máxima de una atención
DB_FILE = "turnos.db"

# ---------- Base de datos ----------
db = sqlite3.connect(DB_FILE, check_same_thread=False)
db.row_factory = sqlite3.Row
db.execute(
    """CREATE TABLE IF NOT EXISTS tickets(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        prefix TEXT, number INTEGER, code TEXT,
        status TEXT,            -- espera | llamado | atendiendo | finalizado | ausente
        desk INTEGER, day TEXT,
        created_at TEXT, called_at TEXT, finished_at TEXT)"""
)
db.commit()
lock = asyncio.Lock()


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def today() -> str:
    return date.today().isoformat()


def get_state() -> dict:
    day = today()
    active = db.execute(
        "SELECT * FROM tickets WHERE day=? AND status IN ('llamado','atendiendo')", (day,)
    ).fetchall()
    by_desk = {r["desk"]: dict(r) for r in active}
    waiting = [
        dict(r)
        for r in db.execute(
            "SELECT * FROM tickets WHERE day=? AND status='espera' ORDER BY id", (day,)
        )
    ]
    return {
        "services": [{"prefix": k, "name": v} for k, v in SERVICES.items()],
        "desks": [{"id": d, "name": f"Mesa {d}", "ticket": by_desk.get(d)} for d in DESKS],
        "waiting": waiting,
    }


def active_ticket(desk: int):
    return db.execute(
        "SELECT * FROM tickets WHERE day=? AND desk=? AND status IN ('llamado','atendiendo')",
        (today(), desk),
    ).fetchone()


async def dispatch_to_desk(desk: int):
    """Llama al turno más antiguo y programa su vencimiento."""
    async with lock:
        if active_ticket(desk):
            return None
        row = db.execute(
            "SELECT * FROM tickets WHERE day=? AND status='espera' ORDER BY id LIMIT 1", (today(),)
        ).fetchone()
        if not row:
            return None
        db.execute(
            "UPDATE tickets SET status='llamado', desk=?, called_at=? WHERE id=?",
            (desk, now(), row["id"]),
        )
        db.commit()
        ticket = dict(db.execute("SELECT * FROM tickets WHERE id=?", (row["id"],)).fetchone())
    await hub.state()
    await hub.broadcast({"type": "call", "desk": desk, "ticket": ticket})
    asyncio.create_task(expire_called_ticket(desk, ticket["id"]))
    return ticket


async def expire_called_ticket(desk: int, ticket_id: int):
    """Marca ausente si no se presenta en un minuto y llama al siguiente."""
    called = db.execute(
        "SELECT called_at FROM tickets WHERE id=? AND day=? AND desk=? AND status='llamado'",
        (ticket_id, today(), desk),
    ).fetchone()
    if not called:
        return
    elapsed = (datetime.now() - datetime.fromisoformat(called["called_at"])).total_seconds()
    await asyncio.sleep(max(0, CALL_TIMEOUT_SECONDS - elapsed))
    async with lock:
        row = db.execute(
            "SELECT id FROM tickets WHERE id=? AND day=? AND desk=? AND status='llamado'",
            (ticket_id, today(), desk),
        ).fetchone()
        if not row:
            return
        db.execute(
            "UPDATE tickets SET status='ausente', finished_at=? WHERE id=?",
            (now(), ticket_id),
        )
        db.commit()
    await hub.state()
    await dispatch_to_desk(desk)


def check_desk(desk: int):
    if desk not in DESKS:
        raise HTTPException(404, "Mesa inexistente")


# ---------- WebSocket hub ----------
class Hub:
    def __init__(self):
        self.clients: set[WebSocket] = set()

    async def broadcast(self, message: dict):
        for ws in list(self.clients):
            try:
                await ws.send_json(message)
            except Exception:
                self.clients.discard(ws)

    async def state(self):
        await self.broadcast({"type": "state", "state": get_state()})


hub = Hub()

# ---------- API ----------
app = FastAPI(title="Turnos Laboratorio")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class NewTicket(BaseModel):
    service: str = "A"


@app.get("/api/state")
async def state():
    return get_state()


@app.post("/api/tickets")
async def create_ticket(body: NewTicket):
    if body.service not in SERVICES:
        raise HTTPException(400, "Servicio inválido")
    async with lock:
        n = db.execute(
            "SELECT COALESCE(MAX(number),0)+1 FROM tickets WHERE day=? AND prefix=? AND status IN ('espera','llamado','atendiendo')",
            (today(), body.service),
        ).fetchone()[0]
        code = f"{body.service}{n:02d}"
        cur = db.execute(
            "INSERT INTO tickets(prefix,number,code,status,day,created_at) VALUES(?,?,?,?,?,?)",
            (body.service, n, code, "espera", today(), now()),
        )
        db.commit()
        ticket = dict(db.execute("SELECT * FROM tickets WHERE id=?", (cur.lastrowid,)).fetchone())
    assigned = None
    for desk in DESKS:
        assigned = await dispatch_to_desk(desk)
        if assigned:
            ticket = dict(db.execute("SELECT * FROM tickets WHERE id=?", (ticket["id"],)).fetchone())
            break
    if not assigned:
        await hub.state()
    return ticket


@app.post("/api/desks/{desk}/call-next")
async def call_next(desk: int):
    check_desk(desk)
    ticket = await dispatch_to_desk(desk)
    if not ticket:
        if active_ticket(desk):
            raise HTTPException(409, "Finaliza o marca ausente el turno actual primero")
        raise HTTPException(404, "No hay turnos en espera")
    return ticket

@app.post("/api/desks/{desk}/recall")
async def recall(desk: int):
    check_desk(desk)
    row = active_ticket(desk)
    if not row:
        raise HTTPException(404, "La mesa no tiene turno activo")
    await hub.broadcast({"type": "call", "desk": desk, "ticket": dict(row)})
    return dict(row)


async def _transition(desk: int, allowed: tuple, new_status: str):
    check_desk(desk)
    async with lock:
        row = active_ticket(desk)
        if not row or row["status"] not in allowed:
            raise HTTPException(409, "Acción no válida para el estado actual")
        db.execute(
            "UPDATE tickets SET status=?, finished_at=? WHERE id=?",
            (new_status, now() if new_status in ("finalizado", "ausente") else None, row["id"]),
        )
        db.commit()
    await hub.state()
    if new_status == "atendiendo":
        asyncio.create_task(expire_attending_ticket(desk, row["id"]))
    return {"ok": True}


async def expire_attending_ticket(desk: int, ticket_id: int):
    """Finaliza la atención al cumplir un minuto y llama al siguiente turno."""
    await asyncio.sleep(ATTENDING_TIMEOUT_SECONDS)
    async with lock:
        row = db.execute(
            "SELECT id FROM tickets WHERE id=? AND day=? AND desk=? AND status='atendiendo'",
            (ticket_id, today(), desk),
        ).fetchone()
        if not row:
            return
        db.execute(
            "UPDATE tickets SET status='finalizado', finished_at=? WHERE id=?",
            (now(), ticket_id),
        )
        db.commit()
    await hub.state()
    await dispatch_to_desk(desk)


@app.post("/api/desks/{desk}/start")
async def start(desk: int):
    return await _transition(desk, ("llamado",), "atendiendo")


@app.post("/api/desks/{desk}/finish")
async def finish(desk: int):
    return await _transition(desk, ("llamado", "atendiendo"), "finalizado")


@app.post("/api/desks/{desk}/no-show")
async def no_show(desk: int):
    return await _transition(desk, ("llamado",), "ausente")


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    hub.clients.add(ws)
    try:
        # Recupera temporizadores de llamados que seguían activos tras reiniciar el servidor.
        active_calls = db.execute(
            "SELECT id, desk FROM tickets WHERE day=? AND status='llamado'",
            (today(),),
        ).fetchall()
        for call in active_calls:
            asyncio.create_task(expire_called_ticket(call["desk"], call["id"]))
        await ws.send_json({"type": "state", "state": get_state()})
        while True:
            await ws.receive_text()     # mantiene la conexión viva
    except WebSocketDisconnect:
        pass
    finally:
        hub.clients.discard(ws)
