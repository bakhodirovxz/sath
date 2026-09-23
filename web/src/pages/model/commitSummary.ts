import type { Draft } from "../../viewer/drafts";

/** Commit oynasi (UX-12): nima o'zgargani — qo'shilgan / o'zgargan / o'chirilgan elementlar soni va IFC ga
 * kirmaydigan narsalar haqida ogohlantirish (CAD-01: jimgina yo'qolmasin). */
export interface CommitSummary {
  added: number;
  changed: number;
  deleted: number;
  warnings: string[];
}

export function commitSummary(drafts: readonly Pick<Draft, "kind" | "sourceGuid" | "visible" | "mesh" | "name">[], underlays = 0): CommitSummary {
  let added = 0, changed = 0, deleted = 0;
  const warnings: string[] = [];
  const hidden: string[] = [];
  const emptyMesh: string[] = [];
  for (const d of drafts) {
    if (d.kind === "deleted") { deleted++; continue; }
    if (d.sourceGuid) changed++; else added++;
    if (!d.visible) hidden.push(d.name || d.kind);
    if (d.kind === "mesh" && (!d.mesh || !d.mesh.faces?.length)) emptyMesh.push(d.name || "mesh");
  }
  if (hidden.length) warnings.push(`${hidden.length} ta yashirilgan qoralama ham versiyaga kiradi: ${hidden.slice(0, 3).join(", ")}${hidden.length > 3 ? "…" : ""}`);
  if (emptyMesh.length) warnings.push(`${emptyMesh.length} ta mesh qoralamada geometriya yo'q — IFC ga kirmaydi: ${emptyMesh.slice(0, 3).join(", ")}`);
  if (underlays > 0) warnings.push(`${underlays} ta rasm tagligi (foto/chizma) IFC ga kirmaydi — faqat 3D ko'rinishda qoladi`);
  return { added, changed, deleted, warnings };
}

export function defaultCommitMessage(s: CommitSummary): string {
  const parts = [s.added && `${s.added} ta qo'shildi`, s.changed && `${s.changed} ta o'zgartirildi`, s.deleted && `${s.deleted} ta o'chirildi`].filter(Boolean);
  return `Web 3D: ${parts.length ? parts.join(", ") : "o'zgarish yo'q"}`;
}
