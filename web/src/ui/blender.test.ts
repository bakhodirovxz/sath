import { describe, expect, it } from "vitest";
import { pickPie, piePosition, searchCommands } from "./blender";

const items = [
  { label: "Yashirish", hint: "H", group: "Tahrir", run: () => {} },
  { label: "Hammasini ko'rsatish", hint: "Alt+H", group: "Tahrir", run: () => {} },
  { label: "Versiyalar", hint: "yon panel", group: "Fayl", run: () => {} },
];

describe("searchCommands", () => {
  it("bo'sh so'rov — birinchi N ta", () => {
    expect(searchCommands("", items, 2).map((i) => i.label)).toEqual(["Yashirish", "Hammasini ko'rsatish"]);
  });
  it("so'zlar label/hint/group ichida, label boshidagi moslik birinchi", () => {
    expect(searchCommands("h", items).map((i) => i.label)).toEqual(["Hammasini ko'rsatish", "Yashirish"]);
    expect(searchCommands("alt h", items).map((i) => i.label)).toEqual(["Hammasini ko'rsatish"]);
    expect(searchCommands("fayl", items).map((i) => i.label)).toEqual(["Versiyalar"]);
    expect(searchCommands("yo'q", items)).toEqual([]);
  });
});

describe("pickPie", () => {
  it("markazda null, yuqori 0, o'ng 1, past 2, chap 3 (n=4)", () => {
    expect(pickPie(3, -3, 4)).toBeNull();
    expect(pickPie(0, -50, 4)).toBe(0);
    expect(pickPie(50, 0, 4)).toBe(1);
    expect(pickPie(0, 50, 4)).toBe(2);
    expect(pickPie(-50, 0, 4)).toBe(3);
    expect(pickPie(-40, -40, 4)).toBe(0); // 315° → 0 ga yaqinroq (yaxlitlash)
  });
  it("piePosition 0 yuqorida", () => {
    expect(piePosition(0, 4, 80)).toEqual({ x: 0, y: -80 });
    expect(piePosition(1, 4, 80)).toEqual({ x: 80, y: 0 });
  });
});
