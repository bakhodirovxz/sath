// Server API bilan ishlash. Token localStorage da saqlanadi.

export type Role = "viewer" | "operator" | "engineer" | "approver";
export type VersionState = "wip" | "shared" | "published" | "archived";
export type CRStatus = "open" | "changes_requested" | "approved" | "rejected" | "merged";
export type IssueStatus = "open" | "in_progress" | "resolved" | "closed";

export interface User {
  id: number;
  username: string;
  full_name: string;
  email?: string;
  is_admin: boolean;
  is_active: boolean;
}
export interface Project {
  id: number;
  name: string;
  description: string;
  location: string;
  my_role: Role | null;
  model_count: number;
}
export interface Member {
  user_id: number;
  username: string;
  full_name: string;
  role: Role;
}
export interface Model {
  id: number;
  project_id: number;
  name: string;
  description: string;
  version_count: number;
  safety?: { score: number; counts: { ok: number; warn: number; fail: number; skip: number }; verdict: string; version_id: number | null; at: string; fails: string[] } | null;
  latest_version_id: number | null;
  published_version_id: number | null;
}
export interface Version {
  id: number;
  model_id: number;
  number: number;
  parent_id: number | null;
  author_id: number;
  author_username: string;
  message: string;
  tag?: string;
  file_sha256: string;
  file_name: string;
  file_size: number;
  state: VersionState;
  meta: {
    schema?: string;
    project_name?: string | null;
    element_count?: number;
    type_counts?: Record<string, number>;
    storeys?: { guid: string; name: string; elevation: number | null }[];
  };
  created_at: string;
}
export interface Review {
  id: number;
  reviewer_id: number;
  reviewer_username: string;
  decision: "approve" | "request_changes" | "comment";
  comment: string;
  created_at: string;
}
export interface ChangeRequest {
  id: number;
  model_id: number;
  version_id: number;
  version_number: number;
  author_id: number;
  author_username: string;
  title: string;
  description: string;
  status: CRStatus;
  created_at: string;
  closed_at: string | null;
  reviews: Review[];
}
export interface DiffItem {
  guid: string;
  type: string;
  name: string;
  changes?: string[];
}
export interface Diff {
  from_version_id: number;
  to_version_id: number;
  added: DiffItem[];
  deleted: DiffItem[];
  changed: DiffItem[];
  summary: { added: number; deleted: number; changed: number };
}
export interface Viewpoint {
  // space: "ifc" — IFC koordinatalari (metr, Z yuqoriga); yo'q bo'lsa eski three fazosi
  camera?: { space?: "ifc" | "freecad"; position: number[]; target: number[]; projection?: string };
  selected_guids?: string[];
  section?: { normal: number[]; origin: number[] }[];
}
export interface SavedView { id: number; name: string; author_username: string; viewpoint: Viewpoint; created_at: string }
export interface IssueComment {
  id: number;
  author_id: number;
  author_username: string;
  body: string;
  viewpoint: Viewpoint | null;
  created_at: string;
}
export interface Issue {
  id: number;
  model_id: number;
  version_id: number | null;
  change_request_id: number | null;
  author_id: number;
  author_username: string;
  assignee_id: number | null;
  assignee_username: string | null;
  title: string;
  description: string;
  status: IssueStatus;
  priority: "low" | "normal" | "high" | "critical";
  viewpoint: Viewpoint;
  created_at: string;
  updated_at: string;
  comment_count: number;
  comments: IssueComment[];
}

export type SimStatus = "queued" | "running" | "done" | "failed";
/** Simulyatsiya katalogi (server: ges_sim.catalog) */
export interface SimField { key: string; label: string; unit: string; type: "number" | "int" | "bool" | "select" | "text" | "series"; default: unknown; min: number | null; max: number | null; step: number | null; options: [string, string][]; group: string; hint: string; live: string; model: string; advanced: boolean }
export interface SimKind { id: string; title: string; description: string; group: string; icon: string; formulas: string[]; viz: Record<string, string | null>; outputs: { key: string; label: string; unit: string }[]; fields: SimField[]; custom_ui: boolean }
export interface SafetyRow { id: string; title: string; kind: string; why: string; status: "ok" | "warn" | "fail" | "skip"; message: string; metrics: Record<string, unknown>; job_id: number | null }
export interface SafetyCheck { rows: SafetyRow[]; score: number; counts: { ok: number; warn: number; fail: number; skip: number }; verdict: string; version_id: number | null }
export interface SimCatalog { kinds: SimKind[]; groups: Record<string, string>; site_fields: SimField[] }
export type GenericParams = Record<string, unknown>;
export interface ProneSpot { where: string; why: string; severity: string }
export interface DamTypeRow { type: string; name: string; score: number; verdict: string; reasons: string[]; good: string[]; bad: string[]; cracks: string[] }
export interface GenericResult { series: Record<string, (number | string)[]>; summary: Record<string, unknown>; profile?: Record<string, unknown>; field?: { nx: number; ny: number; values: number[]; legend?: string }; downstream?: Record<string, number[]>; breach?: Record<string, unknown> | null; seismic_scan?: Record<string, number[]>; forces?: Record<string, unknown>[]; structures?: Record<string, unknown>[]; prone?: ProneSpot[]; ranking?: DamTypeRow[]; thermal?: Record<string, unknown>; units?: Record<string, unknown>[] }
export interface MaterialsCatalog { concrete: { id: string; name: string; Rb: number; Rbt: number; Rbn: number; Rbtn: number; E: number; gamma: number; use: string }[]; cement: { id: string; name: string; q: number; note: string }[]; steel: { id: string; name: string; yield: number; ult: number; E: number; note: string }[]; soil: { id: string; name: string; gamma: number; phi: number; c: number; k: number; note: string }[]; zones: { zone: string; concrete: string; why: string }[] }
export interface SimPrefill { site: GenericParams; model: GenericParams; live: GenericParams; site_filled: boolean }
export interface SiteRisk { name: string; value: number; unit: string; ok: boolean; note: string }
export interface SiteProfile { values: GenericParams; filled: boolean; risks: SiteRisk[] }
export interface CustomTemplate { name?: string; description?: string; inputs: { key: string; label?: string; unit?: string; default?: number; min?: number; max?: number }[]; steps: number; dt: number; init: Record<string, string>; step: { target: string; expr: string }[]; outputs: string[]; summary: Record<string, string>; checks: { expr: string; message: string }[] }
export interface DraftRow { id: number; model_id: number; author_id: number; author_username: string; kind: string; name: string; ifc_class: string; params: Record<string, number | string>; transform: Record<string, number>; psets: Record<string, Record<string, unknown>>; has_mesh: boolean; source_guid?: string | null; mesh?: { vertices: number[][]; faces: number[][] } | null; created_at: string; updated_at: string }
export interface DraftBody { kind: string; name: string; ifc_class: string; params: Record<string, number | string>; transform: Record<string, number>; psets: Record<string, Record<string, unknown>>; mesh: { vertices: number[][]; faces: number[][] } | Record<string, never>; source_guid?: string | null }
export interface SimTemplate { id: number; project_id: number; author_id: number; author_username: string; name: string; description: string; template: CustomTemplate; created_at: string; updated_at: string }
export interface SimJob {
  id: number;
  model_id: number;
  version_id: number | null;
  author_id: number;
  author_username: string;
  kind: string;
  name: string;
  status: SimStatus;
  progress: number;
  summary: Record<string, number> & { ok?: boolean; verdict?: string };
  error: string;
  created_at: string;
  finished_at: string | null;
  params: (SimParams & Partial<CfdParams> & GenericParams) | null;
}
export interface SimUnit {
  name: string;
  type: string;
  rated_power_mw: number;
  rated_head_m: number;
  rated_flow_m3s: number;
  max_efficiency: number;
  guid?: string;
}
export interface SimParams {
  dt_hours: number;
  start_date?: string;
  inflow_m3s: number[] | { constant: number; steps: number };
  reservoir: {
    curve: { elevations_m: number[]; volumes_mcm: number[] };
    dead_level_m: number;
    normal_level_m: number;
    max_level_m?: number | null;
    initial_level_m?: number;
    tailwater_m?: number;
    other_outflow_m3s?: number;
    evaporation_mm_day?: number;
    spillway?: { crest_m: number; width_m: number; coefficient: number; gate_opening: number } | null;
  };
  penstock?: { length_m: number; diameter_m: number; roughness_mm: number; minor_loss_k: number; per_unit: boolean } | null;
  units: SimUnit[];
  operation: { mode: "max_power" | "run_of_river" | "constant_flow" | "target_level" | "target_power"; target_level_m?: number; flow_m3s?: number; power_mw?: number };
  model_zero_elevation_m?: number; // IFC z=0 ga mos absolyut belgi (3D da suv sathi uchun)
}
export interface SimResult {
  series: { t: (string | number)[]; inflow: number[]; level: number[]; volume_mcm: number[]; turbine_flow: number[]; spill: number[]; power_mw: number[]; head_gross: number[]; head_net: number[]; units_on: number[]; curtailed: number[] };
  units: { name: string; type: string; power_mw: number[] }[];
  summary: Record<string, number>;
}
export interface CfdParams {
  kind: "penstock" | "spillway" | "geometry";
  // geometry (model elementlari atrofida oqim)
  element_guids?: string[]; velocity_ms?: number; flow_axis?: "x" | "y"; refinement?: number; bbox?: number[][]; stl_elements?: { guid: string; name: string; type: string }[]; stl_triangles?: number;
  // penstock
  length_m?: number; diameter_m?: number; flow_m3s?: number; roughness_mm?: number; max_iterations?: number;
  // spillway
  crest_height_m?: number; head_m?: number; crest_length_m?: number; upstream_m?: number; downstream_m?: number; unit_discharge_m2s?: number | null; end_time_s?: number;
  resolution?: number;
  element_guid?: string | null; // 3D da natijani qo'yish uchun
}
export interface CfdPoint { x: number; y: number; p?: number; u: number; alpha?: number }
export interface CfdResult {
  kind: "penstock" | "spillway" | "geometry";
  inputs: Record<string, number | string | number[]>;
  summary: Record<string, number | null | number[]>;
  body_pressure?: { points: { x: number; y: number; z: number; p: number }[] };
  plane: CfdPoint[];
  axis?: { x: number[]; head_m: number[]; u: number[] };
  radial?: { r: number[]; u: number[] };
  profile?: { x: number; y: number }[];
}
export interface Underlay { id: number; model_id: number; name: string; x: number; y: number; z: number; width_m: number; height_m: number; rotation_deg: number; opacity: number; vertical: boolean; visible: boolean; url: string }

export interface GesParams {
  units: (SimUnit & { guid: string })[];
  penstocks: { guid: string; name: string; length_m: number; diameter_m: number; roughness_mm: number; material: string }[];
  spillways: { guid: string; name: string; crest_m: number; width_m: number; coefficient: number; gates: number }[];
  dams: { guid: string; name: string; type: string; height_m: number | null; length_m: number | null; crest_elevation_m: number | null }[];
}

export type AlarmState = "ok" | "low" | "high" | "stale";
export type SensorKind = "level" | "flow" | "power" | "pressure" | "temperature" | "vibration" | "status" | "position" | "value";
export type SensorProtocol = "http" | "csv" | "mqtt" | "opcua" | "modbus" | "twin";
export interface Sensor {
  id: number;
  project_id: number;
  model_id: number | null;
  key: string;
  name: string;
  kind: SensorKind;
  unit: string;
  element_guid: string | null;
  protocol: SensorProtocol;
  address: Record<string, unknown>;
  low_alarm: number | null;
  high_alarm: number | null;
  stale_after_s: number;
  enabled: boolean;
  last_value: number | null;
  last_ts: string | null;
  alarm: AlarmState;
  priority: "low" | "medium" | "high" | "critical";
  writable: boolean;
}
export interface SensorIn {
  key: string;
  name: string;
  kind: SensorKind;
  unit: string;
  model_id?: number | null;
  element_guid?: string | null;
  protocol: SensorProtocol;
  address: Record<string, unknown>;
  low_alarm: number | null;
  high_alarm: number | null;
  stale_after_s: number;
  enabled: boolean;
  priority?: "low" | "medium" | "high" | "critical";
  writable?: boolean;
}
export type CommandStatus = "pending" | "sent" | "acked" | "failed" | "cancelled";
export interface Command { id: number; sensor_id: number; sensor_key: string; sensor_name: string; unit: string; value: number; note: string; status: CommandStatus; result: string; author_username: string; created_at: string; updated_at: string }
export interface JournalEntry { id: number; kind: "note" | "shift_start" | "shift_end" | "event"; text: string; author_username: string; created_at: string }
export interface TwinUnit { sensor_id: number; name: string; model_unit: string; running: boolean; measured_mw: number | null; expected_mw: number; deviation_pct: number | null; efficiency: number | null; expected_efficiency: number | null; flow_m3s: number | null; head_net_m: number }
export interface TwinState { status: "ok" | "insufficient"; reason?: string; has_model?: boolean; version_id?: number; head_gross_m: number | null; flow_total_m3s?: number | null; units: TwinUnit[]; expected_total_mw?: number; measured_total_mw?: number; safety?: SiteRisk[]; what_if?: boolean }
export interface HealthSensorBlock { sensor_id: number; name: string; unit: string; value: number | null; stale: boolean; slope_per_day: number | null; baseline_mean: number | null; baseline_std: number | null; z: number | null; anomaly: boolean; points: number; zone?: string; zone_note?: string; days_to_c?: number | null; days_to_d?: number | null; warn?: number; alarm?: number; days_to_alarm?: number | null }
export interface AssetHealth { asset_id: number; name: string; element_guid: string | null; score: number; level: string; vibration: HealthSensorBlock | null; bearing_temp: HealthSensorBlock | null; efficiency: { measured: number | null; expected: number | null; deviation_pct: number | null; trend_pct_per_month: number | null; running: boolean } | null; cavitation: { sigma_plant: number; sigma_critical: number; ns: number; suction_head_m: number; margin: number } | null; electrical?: { load_factor: number; top_oil_c: number; hot_spot_c: number; aging_rate: number } | null; problems: string[]; tips: string[]; machine_group: number }
export interface HealthReport { plant_score: number | null; assets: AssetHealth[]; twin_status?: string }
export interface DispatchResult { status: string; reason?: string; target_mw?: number; head_gross_m?: number; units: { name: string; power_mw: number; flow_m3s: number; efficiency: number | null; head_net_m: number; load_pct: number }[]; total_flow_m3s?: number; current_flow_m3s?: number | null; saving_pct?: number | null; units_on?: number }
export type WorkOrderStatus = "open" | "in_progress" | "done" | "cancelled";
export interface WorkOrder { id: number; project_id: number; asset_id: number | null; asset_name: string | null; title: string; description: string; priority: string; source: string; status: WorkOrderStatus; author_username: string; assignee_id: number | null; assignee_username: string | null; due_at: string | null; started_at: string | null; closed_at: string | null; downtime_hours: number; cost: number; resolution: string; created_at: string; updated_at: string; overdue: boolean }
export interface WorkOrderKpi { open: number; in_progress: number; overdue: number; done_90d: number; mttr_hours: number | null; mtbf_hours: number | null; downtime_90d_hours: number; cost_90d: number; by_priority: Record<string, number> }
export interface FloodForecast { status: string; live: Record<string, number>; site_filled: boolean; rain: Record<string, unknown>; summary: Record<string, number | boolean | string | null>; series: Record<string, number[]>; recommendation: { action: string; text: string; safe_level_m?: number | null; lower_by_m?: number | null; hours_to_overtop?: number | null } | null }
export interface SparePart { id: number; project_id: number; name: string; code: string; unit: string; qty: number; min_qty: number; location: string; unit_cost: number; asset_id: number | null; asset_name: string | null; notes: string; low: boolean; updated_at: string }
export interface PartMovement { id: number; part_id: number; part_name: string; work_order_id: number | null; qty: number; note: string; author_username: string; created_at: string }
export interface AssetState { id: number; name: string; element_guid: string | null; power_sensor_id: number | null; running: boolean; run_hours_total: number; starts_total: number; run_hours_30d: number; energy_30d_mwh: number; availability_30d: number; maintenance_interval_hours: number | null; last_maintenance_at: string | null; hours_since_maintenance: number; hours_to_maintenance: number | null; status: "ok" | "due" | "overdue"; notes: string }
export interface Snapshot { at: string; sensors: LiveReading[] }
export interface ReadingPoint { ts: string; v: number; min: number; max: number }
export interface AlarmEvent {
  id: number;
  sensor_id: number;
  sensor_name: string;
  sensor_key: string;
  unit: string;
  priority?: string;
  state: AlarmState;
  value: number | null;
  started_at: string;
  ended_at: string | null;
  acked_by: number | null;
  acked_at: string | null;
  comment: string;
}
export interface MimicSlot { slot: string; label: string; kind: SensorKind }
export interface Dashboard {
  sensors: Sensor[];
  units: { sensor_id: number; name: string; running: boolean; power: number | null }[];
  mimic: Record<string, number>;
  slots: MimicSlot[];
  tiles: number[];
  active_alarms: number;
  energy_24h_mwh: number | null;
  alarms_24h: { count: number; by_state: Record<string, number>; unacked: number };
  live_clients: number;
}
export interface ReportRow { sensor_id: number; key: string; name: string; kind: SensorKind; unit: string; n: number; avg: number | null; min: number | null; max: number | null; energy_mwh: number | null }
export interface Report { project: string; period: "day" | "week" | "month"; start: string; end: string; energy_mwh: number; alarms: { count: number; by_state: Record<string, number>; unacked: number }; sensors: ReportRow[] }
export interface Notification { id: number; kind: "review" | "issue" | "alarm" | "system"; title: string; body: string; link: string; created_at: string; read_at: string | null }
export interface AuditRow { id: number; user_id: number | null; username: string | null; action: string; target_type: string; target_id: number | null; project_id: number | null; detail: Record<string, unknown>; created_at: string }
export interface QtoElement { guid: string; type: string; name: string; storey: string; material: string; volume_m3: number; area_m2: number; footprint_m2: number; length_m: number; width_m: number; height_m: number; bbox: [number[], number[]]; ifc_quantities: Record<string, number> }
export interface Qto { element_count: number; total_volume_m3: number; by_type: Record<string, { count: number; volume_m3: number; area_m2: number }>; by_storey: Record<string, { count: number; volume_m3: number; area_m2: number }>; elements: QtoElement[] }
export interface Clash { kind: "hard" | "possible" | "touch"; a: { guid: string; type: string; name: string }; b: { guid: string; type: string; name: string }; point: number[]; overlap_m: number[]; overlap_volume_m3: number; triangle_hits: number }
export interface ClashReport { element_count: number; pairs_checked: number; exact: boolean; tolerance: number; hard: number; possible: number; touch: number; clashes: Clash[] }
export interface LiveMessage {
  type: "snapshot" | "reading" | "alarm" | "command" | "journal";
  sensors?: LiveReading[];
  event?: { id: number; sensor_id: number; sensor_name: string; state: AlarmState; value: number | null; started_at: string; ended_at: string | null; acked_by: number | null; priority?: string };
  command?: Command;
  entry?: JournalEntry;
  sensor_id?: number;
  key?: string;
  value?: number | null;
  ts?: string | null;
  alarm?: AlarmState;
  element_guid?: string | null;
  unit?: string;
}
export interface LiveReading { sensor_id: number; key: string; value: number | null; ts: string | null; alarm: AlarmState; element_guid: string | null; unit: string }

const TOKEN_KEY = "ges_token";

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}
export function setToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* private mode */
  }
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const res = await fetch(path, { ...init, headers });
  if (res.status === 401) {
    setToken(null);
    onUnauthorized?.();
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const j = await res.json();
      detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch {
      /* matn emas */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

const json = (body: unknown) => JSON.stringify(body);

export type DesktopFile = { kind: "installer" | "zip"; name: string; url: string; size: number };
/** Eng yangi desktop paketi: installer (o'rnatish) asosiy, zip (portable) qo'shimcha */
export type DesktopPackage = { version: string; kind: "installer" | "zip"; url: string; size: number; files: DesktopFile[] };

export const api = {
  // auth
  async login(username: string, password: string) {
    const form = new URLSearchParams({ username, password });
    const r = await request<{ access_token: string }>("/api/auth/login", {
      method: "POST",
      body: form,
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
    });
    setToken(r.access_token);
    return r;
  },
  me: () => request<User>("/api/auth/me"),
  changePassword: (old_password: string, new_password: string) =>
    request<void>("/api/auth/change-password", {
      method: "POST",
      body: json({ old_password, new_password }),
    }),
  // users (admin)
  users: () => request<User[]>("/api/users"),
  createUser: (body: { username: string; password: string; full_name: string; email?: string; is_admin: boolean }) =>
    request<User>("/api/users", { method: "POST", body: json(body) }),
  updateUser: (id: number, body: Partial<{ full_name: string; email: string; password: string; is_admin: boolean; is_active: boolean }>) =>
    request<User>(`/api/users/${id}`, { method: "PATCH", body: json(body) }),
  // projects
  projects: () => request<Project[]>("/api/projects"),
  project: (id: number) => request<Project>(`/api/projects/${id}`),
  createProject: (body: { name: string; description: string; location: string }) =>
    request<Project>("/api/projects", { method: "POST", body: json(body) }),
  members: (projectId: number) => request<Member[]>(`/api/projects/${projectId}/members`),
  setMember: (projectId: number, user_id: number, role: Role) =>
    request<Member>(`/api/projects/${projectId}/members`, { method: "PUT", body: json({ user_id, role }) }),
  removeMember: (projectId: number, userId: number) =>
    request<void>(`/api/projects/${projectId}/members/${userId}`, { method: "DELETE" }),
  // models
  models: (projectId: number) => request<Model[]>(`/api/projects/${projectId}/models`),
  model: (id: number) => request<Model>(`/api/models/${id}`),
  createModel: (projectId: number, body: { name: string; description: string }) =>
    request<Model>(`/api/projects/${projectId}/models`, { method: "POST", body: json(body) }),
  versions: (modelId: number) => request<Version[]>(`/api/models/${modelId}/versions`),
  version: (id: number) => request<Version>(`/api/versions/${id}`),
  uploadVersion: (modelId: number, file: File, message: string, parentId?: number) => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("message", message);
    if (parentId != null) fd.append("parent_id", String(parentId));
    return request<Version>(`/api/models/${modelId}/versions`, { method: "POST", body: fd });
  },
  importMeshVersion: (modelId: number, file: File, opts: { message?: string; unit?: string; y_up?: boolean; merge?: boolean; onto_current?: boolean; extrude_m?: number }) => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("message", opts.message ?? "");
    fd.append("unit", opts.unit ?? "m");
    fd.append("y_up", String(!!opts.y_up));
    fd.append("merge", String(!!opts.merge));
    fd.append("onto_current", String(opts.onto_current ?? true));
    fd.append("extrude_m", String(opts.extrude_m ?? 0));
    return request<Version & { imported: number; names: string[] }>(`/api/models/${modelId}/versions/import-mesh`, { method: "POST", body: fd });
  },
  importImageVersion: (modelId: number, file: File, opts: { mode: "drawing" | "heightmap" | "photo"; message?: string; width_m?: number; extrude_m?: number; z_min?: number; z_max?: number; grid?: number; min_area_px?: number; invert?: boolean; onto_current?: boolean }) => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("mode", opts.mode);
    fd.append("message", opts.message ?? "");
    fd.append("width_m", String(opts.width_m ?? 100));
    fd.append("extrude_m", String(opts.extrude_m ?? 3));
    fd.append("z_min", String(opts.z_min ?? 0));
    fd.append("z_max", String(opts.z_max ?? 100));
    fd.append("grid", String(opts.grid ?? 160));
    fd.append("min_area_px", String(opts.min_area_px ?? 40));
    fd.append("invert", String(!!opts.invert));
    fd.append("onto_current", String(opts.onto_current ?? true));
    return request<Version & { imported: number; names: string[] }>(`/api/models/${modelId}/versions/import-image`, { method: "POST", body: fd });
  },
  underlays: (modelId: number) => request<Underlay[]>(`/api/models/${modelId}/underlays`),
  createUnderlay: (modelId: number, file: File, opts: { name?: string; width_m?: number; x?: number; y?: number; z?: number; vertical?: boolean }) => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("name", opts.name ?? "");
    fd.append("width_m", String(opts.width_m ?? 100));
    fd.append("x", String(opts.x ?? 0));
    fd.append("y", String(opts.y ?? 0));
    fd.append("z", String(opts.z ?? 0));
    fd.append("vertical", String(!!opts.vertical));
    return request<Underlay>(`/api/models/${modelId}/underlays`, { method: "POST", body: fd });
  },
  updateUnderlay: (id: number, body: Partial<Pick<Underlay, "name" | "x" | "y" | "z" | "width_m" | "rotation_deg" | "opacity" | "vertical" | "visible">>) => request<Underlay>(`/api/underlays/${id}`, { method: "PATCH", body: json(body) }),
  deleteUnderlay: (id: number) => request<void>(`/api/underlays/${id}`, { method: "DELETE" }),
  heightmap: (versionId: number, nx = 160) => request<{ x0: number; y0: number; dx: number; dy: number; nx: number; ny: number; z_min: number; z_max: number; z: number[] }>(`/api/versions/${versionId}/heightmap?nx=${nx}`),
  twinPresets: () => request<{ id: string; title: string; description: string; location: string; sources: string[]; photo: boolean }[]>("/api/twin/presets"),
  createTwin: (projectId: number, preset: string, name = "") => request<{ model_id: number; model_name: string; version_id: number; elements: number; photo_underlay_id: number | null }>(`/api/projects/${projectId}/twin`, { method: "POST", body: json({ preset, name }) }),
  importDem: (modelId: number, body: { lat: number; lon: number; width_m: number; height_m: number; rotation_deg: number; zoom: number; nx: number; z_offset_m: number; message?: string; onto_current?: boolean }) => request<Version & { imported: number; dem: Record<string, unknown> }>(`/api/models/${modelId}/versions/import-dem`, { method: "POST", body: json(body) }),
  versionFileUrl: (id: number) => `/api/versions/${id}/file`,
  updateVersion: (id: number, body: { message?: string; tag?: string }) => request<Version>(`/api/versions/${id}`, { method: "PATCH", body: json(body) }),
  restoreVersion: (id: number) => request<Version>(`/api/versions/${id}/restore`, { method: "POST" }),
  /** Server tomonida tayyorlangan fragments (.frag); yo'q bo'lsa null — IFC yuklanadi */
  async versionFragments(id: number): Promise<Uint8Array | null> {
    // no-cache: ETag bilan qayta tekshiriladi (fayl yangilangan bo'lsa eskisi qolmasin)
    const res = await fetch(`/api/versions/${id}/fragments`, { cache: "no-cache", headers: { Authorization: `Bearer ${getToken() ?? ""}` } });
    if (res.status === 404) return null;
    if (!res.ok) throw new ApiError(res.status, "Fragments yuklab bo'lmadi");
    return new Uint8Array(await res.arrayBuffer());
  },
  async versionFile(id: number): Promise<Uint8Array> {
    const res = await fetch(`/api/versions/${id}/file`, {
      headers: { Authorization: `Bearer ${getToken() ?? ""}` },
    });
    if (!res.ok) throw new ApiError(res.status, "Faylni yuklab bo'lmadi");
    return new Uint8Array(await res.arrayBuffer());
  },
  diff: (versionId: number, fromVersionId?: number) =>
    request<Diff>(`/api/versions/${versionId}/diff${fromVersionId ? `?from_version_id=${fromVersionId}` : ""}`),
  // change requests
  changeRequests: (modelId: number) => request<ChangeRequest[]>(`/api/models/${modelId}/change-requests`),
  changeRequest: (id: number) => request<ChangeRequest>(`/api/change-requests/${id}`),
  createCR: (modelId: number, body: { version_id: number; title: string; description: string }) =>
    request<ChangeRequest>(`/api/models/${modelId}/change-requests`, { method: "POST", body: json(body) }),
  reviewCR: (id: number, decision: Review["decision"], comment: string) =>
    request<ChangeRequest>(`/api/change-requests/${id}/reviews`, { method: "POST", body: json({ decision, comment }) }),
  mergeCR: (id: number) => request<ChangeRequest>(`/api/change-requests/${id}/merge`, { method: "POST" }),
  rejectCR: (id: number) => request<ChangeRequest>(`/api/change-requests/${id}/reject`, { method: "POST" }),
  setCRVersion: (id: number, version_id: number) =>
    request<ChangeRequest>(`/api/change-requests/${id}/version`, { method: "POST", body: json({ version_id }) }),
  // issues
  issues: (modelId: number) => request<Issue[]>(`/api/models/${modelId}/issues`),
  issue: (id: number) => request<Issue>(`/api/issues/${id}`),
  createIssue: (
    modelId: number,
    body: { title: string; description: string; version_id?: number | null; change_request_id?: number | null; assignee_id?: number | null; priority: Issue["priority"]; viewpoint: Viewpoint },
  ) => request<Issue>(`/api/models/${modelId}/issues`, { method: "POST", body: json(body) }),
  updateIssue: (id: number, body: Partial<Pick<Issue, "title" | "description" | "status" | "assignee_id" | "priority" | "viewpoint">>) =>
    request<Issue>(`/api/issues/${id}`, { method: "PATCH", body: json(body) }),
  async bcfExport(modelId: number): Promise<Blob> {
    const res = await fetch(`/api/models/${modelId}/issues/bcf`, { headers: { Authorization: `Bearer ${getToken() ?? ""}` } });
    if (!res.ok) throw new ApiError(res.status, "BCF eksport bo'lmadi");
    return res.blob();
  },
  bcfImport: (modelId: number, file: File) => { const fd = new FormData(); fd.append("file", file); return request<{ created: number; updated: number }>(`/api/models/${modelId}/issues/bcf`, { method: "POST", body: fd }); },
  views: (modelId: number) => request<SavedView[]>(`/api/models/${modelId}/views`),
  saveView: (modelId: number, name: string, viewpoint: Viewpoint) => request<SavedView>(`/api/models/${modelId}/views`, { method: "PUT", body: json({ name, viewpoint }) }),
  deleteView: (id: number) => request<void>(`/api/views/${id}`, { method: "DELETE" }),
  commentIssue: (id: number, body: string, viewpoint: Viewpoint | null) =>
    request<Issue>(`/api/issues/${id}/comments`, { method: "POST", body: json({ body, viewpoint }) }),
  desktopLatest: () => request<DesktopPackage>("/api/desktop/latest"),
  async desktopDownload(url: string) {
    const { token } = await request<{ token: string }>("/api/desktop/download-token", { method: "POST" });
    location.href = `${url}?token=${encodeURIComponent(token)}`;
  },
  // simulyatsiya
  simExample: () => request<SimParams>("/api/sim/example"),
  gesParams: (versionId: number) => request<GesParams>(`/api/versions/${versionId}/ges-params`),
  simJobs: (modelId: number) => request<SimJob[]>(`/api/models/${modelId}/sim`),
  cfdStatus: () => request<{ mode: string; available: boolean; image: string }>("/api/sim/cfd-status"),
  simLog: (id: number) => request<Record<string, string>>(`/api/sim/${id}/log`),
  cfdResult: (id: number) => request<CfdResult>(`/api/sim/${id}/result`),
  createSim: (modelId: number, body: { name: string; version_id: number | null; kind?: string; params: SimParams | CfdParams | GenericParams }) =>
    request<SimJob>(`/api/models/${modelId}/sim`, { method: "POST", body: json(body) }),
  drafts: (modelId: number) => request<DraftRow[]>(`/api/models/${modelId}/drafts`),
  createDraft: (modelId: number, body: DraftBody) => request<DraftRow>(`/api/models/${modelId}/drafts`, { method: "POST", body: json(body) }),
  updateDraft: (id: number, body: Partial<DraftBody>) => request<DraftRow>(`/api/drafts/${id}`, { method: "PATCH", body: json(body) }),
  deleteDraft: (id: number) => request<void>(`/api/drafts/${id}`, { method: "DELETE" }),
  commitDrafts: (modelId: number, body: { message?: string; base_version_id?: number | null; draft_ids?: number[]; keep_drafts?: boolean }) => request<Version & { guids: string[] }>(`/api/models/${modelId}/drafts/commit`, { method: "POST", body: json(body) }),
  simCatalog: () => request<SimCatalog>("/api/sim/catalog"),
  materials: () => request<MaterialsCatalog>("/api/sim/materials"),
  safetyCheck: (modelId: number, versionId?: number | null) => request<SafetyCheck>(`/api/models/${modelId}/sim/safety-check${versionId ? `?version_id=${versionId}` : ""}`, { method: "POST" }),
  simSweep: (body: { kind: string; params: GenericParams; key: string; values: number[] }) => request<{ key: string; label: string; unit: string; rows: { value: number; summary: Record<string, unknown>; error: string | null }[]; outputs: { key: string; label: string; unit: string }[] }>("/api/sim/sweep", { method: "POST", body: json(body) }),
  simPrefill: (modelId: number, kind: string, versionId?: number | null) => request<SimPrefill>(`/api/models/${modelId}/sim/prefill?kind=${encodeURIComponent(kind)}${versionId ? `&version_id=${versionId}` : ""}`),
  genericResult: (id: number) => request<GenericResult>(`/api/sim/${id}/result`),
  site: (projectId: number) => request<SiteProfile>(`/api/projects/${projectId}/site`),
  saveSite: (projectId: number, values: GenericParams) => request<SiteProfile>(`/api/projects/${projectId}/site`, { method: "PUT", body: json(values) }),
  customExample: () => request<CustomTemplate>("/api/sim/custom-example"),
  customPreview: (template: CustomTemplate, inputs: GenericParams) => request<GenericResult>("/api/sim/custom-preview", { method: "POST", body: json({ template, inputs }) }),
  simTemplates: (projectId: number) => request<SimTemplate[]>(`/api/projects/${projectId}/sim-templates`),
  createTemplate: (projectId: number, body: { name: string; description?: string; template: CustomTemplate }) => request<SimTemplate>(`/api/projects/${projectId}/sim-templates`, { method: "POST", body: json(body) }),
  updateTemplate: (id: number, body: { name: string; description?: string; template: CustomTemplate }) => request<SimTemplate>(`/api/sim-templates/${id}`, { method: "PUT", body: json(body) }),
  deleteTemplate: (id: number) => request<void>(`/api/sim-templates/${id}`, { method: "DELETE" }),
  simJob: (id: number) => request<SimJob>(`/api/sim/${id}`),
  simResult: (id: number) => request<SimResult>(`/api/sim/${id}/result`),
  deleteSim: (id: number) => request<void>(`/api/sim/${id}`, { method: "DELETE" }),
  // monitoring
  sensors: (projectId: number, modelId?: number) => request<Sensor[]>(`/api/projects/${projectId}/sensors${modelId ? `?model_id=${modelId}` : ""}`),
  createSensor: (projectId: number, body: SensorIn) => request<Sensor>(`/api/projects/${projectId}/sensors`, { method: "POST", body: json(body) }),
  updateSensor: (id: number, body: Partial<SensorIn> & { clear_alarms?: boolean }) => request<Sensor>(`/api/sensors/${id}`, { method: "PATCH", body: json(body) }),
  deleteSensor: (id: number) => request<void>(`/api/sensors/${id}`, { method: "DELETE" }),
  importSensors: (projectId: number, csv: string, modelId: number | null) => request<{ created: number; updated: number; bound: number; errors: string[] }>(`/api/projects/${projectId}/sensors/import`, { method: "POST", body: json({ csv, model_id: modelId }) }),
  readings: (sensorId: number, hours: number, limit = 600) => request<{ sensor_id: number; unit: string; total: number; points: ReadingPoint[]; hourly: boolean }>(`/api/sensors/${sensorId}/readings?hours=${hours}&limit=${limit}`),
  alarms: (projectId: number) => request<Sensor[]>(`/api/projects/${projectId}/alarms`),
  // BIM tekshiruvlar
  qto: (versionId: number) => request<Qto>(`/api/versions/${versionId}/qto`),
  clashes: (versionId: number, kind?: string) => request<ClashReport>(`/api/versions/${versionId}/clashes${kind ? `?kind=${kind}` : ""}`),
  // SCADA: alarm jurnali, dispetcher paneli, hisobot, bildirishnomalar, audit
  alarmEvents: (projectId: number, active: boolean, hours = 168) => request<AlarmEvent[]>(`/api/projects/${projectId}/alarm-events?active=${active}&hours=${hours}`),
  ackAlarm: (id: number, comment = "") => request<AlarmEvent>(`/api/alarm-events/${id}/ack`, { method: "POST", body: json({ comment }) }),
  ackAll: (projectId: number) => request<{ acked: number }>(`/api/projects/${projectId}/alarm-events/ack-all`, { method: "POST" }),
  dashboard: (projectId: number) => request<Dashboard>(`/api/projects/${projectId}/dashboard`),
  saveDashboard: (projectId: number, body: { mimic: Record<string, number | null>; tiles: number[] }) => request<Dashboard["mimic"]>(`/api/projects/${projectId}/dashboard`, { method: "PUT", body: json(body) }),
  report: (projectId: number, period: Report["period"], date?: string) => request<Report>(`/api/projects/${projectId}/report?period=${period}${date ? `&date=${date}` : ""}`),
  async downloadCsv(path: string, filename: string) {
    // Bearer bilan yuklab olish (URL da token yo'q): blob → <a download>
    const r = await fetch(path, { headers: { Authorization: `Bearer ${getToken() ?? ""}` } });
    if (!r.ok) throw new Error(`Yuklab bo'lmadi (${r.status})`);
    const url = URL.createObjectURL(await r.blob());
    const a = document.createElement("a"); a.href = url; a.download = filename; a.click();
    URL.revokeObjectURL(url);
  },
  // Raqamli egizak, boshqaruv, jurnal, aktivlar, vaqt mashinasi
  twin: (projectId: number) => request<TwinState>(`/api/projects/${projectId}/twin`),
  twinRun: (projectId: number) => request<TwinState>(`/api/projects/${projectId}/twin/run`, { method: "POST" }),
  commands: (projectId: number, hours = 168) => request<Command[]>(`/api/projects/${projectId}/commands?hours=${hours}`),
  sendCommand: (projectId: number, sensor_id: number, value: number, note = "") => request<Command>(`/api/projects/${projectId}/commands`, { method: "POST", body: json({ sensor_id, value, note }) }),
  cancelCommand: (id: number) => request<Command>(`/api/commands/${id}/cancel`, { method: "POST" }),
  journal: (projectId: number, hours = 168) => request<JournalEntry[]>(`/api/projects/${projectId}/journal?hours=${hours}`),
  addJournal: (projectId: number, text: string, kind: JournalEntry["kind"] = "note") => request<JournalEntry>(`/api/projects/${projectId}/journal`, { method: "POST", body: json({ text, kind }) }),
  assets: (projectId: number) => request<AssetState[]>(`/api/projects/${projectId}/assets`),
  createAsset: (projectId: number, body: { name: string; element_guid?: string | null; power_sensor_id?: number | null; base_run_hours?: number; maintenance_interval_hours?: number | null }) => request<AssetState>(`/api/projects/${projectId}/assets`, { method: "POST", body: json(body) }),
  updateAsset: (id: number, body: { name?: string; power_sensor_id?: number | null; maintenance_interval_hours?: number | null; notes?: string; config?: Record<string, unknown> }) => request<AssetState>(`/api/assets/${id}`, { method: "PATCH", body: json(body) }),
  health: (projectId: number) => request<HealthReport>(`/api/projects/${projectId}/health`),
  workOrders: (projectId: number, status?: string) => request<WorkOrder[]>(`/api/projects/${projectId}/work-orders${status ? `?status=${status}` : ""}`),
  workOrderKpi: (projectId: number) => request<WorkOrderKpi>(`/api/projects/${projectId}/work-orders/kpi`),
  createWorkOrder: (projectId: number, body: { title: string; description?: string; asset_id?: number | null; assignee_id?: number | null; priority?: string; source?: string; due_at?: string | null }) => request<WorkOrder>(`/api/projects/${projectId}/work-orders`, { method: "POST", body: json(body) }),
  updateWorkOrder: (id: number, body: Partial<{ title: string; description: string; assignee_id: number | null; priority: string; status: WorkOrderStatus; due_at: string | null; downtime_hours: number; cost: number; resolution: string }>) => request<WorkOrder>(`/api/work-orders/${id}`, { method: "PATCH", body: json(body) }),
  deleteWorkOrder: (id: number) => request<void>(`/api/work-orders/${id}`, { method: "DELETE" }),
  parts: (projectId: number) => request<SparePart[]>(`/api/projects/${projectId}/parts`),
  createPart: (projectId: number, body: { name: string; code?: string; unit?: string; qty?: number; min_qty?: number; location?: string; unit_cost?: number; asset_id?: number | null; notes?: string }) => request<SparePart>(`/api/projects/${projectId}/parts`, { method: "POST", body: json(body) }),
  updatePart: (id: number, body: Partial<{ name: string; code: string; unit: string; min_qty: number; location: string; unit_cost: number; asset_id: number | null; notes: string }>) => request<SparePart>(`/api/parts/${id}`, { method: "PATCH", body: json(body) }),
  deletePart: (id: number) => request<void>(`/api/parts/${id}`, { method: "DELETE" }),
  movePart: (id: number, body: { qty: number; work_order_id?: number | null; note?: string }) => request<SparePart>(`/api/parts/${id}/move`, { method: "POST", body: json(body) }),
  partMovements: (id: number) => request<PartMovement[]>(`/api/parts/${id}/movements`),
  floodForecast: (projectId: number, body: { rain_mm: number; rain_hours?: number; amc?: string; snowmelt?: boolean; air_temp?: number; glof?: boolean; lake_mcm?: number; gate_opening?: number }) => request<FloodForecast>(`/api/projects/${projectId}/twin/forecast`, { method: "POST", body: json(body) }),
  healthRun: (projectId: number) => request<HealthReport>(`/api/projects/${projectId}/health/run`, { method: "POST" }),
  twinWhatIf: (projectId: number, body: Record<string, number>) => request<TwinState & { dispatch?: DispatchResult }>(`/api/projects/${projectId}/twin/what-if`, { method: "POST", body: json(body) }),
  twinDispatch: (projectId: number, targetMw?: number) => request<DispatchResult>(`/api/projects/${projectId}/twin/dispatch${targetMw != null ? `?target_mw=${targetMw}` : ""}`),
  assetMaintenance: (id: number, note: string) => request<AssetState>(`/api/assets/${id}/maintenance?note=${encodeURIComponent(note)}`, { method: "POST" }),
  deleteAsset: (id: number) => request<void>(`/api/assets/${id}`, { method: "DELETE" }),
  snapshot: (projectId: number, at: string) => request<Snapshot>(`/api/projects/${projectId}/snapshot?at=${encodeURIComponent(at)}`),
  notifications: (unread = false, limit = 50) => request<Notification[]>(`/api/notifications?unread=${unread}&limit=${limit}`),
  notificationCount: () => request<{ unread: number }>("/api/notifications/count"),
  markRead: (ids: number[] | null) => request<{ read: number }>("/api/notifications/read", { method: "POST", body: json({ ids }) }),
  audit: (q: { project_id?: number; action?: string; user_id?: number; limit?: number; before_id?: number }) => {
    const qs = Object.entries(q).filter(([, v]) => v != null && v !== "").map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`).join("&");
    return request<AuditRow[]>(`/api/audit${qs ? `?${qs}` : ""}`);
  },
  ingestKey: (projectId: number) => request<{ ingest_key: string; url: string }>(`/api/projects/${projectId}/ingest-key`),
  rotateIngestKey: (projectId: number) => request<{ ingest_key: string }>(`/api/projects/${projectId}/ingest-key`, { method: "POST" }),
  pushReadings: (projectId: number, items: { key?: string; sensor_id?: number; value: number; ts?: string }[]) =>
    request<{ accepted: number; unknown: unknown[] }>(`/api/projects/${projectId}/readings`, { method: "POST", body: json(items) }),
  importReadings: (sensorId: number, file: File) => { const fd = new FormData(); fd.append("file", file); return request<{ accepted: number }>(`/api/sensors/${sensorId}/import`, { method: "POST", body: fd }); },
  liveSocket(projectId: number): WebSocket {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    return new WebSocket(`${proto}://${location.host}/api/projects/${projectId}/live?token=${encodeURIComponent(getToken() ?? "")}`);
  },
};
