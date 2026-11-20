# SEATIQ — smart library seat booking

**Find a seat. Check in. Study without the guesswork.**

SEATIQ is a hackathon-ready library seat reservation demo. It includes a React student experience, a FastAPI backend, SQLite persistence, QR-style check-in, a 20-minute break with server-side auto-release, and an admin occupancy view.

## Demo highlights

- Browse three floors and 72 seeded seats without signing in.
- Sign in using a fictional display name in **Demo mode**. No email, password, or real student number is requested.
- Reserve an available seat; the server prevents duplicate active reservations for a seat or student.
- Check in using the seat's displayed QR token (or the demo scan button).
- Start a 20-minute break, return early, or let the server release the seat when time runs out.
- Open **Admin view** to see occupancy and recent activity. Demo-only access is clearly labeled.
- SQLite data survives restarts. Use **Reset demo data** from the admin view to restore the seed state.

> This is a hackathon prototype, not a production identity or access-control system. Demo login and admin mode are intentionally open. Use fictional names only; do not collect real student data or deploy this demo as an operational booking service.

## Quick start

Requirements: Python 3.10 or newer. On Windows, double-click `start.bat`; first startup creates an environment and installs the small Python dependency list.

```bash
cd backend
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000>. The API reference is at <http://127.0.0.1:8000/docs>.

The backend serves the included React UI from `frontend/`. The UI uses React and ReactDOM from the public `esm.sh` CDN; an internet connection is needed to load those two runtime modules. The API and demo data remain local.

## API overview

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Health and demo mode status |
| GET | `/api/floors` | Floor list and available seat counts |
| GET | `/api/floors/{floor_id}/seats` | Seat map and current states |
| POST | `/api/demo/session` | Create a fictional demo session |
| GET | `/api/me` | Current demo profile and active booking |
| POST | `/api/bookings` | Reserve an available seat |
| POST | `/api/bookings/{id}/check-in` | Check in with the seat QR token |
| POST | `/api/bookings/{id}/break` | Start a timed break |
| POST | `/api/bookings/{id}/return` | Return early from break |
| POST | `/api/bookings/{id}/cancel` | Cancel an unoccupied reservation |
| GET | `/api/admin/analytics` | Demo occupancy and activity dashboard |
| POST | `/api/admin/reset` | Restore demo seed data |

## 12-hour beginner hackathon runbook

1. **Hour 1 — Start up:** install Python, create the environment, run the app, open `/docs`.
2. **Hours 2–3 — UI:** adjust labels, colors, floor names, and seat layout in `frontend/`.
3. **Hours 4–5 — API/data:** explain `backend/app/main.py`, inspect SQLite tables and API responses.
4. **Hours 6–7 — Booking/check-in:** walk through a reservation and the seat token check-in flow.
5. **Hours 8–9 — Break lifecycle:** set `BREAK_MINUTES=1` for a short demo; let the server release a seat after expiry.
6. **Hours 10–11 — Integration:** use two browser sessions to show that a seat cannot be reserved twice; check the admin occupancy view.
7. **Hour 12 — Presentation:** restore demo data and use the talk track below.

Suggested squad split: **Member 1** React UI, **Member 2** FastAPI and SQLite, **Member 3** QR/check-in and break lifecycle, **Member 4** analytics, integration, and judging demo. Pair on integration milestones instead of waiting for a handoff.

## Suggested judging demo (3 minutes)

1. Show the public floor directory and live availability.
2. Sign in as `Demo Student`, reserve an available seat, and show the seat change state.
3. Check in using the displayed token and show the occupied pass.
4. Start a break. Explain the 20-minute deadline; for a live timeout, set `BREAK_MINUTES=1` and restart the server.
5. Open Admin view to show seat occupancy and the recent activity feed.

## Project structure

```text
seatiq/
├── backend/
│   ├── app/main.py       # API, persistence, seat lifecycle, seed data
│   └── requirements.txt
├── frontend/
│   ├── index.html
│   ├── app.jsx           # React UI
│   └── styles.css
├── .env.example
├── .gitignore
├── Dockerfile
└── README.md
```

## Next steps before real deployment

- Replace demo sessions with university SSO and role-based admin authorization.
- Put the database on PostgreSQL, add migrations and automated backup.
- Issue signed, expiring check-in tokens per booking; use a physical QR per seat.
- Add HTTPS, rate limiting, audit logs, privacy policy, and data retention rules.
- Add automated API and browser tests and validate behavior with multiple concurrent users.

## Team checklist

- [ ] Confirm Python and install dependencies.
- [ ] Start the server and open the interactive API docs.
- [ ] Run the student booking → check-in → break → return demo.
- [ ] Run the timeout demo with `BREAK_MINUTES=1`.
- [ ] Review admin view and reset seed data before judging.
- [ ] Keep personal data out of screenshots, demo input, and repository history.

