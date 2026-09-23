/** 3D sahna ranglari — token fayli (UX-08). Three.js CSS o'zgaruvchilarni o'qimaydi, shuning uchun viewport
 * ranglari shu yerda nomlangan konstantalar sifatida (hex faqat token fayllarida: tokens.ts, tokens.css, shu fayl,
 * ui/print.ts). Rollar: viewport foni/grid (Blender Dark), tanlov, BIM diff, suv/relyef, simulyatsiya kuchlari,
 * jonli bog'lanish holati. */
export const PAL = {
  // Blender Dark viewport
  sceneBg: "#3d3d3d",
  grid: "#4a4a4a",
  wire: "#c9ced6",
  /** Tanlov/ta'kid (Blender: tanlangan — to'q sariq) */
  highlight: "#f5a623",
  highlightFill: "rgba(245, 166, 35, 0.10)",
  /** Kesishma bilan tanlash (o'ngdan chapga) ramkasi */
  crossingFill: "rgba(61, 168, 100, 0.10)",
  noEmissive: "#000000",
  // Navigatsiya gizmosi o'qlari (X qizil, Y yashil, Z ko'k — 3D an'ana)
  axisX: "#e0656a",
  axisY: "#3aa864",
  axisZ: "#3d8ee6",
  // BIM versiya farqi (tokens --diff-* bilan bir xil)
  diffAdd: "#2ecc71",
  diffChange: "#f1c40f",
  diffDel: "#e74c3c",
  /** Kategoriya bo'yicha bo'yash (tur/qavat) — 10 ta ajraladigan rang */
  categorical: ["#4da3ff", "#e0a93a", "#3aa864", "#b46dcc", "#e0656a", "#39b7c9", "#c9ced6", "#f5c542", "#8fd3a9", "#d98ec7"],
  // Suv va relyef
  waterFlat: "#6b8fb3",
  waterSurface: "#2b7fd6",
  waterShallow: "#7cc4ee",
  waterDeep: "#12386b",
  waterFoam: "#d9eef8",
  waterShallow2: "#5fb3e6",
  waterDeep2: "#173f75",
  sedimentShallow: "#a07a4a",
  sedimentDeep: "#6b4a2a",
  waterLine: "#3d8ee6",
  /** Suv tashlagich oqimi (kanva tekstura) */
  fallWater: "rgba(180, 220, 255, 0.55)",
  fallFoam: "rgba(255, 255, 255, 0.85)",
  /** Xavf/issiqlik shkalasi (past → o'ta yuqori): suv bosishi h·v, yoriq ehtimoli */
  heatRamp: ["#f2d94e", "#f0902e", "#d9392b", "#7a1010"],
  // Simulyatsiya kuchlari va yorliqlar
  forceWeight: "#e0e0e0",
  forceSeepage: "#e0656a",
  forceInertia: "#b46dcc",
  labelInk: "#ffffff",
  labelText: "#e8eaee",
  labelWater: "#9cc8ff",
  labelBg: "rgba(20, 22, 26, 0.72)",
  labelBgStrong: "rgba(20, 22, 26, 0.8)",
  hazard: "#c8553d",
  // Jonli bog'lanish (3D egizak): ishlayapti / to'xtagan / ogohlantirish
  running: "#3aa864",
  runningGlow: "#1c5c36",
  idle: "#6a6e76",
  idleGlow: "#222222",
  warn: "#e0a93a",
  warnGlow: "#6b4d12",
  flowLine: "#4fc3f7",
  // Simulyatsiya natijasi 3D da: bajarildi / bajarilmadi / ma'lumot yo'q
  pass: "#3aa864",
  fail: "#d95c5c",
  neutral: "#6b7280",
  // Qoralama (web da qo'shilgan) element turlari — standart material ranglari
  draft: {
    primitive: "#9aa3ad",
    concrete: "#8d8f93",
    penstock: "#6f8fb5",
    turbine: "#3aa6a0",
    building: "#b0a088",
    transformer: "#b98626",
    intake: "#7d9bb5",
    edited: "#c9a86a",
    deleted: "#aa4444",
  },
} as const;

/** Inshoot yuklanishi (%) → 3D rang: 0 — neytral; oshgan sari yashil → sariq → qizil (100 % dan keyin qizil tomon). */
export function utilizationColor(pct: number): string {
  if (pct <= 0) return PAL.neutral;
  return `hsl(${120 - Math.max(0, pct - 100)} ${40 + Math.min(pct, 100) * 0.5}% ${55 - Math.min(pct, 100) * 0.2}%)`;
}
