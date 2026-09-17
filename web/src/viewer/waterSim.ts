/* Sayoz suv gidrodinamikasi (balandlik maydoni, «virtual quvurlar» usuli — Mei, Decaudin, Hu 2007; O'Brien & Hodgins 1995).
   Relyef b(x,y) (server balandlik xaritasi: relyef + to'g'on + binolar) ustida suv chuqurligi h(x,y): qo'shni
   kataklar orasidagi oqim f = f + Δt·g·A·Δη/l (η = b + h — suv sathi), hajm saqlanadi, quruq kataklar (h = 0)
   o'z-o'zidan hosil bo'ladi/yo'qoladi. Natija: toshqin to'lqini relyef bo'ylab yuradi, gerbdan oshsa quyi byefga
   oqadi, yorilish (to'g'on kataklarini pasaytirish) — suv o'zi otilib chiqadi, ko'chki impulsi — to'lqin to'g'onga
   urilib qaytadi. Aniqlik: sayoz suv (gidrostatik), ~10–20 m katak; hisob (Puls/Froehlich/Muskingum) o'rniga emas,
   uni relyefda **ko'rsatish** uchun. CPU (JS), 128×128 gacha panjara — 60 kadr/s. */

export interface Heightmap { x0: number; y0: number; dx: number; dy: number; nx: number; ny: number; z: number[] }

export class WaterSim {
  readonly nx: number;
  readonly ny: number;
  readonly dx: number; // katak o'lchami X (m)
  readonly dy: number; // katak o'lchami Y (m)
  readonly x0: number;
  readonly y0: number;
  readonly b: Float32Array; // yer/inshoot balandligi (IFC z, m)
  readonly h: Float32Array; // suv chuqurligi (m)
  private fl: Float32Array; // oqimlar: chap, o'ng, past (j−1), yuqori (j+1) — m³/s
  private fr: Float32Array;
  private fd: Float32Array;
  private fu: Float32Array;
  private readonly g = 9.81;
  readonly base: Float32Array; // asl relyef (yorilishni qaytarish uchun; toshqin xaritasi)
  time = 0; // simulyatsiya vaqti, s
  /** Toshqin xaritasi: har katakda maksimal chuqurlik (m), maksimal tezlik (m/s), maksimal h·v (m²/s — xavf),
   *  suv kelish vaqti (s; −1 — kelmagan; h > 0.3 m). Boshlang'ich to'ldirilgan (ombor) kataklar `initial` da. */
  readonly hMax: Float32Array;
  readonly vMax: Float32Array;
  readonly hvMax: Float32Array;
  readonly tArrive: Float32Array;
  readonly initial: Uint8Array;
  private statAccum = 0; // statistika har ~2 s sim vaqtda (tezlik uchun)
  /** manbalar: {i, j, q} m³/s (musbat — kirim, manfiy — chiqim) */
  sources: { i: number; j: number; q: number }[] = [];
  /** ochiq chegara: quyi byef chekkasida (j = 0..1) suv hududdan chiqib ketadi (daryo davom etadi) */
  openDownstream = true;
  outflowVolume = 0; // hududdan chiqqan hajm, m³

  constructor(hm: Heightmap, maxCells = 128) {
    // kerak bo'lsa siyraklashtirish (tezlik uchun)
    const step = Math.max(1, Math.ceil(Math.max(hm.nx, hm.ny) / maxCells));
    this.nx = Math.floor(hm.nx / step);
    this.ny = Math.floor(hm.ny / step);
    this.dx = hm.dx * step;
    this.dy = hm.dy * step;
    this.x0 = hm.x0;
    this.y0 = hm.y0;
    const n = this.nx * this.ny;
    this.b = new Float32Array(n);
    for (let j = 0; j < this.ny; j++) {
      for (let i = 0; i < this.nx; i++) {
        // katak ichidagi maksimal balandlik — to'g'on gerbi yo'qolib ketmasin
        let m = -Infinity;
        for (let jj = 0; jj < step; jj++) for (let ii = 0; ii < step; ii++) {
          const v = hm.z[(j * step + jj) * hm.nx + i * step + ii];
          if (v != null && v > m) m = v;
        }
        this.b[j * this.nx + i] = m;
      }
    }
    this.base = this.b.slice();
    this.h = new Float32Array(n);
    this.fl = new Float32Array(n);
    this.fr = new Float32Array(n);
    this.fd = new Float32Array(n);
    this.fu = new Float32Array(n);
    this.hMax = new Float32Array(n);
    this.vMax = new Float32Array(n);
    this.hvMax = new Float32Array(n);
    this.tArrive = new Float32Array(n).fill(-1);
    this.initial = new Uint8Array(n);
  }

  cellAt(x: number, y: number): [number, number] {
    return [Math.min(this.nx - 1, Math.max(0, Math.floor((x - this.x0) / this.dx))), Math.min(this.ny - 1, Math.max(0, Math.floor((y - this.y0) / this.dy)))];
  }

  /** Suvni sath (IFC z) gacha to'ldirish: region — bog'langan havza (yuqori byef: j = ny−1 tomon, quyi: j = 0). */
  fill(level: number, region: "upstream" | "downstream" | "all") {
    const { nx, ny, b, h } = this;
    const wet = new Uint8Array(nx * ny);
    for (let k = 0; k < nx * ny; k++) wet[k] = b[k] < level ? 1 : 0;
    let mask = wet;
    if (region !== "all") {
      mask = new Uint8Array(nx * ny);
      const rows = region === "upstream" ? [ny - 1, ny - 2, ny - 3] : [0, 1, 2];
      const q: number[] = [];
      for (const j of rows) {
        let best = -1, bz = Infinity;
        for (let i = 0; i < nx; i++) { const k = j * nx + i; if (wet[k] && b[k] < bz) { bz = b[k]; best = k; } }
        if (best >= 0) { q.push(best); mask[best] = 1; }
      }
      while (q.length) {
        const k = q.pop()!;
        const i = k % nx, j = (k - i) / nx;
        const nb = [i > 0 ? k - 1 : -1, i < nx - 1 ? k + 1 : -1, j > 0 ? k - nx : -1, j < ny - 1 ? k + nx : -1];
        for (const n of nb) if (n >= 0 && wet[n] && !mask[n]) { mask[n] = 1; q.push(n); }
      }
    }
    for (let k = 0; k < nx * ny; k++) if (mask[k]) { h[k] = Math.max(h[k], level - b[k]); if (h[k] > 0.01) this.initial[k] = 1; }
    this.fl.fill(0); this.fr.fill(0); this.fd.fill(0); this.fu.fill(0);
  }

  clear() { this.h.fill(0); this.fl.fill(0); this.fr.fill(0); this.fd.fill(0); this.fu.fill(0); this.time = 0; this.sources = []; }

  /** Yorilish: to'g'on kataklarini (x oralig'i, y oralig'i, IFC) berilgan tub belgisigacha pasaytirish. */
  breach(x0: number, x1: number, y0: number, y1: number, bottom: number) {
    const [i0, j0] = this.cellAt(Math.min(x0, x1), Math.min(y0, y1));
    const [i1, j1] = this.cellAt(Math.max(x0, x1), Math.max(y0, y1));
    for (let j = j0; j <= j1; j++) for (let i = i0; i <= i1; i++) { const k = j * this.nx + i; this.b[k] = Math.min(this.b[k], bottom); }
  }

  restoreTerrain() { this.b.set(this.base); }

  /** Ko'chki impulsi: markaz (x,y), radius r (m), qo'shimcha chuqurlik dh (m) va yo'nalish bo'yicha boshlang'ich oqim. */
  impulse(x: number, y: number, r: number, dh: number, dirX: number, dirY: number, speed: number) {
    const [ci, cj] = this.cellAt(x, y);
    const rc = Math.max(1, Math.round(r / Math.max(this.dx, this.dy)));
    for (let j = cj - rc; j <= cj + rc; j++) for (let i = ci - rc; i <= ci + rc; i++) {
      if (i < 0 || j < 0 || i >= this.nx || j >= this.ny) continue;
      const d = Math.hypot(i - ci, j - cj) / rc;
      if (d > 1) continue;
      const k = j * this.nx + i;
      if (this.h[k] <= 0.01) continue;
      const w = 1 - d * d;
      this.h[k] += dh * w;
      const q = speed * this.h[k] * Math.min(this.dx, this.dy) * w; // m³/s
      if (dirX > 0) this.fr[k] += q * dirX; else this.fl[k] += -q * dirX;
      if (dirY > 0) this.fu[k] += q * dirY; else this.fd[k] += -q * dirY;
    }
  }

  /** Bir qadam (Δt s). Barqarorlik uchun Δt ≤ ~0.5·dx/√(g·h_max) — chaqiruvchi kichik bo'laklarga bo'lib beradi. */
  step(dt: number) {
    const { nx, ny, b, h, fl, fr, fd, fu, g, dx, dy } = this;
    const A = dx * dy;
    const damp = 0.995; // ishqalanish (Manning o'rniga sodda so'nish)
    // 1) oqimlar
    for (let j = 0; j < ny; j++) {
      for (let i = 0; i < nx; i++) {
        const k = j * nx + i;
        const eta = b[k] + h[k];
        // f = f + Δt·g·A·Δη/l: x yo'nalishda A/l = dy, y yo'nalishda dx
        const upd = (f: Float32Array, kn: number, c: number) => {
          const dEta = eta - (b[kn] + h[kn]);
          f[k] = Math.max(0, damp * f[k] + dt * g * c * dEta);
        };
        if (i > 0) upd(fl, k - 1, dy); else fl[k] = 0;
        if (i < nx - 1) upd(fr, k + 1, dy); else fr[k] = 0;
        if (j > 0) upd(fd, k - nx, dx); else fd[k] = 0;
        if (j < ny - 1) upd(fu, k + nx, dx); else fu[k] = 0;
        // chiqadigan hajm katakdagi suvdan oshmasin
        const out = (fl[k] + fr[k] + fd[k] + fu[k]) * dt;
        const avail = h[k] * A;
        if (out > avail && out > 0) {
          const s = avail / out;
          fl[k] *= s; fr[k] *= s; fd[k] *= s; fu[k] *= s;
        }
      }
    }
    // 2) manbalar
    for (const s of this.sources) {
      const k = s.j * nx + s.i;
      h[k] = Math.max(0, h[k] + (s.q * dt) / A);
    }
    // 3) hajm yangilanishi
    for (let j = 0; j < ny; j++) {
      for (let i = 0; i < nx; i++) {
        const k = j * nx + i;
        let inflow = 0;
        if (i > 0) inflow += fr[k - 1];
        if (i < nx - 1) inflow += fl[k + 1];
        if (j > 0) inflow += fu[k - nx];
        if (j < ny - 1) inflow += fd[k + nx];
        const outflow = fl[k] + fr[k] + fd[k] + fu[k];
        h[k] = Math.max(0, h[k] + ((inflow - outflow) * dt) / A);
      }
    }
    if (this.openDownstream) {
      for (let i = 0; i < nx; i++) for (const j of [0, 1]) { const k = j * nx + i; this.outflowVolume += h[k] * A; h[k] = 0; }
    }
    this.time += dt;
    // toshqin xaritasi statistikasi (har ~2 s sim vaqt)
    this.statAccum += dt;
    if (this.statAccum >= 2) {
      this.statAccum = 0;
      const { hMax, vMax, hvMax, tArrive } = this;
      for (let k = 0; k < h.length; k++) {
        const hk = h[k];
        if (hk > hMax[k]) hMax[k] = hk;
        if (hk > 0.3 && tArrive[k] < 0) tArrive[k] = this.time;
        if (hk > 0.3) {
          // tezlik: katakdan chiqayotgan sof oqim / (h · kesim kengligi); yupqa suvda son artefakti bo'lmasin
          // uchun ≥ 0.3 m va fizik chegara √(2g·h) + 30 m/s (yorilish oqimlari ~20–30 m/s)
          const vx = Math.abs(fr[k] - fl[k]) / (hk * dy), vy = Math.abs(fu[k] - fd[k]) / (hk * dx);
          const v = Math.min(Math.hypot(vx, vy), Math.sqrt(2 * this.g * hk) + 30);
          if (v > vMax[k]) vMax[k] = v;
          if (hk * v > hvMax[k]) hvMax[k] = hk * v;
        }
      }
    }
  }

  /** Sub-qadamlar bilan xavfsiz integratsiya (CFL). */
  advance(seconds: number) {
    let hmax = 0;
    for (let k = 0; k < this.h.length; k++) if (this.h[k] > hmax) hmax = this.h[k];
    const dtMax = 0.35 * Math.min(this.dx, this.dy) / Math.sqrt(this.g * Math.max(hmax, 1));
    let left = seconds;
    let n = 0;
    while (left > 1e-6 && n < 400) {
      const dt = Math.min(dtMax, left);
      this.step(dt);
      left -= dt;
      n++;
    }
  }

  /** Toshqin xaritasi xulosasi: ombor (boshlang'ich) tashqarisida suv bosgan maydon, maks. chuqurlik/tezlik,
   *  xavf sinflari (AIDR 2017 / NZ: h·v < 0.3 — past, < 0.6 — o'rtacha (odam), < 1.2 — yuqori (mashina),
   *  ≥ 1.2 — o'ta yuqori (binolar)), suvning eng uzoq nuqtaga (quyi chegara) yetib kelish vaqti. */
  floodSummary() {
    const A = this.dx * this.dy;
    let flooded = 0, hmax = 0, vmax = 0, hvmax = 0, tFar = -1;
    const cls = [0, 0, 0, 0];
    for (let k = 0; k < this.hMax.length; k++) {
      if (this.initial[k] || this.hMax[k] < 0.3) continue;
      flooded++;
      if (this.hMax[k] > hmax) hmax = this.hMax[k];
      if (this.vMax[k] > vmax) vmax = this.vMax[k];
      const hv = this.hvMax[k];
      if (hv > hvmax) hvmax = hv;
      cls[hv < 0.3 ? 0 : hv < 0.6 ? 1 : hv < 1.2 ? 2 : 3]++;
      const j = Math.floor(k / this.nx);
      if (j <= 2 && this.tArrive[k] >= 0 && (tFar < 0 || this.tArrive[k] < tFar)) tFar = this.tArrive[k];
    }
    return { flooded_area_m2: flooded * A, h_max: hmax, v_max: vmax, hv_max: hvmax, classes_m2: cls.map((c) => c * A), t_arrive_far_s: tFar, t: this.time };
  }

  /** Nuqtadagi (IFC x, y) maks. chuqurlik / kelish vaqti / xavf. */
  floodAt(x: number, y: number) {
    const [i, j] = this.cellAt(x, y);
    const k = j * this.nx + i;
    return { h_max: this.hMax[k], v_max: this.vMax[k], hv_max: this.hvMax[k], t_arrive: this.tArrive[k], initial: !!this.initial[k], ground: this.b[k] };
  }

  /** Umumiy hajm (m³) va maksimal chuqurlik — diagnostika. */
  stats() {
    let vol = 0, hmax = 0, wet = 0;
    for (let k = 0; k < this.h.length; k++) { vol += this.h[k]; if (this.h[k] > hmax) hmax = this.h[k]; if (this.h[k] > 0.02) wet++; }
    return { volume_m3: vol * this.dx * this.dy, h_max: hmax, wet_cells: wet, t: this.time };
  }
}
