// Time charts with uPlot: one measure per chart (no dual axes), last 2 minutes.
const WINDOW_S = 120;

export class Charts {
  constructor(els, css) {
    this.css = css;
    this.buf = { t: [], err: [], mode: [], az: [], el: [], roll: [], pitch: [] };
    this.dirty = false;
    const axis = (label) => ({
      stroke: css.text2, label, labelSize: 16, labelFont: "12px " + css.font, font: "11px " + css.font,
      grid: { stroke: css.grid, width: 1 }, ticks: { stroke: css.border, width: 1 }, size: 44, space: 18,
    });
    const xAxis = { ...axis(), label: undefined, space: 50, values: (u, v) => v.map(x => x + " s") };
    const make = (el, title, unit, series, yRange) => {
      // one header line (title + legend) instead of uPlot's title and legend rows
      const head = document.createElement("div");
      head.className = "chart-head";
      head.innerHTML = `<b>${title}</b>` + series.map(sr =>
        `<span><i style="border-top:${sr.width}px ${sr.dash ? "dashed" : "solid"} ${sr.stroke}"></i>${sr.label}</span>`).join("");
      const box = document.createElement("div");
      box.className = "chart-plot";
      el.append(head, box);
      const opts = {
        width: 400, height: 150, pxAlign: false,
        cursor: { drag: { x: false, y: false }, points: { size: 6 } },
        legend: { show: false },
        scales: { x: { time: false, range: [-WINDOW_S, 0] }, y: { range: yRange } },
        axes: [xAxis, axis(unit)],
        series: [{}, ...series],
      };
      const u = new uPlot(opts, [[], ...series.map(() => [])], box);
      new ResizeObserver(() => {
        const w = box.clientWidth, h = box.clientHeight;
        if (w && h) u.setSize({ width: w, height: Math.max(70, h) });
      }).observe(box);
      return u;
    };
    const s = (label, stroke, dash) => ({ label, stroke, width: 2, dash, points: { show: false }, spanGaps: false });
    this.errChart = make(els.err, "Eroare de pointare", "grade",
      [s("eroare", css.accent), { ...s("prag 1°", css.muted, [5, 4]), width: 1 }],
      () => [0, this.errTop()]);
    this.speedChart = make(els.speed, "Viteza axelor", "°/s",
      [s("azimut", css.second), s("elevație", css.accent)], (u, lo, hi) => sym(lo, hi, 5));
    this.attChart = make(els.att, "Înclinarea vehiculului", "grade",
      [s("ruliu (roll)", css.accent), s("tangaj (pitch)", css.second)], (u, lo, hi) => sym(lo, hi, 2));
    setInterval(() => this.redraw(), 200);
  }

  errTop() {
    const b = this.buf;
    let top = 2.0;
    for (let i = 0; i < b.t.length; i++) if (b.mode[i] === "TRACK" || b.mode[i] === "ACQUIRE") top = Math.max(top, b.err[i] ?? 0);
    return Math.max(2.0, Math.min(top * 1.15, 30.0));
  }

  reset(rows) {
    for (const k in this.buf) this.buf[k] = [];
    for (const r of rows || []) this._push(...r);
    this.dirty = true;
  }

  add(d) {
    this._push(d._t, d.err_deg, d.mode, d.az_rate, d.el_rate, d.roll, d.pitch);
    this.dirty = true;
  }

  _push(t, err, mode, az, el, roll, pitch) {
    const b = this.buf;
    b.t.push(t); b.err.push(err); b.mode.push(mode); b.az.push(az); b.el.push(el); b.roll.push(roll); b.pitch.push(pitch);
    const lim = t - WINDOW_S - 5;
    let n = 0;
    while (n < b.t.length && b.t[n] < lim) n++;
    if (n) for (const k in b) b[k].splice(0, n);
  }

  redraw() {
    if (!this.dirty) return;
    this.dirty = false;
    const b = this.buf;
    if (!b.t.length) return;
    const tmax = b.t[b.t.length - 1];
    const x = b.t.map(t => t - tmax);
    this.errChart.setData([x, b.err, x.map(() => 1.0)]);
    this.speedChart.setData([x, b.az, b.el]);
    this.attChart.setData([x, b.roll, b.pitch]);
  }
}

function sym(lo, hi, min) {
  const m = Math.max(min, Math.abs(lo ?? 0), Math.abs(hi ?? 0)) * 1.1;
  return [-m, m];
}
