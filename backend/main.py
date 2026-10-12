"""Sistema de turnos para laboratorio (tipo banco).
Ejecutar:  uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""
import asyncio
import os
import sqlite3
from contextvars import ContextVar
from datetime import date, datetime
from pathlib import Path

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
DB_FILE = os.getenv("TURNOS_DB_FILE", str(Path(__file__).with_name("turnos.db")))
DATABASE_URL = os.getenv("DATABASE_URL", "").replace("postgres://", "postgresql://", 1)


class PgRow(dict):
    """PostgreSQL row with sqlite.Row-style key and index access."""
    def __getitem__(self, key):
        if isinstance(key, int):
            return tuple(self.values())[key]
        return super().__getitem__(key)


class PgResult:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class PgDatabase:
    """Small sqlite-compatible adapter; request connections come from middleware."""
    def __init__(self, url):
        import psycopg
        from psycopg.rows import dict_row
        self.psycopg = psycopg
        self.dict_row = dict_row
        self.url = url
        self.connection = ContextVar("turnos_pg_connection", default=None)
        self.row_factory = None

    def execute(self, sql, params=()):
        conn = self.connection.get()
        owned = conn is None
        if owned:
            conn = self.psycopg.connect(self.url, row_factory=self.dict_row)
        try:
            cursor = conn.cursor()
            cursor.execute(sql.replace("?", "%s"), tuple(params))
            rows = [PgRow(row) for row in cursor.fetchall()] if cursor.description else []
            if owned:
                conn.commit()
            return PgResult(rows)
        finally:
            if owned:
                conn.close()

    def commit(self):
        conn = self.connection.get()
        if conn is not None:
            conn.commit()


# ---------- Base de datos ----------
if DATABASE_URL:
    import psycopg
    from psycopg.rows import dict_row

    db = PgDatabase(DATABASE_URL)
    db.execute(
        """CREATE TABLE IF NOT EXISTS tickets(
            id BIGSERIAL PRIMARY KEY,
            prefix TEXT, number INTEGER, code TEXT,
            status TEXT, desk INTEGER, day TEXT,
            created_at TEXT, called_at TEXT, started_at TEXT, finished_at TEXT)"""
    )
    db.execute("ALTER TABLE tickets ADD COLUMN IF NOT EXISTS started_at TEXT")
else:
    db = sqlite3.connect(DB_FILE, check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute(
        """CREATE TABLE IF NOT EXISTS tickets(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prefix TEXT, number INTEGER, code TEXT,
            status TEXT,            -- espera | llamado | atendiendo | finalizado | ausente
            desk INTEGER, day TEXT,
            created_at TEXT, called_at TEXT, started_at TEXT, finished_at TEXT)"""
    )
    columns = {row["name"] for row in db.execute("PRAGMA table_info(tickets)").fetchall()}
    if "started_at" not in columns:
        db.execute("ALTER TABLE tickets ADD COLUMN started_at TEXT")
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
    for_update = " FOR UPDATE" if DATABASE_URL else ""
    return db.execute(
        "SELECT * FROM tickets WHERE day=? AND desk=? AND status IN ('llamado','atendiendo')" + for_update,
        (today(), desk),
    ).fetchone()


async def dispatch_to_desk(desk: int):
    """Llama al turno más antiguo y programa su vencimiento."""
    async with lock:
        if DATABASE_URL:
            db.execute("SELECT pg_advisory_xact_lock(hashtext(?))", (f"desk:{today()}:{desk}",))
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

if DATABASE_URL:
    @app.middleware("http")
    async def postgres_request_connection(request, call_next):
        connection = psycopg.connect(DATABASE_URL, row_factory=dict_row, connect_timeout=10)
        token = db.connection.set(connection)
        try:
            response = await call_next(request)
            connection.commit()
            return response
        except Exception:
            connection.rollback()
            raise
        finally:
            db.connection.reset(token)
            connection.close()


class NewTicket(BaseModel):
    service: str = "A"


@app.get("/api/state")
async def state():
    await refresh_due_tickets()
    return get_state()


async def refresh_due_tickets():
    """Move expired tickets forward when the serverless API is polled."""
    current = datetime.now()
    for desk in DESKS:
        was_expired = False
        is_free = False
        async with lock:
            if DATABASE_URL:
                db.execute("SELECT pg_advisory_xact_lock(hashtext(?))", (f"desk:{today()}:{desk}",))
            row = active_ticket(desk)
            if not row:
                is_free = True
            elif row["status"] == "llamado" and row["called_at"]:
                elapsed = (current - datetime.fromisoformat(row["called_at"])).total_seconds()
                if elapsed >= CALL_TIMEOUT_SECONDS:
                    db.execute(
                        "UPDATE tickets SET status='ausente', finished_at=? WHERE id=?",
                        (now(), row["id"]),
                    )
                    db.commit()
                    was_expired = True
            elif row["status"] == "atendiendo" and row["started_at"]:
                elapsed = (current - datetime.fromisoformat(row["started_at"])).total_seconds()
                if elapsed >= ATTENDING_TIMEOUT_SECONDS:
                    db.execute(
                        "UPDATE tickets SET status='finalizado', finished_at=?, started_at=NULL WHERE id=?",
                        (now(), row["id"]),
                    )
                    db.commit()
                    was_expired = True
        if was_expired:
            await hub.state()
        if was_expired or is_free:
            await dispatch_to_desk(desk)


@app.post("/api/tickets")
async def create_ticket(body: NewTicket):
    if body.service not in SERVICES:
        raise HTTPException(400, "Servicio inválido")
    async with lock:
        if DATABASE_URL:
            db.execute("SELECT pg_advisory_xact_lock(hashtext(?))", (f"ticket:{today()}:{body.service}",))
        n = db.execute(
            "SELECT COALESCE(MAX(number),0)+1 FROM tickets WHERE day=? AND prefix=? AND status IN ('espera','llamado','atendiendo')",
            (today(), body.service),
        ).fetchone()[0]
        code = f"{body.service}{n:02d}"
        cur = db.execute(
            "INSERT INTO tickets(prefix,number,code,status,day,created_at) VALUES(?,?,?,?,?,?) RETURNING id",
            (body.service, n, code, "espera", today(), now()),
        )
        ticket_id = cur.fetchone()[0]
        db.commit()
        ticket = dict(db.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,)).fetchone())
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
            "UPDATE tickets SET status=?, finished_at=?, started_at=? WHERE id=?",
            (
                new_status,
                now() if new_status in ("finalizado", "ausente") else None,
                now() if new_status == "atendiendo" else None,
                row["id"],
            ),
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
            "UPDATE tickets SET status='finalizado', finished_at=?, started_at=NULL WHERE id=?",
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


# Vercel builds the Angular app first, then FastAPI serves its files and API together.
FRONTEND_DIST = Path(__file__).resolve().parents[1] / "turnos-web" / "dist" / "turnos-web" / "browser"
app.frontend("/", directory=str(FRONTEND_DIST), fallback="index.html")
