import React, { useCallback, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import QRCode from "qrcode";

const h = React.createElement;
const FLOOR_LABELS = ["The Commons", "Reading Room", "Quiet Loft"];
const fmtTime = (iso) => iso ? new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "—";
const initials = (name = "Guest") => name.split(/\s+/).map((part) => part[0]).slice(0, 2).join("").toUpperCase();

function App() {
  const [page, setPage] = useState("home");
  const [floor, setFloor] = useState(1);
  const [floors, setFloors] = useState([]);
  const [map, setMap] = useState({ floor: null, seats: [] });
  const [selected, setSelected] = useState(null);
  const [session, setSession] = useState(() => {
    try { return JSON.parse(localStorage.getItem("seatiq-demo-session") || "null"); } catch { return null; }
  });
  const [profile, setProfile] = useState(null);
  const [booking, setBooking] = useState(null);
  const [analytics, setAnalytics] = useState(null);
  const [name, setName] = useState("");
  const [qrImage, setQrImage] = useState("");
  const [notice, setNotice] = useState(null);
  const [busy, setBusy] = useState(false);

  const api = useCallback(async (path, options = {}) => {
    const response = await fetch(`/api${path}`, {
      ...options,
      headers: { "Content-Type": "application/json", ...(session?.token ? { "X-Demo-Token": session.token } : {}), ...options.headers },
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || `Request failed (${response.status})`);
    return data;
  }, [session]);

  const tell = (message, kind = "success") => {
    setNotice({ message, kind });
    window.clearTimeout(tell.timer);
    tell.timer = window.setTimeout(() => setNotice(null), 3800);
  };

  const refresh = useCallback(async () => {
    try {
      const [f, m] = await Promise.all([api("/floors"), api(`/floors/${floor}/seats`)]);
      setFloors(f); setMap(m);
      if (session) {
        const me = await api("/me");
        setProfile(me); setBooking(me.booking);
      }
      if (session?.role === "admin") setAnalytics(await api("/admin/analytics"));
    } catch (error) {
      if (error.message.includes("session")) {
        localStorage.removeItem("seatiq-demo-session"); setSession(null); setProfile(null); setBooking(null);
      }
    }
  }, [api, floor, session]);

  useEffect(() => { refresh(); }, [refresh]);
  useEffect(() => {
    const timer = window.setInterval(refresh, 10000);
    return () => window.clearInterval(timer);
  }, [refresh]);
  useEffect(() => {
    if (booking?.qr_token) QRCode.toDataURL(booking.qr_token, { width: 176, margin: 1, color: { dark: "#18352f", light: "#ffffff" } }).then(setQrImage).catch(() => setQrImage(""));
    else setQrImage("");
  }, [booking?.qr_token]);

  async function signIn(event, asAdmin = false) {
    event?.preventDefault(); setBusy(true);
    try {
      const result = asAdmin
        ? await fetch("/api/demo/admin-session", { method: "POST" }).then(async (res) => { const data = await res.json(); if (!res.ok) throw new Error(data.detail || "Could not open demo admin"); return data; })
        : await fetch("/api/demo/session", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ display_name: name.trim() || "Demo Student" }) }).then(async (res) => { const data = await res.json(); if (!res.ok) throw new Error(data.detail || "Could not open demo profile"); return data; });
      localStorage.setItem("seatiq-demo-session", JSON.stringify(result)); setSession(result); setPage(asAdmin ? "admin" : "home");
      tell(asAdmin ? "Demo admin view opened." : `Welcome, ${result.display_name}. This is a demo profile.`);
    } catch (error) { tell(error.message, "error"); }
    finally { setBusy(false); }
  }

  async function signOut() {
    try { await api("/demo/session", { method: "DELETE" }); } catch { /* Local demo sign-out still completes. */ }
    localStorage.removeItem("seatiq-demo-session"); setSession(null); setProfile(null); setBooking(null); setPage("home"); tell("Signed out of demo mode.");
  }

  async function action(run, success) {
    setBusy(true);
    try { await run(); await refresh(); tell(success); }
    catch (error) { tell(error.message, "error"); await refresh(); }
    finally { setBusy(false); }
  }

  async function reserve(seat) {
    if (!session) { setSelected(seat); setPage("login"); return; }
    await action(async () => { const result = await api("/bookings", { method: "POST", body: JSON.stringify({ seat_id: seat.id }) }); setSelected(seat); setPage("pass"); return result; }, `Seat ${seat.id} reserved. Check in when you arrive.`);
  }

  async function resetDemo() {
    if (!window.confirm("Reset demo bookings and restore seed availability? This clears demo reservations.")) return;
    await action(() => api("/admin/reset", { method: "POST" }), "Demo data restored.");
  }

  function navTo(next) { setPage(next); setSelected(null); window.scrollTo({ top: 0, behavior: "smooth" }); }

  const floorInfo = floors.find((item) => item.id === floor);
  const openTotal = floors.reduce((sum, item) => sum + (item.available || 0), 0);
  const occupiedCount = map.seats.filter((seat) => seat.status !== "available").length;

  return h(React.Fragment, null,
    h("header", { className: "topbar" },
      h("a", { className: "brand", href: "#home", onClick: (e) => { e.preventDefault(); navTo("home"); } }, h("span", { className: "brand-mark" }, "S"), h("span", null, "SEATIQ")),
      h("nav", { className: "main-nav", "aria-label": "Main navigation" },
        [ ["home", "Overview"], ["floors", "Find a seat"], ["pass", "My pass"] ].map(([key, label]) => h("button", { key, className: page === key ? "nav-link active" : "nav-link", onClick: () => navTo(key) }, label)),
      ),
      h("div", { className: "top-actions" },
        session ? h(React.Fragment, null,
          h("span", { className: "user-chip" }, h("span", { className: "avatar" }, initials(session.display_name)), h("span", { className: "user-name" }, session.display_name), session.role === "admin" ? h("span", { className: "demo-tag" }, "ADMIN DEMO") : null),
          session.role === "admin" ? h("button", { className: "button button-quiet", onClick: () => navTo("admin") }, "Analytics") : null,
          h("button", { className: "button button-quiet sign-out", onClick: signOut }, "Sign out"),
        ) : h(React.Fragment, null, h("span", { className: "demo-note" }, "Prototype · demo mode"), h("button", { className: "button button-dark", onClick: () => navTo("login") }, "Try the demo")),
      ),
    ),
    notice && h("div", { className: `toast ${notice.kind}`, role: "status" }, h("span", { className: "toast-dot" }), notice.message, h("button", { onClick: () => setNotice(null), "aria-label": "Dismiss" }, "×")),
    page === "home" && h("main", { className: "page-shell" },
      h("section", { className: "hero" },
        h("div", { className: "hero-copy" },
          h("span", { className: "eyebrow light" }, h("span", { className: "eyebrow-line" }), "SMART LIBRARY SEATING"),
          h("h1", null, "Your next", h("br"), h("em", null, "good idea"), " starts here."),
          h("p", null, "Know where to settle in before you get there. Find an open seat, make it yours, and get back to what matters."),
          h("div", { className: "hero-actions" }, h("button", { className: "button button-lime", onClick: () => navTo("floors") }, "Explore seats", h("span", null, "↗")), h("span", { className: "hero-caption" }, "3 floors · 72 study seats")),
          h("div", { className: "hero-footnote" }, h("span", { className: "pulse" }), "Availability refreshes automatically"),
        ),
        h("div", { className: "hero-visual" },
          h("div", { className: "hero-glow" }), h("div", { className: "hero-orbit orbit-one" }), h("div", { className: "hero-orbit orbit-two" }),
          h("div", { className: "hero-stat" }, h("span", { className: "stat-label" }, "OPEN RIGHT NOW"), h("strong", null, floors.length ? openTotal : "—"), h("span", null, "seats across the library")),
          h("div", { className: "desk-scene" }, h("div", { className: "desk-top" }), h("div", { className: "desk-leg leg-a" }), h("div", { className: "desk-leg leg-b" }), h("div", { className: "desk-book" }), h("div", { className: "desk-cup" }), h("div", { className: "chair chair-a" }), h("div", { className: "chair chair-b" })),
          h("div", { className: "hero-floor-label" }, h("span", { className: "floor-label-dot" }), "A quieter kind of productive"),
        ),
      ),
      h("section", { className: "metrics-row", "aria-label": "Library summary" },
        h(Metric, { value: "72", label: "Thoughtful places to study", icon: "✳" }), h(Metric, { value: "3", label: "Distinct study floors", icon: "⌂" }), h(Metric, { value: "20", label: "Minutes for a short break", icon: "◷", suffix: "min" }),
        h("div", { className: "metric-note" }, "Find a seat that fits", h("br"), "the way you study."),
      ),
      h("section", { className: "section-block" },
        h("div", { className: "section-heading" }, h("div", null, h("span", { className: "eyebrow" }, "A PLACE FOR EVERY PACE"), h("h2", null, "Pick your kind of focus.")), h("button", { className: "text-link", onClick: () => navTo("floors") }, "View all floors ↗")),
        h("div", { className: "floor-cards" }, floors.map((item, index) => h("button", { key: item.id, className: `floor-card floor-card-${index + 1}`, onClick: () => { setFloor(item.id); navTo("floors"); } },
          h("span", { className: "card-number" }, `0${item.id}`), h("span", { className: "card-icon" }, ["◌", "▦", "☾"][index]), h("span", { className: "card-title" }, item.name), h("span", { className: "card-subtitle" }, item.description), h("span", { className: "card-available" }, h("i", null), `${item.available} spots open`), h("span", { className: "card-arrow" }, "↗"),
        ))),
      ),
      h("section", { className: "steps-band" }, h("div", { className: "steps-heading" }, h("span", { className: "eyebrow light" }, "EASY AS FIND, BOOK, FOCUS"), h("h2", null, "A little less looking around.")),
        h("div", { className: "steps-grid" }, [["01", "Find your spot", "See open seats on a simple floor map."], ["02", "Make it yours", "Reserve the seat you want in a moment."], ["03", "Get settled", "Check in when you arrive, then focus."]].map(([num, title, body]) => h("div", { className: "step", key: num }, h("span", { className: "step-num" }, num), h("h3", null, title), h("p", null, body)))),
      ),
      h("footer", { className: "footer" }, h("a", { className: "brand", href: "#home", onClick: (e) => e.preventDefault() }, h("span", { className: "brand-mark" }, "S"), h("span", null, "SEATIQ")), h("span", null, "A hackathon prototype · fictional demo data only"), h("span", null, "Make room for good work.")),
    ),
    page === "floors" && h("main", { className: "content-shell" },
      h("div", { className: "page-intro" }, h("span", { className: "eyebrow" }, "THE LIBRARY, AT A GLANCE"), h("h1", null, "Find your corner."), h("p", null, "Every seat has a place. Pick a floor, see what's open, and settle in.")),
      h("div", { className: "map-toolbar" }, h("label", { htmlFor: "floor-select" }, "YOUR FLOOR"), h("select", { id: "floor-select", value: floor, onChange: (e) => { setFloor(Number(e.target.value)); setSelected(null); } }, floors.map((item) => h("option", { key: item.id, value: item.id }, `Floor ${item.id} · ${item.name}`))), h("div", { className: "availability-pill" }, h("i", null), "Live availability")),
      h("div", { className: "map-layout" },
        h("section", { className: "map-panel" }, h("div", { className: "map-panel-head" }, h("div", null, h("span", { className: "eyebrow" }, `FLOOR 0${floor}`), h("h2", null, floorInfo?.name || FLOOR_LABELS[floor - 1]), h("p", null, floorInfo?.description || "Study spaces for you")), h("span", { className: "map-count" }, `${map.seats.filter((seat) => seat.status === "available").length} open`)),
          h("div", { className: "window-line" }, h("span", null, "WINDOWS")),
          h("div", { className: "seat-map" }, [1, 2, 3, 4, 5, 6].map((table) => h("div", { className: "table-group", key: table }, h("div", { className: "table-label" }, `TABLE ${table}`), h("div", { className: "seat-grid" }, map.seats.filter((seat) => seat.table_no === table).map((seat) => h("button", { key: seat.id, className: `seat seat-${seat.status}${selected?.id === seat.id ? " selected" : ""}`, disabled: seat.status !== "available", onClick: () => setSelected(seat), title: `${seat.id} · ${seat.status}`, "aria-label": `Seat ${seat.id}, ${seat.status}` }, h("span", { className: "seat-dot" }), seat.id))))), h("div", { className: "entrance-label" }, h("span", null, "ENTRANCE"))),
          h("div", { className: "legend" }, [["available", "Available"], ["reserved", "Reserved"], ["occupied", "Occupied"], ["break", "On break"]].map(([key, label]) => h("span", { key }, h("i", { className: `legend-dot ${key}` }), label))),
        ),
        h("aside", { className: "selection-panel" }, selected ? h(React.Fragment, null,
          h("span", { className: "eyebrow" }, "YOUR STUDY SPOT"), h("div", { className: "selection-seat" }, selected.id), h("h2", null, "Looks like a good fit."), h("p", null, `Floor ${floor} · Table ${selected.table_no}. This seat is open and ready when you are.`), h("div", { className: "selection-detail" }, h("span", null, "STATUS"), h("strong", null, "Available now")), h("button", { className: "button button-dark button-wide", disabled: busy || !!booking, onClick: () => reserve(selected) }, booking ? "You already have a seat" : session ? "Reserve this seat" : "Try demo to reserve", h("span", null, "↗")), !session && h("span", { className: "demo-hint" }, "Use any fictional name to try the demo."),
        ) : h(React.Fragment, null, h("div", { className: "selection-icon" }, "⌖"), h("span", { className: "eyebrow" }, "CHOOSE A SEAT"), h("h2", null, "Your spot is out there."), h("p", null, "Select any green seat on the map to see its location and reserve it."), h("div", { className: "selection-summary" }, h("span", { className: "summary-icon" }, "◷"), h("span", null, h("strong", null, "20-minute break window"), h("small", null, "A little breathing room, built in.")))),
        ),
      ),
      h("div", { className: "prototype-banner" }, h("span", { className: "prototype-icon" }, "i"), h("span", null, h("strong", null, "Hackathon demo"), " · seat availability uses local demo data. No real reservations are made.")),
    ),
    page === "login" && h("main", { className: "auth-shell" }, h("section", { className: "auth-card" }, h("div", { className: "auth-art" }, h("span", { className: "eyebrow light" }, "WELCOME TO NEXORA LIBRARY"), h("h1", null, "A place to land.", h("br"), h("em", null, "Room to think.")), h("p", null, "Find your study rhythm. Your seat is just a few clicks away."), h("div", { className: "auth-art-lines" }, h("i"), h("i"), h("i"))), h("form", { className: "auth-form", onSubmit: (e) => signIn(e) }, h("span", { className: "eyebrow" }, "STUDENT DEMO ACCESS"), h("h2", null, "Come on in."), h("p", null, "Choose a fictional name. This prototype does not ask for email, password, or student ID."), h("label", { htmlFor: "demo-name" }, "Name for your demo pass"), h("input", { id: "demo-name", value: name, onChange: (e) => setName(e.target.value), placeholder: "e.g. Demo Student", minLength: 2, maxLength: 32, pattern: "[A-Za-z][A-Za-z0-9 .'-]*", autoComplete: "off" }), h("button", { className: "button button-dark button-wide", disabled: busy }, busy ? "Opening demo…" : "Continue in demo mode", h("span", null, "↗")), h("div", { className: "auth-separator" }, h("span"), "OR", h("span")), h("button", { type: "button", className: "button button-outline button-wide", disabled: busy, onClick: (e) => signIn(e, true) }, "Open admin demo"), h("span", { className: "auth-footnote" }, "Admin mode is open for presentation only. It is not secured for real use."))), h("button", { className: "back-link", onClick: () => navTo("home") }, "← Back to overview")),
    page === "pass" && h("main", { className: "content-shell pass-shell" }, h("div", { className: "page-intro" }, h("span", { className: "eyebrow" }, "YOUR LIBRARY PASS"), h("h1", null, "Ready when you are."), h("p", null, booking ? "Your seat is saved in this demo. Check in when you arrive." : "Your next study session starts with a seat.")), booking ? h("section", { className: "pass-card" }, h("div", { className: "pass-main" }, h("span", { className: "pass-status" }, h("i", null), booking.status === "break" ? "ON A SHORT BREAK" : booking.status === "occupied" ? "CHECKED IN · READY TO FOCUS" : "RESERVED · CHECK IN WHEN YOU ARRIVE"), h("span", { className: "eyebrow" }, "YOUR SEAT"), h("div", { className: "pass-seat" }, booking.seat_id), h("p", null, `${booking.floor_name || `Floor ${booking.floor_id}`} · Table ${booking.table_no}`), booking.status === "break" && h("div", { className: "break-clock" }, h("span", null, "BACK BY"), h("strong", null, fmtTime(booking.break_until)), h("small", null, "The seat releases automatically when time is up.")), h("div", { className: "pass-actions" }, booking.status === "reserved" && h("button", { className: "button button-dark", disabled: busy, onClick: () => action(() => api(`/bookings/${booking.id}/check-in`, { method: "POST", body: JSON.stringify({ qr_token: booking.qr_token }) }), "Checked in. Settle in and enjoy your focus time.") }, "Simulate QR check-in ↗"), booking.status === "occupied" && h("button", { className: "button button-dark", disabled: busy, onClick: () => action(() => api(`/bookings/${booking.id}/break`, { method: "POST" }), "Break started. Your seat is held for 20 minutes.") }, "Start a 20-min break"), booking.status === "break" && h("button", { className: "button button-dark", disabled: busy, onClick: () => action(() => api(`/bookings/${booking.id}/return`, { method: "POST" }), "Welcome back. Your seat is yours again.") }, "I’m back ↗"), booking.status === "reserved" && h("button", { className: "button button-outline", disabled: busy, onClick: () => action(() => api(`/bookings/${booking.id}/cancel`, { method: "POST" }), "Reservation cancelled.") }, "Cancel reservation")), h("span", { className: "prototype-caption" }, "DEMO CHECK-IN · BUTTON SIMULATES SCANNING THE DISPLAYED SEAT CODE")), h("div", { className: "pass-qr" }, qrImage ? h("img", { src: qrImage, alt: `QR code for ${booking.seat_id} demo check-in` }) : h("div", { className: "qr-placeholder" }, "QR"), h("span", null, "SEAT CODE"), h("code", null, booking.qr_token || ""), h("small", null, "Demo token only · do not use for real access"))) : session ? h("section", { className: "empty-pass" }, h("div", { className: "selection-icon" }, "⌖"), h("h2", null, "No seat on your pass yet."), h("p", null, "Choose a floor and reserve an open seat for your next study session."), h("button", { className: "button button-dark", onClick: () => navTo("floors") }, "Explore open seats ↗")) : h("section", { className: "empty-pass" }, h("div", { className: "selection-icon" }, "⌖"), h("h2", null, "Your pass starts with a seat."), h("p", null, "Open a fictional demo profile to reserve a seat and see your check-in code."), h("button", { className: "button button-dark", onClick: () => navTo("login") }, "Try the demo ↗"))),
    page === "admin" && h("main", { className: "content-shell admin-shell" }, h("div", { className: "page-intro admin-intro" }, h("span", { className: "eyebrow" }, "LIBRARY OPERATIONS · DEMO ONLY"), h("div", { className: "admin-title-row" }, h("div", null, h("h1", null, "A little more room."), h("p", null, "A live snapshot of seats across the library.")), h("button", { className: "button button-outline", disabled: busy, onClick: resetDemo }, "↻ Reset demo data"))), analytics ? h(React.Fragment, null, h("div", { className: "admin-kpis" }, [["AVAILABLE", analytics.totals.available, "#dbe9be"], ["RESERVED", analytics.totals.reserved, "#ead9ad"], ["IN USE", analytics.totals.occupied, "#b5c7bb"], ["ON BREAK", analytics.totals.on_break, "#d7cce5"]].map(([label, value, color]) => h("div", { className: "admin-kpi", key: label }, h("span", { className: "kpi-dot", style: { background: color } }), h("span", { className: "kpi-label" }, label), h("strong", null, value ?? 0), h("small", null, `of ${analytics.totals.total} seats`)))), h("div", { className: "analytics-grid" }, h("section", { className: "analytics-card" }, h("span", { className: "eyebrow" }, "OCCUPANCY BY FLOOR"), h("h2", null, "Space in use."), h("div", { className: "floor-analytics" }, analytics.floors.map((item) => { const used = item.total - item.available; const percent = Math.round(used / item.total * 100); return h("div", { className: "floor-bar-row", key: item.id }, h("div", { className: "bar-row-label" }, h("strong", null, item.name), h("span", null, `${used}/${item.total} in use`)), h("div", { className: "bar-track" }, h("div", { className: "bar-fill", style: { width: `${percent}%` } })), h("span", { className: "bar-percent" }, `${percent}%`)); }))), h("section", { className: "analytics-card activity-card" }, h("span", { className: "eyebrow" }, "RECENT ACTIVITY"), h("h2", null, "The room, in motion."), analytics.recent_activity.length ? h("div", { className: "activity-list" }, analytics.recent_activity.map((event) => h("div", { className: "activity-item", key: event.id }, h("span", { className: `activity-icon activity-${event.kind}` }, ({ reserved: "↗", check_in: "✓", break_started: "◷", returned: "↩", auto_release: "↻", cancelled: "×", reset: "⟳" })[event.kind] || "·"), h("span", { className: "activity-detail" }, event.detail), h("time", null, fmtTime(event.created_at))))) : h("p", { className: "empty-activity" }, "No seat updates yet. Make a demo reservation to see activity here."))), h("div", { className: "admin-note" }, "Demo admin is open and uses fictional data. Add real authentication, staff permissions, and auditing before any real deployment.")) : h("div", { className: "loading-card" }, "Gathering the room’s details…")),
    h("div", { className: "bottom-note" }, "SEATIQ · MAKE ROOM FOR GOOD WORK", h("span", null, "Hackathon prototype · fictional demo data")),
  );
}

function Metric({ value, label, icon, suffix }) {
  return h("div", { className: "metric" }, h("span", { className: "metric-icon" }, icon), h("strong", null, value, suffix && h("small", null, suffix)), h("span", null, label));
}

createRoot(document.getElementById("root")).render(h(App));

