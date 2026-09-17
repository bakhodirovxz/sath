/* Ikonkalar to'plami — inline SVG (Lucide uslubi: 24×24, chiziq 1.75, yumaloq uchlar).
   Emoji/belgilar o'rniga ishlatiladi: <Icon name="bell" /> — rang matn rangidan (currentColor). */

const PATHS: Record<string, string> = {
  // Umumiy
  bell: "M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9M10.3 21a1.94 1.94 0 0 0 3.4 0",
  "bell-off": "M8.7 3A6 6 0 0 1 18 8a21.3 21.3 0 0 0 .6 5M17 17H3s3-2 3-9a4.7 4.7 0 0 1 .3-1.7M10.3 21a1.94 1.94 0 0 0 3.4 0M2 2l20 20",
  "volume-x": "M11 5 6 9H2v6h4l5 4V5zM22 9l-6 6M16 9l6 6",
  volume: "M11 5 6 9H2v6h4l5 4V5zM15.5 8.5a5 5 0 0 1 0 7M19 5a9 9 0 0 1 0 14",
  "alert-triangle": "M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0zM12 9v4M12 17h.01",
  "alert-circle": "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM12 8v4M12 16h.01",
  info: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM12 16v-4M12 8h.01",
  clock: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM12 6v6l4 2",
  history: "M3 12a9 9 0 1 0 3-6.7L3 8M3 3v5h5M12 7v5l4 2",
  camera: "M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-2.5-3zM12 17a4 4 0 1 0 0-8 4 4 0 0 0 0 8z",
  tag: "M12.6 2.6 21.4 11.4a2 2 0 0 1 0 2.8l-7.2 7.2a2 2 0 0 1-2.8 0L2.6 12.6A2 2 0 0 1 2 11.2V4a2 2 0 0 1 2-2h7.2c.5 0 1 .2 1.4.6zM7 7h.01",
  x: "M18 6 6 18M6 6l12 12",
  check: "M20 6 9 17l-5-5",
  "check-circle": "M22 11.1V12a10 10 0 1 1-5.9-9.1M22 4 12 14l-3-3",
  plus: "M12 5v14M5 12h14",
  minus: "M5 12h14",
  play: "M6 4l14 8-14 8z",
  pause: "M6 4h4v16H6zM14 4h4v16h-4z",
  "skip-back": "M19 20 9 12l10-8zM5 19V5",
  refresh: "M21 12a9 9 0 1 1-2.6-6.4L21 8M21 3v5h-5",
  map: "M1 6v16l7-4 8 4 7-4V2l-7 4-8-4-7 4zM8 2v16M16 6v16",
  printer: "M6 9V2h12v7M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2M6 14h12v8H6z",
  "external-link": "M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6M15 3h6v6M10 14 21 3",
  download: "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3",
  upload: "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12",
  search: "M21 21l-4.3-4.3M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14z",
  settings: "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z",
  "chevron-right": "m9 18 6-6-6-6",
  "chevron-down": "m6 9 6 6 6-6",
  "chevron-left": "m15 18-6-6 6-6",
  "chevron-up": "m18 15-6-6-6 6",
  "arrow-left": "M19 12H5M12 19l-7-7 7-7",
  "arrow-right": "M5 12h14M12 5l7 7-7 7",
  "arrow-up": "M12 19V5M5 12l7-7 7 7",
  "arrow-down": "M12 5v14M19 12l-7 7-7-7",
  terminal: "m4 17 6-6-6-6M12 19h8",
  // 3D viewport / asboblar
  cursor: "M4 4l7.1 16.9 2.4-7.4 7.4-2.4z",
  ruler: "M21.3 8.7 8.7 21.3a2 2 0 0 1-2.8 0L2.7 18a2 2 0 0 1 0-2.8L15.3 2.7a2 2 0 0 1 2.8 0l3.2 3.2a2 2 0 0 1 0 2.8zM14.5 6.5l1.5 1.5M11.5 9.5l1.5 1.5M8.5 12.5l1.5 1.5M5.5 15.5 7 17",
  scissors: "M6 9a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM6 21a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM20 4 8.1 15.9M14.5 14.5 20 20M8.1 8.1 12 12",
  "section-box": "M3 3h18v18H3zM3 12h18M12 3v18",
  maximize: "M8 3H5a2 2 0 0 0-2 2v3M21 8V5a2 2 0 0 0-2-2h-3M3 16v3a2 2 0 0 0 2 2h3M16 21h3a2 2 0 0 0 2-2v-3",
  "eye-off": "M9.9 4.2A10 10 0 0 1 12 4c7 0 10 8 10 8a13.2 13.2 0 0 1-1.7 2.5M6.6 6.6A13.5 13.5 0 0 0 2 12s3 8 10 8a9.7 9.7 0 0 0 5.4-1.6M14.1 14.1a3 3 0 1 1-4.2-4.2M2 2l20 20",
  eye: "M2 12s3-8 10-8 10 8 10 8-3 8-10 8-10-8-10-8zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z",
  "eye-all": "M2 12s3-8 10-8 10 8 10 8-3 8-10 8-10-8-10-8zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19 3l2 2M3 3l2 2",
  isolate: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8z",
  flag: "M4 22V4a1 1 0 0 1 1-1h11l1 2h4v10h-6l-1-2H4",
  trash: "M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6M10 11v6M14 11v6",
  // Shading (Blender viewport shading tugmalari)
  "shade-solid": "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z",
  "shade-wire": "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 3c-3 3-3 15 0 18M12 3c3 3 3 15 0 18M3 12h18",
  "shade-xray": "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 3v18M12 12l6.4-6.4M12 12l6.4 6.4",
  "shade-rendered": "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM9 8.5a3.5 3.5 0 0 1 3.5-3.5",
  grid: "M3 3h18v18H3zM3 9h18M3 15h18M9 3v18M15 3v18",
  layers: "m12 2 10 5-10 5L2 7zM2 12l10 5 10-5M2 17l10 5 10-5",
  "git-branch": "M6 3v12M18 9a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM6 21a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM18 9a9 9 0 0 1-9 9",
  waves: "M2 6c.6.5 1.2 1 2.5 1C7 7 7 5 9.5 5c2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1M2 12c.6.5 1.2 1 2.5 1 2.5 0 2.5-2 5-2 2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1M2 18c.6.5 1.2 1 2.5 1 2.5 0 2.5-2 5-2 2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1",
  activity: "M22 12h-4l-3 9L9 3l-3 9H2",
  "check-square": "m9 11 3 3L22 4M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11",
  box: "M21 16V8a2 2 0 0 0-1-1.7l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.7l7 4a2 2 0 0 0 2 0l7-4a2 2 0 0 0 1-1.7zM3.3 7 12 12l8.7-5M12 22V12",
  cylinder: "M12 8c5 0 9-1.3 9-3s-4-3-9-3-9 1.3-9 3 4 3 9 3zM3 5v14c0 1.7 4 3 9 3s9-1.3 9-3V5",
  sphere: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM3 12a9 3.5 0 0 0 18 0",
  plane: "M3 17 12 7l9 10z",
  cone: "M12 3 4 19h16zM4 19a8 2 0 0 0 16 0",
  move: "m5 9-3 3 3 3M9 5l3-3 3 3M15 19l-3 3-3-3M19 9l3 3-3 3M2 12h20M12 2v20",
  rotate: "M21 12a9 9 0 1 1-9-9c2.5 0 4.8 1 6.4 2.6L21 8M21 3v5h-5",
  scale: "M21 3 14 10M21 3h-6M21 3v6M3 21l7-7M3 21h6M3 21v-6",
  dam: "M3 21h18M6 21V8l4-5v18M10 3h4l4 5v13M14 9h4M14 13h4M14 17h4",
  turbine: "M12 12m-3 0a3 3 0 1 0 6 0a3 3 0 1 0-6 0M12 9V3M12 15v6M9 12H3M15 12h6M14.1 9.9 18.4 5.6M9.9 14.1l-4.3 4.3M9.9 9.9 5.6 5.6M14.1 14.1l4.3 4.3",
  pipe: "M3 8h12a4 4 0 0 1 4 4v8M3 8V4M3 8v4M21 20h-4",
  zap: "M13 2 3 14h9l-1 8 10-12h-9z",
  house: "m3 10 9-7 9 7v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2zM9 22V12h6v10",
  mountain: "m8 3 4 8 5-5 5 15H2zM4.1 16.5 8 11",
  earthquake: "M2 12h3l2-6 3 12 3-14 3 16 2-8h4",
  flood: "M2 4c2 0 2 2 4 2s2-2 4-2 2 2 4 2 2-2 4-2 2 2 4 2M2 12c2 0 2 2 4 2s2-2 4-2 2 2 4 2 2-2 4-2 2 2 4 2M2 20c2 0 2 2 4 2s2-2 4-2 2 2 4 2 2-2 4-2 2 2 4 2",
  gauge: "m12 14 4-4M3.3 17a10 10 0 1 1 17.4 0",
  droplet: "M12 22a7 7 0 0 0 7-7c0-2-1-3.9-3-5.5s-3.5-4-4-6.5c-.5 2.5-2 4.9-4 6.5S5 13 5 15a7 7 0 0 0 7 7z",
  "flask": "M9 3h6M10 3v6.5L4.5 19a2 2 0 0 0 1.7 3h11.6a2 2 0 0 0 1.7-3L14 9.5V3M7 15h10",
  code: "m16 18 6-6-6-6M8 6l-6 6 6 6",
  sliders: "M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6",
  "file-text": "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6M16 13H8M16 17H8M10 9H8",
  list: "M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01",
  user: "M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z",
  mail: "M4 4h16a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2zM22 6l-10 7L2 6",
  lock: "M19 11H5a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7a2 2 0 0 0-2-2zM7 11V7a5 5 0 0 1 10 0v4",
  wrench: "M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.8-3.8a6 6 0 0 1-7.9 7.9l-7 7a2.1 2.1 0 0 1-3-3l7-7a6 6 0 0 1 7.9-7.9z",
  send: "m22 2-7 20-4-9-9-4zM22 2 11 13",
  "book-open": "M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2zM22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z",
  "help-circle": "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3M12 17h.01",
  "log-out": "M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9",
  target: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM12 18a6 6 0 1 0 0-12 6 6 0 0 0 0 12zM12 14a2 2 0 1 0 0-4 2 2 0 0 0 0 4z",
  square: "M3 3h18v18H3z",
  "square-check": "M3 3h18v18H3zM8 12l3 3 5-6",
  dot: "M12 12m-3 0a3 3 0 1 0 6 0a3 3 0 1 0-6 0",
  circle: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z",
  "circle-dot": "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 12m-2 0a2 2 0 1 0 4 0a2 2 0 1 0-4 0",
  "circle-off": "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM5.6 5.6l12.8 12.8",
  compass: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM16.2 7.8l-2.1 6.3-6.3 2.1 2.1-6.3z",
  crosshair: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM22 12h-4M6 12H2M12 6V2M12 22v-4",
  image: "M3 5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2zM8.5 10a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3M21 15l-5-5L5 21",
  "bar-chart": "M12 20V10M18 20V4M6 20v-4",
  "trending-up": "m22 7-8.5 8.5-5-5L2 17M16 7h6v6",
  thermometer: "M14 14.8V3.5a2.5 2.5 0 0 0-5 0v11.3a4 4 0 1 0 5 0z",
  power: "M18.4 6.6a9 9 0 1 1-12.8 0M12 2v10",
  "power-off": "M18.4 6.6a9 9 0 1 1-12.8 0M12 2v10M2 2l20 20",
  wifi: "M5 12.5a11 11 0 0 1 14 0M8.5 16a6 6 0 0 1 7 0M2 8.8a16 16 0 0 1 20 0M12 20h.01",
  "wifi-off": "M2 2l20 20M8.5 16a6 6 0 0 1 7 0M5 12.5a11 11 0 0 1 4.5-2.3M12 20h.01M16.7 11.5a11 11 0 0 1 2.3 1M2 8.8a16 16 0 0 1 5.4-2.7M11.4 4.1a16 16 0 0 1 10.6 4.7",
  external: "M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6M15 3h6v6M10 14 21 3",
  edit: "M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7M18.5 2.5a2.1 2.1 0 0 1 3 3L12 15l-4 1 1-4z",
  save: "M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2zM17 21v-8H7v8M7 3v5h8",
  copy: "M8 8h12v12H8zM16 8V4H4v12h4",
  link: "M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7.1-7.1l-1.7 1.7M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7.1 7.1l1.7-1.7",
  filter: "M22 3H2l8 9.5V19l4 2v-8.5z",
  calendar: "M3 6a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2zM16 2v4M8 2v4M3 10h18",
  sun: "M12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4",
  shield: "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z",
  "shield-alert": "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10zM12 8v4M12 16h.01",
  layout: "M3 3h18v18H3zM3 9h18M9 21V9",
  monitor: "M2 3h20v14H2zM8 21h8M12 17v4",
  timer: "M10 2h4M12 14l3-3M12 22a8 8 0 1 0 0-16 8 8 0 0 0 0 16z",
  puzzle: "M19.4 13.9a1.2 1.2 0 0 0-.9-.3 1.2 1.2 0 0 1-1-.4 1.2 1.2 0 0 1-.3-.9c0-.4.1-.8.4-1a1.2 1.2 0 0 0 .3-.9 1.2 1.2 0 0 0-.4-.9L15 7a1 1 0 0 0-1.4 0l-1.1 1.1a1.2 1.2 0 0 1-1.7 0 1.2 1.2 0 0 1 0-1.7l1.1-1.1a1 1 0 0 0 0-1.4L9.4 1.4a1 1 0 0 0-1.4 0L5.5 3.9a1 1 0 0 0 0 1.4l1 1a1.2 1.2 0 0 1 0 1.7 1.2 1.2 0 0 1-1.7 0l-1-1a1 1 0 0 0-1.4 0L.4 9a1 1 0 0 0 0 1.4l2.5 2.5",
};

export type IconName = keyof typeof PATHS | string;

interface Props {
  name: IconName;
  size?: number;
  className?: string;
  title?: string;
  strokeWidth?: number;
  style?: React.CSSProperties;
}

/** Inline SVG ikonka; nomi PATHS ro'yxatidan. Noma'lum nom — bo'sh doira (xatoni ko'rish oson bo'lishi uchun). */
export default function Icon({ name, size = 16, className, title, strokeWidth = 1.75, style }: Props) {
  const d = PATHS[name] ?? PATHS.circle;
  return (
    <svg className={`ico${className ? ` ${className}` : ""}`} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" aria-hidden={title ? undefined : true} role={title ? "img" : undefined} style={style}>
      {title && <title>{title}</title>}
      <path d={d} />
    </svg>
  );
}

export const ICON_NAMES = Object.keys(PATHS);
