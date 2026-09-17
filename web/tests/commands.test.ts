import { describe, expect, it } from "vitest";
import { COMMANDS, CommandHistory, parseCommand, suggest } from "../src/viewer/commands";

describe("parseCommand", () => {
  it("bo'sh kiritish null", () => {
    expect(parseCommand("")).toBeNull();
    expect(parseCommand("   ")).toBeNull();
  });
  it("nom va alias, katta-kichik harf farqsiz", () => {
    expect(parseCommand("zoom e")).toEqual({ name: "ZOOM", args: ["e"], raw: "zoom e" });
    expect(parseCommand("Z")).toMatchObject({ name: "ZOOM", args: [] });
    expect(parseCommand("sec")).toMatchObject({ name: "SECTION" });
    expect(parseCommand("di")).toMatchObject({ name: "MEASURE" });
  });
  it("noma'lum buyruq", () => {
    expect(parseCommand("foo bar")).toMatchObject({ name: "UNKNOWN", args: ["foo", "bar"] });
  });
  it("argumentlar bo'shliqlar bo'yicha ajratiladi", () => {
    expect(parseCommand("select  1abc   2def ")).toMatchObject({ name: "SELECT", args: ["1abc", "2def"] });
  });
  it("aliaslar takrorlanmaydi", () => {
    const all = COMMANDS.flatMap((c) => [c.name, ...c.aliases]);
    expect(new Set(all).size).toBe(all.length);
  });
});

describe("suggest", () => {
  it("prefiks bo'yicha, takrorsiz", () => {
    const names = suggest("s").map((c) => c.name);
    expect(names).toContain("SECTION");
    expect(names).toContain("SELECT");
    expect(names).toContain("SHOWALL");
    expect(new Set(names).size).toBe(names.length);
  });
  it("bo'sh prefiks → bo'sh", () => {
    expect(suggest("")).toEqual([]);
  });
});

describe("CommandHistory", () => {
  it("yuqoriga/pastga navigatsiya", () => {
    const h = new CommandHistory();
    h.push("ZOOM E");
    h.push("HIDE");
    expect(h.prev()).toBe("HIDE");
    expect(h.prev()).toBe("ZOOM E");
    expect(h.prev()).toBe("ZOOM E");
    expect(h.next()).toBe("HIDE");
    expect(h.next()).toBeNull();
    expect(h.last).toBe("HIDE");
  });
  it("ketma-ket bir xil buyruq takrorlanmaydi", () => {
    const h = new CommandHistory();
    h.push("HIDE");
    h.push("HIDE");
    expect(h.prev()).toBe("HIDE");
    expect(h.prev()).toBe("HIDE");
    h.push("");
    expect(h.last).toBe("HIDE");
  });
});
