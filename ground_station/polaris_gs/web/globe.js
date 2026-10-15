// 3D globe in the Earth-fixed frame: coastlines, orbit, ground track,
// station visibility cone and the live satellite. 1 unit = Earth radius.
import * as THREE from "three";
import { OrbitControls } from "/static/vendor/three/OrbitControls.js";
import { Line2 } from "/static/vendor/three/lines/Line2.js";
import { LineGeometry } from "/static/vendor/three/lines/LineGeometry.js";
import { LineMaterial } from "/static/vendor/three/lines/LineMaterial.js";

const D2R = Math.PI / 180;
const WGS84_A = 6378.137;

function llToXyz(lat, lon, r = 1) {
  const a = lat * D2R, b = lon * D2R;
  return [r * Math.cos(a) * Math.cos(b), r * Math.cos(a) * Math.sin(b), r * Math.sin(a)];
}
const norm = v => Math.hypot(v[0], v[1], v[2]);
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];

export class GlobeView {
  constructor(el, css, station, maskEl) {
    this.el = el;
    this.css = css;
    this.maskEl = maskEl;
    this.station = station;            // ECEF in Earth radii
    this.renderer = new THREE.WebGLRenderer({ antialias: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.setClearColor(css.bg);
    el.appendChild(this.renderer.domElement);
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(40, 1, 0.01, 100);
    this.scene.add(this.camera);
    this.camera.add(new THREE.DirectionalLight(0xffffff, 2.2));
    this.scene.add(new THREE.AmbientLight(0xffffff, 0.9));
    // ECEF inside this group (z = north pole), three.js is y-up
    this.earth = new THREE.Group();
    this.earth.rotation.x = -Math.PI / 2;
    this.scene.add(this.earth);
    this.mats = [];

    this.earth.add(new THREE.Mesh(new THREE.SphereGeometry(0.995, 96, 48).rotateX(Math.PI / 2),
      new THREE.MeshPhongMaterial({ color: 0x132544, shininess: 8 })));
    const grat = [];
    for (let lat = -60; lat <= 60; lat += 30) for (let lon = -180; lon < 180; lon += 2) grat.push(llToXyz(lat, lon, 1.001), llToXyz(lat, lon + 2, 1.001));
    for (let lon = -180; lon < 180; lon += 30) for (let lat = -90; lat < 90; lat += 2) grat.push(llToXyz(lat, lon, 1.001), llToXyz(lat + 2, lon, 1.001));
    this.earth.add(this._segments(grat, 0x22355a, 1));
    fetch("/assets/coastline_110m.json").then(r => r.json()).then(j => {
      const segs = [];
      for (const ln of j.lines) for (let i = 1; i < ln.length; i++) segs.push(llToXyz(ln[i - 1][1], ln[i - 1][0], 1.002), llToXyz(ln[i][1], ln[i][0], 1.002));
      this.earth.add(this._segments(segs, 0x6f87b3, 1));
    });

    const st = new THREE.Mesh(new THREE.SphereGeometry(0.02, 16, 12), new THREE.MeshBasicMaterial({ color: css.accent }));
    st.position.set(...station.map(c => c * 1.004));
    this.earth.add(st);

    this.orbit = this._thick(0xc9d6ee, 1.5, 0.8);
    this.track = this._thick(css.accent, 2.5);
    this.footprint = this._thick(css.second, 2.5);
    this.link = this._thick(css.accent, 2);
    this.cone = this._segments([[0, 0, 0], [0, 0, 0]], css.second, 0.45);
    this.sat = new THREE.Mesh(new THREE.SphereGeometry(0.035, 16, 12), new THREE.MeshBasicMaterial({ color: 0xffffff }));
    this.sat.visible = false;
    this.earth.add(this.sat);

    // camera: distance 4.2, elevation 32 deg, above the station longitude + 15 deg
    const lat = 32, lon = 26.05 + 15, d = 3.5;
    const p = llToXyz(lat, lon, d);
    this.camera.position.set(p[0], p[2], -p[1]);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enablePan = false;
    this.controls.minDistance = 1.6;
    this.controls.maxDistance = 14;
    this.controls.enableDamping = true;
    this.controls.update();

    new ResizeObserver(() => this.resize()).observe(el);
    this.resize();
    const loop = () => { this.controls.update(); this.renderer.render(this.scene, this.camera); requestAnimationFrame(loop); };
    loop();
  }

  _segments(pairs, color, opacity) {
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(pairs.flat(), 3));
    const l = new THREE.LineSegments(g, new THREE.LineBasicMaterial({ color, transparent: opacity < 1, opacity }));
    l.frustumCulled = false;
    this.earth.add(l);
    return l;
  }

  _thick(color, width, opacity = 1) {
    const m = new LineMaterial({ color, linewidth: width, transparent: opacity < 1, opacity, worldUnits: false });
    this.mats.push(m);
    const l = new Line2(new LineGeometry(), m);
    l.visible = false;
    l.frustumCulled = false;
    this.earth.add(l);
    return l;
  }

  _setLine(line, pts) {
    if (!pts || pts.length < 2) { line.visible = false; return; }
    const g = new LineGeometry();
    g.setPositions(pts.flat());
    line.geometry.dispose();
    line.geometry = g;
    line.computeLineDistances();
    line.visible = true;
  }

  resize() {
    const w = this.el.clientWidth, h = this.el.clientHeight;
    if (!w || !h) return;
    this.renderer.setSize(w, h, false);
    this.renderer.domElement.style.width = "100%";
    this.renderer.domElement.style.height = "100%";
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    for (const m of this.mats) m.resolution.set(w, h);
  }

  setOrbit(pos, track) {
    this._setLine(this.orbit, pos);
    this._setLine(this.track, track.map(p => p.map(c => c * 1.003)));
  }

  setSatellite(r, altKm, satEl) {
    if (!r) { this.sat.visible = false; return; }
    const up = satEl > this.maskEl;
    this.sat.position.set(r[0], r[1], r[2]);
    this.sat.material.color.set(up ? this.css.accent : 0xffffff);
    this.sat.visible = true;
    const s = this.station.map(c => c * 1.004);
    if (up) this._setLine(this.link, [s, r]);
    else this.link.visible = false;
    // visibility footprint for the satellite altitude and the elevation mask
    const e = this.maskEl * D2R;
    const lam = Math.acos(WGS84_A / (WGS84_A + altKm) * Math.cos(e)) - e;
    const n = this.station.map(c => c / norm(this.station));
    let u = cross(n, [0, 0, 1]);
    u = u.map(c => c / norm(u));
    const v = cross(n, u);
    const k = (WGS84_A + altKm) / WGS84_A;
    const circle = [], edges = [];
    for (let i = 0; i <= 120; i++) {
      const a = 2 * Math.PI * i / 120;
      const p = [0, 1, 2].map(j => Math.cos(lam) * n[j] + Math.sin(lam) * (Math.cos(a) * u[j] + Math.sin(a) * v[j]));
      circle.push(p.map(c => c * 1.004));
      if (i % 10 === 0 && i < 120) edges.push(s, p.map(c => c * k));
    }
    this._setLine(this.footprint, circle);
    const g = this.cone.geometry;
    g.setAttribute("position", new THREE.Float32BufferAttribute(edges.flat(), 3));
  }
}
