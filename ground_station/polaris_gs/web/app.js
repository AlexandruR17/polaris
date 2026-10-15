// POLARIS Ground Station, web front end. Talks to polaris_gs.server over /ws.
import { icon, ICONS } from "./icons.js";
import { GlobeView } from "./globe.js";
import { VehicleView } from "./vehicle.js";
import { SkyPlot } from "./sky.js";
import { Charts } from "./charts.js";

const cssVar = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const CSS = {
  bg: cssVar("--bg"), panel: cssVar("--panel"), border: cssVar("--border"), text: cssVar("--text"),
  text2: cssVar("--text-2"), muted: cssVar("--muted"), accent: cssVar("--accent"), second: cssVar("--second"),
  grid: cssVar("--grid"), good: cssVar("--good"), warning: cssVar("--warning"), critical: cssVar("--critical"),
  font: cssVar("--font"),
};

const STATE_RO = {
  BOOT: "PORNIRE", HOMING: "CALIBRARE AXE", IDLE: "REPAUS", WAIT_AOS: "AȘTEPTARE AOS", ACQUIRE: "CĂUTARE",
  TRACK: "URMĂRIRE", STOW: "PARCAT", MANUAL: "MANUAL", DEMO: "DEMO", ESTOP: "OPRIRE DE URGENȚĂ", FAULT: "DEFECT",
};
const STATE_COLOR = {
  TRACK: CSS.good, ACQUIRE: CSS.warning, WAIT_AOS: CSS.warning, HOMING: CSS.warning, DEMO: CSS.warning,
  ESTOP: CSS.critical, FAULT: CSS.critical,
};
const EVENT_RO = {
  BOOT: "Pornire firmware", AOS: "AOS: satelitul a răsărit", LOS: "LOS: satelitul a apus", HOME_OK: "Homing reușit",
  ESTOP: "OPRIRE DE URGENȚĂ", FAULT: "DEFECT", MODE: "Stare", TLE_OK: "TLE descărcat", TLE_FALLBACK: "TLE de rezervă (vechi)",
  KEYHOLE: "Keyhole", RATE_LIMIT: "Limită de viteză", WRAP: "Derulare cablu", PASS: "Pasaj calculat", ACK: "Confirmare",
  CMD: "Comandă", ERR: "Eroare comandă", INFO: "Info",
};
const EVENT_COLOR = {
  ESTOP: CSS.critical, FAULT: CSS.critical, ERR: CSS.critical, AOS: CSS.good, HOME_OK: CSS.good,
  LOS: CSS.warning, KEYHOLE: CSS.warning, RATE_LIMIT: CSS.warning, TLE_FALLBACK: CSS.warning,
};

const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const fmtTime = t => t == null ? "—" : new Date(t * 1000).toISOString().slice(11, 19);
const fmtDate = t => t == null ? "" : new Date(t * 1000).toISOString().slice(0, 10);

// ------------------------------------------------------------ static decoration
$("favicon").href = "data:image/svg+xml," + encodeURIComponent(
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path fill="${CSS.accent}" d="${ICONS["satellite-uplink"]}"/></svg>`);
$("logo").innerHTML = icon("satellite-uplink");
document.querySelectorAll(".panel[data-title]").forEach(p => {
  const h = document.createElement("h2");
  h.innerHTML = icon(p.dataset.icon) + esc(p.dataset.title);
  p.prepend(h);
});
document.querySelectorAll("button[data-icon]").forEach(b => b.insertAdjacentHTML("afterbegin", icon(b.dataset.icon)));
document.querySelectorAll(".chip").forEach(c => { c.querySelector(".cic").innerHTML = icon(c.dataset.icon); });

function chip(id, text, color, iconName) {
  const c = $(id);
  const v = c.querySelector(".val");
  v.textContent = text;
  v.style.color = color || "";
  c.querySelector(".cic").innerHTML = icon(iconName || c.dataset.icon);
  c.querySelector(".cic .ic").style.color = color || "";
}

// ------------------------------------------------------------ views
let globe = null, vehicle = null;
const sky = new SkyPlot($("sky"), CSS, 5);
const charts = new Charts({ err: $("ch-err"), speed: $("ch-speed"), att: $("ch-att") }, CSS);
try {
  vehicle = new VehicleView($("vehicle"), CSS);
} catch (e) {
  $("vehicle").innerHTML = `<p class="small" style="padding:12px">WebGL indisponibil: ${esc(e.message)}</p>`;
}

// ------------------------------------------------------------ connection
let ws = null, hello = null, last = null, isSim = false;
function send(msg) { if (ws && ws.readyState === 1) ws.send(JSON.stringify(msg)); }
function cmd(text) { send({ op: "cmd", text }); }

function connect() {
  ws = new WebSocket((location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws");
  ws.onopen = () => { $("server").textContent = "server conectat"; $("server").className = "small"; };
  ws.onclose = () => {
    $("server").textContent = "Server oprit, reîncerc…";
    $("server").className = "small down";
    setTimeout(connect, 2000);
  };
  ws.onmessage = m => {
    const msg = JSON.parse(m.data);
    const h = HANDLERS[msg.t];
    if (h) h(msg);
  };
}

const HANDLERS = {
  hello(m) {
    hello = m;
    isSim = m.link.sim;
    if (!globe) {
      try {
        globe = new GlobeView($("globe"), CSS, m.station.ecef, m.mask_el);
      } catch (e) {
        $("globe").innerHTML = `<p class="small" style="padding:12px">WebGL indisponibil: ${esc(e.message)}</p>`;
      }
      sky.maskEl = m.mask_el;
    }
    fillSelect($("link-select"), m.links);
    const spec = m.link.spec || "sim";
    const known = m.links.some(([k]) => k === spec);
    $("link-select").value = known ? spec : "port";
    if (!known) $("port-input").value = spec;
    $("port-input").hidden = $("link-select").value !== "port";
    fillSelect($("sat-select"), m.sats.map(([k, v]) => [k, `${v}  ·  ${k}`]));
    fillSelect($("veh-select"), m.vehicle_modes);
    const wb = $("warp-btns");
    if (!wb.children.length) {
      for (const w of m.warps) {
        const b = document.createElement("button");
        b.textContent = "x" + w;
        b.dataset.warp = w;
        b.onclick = () => { cmd("WARP:" + w); setWarp(w); };
        wb.appendChild(b);
      }
      setWarp(m.default_warp);
    }
    status(m.link.text, m.link.ok);
    settings(m);
    charts.reset([]);
    $("log").innerHTML = "";
  },
  status(m) { isSim = m.sim; status(m.text, m.ok); settings(null); },
  settings(m) { settings(m); },
  history(m) { charts.reset(m.rows); },
  tm(m) { telemetry(m.d); },
  ev(m) { logEvent(m.d); },
  orbit(m) { if (globe) globe.setOrbit(m.pos, m.track); },
  passes(m) { passes(m); },
  xcheck(m) {
    const ok = m.diff < 0.1;
    chip("chip-x", `Δ ${m.diff.toFixed(3)}°`, ok ? CSS.good : CSS.critical, ok ? "check-decagram" : "alert");
  },
  results(m) { results(m); },
};

function fillSelect(sel, items) {
  const cur = sel.value;
  sel.innerHTML = items.map(([k, v]) => `<option value="${esc(k)}">${esc(v)}</option>`).join("");
  if ([...sel.options].some(o => o.value === cur)) sel.value = cur;
}

function setWarp(w) {
  for (const b of $("warp-btns").children) b.classList.toggle("on", +b.dataset.warp === +w);
}

function status(text, ok) {
  $("link-status").innerHTML = `<span class="dot" style="color:${ok ? CSS.good : CSS.warning}">${ok ? "●" : "○"}</span> ${esc(text || "—")}`;
}

function settings(m) {
  if (m) {
    if (m.vehicle) $("veh-select").value = m.vehicle;
    if (m.veh_send !== undefined) $("veh-send").checked = m.veh_send;
    if (m.estop !== undefined) $("estop-btn").classList.toggle("on", m.estop);
    if (m.limit !== undefined) $("limit-btn").classList.toggle("on", m.limit);
  }
  $("estop-btn").disabled = !isSim;
  $("limit-btn").disabled = !isSim;
  $("safety-note").hidden = isSim;
}

// ------------------------------------------------------------ telemetry
function telemetry(d) {
  last = d;
  const st = d.mode, warp = d.warp || 1;
  const ic = { ESTOP: "alert-octagon", FAULT: "alert", TRACK: "check-circle" }[st] || "radar";
  chip("chip-state", (STATE_RO[st] || st) + (warp > 1 ? `  x${warp}` : ""), STATE_COLOR[st], ic);
  chip("chip-utc", d.t_utc.slice(11, 19));
  const name = (hello?.sats.find(([k]) => k === d.sat)?.[1] || String(d.sat)).split(" (")[0];
  chip("chip-sat", `${name}  ${d.sat_az.toFixed(1)}° / ${d.sat_el.toFixed(1)}°`);
  if (st === "TRACK" || st === "ACQUIRE") {
    const e = d.err_deg;
    chip("chip-err", e.toFixed(2) + "°" + (d.kh ? (d.sat_el > 70 ? "  keyhole" : "  limită viteză") : ""), e < 0.5 ? CSS.good : e < 2 ? CSS.warning : CSS.critical);
  } else {
    chip("chip-err", "—");
  }
  if (d.tle_fb) chip("chip-tle", `vechi · ${d.tle_age.toFixed(0)} zile`, CSS.warning, "alert");
  else chip("chip-tle", `actual · ${d.tle_age.toFixed(1)} zile`, CSS.good);

  for (const b of $("mode-btns").children) {
    const m = b.dataset.mode;
    b.classList.toggle("on", (m === "DEMO" && warp > 1) ||
      (m === "AUTO" && ["WAIT_AOS", "ACQUIRE", "TRACK"].includes(st) && warp === 1) ||
      (m === "MANUAL" && st === "MANUAL") || (m === "IDLE" && st === "IDLE"));
  }
  if (document.activeElement !== $("sat-select") && $("sat-select").value !== String(d.sat)) $("sat-select").value = d.sat;
  if (document.activeElement !== $("comp")) $("comp").checked = !!d.comp;

  sky.setPositions(d.sat_az, d.sat_el, d.ant_sky_az, d.ant_sky_el);
  if (vehicle) vehicle.setState(d.roll, d.pitch, d.yaw, d.ant_az, d.ant_el, d.sat_az, d.sat_el);
  if (globe) globe.setSatellite(d.sat_ecef, d.sat_alt_km, d.sat_el);
  charts.add(d);
}

function passes(m) {
  sky.setTrack(m.sky);
  $("passes-body").innerHTML = m.rows.map(p => {
    const geo = p.los == null;
    return `<tr class="${p.current ? "cur" : ""}" title="${fmtDate(p.aos)}">
      <td>${geo ? fmtDate(p.aos).slice(5) + " " : ""}${fmtTime(p.aos)}</td><td>${geo ? "—" : fmtTime(p.los)}</td>
      <td>${p.max_el.toFixed(1)}°</td><td>${geo ? "fix" : p.dur_min.toFixed(1) + "′"}</td><td>${p.aos_az}°</td>
      <td>${p.sky_diff_s == null ? "—" : p.sky_diff_s.toFixed(1) + " s"}</td></tr>`;
  }).join("") || `<tr><td colspan="6" class="small">Niciun pasaj în următoarele 36 h</td></tr>`;
}

function results(m) {
  const n = v => v == null ? "—" : v.toFixed(2) + "°";
  $("results-body").innerHTML = m.rows.map(r => `<tr>
      <td>${esc((r.los || "").slice(5, 16).replace("T", " "))}</td><td>${r.sat}</td><td>${r.comp ? "da" : "nu"}</td>
      <td>x${r.warp}</td><td>${esc(r.vehicle || "—")}</td><td>${n(r.max_err)}</td><td>${n(r.rms_err)}</td></tr>`).join("")
    || `<tr><td colspan="7" class="small">Încă nu s-a terminat niciun pasaj (rezultatul se salvează la LOS)</td></tr>`;
  $("results-db").textContent = m.db ? "Fișier: " + m.db : "Fără bază de date";
}

function logEvent(d) {
  const ev = d.ev;
  let rest = Object.entries(d).filter(([k]) => k !== "ev" && k !== "_wall").map(([k, v]) => `${k}=${v}`).join(", ");
  if (ev === "MODE") rest = `${STATE_RO[d.from] || d.from} → ${STATE_RO[d.to] || d.to}`;
  const t = new Date((d._wall || Date.now() / 1000) * 1000).toISOString().slice(11, 19);
  const log = $("log");
  const atBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 30;
  const div = document.createElement("div");
  div.innerHTML = `<span class="t">${t}</span> <b style="color:${EVENT_COLOR[ev] || CSS.text2}">${esc(EVENT_RO[ev] || ev)}</b> <span class="r">${esc(rest)}</span>`;
  log.appendChild(div);
  while (log.children.length > 400) log.firstChild.remove();
  if (atBottom) log.scrollTop = log.scrollHeight;
}

// ------------------------------------------------------------ controls
$("link-select").onchange = () => { $("port-input").hidden = $("link-select").value !== "port"; };
$("link-btn").onclick = () => {
  let spec = $("link-select").value;
  if (spec === "port") spec = $("port-input").value.trim() || "COM3";
  send({ op: "link", spec });
};
$("sat-select").onchange = () => cmd("SAT:" + $("sat-select").value);
for (const b of $("mode-btns").children) b.onclick = () => cmd("MODE:" + b.dataset.mode);
document.querySelectorAll("button[data-cmd]").forEach(b => { b.onclick = () => cmd(b.dataset.cmd); });
$("veh-select").onchange = () => send({ op: "vehicle", mode: $("veh-select").value });
$("veh-send").onchange = () => send({ op: "veh_send", on: $("veh-send").checked });
$("comp").onchange = () => cmd("COMP:" + ($("comp").checked ? 1 : 0));
$("estop-btn").onclick = () => send({ op: "estop", on: !$("estop-btn").classList.contains("on") });
$("limit-btn").onclick = () => send({ op: "limit", axis: "AZ", on: !$("limit-btn").classList.contains("on") });
$("cmd-form").onsubmit = e => {
  e.preventDefault();
  const t = $("cmd-input").value.trim();
  if (t) { cmd(t); $("cmd-input").value = ""; }
};
document.querySelectorAll(".tab").forEach(t => {
  t.onclick = () => {
    document.querySelectorAll(".tab").forEach(x => x.classList.toggle("on", x === t));
    $("tab-passes").hidden = t.dataset.tab !== "passes";
    $("tab-results").hidden = t.dataset.tab !== "results";
  };
});

connect();
