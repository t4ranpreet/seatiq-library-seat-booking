from __future__ import annotations

import asyncio
import os
import secrets
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
DB_PATH = Path(os.getenv("SEATIQ_DB", str(ROOT / "seatiq.sqlite3")))
BREAK_MINUTES = max(1, int(os.getenv("BREAK_MINUTES", "20")))
FLOORS = [
    (1, "The Commons", "Collaborative study", "Floor 1"),
    (2, "Reading Room", "Individual study", "Floor 2"),
    (3, "Quiet Loft", "Silent study", "Floor 3"),
]


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc, tb):
        try:
            return super().__exit__(exc_type, exc, tb)
        finally:
            self.close()


def connect() -> sqlite3.Connection:
    db = sqlite3.connect(DB_PATH, timeout=10, isolation_level=None, factory=ClosingConnection)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def initialize() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS floors (
                id INTEGER PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL, label TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS seats (
                id TEXT PRIMARY KEY, floor_id INTEGER NOT NULL REFERENCES floors(id),
                table_no INTEGER NOT NULL, qr_token TEXT NOT NULL UNIQUE,
                baseline_occupied INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY, display_name TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('student','admin')), created_at TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS bookings (
                id TEXT PRIMARY KEY, seat_id TEXT NOT NULL REFERENCES seats(id),
                display_name TEXT NOT NULL, session_token TEXT NOT NULL REFERENCES sessions(token),
                status TEXT NOT NULL CHECK(status IN ('reserved','occupied','break','released','cancelled')),
                created_at TEXT NOT NULL, checked_in_at TEXT, break_until TEXT, ended_at TEXT
            );
            CREATE INDEX IF NOT EXISTS bookings_seat_status ON bookings(seat_id, status);
            CREATE INDEX IF NOT EXISTS bookings_user_status ON bookings(session_token, status);
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, detail TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
        """)
        if db.execute("SELECT COUNT(*) FROM floors").fetchone()[0] == 0:
            db.executemany("INSERT INTO floors(id,name,description,label) VALUES(?,?,?,?)", FLOORS)
        if db.execute("SELECT COUNT(*) FROM seats").fetchone()[0] == 0:
            for floor_id, *_ in FLOORS:
                prefix = "ABC"[floor_id - 1]
                for i in range(1, 25):
                    seat_id = f"{prefix}{i:02d}"
                    table_no = (i - 1) // 4 + 1
                    occupied = int((floor_id == 1 and i in (1, 8)))
                    db.execute(
                        "INSERT INTO seats(id,floor_id,table_no,qr_token,baseline_occupied) VALUES(?,?,?,?,?)",
                        (seat_id, floor_id, table_no, f"NEXORA-{seat_id}-DEMO", occupied),
                    )


def log_event(db: sqlite3.Connection, kind: str, detail: str) -> None:
    db.execute("INSERT INTO events(kind,detail,created_at) VALUES(?,?,?)", (kind, detail, now().isoformat()))


def expire_breaks(db: sqlite3.Connection) -> None:
    current = now().isoformat()
    rows = db.execute(
        "SELECT id,seat_id FROM bookings WHERE status='break' AND break_until <= ?", (current,)
    ).fetchall()
    for row in rows:
        db.execute("UPDATE bookings SET status='released', ended_at=? WHERE id=?", (current, row["id"]))
        log_event(db, "auto_release", f"{row['seat_id']} was released after the break timer expired")


def session_from_header(x_demo_token: str | None = Header(default=None)) -> sqlite3.Row:
    if not x_demo_token:
        raise HTTPException(401, "Sign in with a demo profile to continue.")
    with connect() as db:
        expire_breaks(db)
        session = db.execute("SELECT * FROM sessions WHERE token=? AND active=1", (x_demo_token,)).fetchone()
    if not session:
        raise HTTPException(401, "Your demo session has ended. Sign in again.")
    return session


def require_admin(session: sqlite3.Row = Depends(session_from_header)) -> sqlite3.Row:
    if session["role"] != "admin":
        raise HTTPException(403, "Admin demo access is required.")
    return session


class DemoLogin(BaseModel):
    display_name: str = Field(min_length=2, max_length=32, pattern=r"^[A-Za-z][A-Za-z0-9 .'-]*$")


class BookingCreate(BaseModel):
    seat_id: str = Field(min_length=3, max_length=8)


class CheckIn(BaseModel):
    qr_token: str = Field(min_length=4, max_length=64)


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize()
    async def release_worker():
        while True:
            await asyncio.sleep(5)
            with connect() as db:
                expire_breaks(db)

    worker = asyncio.create_task(release_worker())
    try:
        yield
    finally:
        worker.cancel()
        try:
            await worker
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="SEATIQ API", version="1.0.0",
    description="Hackathon demo API for library seats, QR-style check-in, breaks, and analytics.",
    lifespan=lifespan,
)


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):
    first = exc.errors()[0]
    field = str(first.get("loc", ["request"])[-1]).replace("_", " ")
    return JSONResponse(status_code=422, content={"detail": f"Please check the {field} and try again."})


@app.get("/api/health")
def health():
    with connect() as db:
        expire_breaks(db)
    return {"status": "ok", "mode": "open demo", "break_minutes": BREAK_MINUTES}


@app.get("/api/floors")
def list_floors():
    with connect() as db:
        expire_breaks(db)
        rows = db.execute("""
            SELECT f.*, COUNT(s.id) AS total,
              SUM(CASE WHEN s.baseline_occupied=0 AND b.id IS NULL THEN 1 ELSE 0 END) AS available
            FROM floors f JOIN seats s ON s.floor_id=f.id
            LEFT JOIN bookings b ON b.seat_id=s.id AND b.status IN ('reserved','occupied','break')
            GROUP BY f.id ORDER BY f.id
        """).fetchall()
    return [dict(row) for row in rows]


@app.get("/api/floors/{floor_id}/seats")
def floor_seats(floor_id: int):
    with connect() as db:
        expire_breaks(db)
        floor = db.execute("SELECT * FROM floors WHERE id=?", (floor_id,)).fetchone()
        if not floor:
            raise HTTPException(404, "Floor not found.")
        rows = db.execute("""
            SELECT s.*, b.id AS booking_id, b.display_name, b.status AS booking_status,
                   b.break_until, b.checked_in_at
            FROM seats s LEFT JOIN bookings b ON b.seat_id=s.id AND b.status IN ('reserved','occupied','break')
            WHERE s.floor_id=? ORDER BY s.id
        """, (floor_id,)).fetchall()
    seats = []
    for row in rows:
        state = row["booking_status"] or ("occupied" if row["baseline_occupied"] else "available")
        seats.append({
            "id": row["id"], "floor_id": row["floor_id"], "table_no": row["table_no"],
            "status": state, "booking_id": row["booking_id"],
            "display_name": row["display_name"], "break_until": row["break_until"],
            "checked_in_at": row["checked_in_at"],
            "qr_token": row["qr_token"] if state in ("reserved", "occupied", "break") else None,
        })
    return {"floor": dict(floor), "seats": seats}


@app.post("/api/demo/session")
def create_student_session(payload: DemoLogin):
    token = secrets.token_urlsafe(28)
    with connect() as db:
        db.execute("INSERT INTO sessions(token,display_name,role,created_at) VALUES(?,?,?,?)",
                   (token, payload.display_name.strip(), "student", now().isoformat()))
    return {"token": token, "display_name": payload.display_name.strip(), "role": "student", "demo": True}


@app.post("/api/demo/admin-session")
def create_admin_session():
    token = secrets.token_urlsafe(28)
    with connect() as db:
        db.execute("INSERT INTO sessions(token,display_name,role,created_at) VALUES(?,?,?,?)",
                   (token, "Demo Librarian", "admin", now().isoformat()))
    return {"token": token, "display_name": "Demo Librarian", "role": "admin", "demo": True}


@app.delete("/api/demo/session")
def sign_out(session: sqlite3.Row = Depends(session_from_header)):
    with connect() as db:
        # Keep the profile row so completed demo bookings retain their foreign key.
        db.execute("UPDATE sessions SET active=0 WHERE token=?", (session["token"],))
    return {"ok": True}


@app.get("/api/me")
def me(session: sqlite3.Row = Depends(session_from_header)):
    with connect() as db:
        expire_breaks(db)
        booking = db.execute("""
            SELECT b.*, s.floor_id, f.name AS floor_name, s.table_no, s.qr_token
            FROM bookings b JOIN seats s ON s.id=b.seat_id JOIN floors f ON f.id=s.floor_id
            WHERE b.session_token=? AND b.status IN ('reserved','occupied','break')
            ORDER BY b.created_at DESC LIMIT 1
        """, (session["token"],)).fetchone()
    return {"display_name": session["display_name"], "role": session["role"], "booking": dict(booking) if booking else None}


@app.post("/api/bookings", status_code=201)
def create_booking(payload: BookingCreate, session: sqlite3.Row = Depends(session_from_header)):
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        expire_breaks(db)
        seat = db.execute("SELECT * FROM seats WHERE id=?", (payload.seat_id.upper(),)).fetchone()
        if not seat:
            raise HTTPException(404, "Seat not found.")
        if seat["baseline_occupied"]:
            raise HTTPException(409, "That seat is occupied.")
        if db.execute("SELECT 1 FROM bookings WHERE session_token=? AND status IN ('reserved','occupied','break')", (session["token"],)).fetchone():
            raise HTTPException(409, "You already have an active seat. Finish or cancel it first.")
        if db.execute("SELECT 1 FROM bookings WHERE seat_id=? AND status IN ('reserved','occupied','break')", (seat["id"],)).fetchone():
            raise HTTPException(409, "That seat was just reserved. Choose another one.")
        booking_id = secrets.token_urlsafe(12)
        db.execute("INSERT INTO bookings(id,seat_id,display_name,session_token,status,created_at) VALUES(?,?,?,?,?,?)",
                   (booking_id, seat["id"], session["display_name"], session["token"], "reserved", now().isoformat()))
        log_event(db, "reserved", f"{seat['id']} reserved by {session['display_name']}")
    return {"id": booking_id, "seat_id": seat["id"], "status": "reserved", "qr_token": seat["qr_token"]}


def owned_booking(db: sqlite3.Connection, booking_id: str, session: sqlite3.Row) -> sqlite3.Row:
    row = db.execute("SELECT b.*,s.qr_token FROM bookings b JOIN seats s ON s.id=b.seat_id WHERE b.id=?", (booking_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Booking not found.")
    if row["session_token"] != session["token"] and session["role"] != "admin":
        raise HTTPException(403, "This booking belongs to another demo profile.")
    return row


@app.post("/api/bookings/{booking_id}/check-in")
def check_in(booking_id: str, payload: CheckIn, session: sqlite3.Row = Depends(session_from_header)):
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        expire_breaks(db)
        booking = owned_booking(db, booking_id, session)
        if booking["status"] != "reserved":
            raise HTTPException(409, "Only a reserved seat can be checked in.")
        if not secrets.compare_digest(payload.qr_token, booking["qr_token"]):
            raise HTTPException(400, "That QR token does not match this seat.")
        stamp = now().isoformat()
        db.execute("UPDATE bookings SET status='occupied',checked_in_at=? WHERE id=?", (stamp, booking_id))
        log_event(db, "check_in", f"{booking['seat_id']} checked in by {booking['display_name']}")
    return {"id": booking_id, "seat_id": booking["seat_id"], "status": "occupied", "checked_in_at": stamp}


@app.post("/api/bookings/{booking_id}/break")
def start_break(booking_id: str, session: sqlite3.Row = Depends(session_from_header)):
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        expire_breaks(db)
        booking = owned_booking(db, booking_id, session)
        if booking["status"] != "occupied":
            raise HTTPException(409, "Check in before starting a break.")
        deadline = now() + timedelta(minutes=BREAK_MINUTES)
        db.execute("UPDATE bookings SET status='break',break_until=? WHERE id=?", (deadline.isoformat(), booking_id))
        log_event(db, "break_started", f"{booking['seat_id']} break ends at {deadline.strftime('%H:%M UTC')}")
    return {"id": booking_id, "seat_id": booking["seat_id"], "status": "break", "break_until": deadline.isoformat()}


@app.post("/api/bookings/{booking_id}/return")
def return_from_break(booking_id: str, session: sqlite3.Row = Depends(session_from_header)):
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        expire_breaks(db)
        booking = owned_booking(db, booking_id, session)
        if booking["status"] != "break":
            raise HTTPException(409, "This seat is not on a break.")
        db.execute("UPDATE bookings SET status='occupied',break_until=NULL WHERE id=?", (booking_id,))
        log_event(db, "returned", f"{booking['seat_id']} returned from break")
    return {"id": booking_id, "seat_id": booking["seat_id"], "status": "occupied"}


@app.post("/api/bookings/{booking_id}/cancel")
def cancel_booking(booking_id: str, session: sqlite3.Row = Depends(session_from_header)):
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        expire_breaks(db)
        booking = owned_booking(db, booking_id, session)
        if booking["status"] != "reserved":
            raise HTTPException(409, "Only a not-yet-checked-in reservation can be cancelled.")
        db.execute("UPDATE bookings SET status='cancelled',ended_at=? WHERE id=?", (now().isoformat(), booking_id))
        log_event(db, "cancelled", f"{booking['seat_id']} reservation cancelled")
    return {"ok": True, "status": "cancelled"}


@app.get("/api/admin/analytics")
def analytics(_: sqlite3.Row = Depends(require_admin)):
    with connect() as db:
        expire_breaks(db)
        floors = db.execute("""
            SELECT f.id,f.name,COUNT(s.id) AS total,
              SUM(CASE WHEN COALESCE(b.status, CASE WHEN s.baseline_occupied=1 THEN 'occupied' ELSE 'available' END)='available' THEN 1 ELSE 0 END) AS available,
              SUM(CASE WHEN COALESCE(b.status, CASE WHEN s.baseline_occupied=1 THEN 'occupied' ELSE 'available' END)='reserved' THEN 1 ELSE 0 END) AS reserved,
              SUM(CASE WHEN COALESCE(b.status, CASE WHEN s.baseline_occupied=1 THEN 'occupied' ELSE 'available' END)='occupied' THEN 1 ELSE 0 END) AS occupied,
              SUM(CASE WHEN COALESCE(b.status, CASE WHEN s.baseline_occupied=1 THEN 'occupied' ELSE 'available' END)='break' THEN 1 ELSE 0 END) AS on_break
            FROM floors f JOIN seats s ON s.floor_id=f.id
            LEFT JOIN bookings b ON b.seat_id=s.id AND b.status IN ('reserved','occupied','break')
            GROUP BY f.id ORDER BY f.id
        """).fetchall()
        events = db.execute("SELECT * FROM events ORDER BY id DESC LIMIT 12").fetchall()
        totals = db.execute("""
            SELECT COUNT(*) AS total, SUM(CASE WHEN status='available' THEN 1 ELSE 0 END) AS available,
                   SUM(CASE WHEN status='reserved' THEN 1 ELSE 0 END) AS reserved,
                   SUM(CASE WHEN status='occupied' THEN 1 ELSE 0 END) AS occupied,
                   SUM(CASE WHEN status='break' THEN 1 ELSE 0 END) AS on_break
            FROM (SELECT CASE WHEN b.status IS NOT NULL THEN b.status WHEN s.baseline_occupied=1 THEN 'occupied' ELSE 'available' END AS status
                  FROM seats s LEFT JOIN bookings b ON b.seat_id=s.id AND b.status IN ('reserved','occupied','break'))
        """).fetchone()
    return {"totals": dict(totals), "floors": [dict(row) for row in floors], "recent_activity": [dict(row) for row in events], "break_minutes": BREAK_MINUTES, "demo_only": True}


@app.post("/api/admin/reset")
def reset_demo(_: sqlite3.Row = Depends(require_admin)):
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("DELETE FROM events")
        db.execute("DELETE FROM bookings")
        log_event(db, "reset", "Demo data was restored to the seed state")
    return {"ok": True, "message": "Demo bookings cleared. Seed availability restored."}


if FRONTEND.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND), name="assets")


@app.get("/{path:path}", include_in_schema=False)
def frontend(path: str):
    index = FRONTEND / "index.html"
    if not index.exists():
        raise HTTPException(404, "Frontend files not found.")
    return FileResponse(index)

