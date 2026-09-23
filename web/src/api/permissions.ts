import type { Role } from "./client";

/** Ruxsatlar (SCADA-01, server `auth/deps.py` ROLE_PERMISSIONS bilan bir xil): UI tugmalarini faqat ruxsati
 * borlarga ko'rsatish uchun — haqiqiy tekshiruv serverda. Loyihalash va ekspluatatsiya kesishmaydi:
 * buyruq — faqat dispetcher va smena boshlig'i; sensor sozlash va simulyatsiya — muhandis/tasdiqlovchi.
 * `scada.ack` (kvitlash, shelving, jurnal, smena) server tomonda hozircha eski ierarxiya: operator+ (muhandis,
 * tasdiqlovchi ham). Administrator (is_admin) loyiha roli bo'lmasa — hech biri. */
export type Permission =
  | "scada.ack"
  | "scada.command"
  | "scada.command.approve"
  | "scada.interlock.override"
  | "scada.manual_entry"
  | "sensor.configure"
  | "sensor.oos"
  | "sim.run"
  | "gateway.keys";

const MATRIX: Record<Permission, readonly Role[]> = {
  "scada.ack": ["operator", "shift_supervisor", "engineer", "approver"],
  "scada.command": ["operator", "shift_supervisor"],
  "scada.command.approve": ["shift_supervisor"],
  "scada.interlock.override": ["shift_supervisor"],
  "scada.manual_entry": ["shift_supervisor"],
  "sensor.configure": ["engineer", "approver"],
  "sensor.oos": ["engineer", "approver"],
  "sim.run": ["engineer", "approver"],
  "gateway.keys": ["approver"],
};

export function can(role: Role | null | undefined, perm: Permission): boolean {
  return !!role && MATRIX[perm].includes(role);
}
