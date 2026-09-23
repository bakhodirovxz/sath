import type { MeshImportInfo, MeshImportResult } from "../../api/client";

/** Mesh/CAD import natijasi (CAD-03/04): ogohlantirishlar — bildirishnoma (xato emas); birlik shubhali — so'rov. */
export interface MeshFollowUp {
  warnings: string[];
  uncertain: boolean;
  info: MeshImportInfo | null;
  /** 3D faylda tashlab ketilgan 2D elementlar (chiziq, matn…) — jimgina yo'qolmaydi */
  skipped2d: number;
}

export function meshFollowUp(r: MeshImportResult): MeshFollowUp {
  const info = r.import_info ?? null;
  const warnings = [...new Set([...(r.warnings ?? []), ...(info?.warnings ?? [])])].filter(Boolean);
  return { warnings, uncertain: !!(r.units_uncertain ?? info?.units_uncertain), info, skipped2d: info?.dxf?.skipped_2d ?? 0 };
}

export const MESH_UNITS: { id: string; label: string }[] = [
  { id: "m", label: "metr" },
  { id: "cm", label: "santimetr" },
  { id: "mm", label: "millimetr" },
  { id: "in", label: "dyuym" },
  { id: "ft", label: "fut" },
];

export function unitLabel(u: string): string {
  return MESH_UNITS.find((x) => x.id === u)?.label ?? u;
}
