// One-time intro, in the style of a launch webcast: title, a few lines about
// the system, a GO / NO-GO poll built from live data, then the globe flies in.
// Shown on the first visit only; ?intro=1 replays it, ?intro=0 skips it.

const KEY = "polaris.introSeen";
const sleep = ms => new Promise(r => setTimeout(r, ms));

function seen() {
  try { return localStorage.getItem(KEY) === "1"; } catch { return false; }
}
function markSeen() {
  try { localStorage.setItem(KEY, "1"); } catch { /* private mode: show again next time */ }
}

export function shouldRun() {
  const q = new URLSearchParams(location.search).get("intro");
  if (q === "1") return true;
  if (q === "0") return false;
  return !seen();
}

// live: () => ({ hello, tm, xdiff }) with whatever the station has sent so far
export async function runIntro(live, onReveal) {
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const root = document.createElement("div");
  root.id = "intro";
  root.innerHTML = `
    <div class="i-line" id="i-line"></div>
    <div class="i-stage" id="i-stage"></div>
    <button class="i-skip" id="i-skip" type="button">Sari peste <span class="lbl">Esc</span></button>`;
  document.body.appendChild(root);
  document.body.classList.add("intro-on");
  let cancelled = false;
  const stage = root.querySelector("#i-stage");
  const finish = () => { cancelled = true; };
  root.querySelector("#i-skip").onclick = finish;
  const onKey = e => { if (e.key === "Escape" || e.key === " " || e.key === "Enter") finish(); };
  window.addEventListener("keydown", onKey);
  const wait = async ms => {
    const end = performance.now() + (reduced ? Math.min(ms, 300) : ms);
    while (!cancelled && performance.now() < end) await sleep(50);
    return !cancelled;
  };
  const show = html => {
    stage.innerHTML = html;
    stage.classList.remove("out");
    void stage.offsetWidth;
    stage.classList.add("in");
  };
  const hide = async () => { stage.classList.add("out"); await wait(450); };

  try {
    // 1. horizon line, then the name letter by letter
    root.querySelector("#i-line").classList.add("grow");
    if (!await wait(900)) return;
    show(`<div class="i-title" aria-label="POLARIS">${[..."POLARIS"].map((c, i) =>
      `<span style="animation-delay:${0.08 * i}s">${c}</span>`).join("")}</div>
      <div class="i-sub">SAT-1 · antenă de urmărire a sateliților, montată pe vehicul</div>`);
    if (!await wait(2600)) return;
    root.querySelector("#i-line").classList.add("gone");
    await hide();

    // 2. what it is
    show(`<div class="i-facts">
      ${[["Predicție orbitală", "SGP4 Vallado, verificat la 0,12 mm"],
         ["Compensare", "ruliu, tangaj și giruire ale vehiculului"],
         ["Siguranță", "E-STOP hardware, limitatoare, homing cu timp limită"],
         ["Stație de sol", "Politehnica București · 44.4386°N 26.0494°E"]]
        .map(([k, v], i) => `<div class="i-fact" style="animation-delay:${0.35 * i}s"><span class="lbl">${k}</span><span>${v}</span></div>`).join("")}
      </div>`);
    if (!await wait(3400)) return;
    await hide();

    // 3. GO / NO-GO poll from live data
    show(`<div class="i-poll"><div class="lbl i-poll-h">Verificare înainte de urmărire · GO / NO-GO</div><div id="i-rows"></div></div>`);
    const rows = stage.querySelector("#i-rows");
    const checks = [
      ["Legătură", () => { const l = live(); return l.hello ? [l.linkOk, l.isSim ? "simulare internă" : (l.linkOk ? "conectat" : "fără legătură")] : null; }],
      ["Timp UTC", () => { const t = live().tm; return t ? [true, t.t_utc.slice(11, 19)] : null; }],
      ["Elemente orbitale", () => { const t = live().tm; return t ? [true, t.tle_fb ? `rezervă · ${t.tle_age.toFixed(0)} zile` : `actuale · ${t.tle_age.toFixed(1)} zile`] : null; }],
      ["Verificare skyfield", () => { const x = live().xdiff; return x != null ? [x < 0.1, `Δ ${x.toFixed(3)}°`] : null; }],
      ["Axe calibrate", () => {
        const t = live().tm;
        if (!t) return null;
        const bad = { BOOT: "pornire", HOMING: "homing în curs", FAULT: "defect", ESTOP: "oprire de urgență" }[t.mode];
        return [!bad, bad || "homing reușit"];
      }],
    ];
    for (const [name, fn] of checks) {
      const row = document.createElement("div");
      row.className = "i-row";
      row.innerHTML = `<span class="n">${name}</span><span class="dots"></span><span class="d"></span><span class="v">…</span>`;
      rows.appendChild(row);
      // wait for real data a little, then report what we have
      let r = null;
      for (let i = 0; i < 16 && !(r = fn()); i++) if (!await wait(150)) return;
      if (!await wait(380)) return;
      const go = r ? r[0] : false;
      row.querySelector(".d").textContent = r ? r[1] : "fără date";
      const v = row.querySelector(".v");
      v.textContent = go ? "GO" : "AȘTEPT";
      v.className = "v " + (go ? "go" : "hold");
    }
    if (!await wait(900)) return;
    await hide();

    // 4. the call
    show(`<div class="i-go">POLARIS ESTE <b>GO</b></div><div class="i-sub">pentru urmărirea sateliților</div>`);
    if (!await wait(1700)) return;
  } finally {
    window.removeEventListener("keydown", onKey);
    markSeen();
    root.classList.add("done");
    document.body.classList.remove("intro-on");
    document.documentElement.classList.remove("intro-pending");
    document.body.classList.add("reveal");
    onReveal && onReveal(reduced || cancelled);
    setTimeout(() => { root.remove(); document.body.classList.remove("reveal"); }, 1600);
  }
}
