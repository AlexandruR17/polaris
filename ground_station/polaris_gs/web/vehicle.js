// 3D vehicle with the antenna pedestal, driven by roll/pitch/yaw and the two
// axis angles. World frame ENU (x east, y north, z up), vehicle FLU.
// Same rotations as core/geometry.py: R = Rz(yaw) Ry(pitch) Rx(roll).
import * as THREE from "three";
import { OrbitControls } from "/static/vendor/three/OrbitControls.js";

const D2R = Math.PI / 180;

// 3x3 matrices as row-major arrays [[...],[...],[...]]
function rotX(a) { const c = Math.cos(a), s = Math.sin(a); return [[1, 0, 0], [0, c, -s], [0, s, c]]; }
function rotY(a) { const c = Math.cos(a), s = Math.sin(a); return [[c, 0, s], [0, 1, 0], [-s, 0, c]]; }
function rotZ(a) { const c = Math.cos(a), s = Math.sin(a); return [[c, -s, 0], [s, c, 0], [0, 0, 1]]; }
function mul(a, b) {
  const r = [[0, 0, 0], [0, 0, 0], [0, 0, 0]];
  for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) for (let k = 0; k < 3; k++) r[i][j] += a[i][k] * b[k][j];
  return r;
}
function apply(m, v) { return [0, 1, 2].map(i => m[i][0] * v[0] + m[i][1] * v[1] + m[i][2] * v[2]); }
function add(a, b) { return [a[0] + b[0], a[1] + b[1], a[2] + b[2]]; }
function scale(v, k) { return [v[0] * k, v[1] * k, v[2] * k]; }
export function attitude(roll, pitch, yaw) { return mul(mul(rotZ(yaw * D2R), rotY(pitch * D2R)), rotX(roll * D2R)); }
export function azelToEnu(az, el) {
  const a = az * D2R, e = el * D2R;
  return [Math.cos(e) * Math.sin(a), Math.cos(e) * Math.cos(a), Math.sin(e)];
}
function setPose(obj, R, t = [0, 0, 0]) {
  obj.matrix.set(R[0][0], R[0][1], R[0][2], t[0],
                 R[1][0], R[1][1], R[1][2], t[1],
                 R[2][0], R[2][1], R[2][2], t[2],
                 0, 0, 0, 1);
}

function dishGeometry(r = 0.9, depth = 0.28, n = 40, rings = 8) {
  // paraboloid opening along +x (boresight)
  const v = [0, 0, 0], idx = [];
  for (let i = 1; i <= rings; i++) {
    const rr = r * i / rings;
    for (let k = 0; k < n; k++) {
      const a = 2 * Math.PI * k / n;
      v.push(depth * (rr / r) ** 2, rr * Math.cos(a), rr * Math.sin(a));
    }
  }
  for (let k = 0; k < n; k++) idx.push(0, 1 + k, 1 + (k + 1) % n);
  for (let i = 1; i < rings; i++) {
    const b0 = 1 + (i - 1) * n, b1 = 1 + i * n;
    for (let k = 0; k < n; k++) {
      const k2 = (k + 1) % n;
      idx.push(b0 + k, b1 + k, b1 + k2, b0 + k, b1 + k2, b0 + k2);
    }
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(v, 3));
  g.setIndex(idx);
  g.computeVertexNormals();
  return g;
}

function textSprite(text, color) {
  const c = document.createElement("canvas");
  c.width = c.height = 64;
  const g = c.getContext("2d");
  g.fillStyle = color;
  g.font = "bold 44px DejaVu Sans, Segoe UI, sans-serif";
  g.textAlign = "center";
  g.textBaseline = "middle";
  g.fillText(text, 32, 34);
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(c), depthTest: false }));
  s.scale.set(0.8, 0.8, 1);
  return s;
}

export class VehicleView {
  constructor(el, css) {
    this.el = el;
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.setClearColor(0x000000, 0);
    const v = css.veh;
    el.appendChild(this.renderer.domElement);
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(42, 1, 0.1, 200);
    // ENU inside this group: x east, y north, z up (three.js is y-up)
    this.world = new THREE.Group();
    this.world.rotation.x = -Math.PI / 2;
    this.scene.add(this.world);
    this.scene.add(new THREE.HemisphereLight(0xdfe8ff, 0x1a2338, 1.6));
    const sun = new THREE.DirectionalLight(0xffffff, 1.6);
    sun.position.set(-6, 10, 8);
    this.scene.add(sun);

    const grid = new THREE.GridHelper(16, 16, v.grid, v.grid);
    grid.material.transparent = true;
    grid.material.opacity = 0.35;
    this.scene.add(grid);
    const north = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(0, 0, 0.01), new THREE.Vector3(0, 7, 0.01)]);
    this.world.add(new THREE.Line(north, new THREE.LineBasicMaterial({ color: css.muted })));
    const n = textSprite("N", css.text2);
    n.position.set(0, 7.6, 0.3);
    this.world.add(n);

    const mesh = (geom, color, edges = true) => {
      const m = new THREE.Mesh(geom, new THREE.MeshStandardMaterial({ color, roughness: 0.75, metalness: 0.05,
        side: edges ? THREE.FrontSide : THREE.DoubleSide, flatShading: edges }));
      if (edges) m.add(new THREE.LineSegments(new THREE.EdgesGeometry(geom, 25),
        new THREE.LineBasicMaterial({ color: v.edge, transparent: true, opacity: v.edgeOpacity })));
      m.matrixAutoUpdate = false;
      this.world.add(m);
      return m;
    };
    const box = (sx, sy, sz, cx = 0, cy = 0, cz = 0) => new THREE.BoxGeometry(sx, sy, sz).translate(cx, cy, cz);
    const cylZ = (r, h, cz = 0) => new THREE.CylinderGeometry(r, r, h, 32).rotateX(Math.PI / 2).translate(0, 0, cz);

    this.bodyItems = [mesh(box(4.6, 2.0, 0.9, 0, 0, 0.85), v.body), mesh(box(1.6, 1.9, 0.7, 1.4, 0, 1.6), v.cab)];
    this.wheels = [];
    for (const wx of [-1.5, 1.5]) for (const wy of [-1.05, 1.05]) {
      // cylinder axis along local y = vehicle left/right
      this.wheels.push([mesh(new THREE.CylinderGeometry(0.45, 0.45, 0.35, 28), v.wheel), [wx, wy, 0.45]]);
    }
    this.base = mesh(cylZ(0.45, 0.35, 1.5), v.base);
    this.turret = mesh(box(0.5, 0.5, 0.7, 0, 0, 0.35), v.turret);
    this.cradle = mesh(box(0.2, 1.2, 0.2), v.cradle);
    this.dish = mesh(dishGeometry(), v.dish, false);

    const line = (color) => {
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.Float32BufferAttribute(new Float32Array(6), 3));
      const l = new THREE.Line(g, new THREE.LineBasicMaterial({ color, linewidth: 3 }));
      l.frustumCulled = false;
      this.world.add(l);
      return l;
    };
    this.bore = line(new THREE.Color(css.second));
    this.target = line(new THREE.Color(css.accent));

    // camera like the former view: distance 10, elevation 20, azimuth -60, centre z 2
    const c = [0, 0, 2], d = 10, camEl = 20 * D2R, camAz = -60 * D2R;
    const p = [c[0] + d * Math.cos(camEl) * Math.cos(camAz), c[1] + d * Math.cos(camEl) * Math.sin(camAz), c[2] + d * Math.sin(camEl)];
    this.camera.position.set(p[0], p[2], -p[1]);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.target.set(c[0], c[2], -c[1]);
    this.controls.enablePan = false;
    this.controls.minDistance = 4;
    this.controls.maxDistance = 30;
    this.controls.enableDamping = true;
    this.controls.update();

    this.setState(0, 0, 90, 0, 90, 0, -90);
    new ResizeObserver(() => this.resize()).observe(el);
    this.resize();
    const loop = () => { this.controls.update(); this.renderer.render(this.scene, this.camera); requestAnimationFrame(loop); };
    loop();
  }

  resize() {
    const w = this.el.clientWidth, h = this.el.clientHeight;
    if (!w || !h) return;
    this.renderer.setSize(w, h, false);
    this.renderer.domElement.style.width = "100%";
    this.renderer.domElement.style.height = "100%";
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
  }

  setState(roll, pitch, yaw, pedAz, pedEl, satAz, satEl) {
    const R = attitude(roll, pitch, yaw);
    for (const m of this.bodyItems) setPose(m, R);
    for (const [w, pos] of this.wheels) setPose(w, R, apply(R, pos));
    setPose(this.base, R);
    // turret: pedestal azimuth, clockwise from forward = rotation about -z
    const Ra = mul(R, rotZ(-pedAz * D2R));
    const top = apply(R, [0, 0, 1.68]);
    setPose(this.turret, Ra, top);
    const Re = mul(Ra, rotY(-pedEl * D2R));
    const hinge = add(top, apply(Ra, [0, 0, 0.9]));
    setPose(this.cradle, Ra, hinge);
    setPose(this.dish, Re, add(hinge, apply(Re, [0.05, 0, 0])));
    const b = apply(Re, [1, 0, 0]);
    this._seg(this.bore, hinge, add(hinge, scale(b, 4.5)));
    if (satEl > -5) {
      this._seg(this.target, hinge, add(hinge, scale(azelToEnu(satAz, satEl), 6.0)));
      this.target.visible = true;
    } else {
      this.target.visible = false;
    }
  }

  _seg(line, a, b) {
    const p = line.geometry.attributes.position;
    p.setXYZ(0, a[0], a[1], a[2]);
    p.setXYZ(1, b[0], b[1], b[2]);
    p.needsUpdate = true;
  }
}
