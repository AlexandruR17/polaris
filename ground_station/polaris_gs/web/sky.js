// Polar sky plot: zenith in the centre, horizon on the rim, north up, east right.
const D2R = Math.PI / 180;

export class SkyPlot {
  constructor(canvas, css, maskEl) {
    this.cv = canvas;
    this.css = css;
    this.maskEl = maskEl;
    this.track = { az: [], el: [] };
    this.pos = null;
    new ResizeObserver(() => this.draw()).observe(canvas.parentElement);
  }

  setTrack(sky) { this.track = sky || { az: [], el: [] }; this.draw(); }
  setPositions(satAz, satEl, antAz, antEl) { this.pos = { satAz, satEl, antAz, antEl }; this.draw(); }

  draw() {
    const cv = this.cv, box = cv.parentElement;
    const w = box.clientWidth, h = box.clientHeight, dpr = window.devicePixelRatio || 1;
    if (!w || !h) return;
    if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) {
      cv.width = Math.round(w * dpr);
      cv.height = Math.round(h * dpr);
    }
    const g = cv.getContext("2d"), c = this.css;
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, w, h);
    const R = Math.min(w, h) / 2 - 22, cx = w / 2, cy = h / 2 + 2;
    const P = (az, el) => {
      const r = (90 - Math.max(-5, Math.min(90, el))) / 90 * R;
      return [cx + r * Math.sin(az * D2R), cy - r * Math.cos(az * D2R)];
    };
    g.lineWidth = 1;
    for (let az = 0; az < 360; az += 30) {
      const [x, y] = P(az, 0);
      g.strokeStyle = c.grid;
      g.beginPath(); g.moveTo(cx, cy); g.lineTo(x, y); g.stroke();
    }
    for (const el of [60, 30, 0]) {
      g.strokeStyle = el === 0 ? c.border : c.grid;
      g.lineWidth = el === 0 ? 1.5 : 1;
      g.beginPath(); g.arc(cx, cy, (90 - el) / 90 * R, 0, 2 * Math.PI); g.stroke();
      if (el) {
        g.fillStyle = c.muted;
        g.font = "11px " + c.font;
        g.fillText(el + "°", cx + 3, cy - (90 - el) / 90 * R - 3);
      }
    }
    g.setLineDash([5, 4]);
    g.strokeStyle = c.muted;
    g.beginPath(); g.arc(cx, cy, (90 - this.maskEl) / 90 * R, 0, 2 * Math.PI); g.stroke();
    g.setLineDash([]);
    g.fillStyle = c.text2;
    g.font = "bold 13px " + c.font;
    g.textAlign = "center";
    g.textBaseline = "middle";
    for (const [t, az] of [["N", 0], ["E", 90], ["S", 180], ["V", 270]]) {
      const r = R + 13;
      g.fillText(t, cx + r * Math.sin(az * D2R), cy - r * Math.cos(az * D2R));
    }
    const tr = this.track;
    if (tr.az.length > 1) {
      g.strokeStyle = c.accent;
      g.lineWidth = 2;
      g.beginPath();
      tr.az.forEach((az, i) => { const [x, y] = P(az, tr.el[i]); i ? g.lineTo(x, y) : g.moveTo(x, y); });
      g.stroke();
      const [x0, y0] = P(tr.az[0], tr.el[0]);
      g.fillStyle = c.text2;
      g.font = "12px " + c.font;
      g.fillText("AOS", x0, y0 - 12);
    }
    const p = this.pos;
    if (p) {
      const [sx, sy] = P(p.satAz, p.satEl), [ax, ay] = P(p.antAz, p.antEl);
      if (p.satEl > -5) {
        g.setLineDash([2, 3]);
        g.strokeStyle = c.text2;
        g.lineWidth = 1.5;
        g.beginPath(); g.moveTo(sx, sy); g.lineTo(ax, ay); g.stroke();
        g.setLineDash([]);
        g.fillStyle = c.accent;
        g.strokeStyle = c.bg;
        g.lineWidth = 2;
        g.beginPath(); g.arc(sx, sy, 8, 0, 2 * Math.PI); g.fill(); g.stroke();
      }
      g.strokeStyle = c.second;
      g.lineWidth = 3;
      g.beginPath(); g.moveTo(ax - 10, ay); g.lineTo(ax + 10, ay); g.moveTo(ax, ay - 10); g.lineTo(ax, ay + 10); g.stroke();
    }
    // legend: identity is not colour alone (marker shape + text)
    g.textAlign = "left";
    g.textBaseline = "middle";
    g.font = "12px " + c.font;
    const items = [["sat", "satelit"], ["ant", "antenă (direcția reală)"], ["trk", "pasaj"]];
    items.forEach(([k, t], i) => {
      const x = 12, y = 14 + i * 18;
      if (k === "sat") { g.fillStyle = c.accent; g.beginPath(); g.arc(x + 6, y, 5, 0, 2 * Math.PI); g.fill(); }
      if (k === "ant") { g.strokeStyle = c.second; g.lineWidth = 2.5; g.beginPath(); g.moveTo(x, y); g.lineTo(x + 12, y); g.moveTo(x + 6, y - 6); g.lineTo(x + 6, y + 6); g.stroke(); }
      if (k === "trk") { g.strokeStyle = c.accent; g.lineWidth = 2; g.beginPath(); g.moveTo(x, y); g.lineTo(x + 12, y); g.stroke(); }
      g.fillStyle = c.text2;
      g.fillText(t, x + 20, y);
    });
  }
}
