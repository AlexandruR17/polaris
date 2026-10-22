// POLARIS Ground Station, web front end (mission control layout).
// Talks to polaris_gs.server over /ws.
import { icon, ICONS } from "./icons.js";
import { GlobeView } from "./globe.js";
import { VehicleView } from "./vehicle.js";
import { SkyPlot } from "./sky.js";
import { Charts } from "./charts.js";
import { runIntro, shouldRun } from "./intro.js";

const cssVar = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const CSS = {
  bg: cssVar("--bg"), text: cssVar("--text"), text2: cssVar("--text-2"), muted: cssVar("--muted"),
  accent: cssVar("--accent"), second: cssVar("--second"), grid: cssVar("--grid"), border: cssVar("--border"),
  good: cssVar("--good"), warning: cssVar("--warning"), critical: cssVar("--critical"),
  font: cssVar("--font"), mono: cssVar("--mono"),
  globe: { earth: 0x050608, glow: 0x4f7fd0, grid: 0xffffff, gridOpacity: 0.07, coast: 0xffffff, coastOpacity: 0.55,
           orbit: 0xffffff, station: 0xffffff, distance: 4.0 },
  veh: { body: 0x2b3038, cab: 0x3a4049, wheel: 0x111317, base: 0x8a929c, turret: 0xd9dde3, cradle: 0x9aa2ab,
         dish: 0xf2f4f7, edge: 0xffffff, edgeOpacity: 0.35, grid: 0xffffff },
};

const STATE_RO = {
  BOOT: "Pornire", HOMING: "Calibrare axe", IDLE: "Repaus", WAIT_AOS: "Așteptare AOS", ACQUIRE: "Căutare",
  TRACK: "Urmărire", STOW: "Parcat", MANUAL: "Manual", DEMO: "Demo", ESTOP: "Oprire de urgență", FAULT: "Defect",
};
const STATE_COLOR = {
  TRACK: CSS.good, ACQUIRE: CSS.warning, WAIT_AOS: CSS.text, HOMING: CSS.warning, DEMO: CSS.warning,
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
function hms(s) {
  s = Math.max(0, Math.floor(s));
  const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), x = s % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(x).padStart(2, "0")}`;
}

// ------------------------------------------------------------ static decoration
$("favicon").href = "data:image/svg+xml," + encodeURIComponent(
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path fill="#ffffff" d="${ICONS["satellite-uplink"]}"/></svg>`);
document.querySelectorAll("button[data-icon]").forEach(b => b.insertAdjacentHTML("afterbegin", icon(b.dataset.icon)));

// ------------------------------------------------------------ gauges (SVG rings)
const GAUGES = {};
function makeGauge(key, label, unit, opt) {
  const R = opt.full ? 36 : 44, cx = 66, cy = 58, sweep = opt.full ? 360 : 270, start = opt.full ? -90 : 135;
  const len = 2 * Math.PI * R * sweep / 360;
  const pt = (deg, r) => [cx + r * Math.cos(deg * Math.PI / 180), cy + r * Math.sin(deg * Math.PI / 180)];
  const arc = () => {
    if (opt.full) return `M ${cx} ${cy - R} A ${R} ${R} 0 1 1 ${cx - 0.01} ${cy - R}`;
    const [x0, y0] = pt(start, R), [x1, y1] = pt(start + sweep, R);
    return `M ${x0} ${y0} A ${R} ${R} 0 1 1 ${x1} ${y1}`;
  };
  let ticks = "";
  if (opt.full) {
    for (const [t, a] of [["N", 0], ["E", 90], ["S", 180], ["V", 270]]) {
      const [x0, y0] = pt(a - 90, R - 6), [x1, y1] = pt(a - 90, R + 6);
      ticks += `<line class="g-tick" x1="${x0}" y1="${y0}" x2="${x1}" y2="${y1}"/>`;
      const [tx, ty] = pt(a - 90, R + 11);
      ticks += `<text class="g-unit" x="${tx}" y="${ty + 3}">${t}</text>`;
    }
  }
  const el = document.createElement("div");
  el.className = "gauge";
  el.innerHTML = `<svg viewBox="0 0 132 112" role="img" aria-label="${esc(label)}">
      <path class="g-bg" d="${arc()}"/>
      ${opt.full ? "" : `<path class="g-val" d="${arc()}" stroke-dasharray="${len}" stroke-dashoffset="${len}"/>`}
      ${ticks}
      ${opt.full ? `<line class="g-needle" x1="${cx}" y1="${cy}" x2="${cx}" y2="${cy - R + 4}"/>` : ""}
      <text class="g-num" x="${cx}" y="${cy + (opt.full ? 20 : 8)}"${opt.full ? ' style="font-size:17px"' : ""}>—</text>
      ${opt.full ? "" : `<text class="g-unit" x="${cx}" y="${cy + 24}">${unit}</text>`}
    </svg><div class="lbl">${esc(label)}</div>`;
  $("gauges").appendChild(el);
  GAUGES[key] = { el, len, opt, cx, cy };
}
function setGauge(key, value, text, color) {
  const g = GAUGES[key];
  if (!g) return;
  g.el.querySelector(".g-num").textContent = text;
  if (g.opt.full) {
    g.el.querySelector(".g-needle").setAttribute("transform", `rotate(${value ?? 0} ${g.cx} ${g.cy})`);
    return;
  }
  const val = g.el.querySelector(".g-val");
  let frac;
  if (g.opt.center) frac = 0.5 + Math.max(-1, Math.min(1, (value ?? 0) / g.opt.max)) / 2;
  else frac = Math.max(0, Math.min(1, ((value ?? 0) - g.opt.min) / (g.opt.max - g.opt.min)));
  val.setAttribute("stroke-dashoffset", g.len * (1 - frac));
  val.style.stroke = color || "";
}
makeGauge("az", "Azimut antenă", "grade", { full: true });
makeGauge("el", "Elevație antenă", "grade", { min: -10, max: 90 });
makeGauge("err", "Eroare pointare", "grade", { min: 0, max: 5 });
makeGauge("rng", "Distanță", "km", { min: 0, max: 3000 });
makeGauge("roll", "Ruliu vehicul", "grade", { center: true, max: 15 });
makeGauge("pitch", "Tangaj vehicul", "grade", { center: true, max: 15 });

// ------------------------------------------------------------ views
let globe = null, vehicle = null;
const sky = new SkyPlot($("sky"), CSS, 5);
const charts = new Charts({ err: $("ch-err"), speed: $("ch-speed"), att: $("ch-att") }, CSS);
try {
  vehicle = new VehicleView($("vehicle"), CSS);
} catch (e) {
  $("vehicle").innerHTML = `<p class="lbl" style="padding:12px">WebGL indisponibil: ${esc(e.message)}</p>`;
}

// ------------------------------------------------------------ connection
let ws = null, hello = null, isSim = false, curPass = null, lastTm = null;
let linkOk = false, xdiff = null, flyPending = false;
function send(msg) { if (ws && ws.readyState === 1) ws.send(JSON.stringify(msg)); }
function cmd(text) { send({ op: "cmd", text }); }

function connect() {
  ws = new WebSocket((location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws");
  ws.onopen = () => { $("server").textContent = ""; $("server").className = "lbl"; };
  ws.onclose = () => {
    $("server").textContent = "Server oprit · reîncerc";
    $("server").className = "lbl down";
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
        if (flyPending) { flyPending = false; globe.flyIn(); }
      } catch (e) {
        $("globe").innerHTML = `<p class="lbl" style="padding:24px">WebGL indisponibil: ${esc(e.message)}</p>`;
      }
      sky.maskEl = m.mask_el;
    }
    fillSelect($("link-select"), m.links);
    const spec = m.link.spec || "sim";
    const known = m.links.some(([k]) => k === spec);
    $("link-select").value = known ? spec : "port";
    if (!known) $("port-input").value = spec;
    $("port-input").hidden = $("link-select").value !== "port";
    fillSelect($("sat-select"), m.sats.map(([k, v]) => [k, `${v} · ${k}`]));
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
    linkOk = m.link.ok;
    status(m.link.text, m.link.ok);
    settings(m);
    charts.reset([]);
    $("log").innerHTML = "";
  },
  status(m) { isSim = m.sim; linkOk = m.ok; status(m.text, m.ok); settings(null); },
  settings(m) { settings(m); },
  history(m) { charts.reset(m.rows); },
  tm(m) { telemetry(m.d); },
  ev(m) { logEvent(m.d); },
  orbit(m) { if (globe) globe.setOrbit(m.pos, m.track); },
  passes(m) { passes(m); },
  xcheck(m) {
    xdiff = m.diff;
    const ok = m.diff < 0.1;
    $("kv-x").innerHTML = `<span style="color:${ok ? CSS.good : CSS.critical}">Δ ${m.diff.toFixed(3)}°</span>`;
  },
  results(m) { results(m); },
};

function fillSelect(sel, items) {
  const cur = sel.value;
  sel.innerHTML = items.map(([k, v]) => `<option value="${esc(k)}">${esc(v)}</option>`).join("");
  if ([...sel.options].some(o => o.value === cur)) sel.value = cur;
}
function setWarp(w) { for (const b of $("warp-btns").children) b.classList.toggle("on", +b.dataset.warp === +w); }
function status(text, ok) {
  const col = ok ? CSS.good : CSS.warning;
  $("link-status").textContent = text || "—";
  $("link-mini").innerHTML = `<span class="dot" style="background:${col}"></span>${ok ? (isSim ? "Simulare" : "Conectat") : "Fără legătură"}`;
  $("link-mini").title = text || "";
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
  lastTm = d;
  const st = d.mode, warp = d.warp || 1, col = STATE_COLOR[st] || CSS.text;
  $("state-text").textContent = (STATE_RO[st] || st) + (warp > 1 ? `  x${warp}` : "");
  $("state").style.color = col;
  $("state").querySelector(".dot").style.background = col;
  $("utc").textContent = d.t_utc.slice(11, 19);
  const name = (hello?.sats.find(([k]) => k === d.sat)?.[1] || String(d.sat)).split(" (")[0];
  $("kv-sat").textContent = `${name} · ${d.sat}`;
  $("kv-azel").textContent = `${d.sat_az.toFixed(1)}° / ${d.sat_el.toFixed(1)}°`;
  const tracking = st === "TRACK" || st === "ACQUIRE";
  const e = d.err_deg, ecol = e < 0.5 ? CSS.good : e < 2 ? CSS.warning : CSS.critical;
  $("kv-err").innerHTML = tracking
    ? `<span style="color:${ecol}">${e.toFixed(2)}°${d.kh ? (d.sat_el > 70 ? " keyhole" : " limită viteză") : ""}</span>` : "—";
  $("kv-tle").innerHTML = d.tle_fb
    ? `<span style="color:${CSS.warning}">vechi · ${d.tle_age.toFixed(0)} zile</span>`
    : `<span style="color:${CSS.good}">actual · ${d.tle_age.toFixed(1)} zile</span>`;

  for (const b of $("mode-btns").children) {
    const m = b.dataset.mode;
    b.classList.toggle("on", (m === "DEMO" && warp > 1) ||
      (m === "AUTO" && ["WAIT_AOS", "ACQUIRE", "TRACK"].includes(st) && warp === 1) ||
      (m === "MANUAL" && st === "MANUAL") || (m === "IDLE" && st === "IDLE"));
  }
  if (document.activeElement !== $("sat-select") && $("sat-select").value !== String(d.sat)) $("sat-select").value = d.sat;
  if (document.activeElement !== $("comp")) $("comp").checked = !!d.comp;

  const az = ((d.ant_az % 360) + 360) % 360;
  setGauge("az", d.ant_sky_az ?? az, `${(d.ant_sky_az ?? az).toFixed(1)}°`);
  setGauge("el", d.ant_sky_el, `${(d.ant_sky_el ?? d.ant_el).toFixed(1)}°`);
  setGauge("err", tracking ? e : 0, tracking ? e.toFixed(2) : "—", tracking ? ecol : CSS.muted);
  setGauge("rng", d.range_km, d.sat_el > -5 ? d.range_km.toFixed(0) : "—");
  setGauge("roll", d.roll, `${d.roll >= 0 ? "+" : ""}${d.roll.toFixed(1)}`);
  setGauge("pitch", d.pitch, `${d.pitch >= 0 ? "+" : ""}${d.pitch.toFixed(1)}`);

  sky.setPositions(d.sat_az, d.sat_el, d.ant_sky_az, d.ant_sky_el);
  if (vehicle) vehicle.setState(d.roll, d.pitch, d.yaw, d.ant_az, d.ant_el, d.sat_az, d.sat_el);
  if (globe) globe.setSatellite(d.sat_ecef, d.sat_alt_km, d.sat_el);
  charts.add(d);
  clockAndTimeline(d);
}

// mission clock (T− to AOS, T+ during the pass) and the pass timeline
function clockAndTimeline(d) {
  const t = d.t_utc_unix;
  let p = curPass && curPass.sat === d.sat && (curPass.los == null || curPass.los > t - 60) ? curPass : null;
  if (!p && d.next_aos_unix) p = { aos: d.next_aos_unix, los: d.next_los_unix, tmax: null, max_el: d.max_el, sat: d.sat };
  const name = (hello?.sats.find(([k]) => k === d.sat)?.[1] || String(d.sat)).split(" (")[0].toUpperCase();
  if (!p) {
    $("clock").textContent = "T− --:--:--";
    $("clock-label").textContent = `${name} · fără pasaj în 24 h`;
    drawTimeline(null, t);
    return;
  }
  if (p.los == null) {
    $("clock").textContent = "GEO";
    $("clock-label").textContent = `${name} · geostaționar, vizibil permanent`;
    drawTimeline(null, t, "Satelit geostaționar · fără AOS / LOS");
    return;
  }
  if (t < p.aos) {
    $("clock").textContent = "T− " + hms(p.aos - t);
    $("clock-label").textContent = `${name} · până la AOS · max ${p.max_el?.toFixed?.(0) ?? "—"}°`;
  } else if (t <= p.los) {
    $("clock").textContent = "T+ " + hms(t - p.aos);
    $("clock-label").textContent = `${name} · pasaj în curs · LOS în ${hms(p.los - t).slice(3)}`;
  } else {
    $("clock").textContent = "T+ " + hms(t - p.aos);
    $("clock-label").textContent = `${name} · după LOS`;
  }
  drawTimeline(p, t);
}

function drawTimeline(p, t, note = "") {
  const marks = $("tl-marks");
  if (!p) {
    marks.innerHTML = "";
    $("tl-fill").style.width = "0";
    $("tl-now").style.display = "none";
    $("tl-note").textContent = note;
    return;
  }
  const dur = p.los - p.aos;
  const a = p.aos - 0.35 * dur, b = p.los + 0.12 * dur;
  const x = v => Math.max(0, Math.min(100, (v - a) / (b - a) * 100));
  const ev = [["AOS", p.aos, "5°"], ...(p.tmax ? [["Max el", p.tmax, `${p.max_el.toFixed(0)}°`]] : []), ["LOS", p.los, "5°"]];
  marks.innerHTML = ev.map(([n, tt, sub]) => `<div class="tl-mark${t >= tt ? " past" : ""}" style="left:${x(tt)}%">
      <div class="n">${n} <span class="lbl">${sub}</span></div><div class="tick"></div><div class="t">${fmtTime(tt)}</div></div>`).join("");
  $("tl-fill").style.width = x(t) + "%";
  $("tl-now").style.display = "";
  $("tl-now").style.left = x(t) + "%";
  $("tl-note").textContent = t < a ? `◀ acum · AOS peste ${hms(p.aos - t)}` : note;
}

function passes(m) {
  sky.setTrack(m.sky);
  curPass = m.rows.find(r => r.current) ? { ...m.rows.find(r => r.current), sat: m.sat } : null;
  $("passes-body").innerHTML = m.rows.map(p => {
    const geo = p.los == null;
    return `<tr class="${p.current ? "cur" : ""}" title="${fmtDate(p.aos)}">
      <td>${geo ? fmtDate(p.aos).slice(5) + " " : ""}${fmtTime(p.aos)}</td><td>${geo ? "—" : fmtTime(p.los)}</td>
      <td>${p.max_el.toFixed(0)}°</td><td>${geo ? "fix" : p.dur_min.toFixed(1) + "′"}</td><td>${p.aos_az}°</td>
      <td>${p.sky_diff_s == null ? "—" : p.sky_diff_s.toFixed(1) + "s"}</td></tr>`;
  }).join("") || `<tr><td colspan="6">Niciun pasaj în următoarele 36 h</td></tr>`;
  if (lastTm) clockAndTimeline(lastTm);
}

function results(m) {
  const n = v => v == null ? "—" : v.toFixed(2) + "°";
  $("results-body").innerHTML = m.rows.map(r => `<tr>
      <td>${esc((r.los || "").slice(5, 16).replace("T", " "))}</td><td>${r.sat}</td><td>${r.comp ? "da" : "nu"}</td>
      <td>x${r.warp}</td><td>${esc(r.vehicle || "—")}</td><td>${n(r.max_err)}</td><td>${n(r.rms_err)}</td></tr>`).join("")
    || `<tr><td colspan="7">Încă niciun pasaj încheiat (se salvează la LOS)</td></tr>`;
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
  div.innerHTML = `<span class="t">${t}</span> <b style="color:${EVENT_COLOR[ev] || CSS.text}">${esc(EVENT_RO[ev] || ev)}</b> ${esc(rest)}`;
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
document.querySelectorAll(".tab[data-tab]").forEach(t => {
  t.onclick = () => {
    document.querySelectorAll(".tab[data-tab]").forEach(x => x.classList.toggle("on", x === t));
    $("tab-passes").hidden = t.dataset.tab !== "passes";
    $("tab-results").hidden = t.dataset.tab !== "results";
  };
});
document.querySelectorAll(".tab[data-chart]").forEach(t => {
  t.onclick = () => {
    document.querySelectorAll(".tab[data-chart]").forEach(x => x.classList.toggle("on", x === t));
    for (const k of ["err", "speed", "att"]) $("ch-" + k).hidden = t.dataset.chart !== k;
  };
});

connect();

// ------------------------------------------------------------ intro (first visit, or the INTRO button)
function startIntro() {
  runIntro(() => ({ hello, linkOk, isSim, tm: lastTm, xdiff }), fast => {
    if (fast) return;
    if (globe) globe.flyIn(); else flyPending = true;
  });
}
$("intro-btn").onclick = startIntro;
if (shouldRun()) startIntro();
