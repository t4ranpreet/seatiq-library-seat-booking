# SEATIQ — squad execution guide

**Problem:** Students lose time searching for open library seats, while seats can sit unused after someone leaves.  
**Solution:** A live seat map, short reservation flow, check-in code, timed break, and occupancy view for library staff.

## Roles for a four-person beginner squad

| Member | Owns | Finish line |
| --- | --- | --- |
| 1 · Student experience | `frontend/app.js`, `frontend/styles.css` | A judge can find a floor, select a seat, and understand its status. |
| 2 · API and data | `backend/app/main.py`, `backend/requirements.txt` | Seat states and bookings persist and the API docs work. |
| 3 · Check-in lifecycle | Booking/check-in/break endpoints and the pass view | A reserved seat checks in, starts a break, returns, or expires. |
| 4 · Integration and story | `README.md`, admin view, final demo | The full journey runs smoothly and the team can explain its limits. |

Everyone should run the same main flow before the last hour. Keep changes in the listed files and agree on request/response shapes before parallel edits.

## Twelve-hour build schedule

| Time | Milestone | Showable outcome |
| --- | --- | --- |
| 0:00–1:00 | Environment and scope | App starts; team agrees on student → reservation → check-in → break → analytics. |
| 1:00–3:00 | Seat map and API contract | Three floors display 72 seats; available seats can be selected. |
| 3:00–5:00 | Persistence and reservation | A fictional demo profile reserves a seat; the seat state changes. |
| 5:00–7:00 | Check-in code | Seat pass shows its code and check-in changes state to occupied. |
| 7:00–9:00 | Break and release | Return restores occupied state; timer expiry releases the seat. |
| 9:00–10:30 | Admin view and integration | Occupancy totals and recent activity update from the same SQLite data. |
| 10:30–11:30 | Two-session demo and polish | Confirm duplicate seat booking is rejected; refine the small-screen layout. |
| 11:30–12:00 | Reset and rehearse | Seed the demo, agree on speaker order, rehearse the short pitch. |

## Using your local Qwen models

Use **Qwen2.5 7B Instruct** for focused coding tasks and **Qwen3 VL 8B Instruct** when someone needs help interpreting a screenshot. Give each request one file or one bug at a time. Ask the model to summarize its change and avoid rewriting files owned by another member. A teammate should review every generated edit before integration.

### Coding prompt

```text
We are beginners building SEATIQ, a Python FastAPI + React library seat demo.
Task: [one small task]
Files you may edit: [exact files]
Do not change API routes or response shapes unless asked.
Keep demo data fictional and explain the change in simple language.
Return: changed-file list, complete replacement content or a small patch, and
3 manual steps a beginner can use to verify it. Do not claim those steps ran.
```

### Screenshot review prompt (Qwen3 VL)

```text
This is the current SEATIQ screen. Identify visible layout or wording issues
for a student using a phone. Do not infer backend behavior from the screenshot.
Give the 3 most useful changes and the exact file/component likely responsible.
```

## Integration checkpoints

1. Keep seat IDs consistent: `A01`–`A24`, `B01`–`B24`, `C01`–`C24`.
2. The seat states are `available`, `reserved`, `occupied`, and `break`.
3. Reservation must be created by the backend; the browser must not decide which seat is free.
4. Check-in uses the token that belongs to that booking's seat.
5. Break expiry is checked on API requests, so the next refresh displays released availability.
6. A failed request should show the API's readable message and let the user try again.

## Short judging pitch

> Finding a library seat should take seconds, not a lap around every floor. SEATIQ shows open seats across three study spaces, reserves one, and gives the student a check-in pass. A short break keeps the seat temporarily held; if the student does not return, the system releases it automatically. Library staff can see occupancy by floor. This prototype demonstrates the full seat lifecycle with local demo data, and the next step is university sign-in and production access controls.

## Demo safety

- Use fictional names only.
- The demo admin mode is intentionally open; never expose it as real staff access.
- The seat token and “Simulate QR check-in” button demonstrate the workflow; this version does not request camera access or scan a physical code.
- The app's 20-minute timer is server-controlled. Set `BREAK_MINUTES=1` before startup for the live timeout demonstration.
- Restore seed state before judging with **Reset demo data** in Admin view.

