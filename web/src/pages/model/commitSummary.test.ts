import { describe, expect, it } from "vitest";
import { commitSummary, defaultCommitMessage } from "./commitSummary";

/** UX-12: commit oynasi — nima o'zgargani va IFC ga kirmaydiganlar. */
describe("commit xulosasi", () => {
  const d = (kind: string, extra: Record<string, unknown> = {}) => ({ kind, name: kind, visible: true, sourceGuid: null, mesh: null, ...extra });
  it("qo'shilgan / o'zgargan / o'chirilgan hisoblanadi, standart izoh aniq", () => {
    const s = commitSummary([d("transformer"), d("wall"), d("mesh", { sourceGuid: "G1", mesh: { vertices: [[0, 0, 0]], faces: [[0, 0, 0]] } }), d("deleted", { sourceGuid: "G2" })]);
    expect(s).toMatchObject({ added: 2, changed: 1, deleted: 1, warnings: [] });
    expect(defaultCommitMessage(s)).toBe("Web 3D: 2 ta qo'shildi, 1 ta o'zgartirildi, 1 ta o'chirildi");
    expect(defaultCommitMessage(commitSummary([]))).toBe("Web 3D: o'zgarish yo'q");
  });
  it("ogohlantirish: yashirin qoralama, geometriyasiz mesh, rasm tagligi IFC ga kirmaydi", () => {
    const s = commitSummary([d("wall", { visible: false, name: "Devor" }), d("mesh", { name: "Bo'sh" })], 2);
    expect(s.warnings).toHaveLength(3);
    expect(s.warnings.join(" ")).toMatch(/yashirilgan.*Devor/);
    expect(s.warnings.join(" ")).toMatch(/geometriya yo'q.*Bo'sh/);
    expect(s.warnings.join(" ")).toMatch(/2 ta rasm tagligi/);
  });
});
