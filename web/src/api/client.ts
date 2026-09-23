// Server API bilan ishlash. Token localStorage da saqlanadi.

export type Role = "viewer" | "operator" | "shift_supervisor" | "engineer" | "approver";
/** SCADA-01: buyruq faqat dispetcher va smena boshlig'ida (loyihalash rollari buyruq bermaydi). */
export const canCommandRole = (r: Role | null | undefined) => r === "operator" || r === "shift_supervisor";
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
  mfa_enabled?: boolean;
  locked_until?: string | null;
  /** /auth/me: administrator uchun MFA majburiy, hali yoqilmagan (L1) */
  mfa_required?: boolean;
  /** Admin bergan/boshlang'ich parol — almashtirilguncha boshqa amallar 403 (L2) */
  must_change_password?: boolean;
}
export interface UserSession { id: number; client: string; ip: string; user_agent: string; created_at: string; last_used_at: string; expires_at: string; current: boolean }
export interface Project {
  id: number;
  name: string;
  description: string;
  location: string;
  my_role: Role | null;
  model_count: number;
  /** G2: IDS tekshiruvi yiqilgan versiya tasdiqlanmaydi */
  ids_required?: boolean;
  /** G3: georeferensiya — EPSG, lokal (0,0,0) ning global joyi, X o'qi burilishi */
  crs?: ProjectCrs | null;
  /** G4 (ISO 19650): konteyner nomlash shabloni va majburiyligi */
  naming_template?: string;
  naming_required?: boolean;
}
export type DocKind = "eir" | "bep" | "tidp" | "midp" | "other";
export interface ProjectDocument { id: number; project_id: number; kind: DocKind; title: string; file_name: string; file_size: number; uploaded_by: number; uploader_username: string; created_at: string }
export interface ProjectCrs { epsg: number; name: string; origin_e: number; origin_n: number; origin_h: number; rotation_deg: number; scale: number }
export interface Georef { epsg?: number | null; name?: string; datum?: string | null; origin_e?: number; origin_n?: number; origin_h?: number; rotation_deg?: number; scale?: number; supported?: boolean; site_lat?: number; site_lon?: number }
export interface CrsConvert { local: { x: number; y: number; z: number } | null; global: { e: number; n: number; h: number; epsg: number } | null; latlon: { lat: number; lon: number } | null }
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
  safety?: { score: number | null; overall?: string; counts: { ok: number; warn: number; fail: number; skip: number }; verdict: string; version_id: number | null; at: string; fails: string[] } | null;
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
    /** G3: IfcMapConversion + IfcSite lat/lon (yo'q — null) */
    georef?: Georef | null;
    warnings?: string[];
    /** G5: klassifikatorlar va kodlar bo'yicha element soni */
    classification?: { systems: Record<string, { source: string | null; edition: string | null }>; classified: number; by_code: Record<string, number> };
  };
  created_at: string;
  /** G2: IDS natijasi — pass | fail | error | null (navbatda) */
  ids_status?: "pass" | "fail" | "error" | null;
  /** G4 (ISO 19650): yaroqlilik (S0–S7/A/B/CR/PR) va reviziya (P01…/C01…) */
  suitability_code?: string | null;
  revision_code?: string | null;
  suitability_label?: string;
}
export interface IdsFailed { guid: string | null; class: string | null; name: string | null; reason: string | null }
export interface IdsRequirement { description: string; status: boolean; failed: IdsFailed[]; failed_total: number }
export interface IdsSpec { identifier: string | null; name: string; description: string; status: boolean; applicable: number; passed: number; failed: number; requirements: IdsRequirement[] }
export interface IdsResult { status: "pass" | "fail" | "error"; ids: string; checked_at: string; error?: string; title?: string; total_specifications?: number; total_specifications_pass?: number; total_checks?: number; total_checks_pass?: number; specifications?: IdsSpec[] }
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
export interface SafetyRow { id: string; title: string; kind: string; why: string; status: "ok" | "warn" | "fail" | "skip"; message: string; metrics: Record<string, unknown>; warnings?: string[]; job_id: number | null }
/** score — faqat barcha mezonlar hisoblanganda (ma'lumot uchun); overall konyunktiv: bitta fail → fail, skip → incomplete */
export interface SafetyCheck { rows: SafetyRow[]; score: number | null; overall?: "ok" | "warn" | "fail" | "incomplete"; counts: { ok: number; warn: number; fail: number; skip: number }; verdict: string; version_id: number | null }
export interface SimCatalog { kinds: SimKind[]; groups: Record<string, string>; site_fields: SimField[] }
export type GenericParams = Record<string, unknown>;
export interface ProneSpot { where: string; why: string; severity: string }
export interface DamTypeRow { type: string; name: string; score: number; verdict: string; reasons: string[]; good: string[]; bad: string[]; cracks: string[] }
export interface GenericResult { series: Record<string, (number | string)[]>; summary: Record<string, unknown>; profile?: Record<string, unknown>; field?: { nx: number; ny: number; values: number[]; legend?: string }; downstream?: Record<string, number[]>; breach?: Record<string, unknown> | null; seismic_scan?: Record<string, number[]>; forces?: Record<string, unknown>[]; structures?: Record<string, unknown>[]; prone?: ProneSpot[]; ranking?: DamTypeRow[]; thermal?: Record<string, unknown>; units?: Record<string, unknown>[] }
export interface MaterialsCatalog { concrete: { id: string; name: string; Rb: number; Rbt: number; Rbn: number; Rbtn: number; E: number; gamma: number; use: string }[]; cement: { id: string; name: string; q: number; note: string }[]; steel: { id: string; name: string; yield: number; ult: number; E: number; note: string }[]; soil: { id: string; name: string; gamma: number; phi: number; c: number; k: number; note: string }[]; zones: { zone: string; concrete: string; why: string }[] }
export interface SimPrefill { site: GenericParams; model: GenericParams; live: GenericParams; site_filled: boolean }
export interface SiteRisk { name: string; value: number; unit: string; ok: boolean; note: string }
export interface SiteProfile { values: GenericParams; filled: boolean; risks: SiteRisk[] }
export interface CustomTemplate { name?: string; description?: string; inputs: { key: string; label?: string | undefined; unit?: string | undefined; default?: number | undefined; min?: number | undefined; max?: number | undefined }[]; steps: number; dt: number; init: Record<string, string>; step: { target: string; expr: string }[]; outputs: string[]; summary: Record<string, string>; checks: { expr: string; message: string }[] }
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
  start_date?: string | undefined;
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
  crest_height_m?: number; head_m?: number; crest_length_m?: number | undefined; upstream_m?: number; downstream_m?: number; unit_discharge_m2s?: number | null; end_time_s?: number;
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

export type AlarmState = "ok" | "low" | "high" | "stale" | "lowlow" | "highhigh" | "roc" | "deviation";
/** O'lchov sifati (OPC UA/IEC 61850 ga mos soddalashtirilgan): bad — qiymat ishonchsiz, alarm baholanmaydi */
export type Quality = "good" | "uncertain" | "bad" | "substituted" | "manual";
export type SensorKind = "level" | "flow" | "power" | "pressure" | "temperature" | "vibration" | "status" | "position" | "value" | "deviation";
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
  ll_alarm?: number | null;
  hh_alarm?: number | null;
  deadband?: number;
  on_delay_s?: number;
  off_delay_s?: number;
  roc_limit_per_min?: number | null;
  suppress_condition?: string;
  suppressed?: boolean;
  alarm_mode?: "normal" | "shelved" | "out_of_service";
  alarm_mode_until?: string | null;
  alarm_mode_reason?: string;
  cause?: string;
  consequence?: string;
  corrective_action?: string;
  response_time_s?: number | null;
  priority_basis?: string;
  rationalized_by?: number | null;
  rationalized_at?: string | null;
  min_raw?: number | null;
  max_raw?: number | null;
  min_setpoint?: number | null;
  max_setpoint?: number | null;
  max_rate_per_min?: number | null;
  requires_dual_approval?: boolean;
  command_ttl_s?: number;
  readback_tolerance?: number;
  stale_after_s: number;
  enabled: boolean;
  last_value: number | null;
  last_ts: string | null;
  last_quality?: Quality | undefined;
  alarm: AlarmState;
  /** Aloqa yo'q / eskirgan (F4: alarm holatidan alohida) */
  stale?: boolean | undefined;
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
  ll_alarm?: number | null;
  hh_alarm?: number | null;
  deadband?: number;
  on_delay_s?: number;
  off_delay_s?: number;
  roc_limit_per_min?: number | null;
  suppress_condition?: string;
  suppressed?: boolean;
  alarm_mode?: "normal" | "shelved" | "out_of_service";
  alarm_mode_until?: string | null;
  alarm_mode_reason?: string;
  cause?: string;
  consequence?: string;
  corrective_action?: string;
  response_time_s?: number | null;
  priority_basis?: string;
  rationalized_by?: number | null;
  rationalized_at?: string | null;
  stale_after_s: number;
  enabled: boolean;
  priority?: "low" | "medium" | "high" | "critical" | undefined;
  writable?: boolean;
}
export type CommandStatus = "pending" | "sent" | "acked" | "failed" | "cancelled" | "expired" | "pending_approval" | "mismatch";
export interface Command { id: number; sensor_id: number; sensor_key: string; sensor_name: string; unit: string; value: number; note: string; status: CommandStatus; result: string; author_username: string; created_at: string; updated_at: string; expires_at?: string | null; sent_at?: string | null; approved_by_username?: string | null; approved_at?: string | null; readback_value?: number | null; readback_at?: string | null }
export type GatewayKeyKind = "ingest" | "command";
export interface GatewayKey { kind: GatewayKeyKind; key: string; header: string; url: string; expires_at: string | null; days_left: number | null; last_used_at: string | null }
export interface InterlockResult { interlock_id: number; name: string; ok: boolean; message: string }
export interface SelectResult { select_token: string; sensor_id: number; value: number; expires_at: string; requires_approval: boolean; interlocks?: InterlockResult[]; override?: boolean }
export interface Interlock { id: number; project_id: number; sensor_id: number; sensor_key: string; name: string; condition: string; message: string; enabled: boolean; current_ok: boolean | null; current_message: string }
export interface JournalEntry { id: number; kind: "note" | "shift_start" | "shift_end" | "event"; text: string; author_username: string; created_at: string }
export interface TwinUnit { sensor_id: number; name: string; model_unit: string; running: boolean; measured_mw: number | null; expected_mw: number; deviation_pct: number | null; efficiency: number | null; expected_efficiency: number | null; flow_m3s: number | null; head_net_m: number }
export type ValidationStatusKind = "validated" | "expired" | "failed" | "unvalidated";
export interface ValidationStatus { status: ValidationStatusKind; note: string; record_id?: number; verdict?: string; validated_at?: string; validated_by?: string | null; valid_until?: string | null; version_id?: number | null; metrics?: Record<string, number | boolean> }
export interface ValidationCheck { name: string; label: string; value: number; limit: number; ok: boolean }
export interface ValidationEvaluation { ok: boolean; reason: string; criteria: Record<string, number>; checks?: ValidationCheck[]; metrics: Record<string, number | boolean> }
export interface ValidationRecord { id: number; project_id: number; version_id: number | null; calibration_run_id: number | null; validated_by: string | null; created_at: string; window_from: string; window_to: string; criteria: Record<string, number>; metrics: Record<string, number | boolean>; checks: ValidationCheck[]; verdict: string; valid_until: string | null; note: string }
export interface ValidationState { status: ValidationStatus; evaluation: ValidationEvaluation; records: ValidationRecord[] }
export interface RedundancyCheck { name: string; label: string; unit: string; sources: { label: string; value: number }[]; diff: number; tolerance: number; status: "ok" | "alert" | "alarm"; note?: string }
export interface LevelEstimate { status: "ok" | "insufficient"; missing?: string[]; level_measured_m?: number | null; level_estimate_m?: number; sigma_m?: number; gain?: number; source?: "measured" | "model"; frozen?: boolean; sensor_key?: string | null; innovation_m?: number | null; expected_change_m?: number; dt_hours?: number; balance?: { status: string; level_m?: number; inflow_m3s?: number; outflow_m3s?: number; net_m3s?: number; area_m2?: number; dlevel_m_per_h?: number; missing?: string[] } }
export interface EstimatorState { estimate: LevelEstimate; checks: RedundancyCheck[] }
export interface CalibrationInfo { penstock_roughness_mm: number; eff: Record<string, number>; run_id?: number | null; applied_at?: string | null; rmse_mw?: number | null; drifted?: boolean }
export interface CalibrationRun { id: number; project_id: number; created_at: string; author: string | null; window_from: string; window_to: string; n_points: number; targets: string[]; status: string; params_before: { penstock_roughness_mm?: number; eff?: Record<string, number> }; params_after: { penstock_roughness_mm?: number; eff?: Record<string, number> }; rmse_before: number | null; rmse_after: number | null; bias_after: number | null; improvement_pct: number | null; diagnostics: Record<string, { gain: number; identifiable: boolean; note: string }>; applied: boolean; note: string }
export interface CalibrationResiduals { status: "ok" | "drifted" | "uncalibrated" | "insufficient"; calibrated?: boolean; n_points?: number; days?: number; rmse_mw?: number; bias_mw?: number; calibration_rmse_mw?: number | null; run_id?: number | null; applied_at?: string | null; advice?: string; reason?: string }
export interface CalibrationState { current: Record<string, unknown>; residuals: CalibrationResiduals; runs: CalibrationRun[] }
export interface TwinState { status: "ok" | "insufficient"; reason?: string; has_model?: boolean; version_id?: number; head_gross_m: number | null; flow_total_m3s?: number | null; units: TwinUnit[]; expected_total_mw?: number; measured_total_mw?: number; safety?: SiteRisk[]; what_if?: boolean; calibrated?: boolean; calibration?: CalibrationInfo | null; model_note?: string; validation?: ValidationStatus }
export interface HealthSensorBlock { sensor_id: number; name: string; unit: string; value: number | null; stale: boolean; slope_per_day: number | null; baseline_mean: number | null; baseline_std: number | null; z: number | null; anomaly: boolean; points: number; zone?: string; zone_note?: string; days_to_c?: number | null; days_to_d?: number | null; warn?: number; alarm?: number; days_to_alarm?: number | null }
export type CmState = "normal" | "alert" | "alarm" | "unknown";
export interface CmStateItem { state: CmState; reason: string; zone?: string; zone_note?: string; limits?: number[]; warn?: number; alarm?: number; anomaly?: boolean; external?: boolean; match?: { name: string; f: number; amplitude: number; share: number; kind: string; spectrum_id: number } }
export interface CmExternal { id: number; source: string; block: string; ts: string; state: CmState; health_score: number | null; rul_days: number | null; diagnosis: string; confidence: number | null; detail: Record<string, unknown> }
export interface CmPrognosis { days: Record<string, number | null>; rul_days: number | null; rul_basis: string | null; external_rul_days: number | null; efficiency_pct_per_year: number | null }
export interface CmBlocks { DA: { channels: string[]; spectra: number }; DM: { features: string[]; spectra: number }; SD: { state: CmState; items: string[] }; HA: { score: number; internal: number; external: number | null }; PA: { rul_days: number | null }; AG: { problems: number; tips: number } }
export interface SpectrumFeatures { id: number; ts: string; kind: string; unit: string; rpm: number | null; overall: number; peaks: { f: number; a: number }[]; harmonics: Record<string, number>; bearing_frequencies: Record<string, number> | null; bearing_matches: { name: string; f: number; amplitude: number; share: number }[]; source: string }
export interface SpectrumRow { id: number; asset_id: number | null; sensor_id: number | null; ts: string; kind: string; unit: string; rpm: number | null; f_min: number; f_max: number; n_lines: number; source: string; meta: Record<string, unknown>; values?: number[] | null; freqs?: number[] | null; features?: SpectrumFeatures | null }
export interface AssetHealth { asset_id: number; name: string; element_guid: string | null; kks_code?: string | null; score: number; level: string; vibration: HealthSensorBlock | null; bearing_temp: HealthSensorBlock | null; efficiency: { measured: number | null; expected: number | null; deviation_pct: number | null; trend_pct_per_month: number | null; running: boolean } | null; cavitation: { sigma_plant: number; sigma_critical: number; ns: number; suction_head_m: number; margin: number } | null; electrical?: { load_factor: number; top_oil_c: number; hot_spot_c: number; aging_rate: number } | null; problems: string[]; tips: string[]; machine_group: number; state?: CmState; states?: Record<string, CmStateItem>; external?: CmExternal[]; internal_score?: number; external_score?: number | null; prognosis?: CmPrognosis; channels?: Record<string, HealthSensorBlock>; spectra?: SpectrumFeatures[]; blocks?: CmBlocks }
export interface HealthReport { plant_score: number | null; assets: AssetHealth[]; twin_status?: string }
export interface DispatchResult { status: string; reason?: string; target_mw?: number; head_gross_m?: number; units: { name: string; power_mw: number; flow_m3s: number; efficiency: number | null; head_net_m: number; load_pct: number }[]; total_flow_m3s?: number; current_flow_m3s?: number | null; saving_pct?: number | null; units_on?: number }
export type WorkOrderStatus = "open" | "in_progress" | "done" | "cancelled";
export interface WorkOrderTask { title: string; done: boolean }
export interface WorkOrder { id: number; project_id: number; asset_id: number | null; asset_name: string | null; title: string; description: string; priority: string; source: string; status: WorkOrderStatus; author_username: string; assignee_id: number | null; assignee_username: string | null; due_at: string | null; started_at: string | null; closed_at: string | null; downtime_hours: number; cost: number; resolution: string; created_at: string; updated_at: string; overdue: boolean; plan_id: number | null; tasks: WorkOrderTask[]; failure_mode: string | null; failure_cause: string | null; detection_method: string | null; labor_rate: number; labor_hours: number; labor_cost: number; parts_cost: number; extra_cost: number; permit_required: boolean; permit_status: string; permit_note: string; loto_active: boolean; loto_points: { label?: string; sensor_id?: number }[] }
export interface MaintenancePlan { id: number; project_id: number; asset_id: number | null; asset_name: string | null; name: string; description: string; tasks: string[]; interval_days: number | null; interval_hours: number | null; priority: string; lead_days: number; permit_required: boolean; active: boolean; last_generated_at: string | null; last_run_hours: number; due_reason: string | null; created_at: string }
export interface LaborEntry { id: number; work_order_id: number; user_id: number; username: string; hours: number; rate: number | null; note: string; work_date: string }
export interface WorkOrderPart { part_id: number; part_name: string; unit: string; reserved: number; consumed: number; free: number; stock: number }
export interface CmmsCodes { failure_modes: Record<string, string>; failure_causes: Record<string, string>; detection_methods: Record<string, string> }
export interface AssetHistoryItem { id: number; title: string; status: string; source: string; plan_id: number | null; created_at: string; closed_at: string | null; downtime_hours: number; labor_hours: number; labor_cost: number; parts_cost: number; cost: number; failure_mode: string | null; failure_mode_label: string; failure_cause: string | null; detection_method: string | null; parts: { part: string; qty: number; unit: string; cost: number }[]; resolution: string }
export interface AssetHistory { asset: { id: number; name: string; kks_code: string | null }; work_orders: AssetHistoryItem[]; totals: { work_orders: number; cost: number; labor_hours: number; parts_cost: number; downtime_hours: number; failures: number }; by_year: { year: number; work_orders: number; labor_hours: number; cost: number; downtime_hours: number; failures: number }[]; failure_modes: { code: string; label: string; count: number }[] }
export interface LotoEntry { work_order_id: number; title: string; asset_id: number | null; asset_name: string | null; points: { label?: string; sensor_id?: number }[]; applied_at: string | null }
export interface WorkOrderKpi { open: number; in_progress: number; overdue: number; done_90d: number; mttr_hours: number | null; mtbf_hours: number | null; downtime_90d_hours: number; cost_90d: number; by_priority: Record<string, number> }
export interface FloodForecast { status: string; live: Record<string, number>; site_filled: boolean; rain: Record<string, unknown>; summary: Record<string, number | boolean | string | null>; series: Record<string, number[]>; recommendation: { action: string; text: string; safe_level_m?: number | null; lower_by_m?: number | null; hours_to_overtop?: number | null } | null }
export interface SparePart { id: number; project_id: number; name: string; code: string; unit: string; qty: number; min_qty: number; location: string; unit_cost: number; asset_id: number | null; asset_name: string | null; notes: string; low: boolean; updated_at: string }
export interface PartMovement { id: number; part_id: number; part_name: string; work_order_id: number | null; qty: number; note: string; author_username: string; created_at: string }
export interface AssetTreeNode { id: number; name: string; kks_code: string | null; taxonomy_level: string | null; function_location: string; element_guid: string | null; kks: { system_name?: string | null; level: string; scheme: string } | null; status: "ok" | "due" | "overdue" | null; running: boolean | null; score: number | null; level: string | null; agg_score: number | null; agg_status: string; children: AssetTreeNode[] }
export interface AssetTree { roots: AssetTreeNode[]; count: number; levels: string[]; level_labels: Record<string, string> }
export interface AssetState { id: number; name: string; element_guid: string | null; parent_id?: number | null; kks_code?: string | null; taxonomy_level?: string | null; function_location?: string; power_sensor_id: number | null; running: boolean; run_hours_total: number; starts_total: number; run_hours_30d: number; energy_30d_mwh: number; availability_30d: number; maintenance_interval_hours: number | null; last_maintenance_at: string | null; hours_since_maintenance: number; hours_to_maintenance: number | null; status: "ok" | "due" | "overdue"; notes: string; config?: { kind?: string; manufacturer?: string; model?: string; serial?: string; warranty_end?: string; classification?: string; installed?: string } }
export type AssetDocKind = "manual" | "passport" | "test" | "commissioning" | "other";
export interface AssetDocument { id: number; asset_id: number; kind: AssetDocKind; title: string; file_name: string; file_size: number; uploader_username: string; created_at: string }
export interface AssetRegister { facility: Record<string, unknown>; floors: Record<string, unknown>[]; types: Record<string, unknown>[]; components: { Name: string; TypeName: string; Floor: string; SerialNumber: string; ExtIdentifier: string; ExtObject: string; Category: string; Kind: string }[]; counts: { types: number; components: number; attributes: number } }
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
  suppressed?: string | null;
  alarm_state?: string;
  cause?: string;
  consequence?: string;
  corrective_action?: string;
  response_time_s?: number | null;
}

export interface SoeEvent { id: number; type?: "soe" | "alarm" | "command" | "journal"; source: string; point: string; state: string; ts: string; ts_ms: number; quality: string; raw: Record<string, unknown> | null }
export interface ShiftSnapshot {
  since: string; at: string; unacked: number; warnings: string[];
  alarms: { event_id: number; sensor_id: number; key: string; name: string; state: string; label: string; priority: string; value: number | null; started_at: string; acked: boolean }[];
  work_orders: { id: number; title: string; status: string; priority: string; due_at: string | null; overdue: boolean }[];
  interlock_overrides: { at: string; user_id: number | null; detail: Record<string, unknown> }[];
  alarm_modes: { sensor_id: number; key: string; name: string; mode: string; reason: string; until: string | null }[];
  pending_commands: { id: number; sensor_key: string; value: number; status: string; author_id: number; created_at: string }[];
  stale_sensors: { sensor_id: number; key: string; name: string }[];
}
export interface ShiftHandover { id: number; project_id: number; status: "handed" | "received"; since: string; summary: ShiftSnapshot; notes: string; handed_by: number; handed_by_username: string | null; handed_at: string | null; received_by: number | null; received_by_username: string | null; received_at: string | null; receive_notes: string; warnings: string[] }
export interface RationalizationRow { id: number; project_id: number; key: string; name: string; priority: string; alarm_mode: string; missing: string[] }
export interface RationalizationReport { total: number; rationalized: number; unrationalized: RationalizationRow[] }
export interface MimicSlot { slot: string; label: string; kind: SensorKind }
export interface SchemeElement { id: string; type: string; x: number; y: number; w?: number | undefined; h?: number | undefined; label?: string | undefined; sensor_id?: number | null | undefined; unit?: number | undefined; extra?: Record<string, number | null> | undefined }
export interface Scheme { version: 1; units: number; elements: SchemeElement[] }
export interface PenGroup { name: string; sensor_ids: number[] }
export interface Dashboard {
  sensors: Sensor[];
  units: { sensor_id: number; name: string; running: boolean; power: number | null }[];
  mimic: Record<string, number>;
  slots: MimicSlot[];
  tiles: number[];
  scheme?: Scheme | null;
  pen_groups?: PenGroup[];
  active_alarms: number;
  energy_24h_mwh: number | null;
  alarms_24h: { count: number; by_state: Record<string, number>; unacked: number };
  alarm_flood?: boolean;
  live_clients: number;
}
export interface AlarmKpi {
  since: string; until: string; hours: number; total: number; suppressed: Record<string, number>;
  per_hour: number; per_10min: number; peak_10min: number; flood_threshold_10min: number; flood_time_pct: number; flood_now: boolean; last_10min: number;
  standing: { event_id: number; sensor_id: number; key: string; hours: number }[];
  chattering: { sensor_id: number; key: string; name: string; peak_per_hour: number; count: number }[];
  priority_pct: Record<string, number>; priority_target_pct: Record<string, number>;
  top10: { sensor_id: number; key: string; name: string; count: number; share_pct: number }[]; top10_share_pct: number;
  ack_mean_s: number | null; ack_median_s: number | null; unacked_active: number;
  rating: string; rating_note: string; verdicts: string[]; reference: string;
}
export interface ReportRow { sensor_id: number; key: string; name: string; kind: SensorKind; unit: string; n: number; avg: number | null; min: number | null; max: number | null; energy_mwh: number | null }
export interface Report { project: string; period: "day" | "week" | "month"; start: string; end: string; energy_mwh: number; alarms: { count: number; by_state: Record<string, number>; unacked: number }; sensors: ReportRow[] }
export interface Notification { id: number; kind: "review" | "issue" | "alarm" | "system"; title: string; body: string; link: string; created_at: string; read_at: string | null }
export interface AuditRow { id: number; user_id: number | null; username: string | null; action: string; target_type: string; target_id: number | null; project_id: number | null; detail: Record<string, unknown>; created_at: string }
export interface QtoElement { guid: string; type: string; name: string; storey: string; material: string; volume_m3: number; area_m2: number; footprint_m2: number; length_m: number; width_m: number; height_m: number; bbox: [number[], number[]]; ifc_quantities: Record<string, number> }
export interface Qto { element_count: number; total_volume_m3: number; by_type: Record<string, { count: number; volume_m3: number; area_m2: number }>; by_storey: Record<string, { count: number; volume_m3: number; area_m2: number }>; elements: QtoElement[] }
export interface Clash { kind: "hard" | "possible" | "touch"; a: { model?: string; guid: string; type: string; name: string }; b: { model?: string; guid: string; type: string; name: string }; point: number[]; overlap_m: number[]; overlap_volume_m3: number; triangle_hits: number }
export interface ClashReport { element_count: number; pairs_checked: number; exact: boolean; tolerance: number; hard: number; possible: number; touch: number; clashes: Clash[]; cross_only?: boolean }
export interface FedMember { model_id: number; model_name?: string; version_id?: number | null; version_number?: number; dx: number; dy: number; dz: number; rot_deg: number; error?: string }
export interface Federation { id: number; project_id: number; name: string; description: string; members: FedMember[]; created_by: number; created_at: string; updated_at: string }
export interface ClassificationSystem { title: string; source: string; edition: string; kinds: Record<string, [string, string]> }
export interface LiveMessage {
  type: "snapshot" | "reading" | "alarm" | "command" | "journal" | "ping";
  sensors?: LiveReading[];
  event?: { id: number; sensor_id: number; sensor_name: string; state: AlarmState; value: number | null; started_at: string; ended_at: string | null; acked_by: number | null; acked_at?: string | null; priority?: string };
  command?: Command;
  entry?: JournalEntry;
  sensor_id?: number;
  key?: string;
  value?: number | null;
  ts?: string | null;
  alarm?: AlarmState;
  stale?: boolean | undefined;
  age_s?: number | null;
  quality?: Quality;
  element_guid?: string | null;
  unit?: string;
}
export interface LiveReading { sensor_id: number; key: string; value: number | null; ts: string | null; alarm: AlarmState; stale?: boolean; age_s?: number | null; quality?: Quality; element_guid: string | null; unit: string }

/** Access token faqat xotirada (L2): localStorage da emas — XSS o'qiy olmaydi; sahifa qayta yuklanganda
 * HttpOnly refresh cookie orqali `POST /api/auth/refresh` bilan tiklanadi. */
let accessToken: string | null = null;
const LEGACY_TOKEN_KEY = "ges_token";

export function getToken(): string | null {
  return accessToken;
}
export function setToken(token: string | null) {
  accessToken = token;
  try {
    localStorage.removeItem(LEGACY_TOKEN_KEY); // eski versiyadan qolgan token tozalanadi
  } catch {
    /* private mode */
  }
}

export interface TokenOut { access_token: string; expires_in: number; refresh_token?: string; must_change_password?: boolean }

/** Refresh (cookie bilan). Bir vaqtda bitta so'rov — parallel 401 lar bitta refresh ni kutadi. */
let refreshing: Promise<boolean> | null = null;
export function refreshSession(): Promise<boolean> {
  if (!refreshing) {
    refreshing = (async () => {
      try {
        const res = await fetch("/api/auth/refresh", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: "{}" });
        if (!res.ok) return false;
        const t = (await res.json()) as TokenOut;
        setToken(t.access_token);
        return true;
      } catch {
        return false;
      } finally {
        refreshing = null;
      }
    })();
  }
  return refreshing;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    /** 401 + `X-MFA-Required` — parol to'g'ri, TOTP kodi kerak (L1) */
    public mfaRequired = false,
  ) {
    super(message);
  }
}

let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn;
}

async function request<T>(path: string, init: RequestInit = {}, retried = false): Promise<T> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const res = await fetch(path, { ...init, headers });
  if (res.status === 401 && !res.headers.get("X-MFA-Required") && !path.startsWith("/api/auth/login")) {
    // Access token muddati tugadi (15 daqiqa) — cookie bilan yangilab, so'rovni bir marta takrorlaymiz
    if (!retried && !path.startsWith("/api/auth/refresh") && (await refreshSession())) return request<T>(path, init, true);
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
    throw new ApiError(res.status, detail, res.status === 401 && !!res.headers.get("X-MFA-Required"));
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
  async login(username: string, password: string, otp?: string) {
    const form = new URLSearchParams({ username, password, client: "web" });
    if (otp) form.set("otp", otp);
    const r = await request<TokenOut>("/api/auth/login", {
      method: "POST",
      body: form,
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      credentials: "same-origin",
    });
    setToken(r.access_token);
    return r;
  },
  logout: () => request<void>("/api/auth/logout", { method: "POST", credentials: "same-origin" }),
  logoutAll: () => request<void>("/api/auth/logout-all", { method: "POST", credentials: "same-origin" }),
  sessions: () => request<UserSession[]>("/api/auth/sessions"),
  revokeSession: (id: number) => request<void>(`/api/auth/sessions/${id}`, { method: "DELETE" }),
  wsTicket: () => request<{ ticket: string; expires_in: number }>("/api/auth/ws-ticket", { method: "POST" }),
  me: () => request<User>("/api/auth/me"),
  async changePassword(old_password: string, new_password: string) {
    // Parol o'zgarganda barcha sessiyalar bekor — javobdagi yangi token bilan davom etamiz (L2)
    const t = await request<TokenOut>("/api/auth/change-password", {
      method: "POST",
      body: json({ old_password, new_password }),
      credentials: "same-origin",
    });
    setToken(t.access_token);
    return t;
  },
  // MFA (TOTP, L1)
  mfaSetup: () => request<{ secret: string; otpauth_url: string }>("/api/auth/mfa/setup", { method: "POST" }),
  mfaEnable: (code: string) => request<void>("/api/auth/mfa/enable", { method: "POST", body: json({ code }) }),
  mfaDisable: (password: string, code: string) => request<void>("/api/auth/mfa/disable", { method: "POST", body: json({ password, code }) }),
  // users (admin)
  users: () => request<User[]>("/api/users"),
  createUser: (body: { username: string; password: string; full_name: string; email?: string; is_admin: boolean; must_change_password?: boolean }) =>
    request<User>("/api/users", { method: "POST", body: json(body) }),
  updateUser: (id: number, body: Partial<{ full_name: string; email: string; password: string; is_admin: boolean; is_active: boolean; mfa_reset: boolean; unlock: boolean }>) =>
    request<User>(`/api/users/${id}`, { method: "PATCH", body: json(body) }),
  // projects
  projects: () => request<Project[]>("/api/projects"),
  project: (id: number) => request<Project>(`/api/projects/${id}`),
  createProject: (body: { name: string; description: string; location: string }) =>
    request<Project>("/api/projects", { method: "POST", body: json(body) }),
  updateProject: (id: number, body: Partial<{ name: string; description: string; location: string; ids_required: boolean; epsg_code: number; origin_e: number; origin_n: number; origin_h: number; crs_rotation_deg: number; naming_template: string; naming_required: boolean }>) =>
    request<Project>(`/api/projects/${id}`, { method: "PATCH", body: json(body) }),
  classificationSystems: () => request<Record<string, ClassificationSystem>>("/api/classification/systems"),
  classifyVersion: (versionId: number, system: string, overwrite = false) => request<Version>(`/api/versions/${versionId}/classify`, { method: "POST", body: json({ system, overwrite }) }),
  federations: (projectId: number) => request<Federation[]>(`/api/projects/${projectId}/federations`),
  federation: (id: number) => request<Federation>(`/api/federations/${id}`),
  createFederation: (projectId: number, body: { name: string; description: string; members: FedMember[] }) => request<Federation>(`/api/projects/${projectId}/federations`, { method: "POST", body: json(body) }),
  updateFederation: (id: number, body: { name: string; description: string; members: FedMember[] }) => request<Federation>(`/api/federations/${id}`, { method: "PUT", body: json(body) }),
  deleteFederation: (id: number) => request<void>(`/api/federations/${id}`, { method: "DELETE" }),
  federationClashes: (id: number, tolerance = 0, crossOnly = true) => request<ClashReport>(`/api/federations/${id}/clashes?tolerance=${tolerance}&cross_only=${crossOnly}`),
  async federationIfc(id: number): Promise<Uint8Array> {
    const res = await fetch(`/api/federations/${id}/ifc`, { headers: { Authorization: `Bearer ${getToken() ?? ""}` } });
    if (!res.ok) throw new ApiError(res.status, "Federatsiya IFC yuklab bo'lmadi");
    return new Uint8Array(await res.arrayBuffer());
  },
  documents: (projectId: number) => request<ProjectDocument[]>(`/api/projects/${projectId}/documents`),
  uploadDocument: (projectId: number, file: File, kind: DocKind, title: string) => {
    const fd = new FormData();
    fd.append("file", file); fd.append("kind", kind); fd.append("title", title);
    return request<ProjectDocument>(`/api/projects/${projectId}/documents`, { method: "POST", body: fd });
  },
  deleteDocument: (projectId: number, id: number) => request<void>(`/api/projects/${projectId}/documents/${id}`, { method: "DELETE" }),
  crsConvert: (projectId: number, q: { x: number; y: number; z?: number } | { lat: number; lon: number }) =>
    request<CrsConvert>(`/api/projects/${projectId}/crs/convert?${new URLSearchParams(Object.entries(q).map(([k, v]) => [k, String(v)])).toString()}`),
  crsSuggest: (projectId: number, lat: number, lon: number, family: "utm" | "gk" = "utm") =>
    request<{ epsg: number; name: string; origin_e: number; origin_n: number }>(`/api/projects/${projectId}/crs/suggest?lat=${lat}&lon=${lon}&family=${family}`),
  georeference: (modelId: number, message = "") => request<Version>(`/api/models/${modelId}/georeference`, { method: "POST", body: json({ message }) }),
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
  updateVersion: (id: number, body: { message?: string; tag?: string; suitability_code?: string; revision_code?: string }) => request<Version>(`/api/versions/${id}`, { method: "PATCH", body: json(body) }),
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
  readings: (sensorId: number, hours: number, limit = 600) => request<{ sensor_id: number; unit: string; total: number; points: ReadingPoint[]; hourly: boolean; tier?: "raw" | "1m" | "10m" | "1h" }>(`/api/sensors/${sensorId}/readings?hours=${hours}&limit=${limit}`),
  alarms: (projectId: number) => request<Sensor[]>(`/api/projects/${projectId}/alarms`),
  // BIM tekshiruvlar
  qto: (versionId: number) => request<Qto>(`/api/versions/${versionId}/qto`),
  ids: (versionId: number) => request<IdsResult>(`/api/versions/${versionId}/ids`),
  runIds: (versionId: number) => request<IdsResult>(`/api/versions/${versionId}/ids`, { method: "POST" }),
  clashes: (versionId: number, kind?: string) => request<ClashReport>(`/api/versions/${versionId}/clashes${kind ? `?kind=${kind}` : ""}`),
  // SCADA: alarm jurnali, dispetcher paneli, hisobot, bildirishnomalar, audit
  alarmEvents: (projectId: number, active: boolean, hours = 168, beforeId?: number, includeSuppressed = false) => request<AlarmEvent[]>(`/api/projects/${projectId}/alarm-events?active=${active}&hours=${hours}${beforeId ? `&before_id=${beforeId}` : ""}${includeSuppressed ? "&include_suppressed=true" : ""}`),
  annunciatorSilence: (projectId: number, minutes: number, reason = "") => request<{ ok: boolean; minutes: number }>(`/api/projects/${projectId}/annunciator/silence`, { method: "POST", body: json({ minutes, reason }) }),
  ackAlarmsBatch: (projectId: number, ids: number[], comment = "") => request<{ acked: number }>(`/api/projects/${projectId}/alarm-events/ack-batch`, { method: "POST", body: json({ ids, comment }) }),
  ackAlarm: (id: number, comment = "") => request<AlarmEvent>(`/api/alarm-events/${id}/ack`, { method: "POST", body: json({ comment }) }),
  ackAll: (projectId: number) => request<{ acked: number }>(`/api/projects/${projectId}/alarm-events/ack-all`, { method: "POST" }),
  shelveSensor: (id: number, reason: string, hours?: number) => request<Sensor>(`/api/sensors/${id}/shelve`, { method: "POST", body: json({ reason, hours }) }),
  unshelveSensor: (id: number) => request<Sensor>(`/api/sensors/${id}/unshelve`, { method: "POST" }),
  sensorOutOfService: (id: number, reason: string) => request<Sensor>(`/api/sensors/${id}/out-of-service`, { method: "POST", body: json({ reason }) }),
  sensorInService: (id: number) => request<Sensor>(`/api/sensors/${id}/in-service`, { method: "POST" }),
  rationalizeSensor: (id: number, body: { cause: string; consequence: string; corrective_action: string; response_time_s: number; priority_basis: string }) => request<Sensor>(`/api/sensors/${id}/rationalize`, { method: "POST", body: json(body) }),
  rationalization: (projectId: number) => request<RationalizationReport>(`/api/projects/${projectId}/alarms/rationalization`),
  soe: (projectId: number, hours = 24, point?: string) => request<SoeEvent[]>(`/api/projects/${projectId}/soe?hours=${hours}${point ? `&point=${encodeURIComponent(point)}` : ""}`),
  timeline: (projectId: number, hours = 24) => request<SoeEvent[]>(`/api/projects/${projectId}/timeline?hours=${hours}`),
  shiftSnapshot: (projectId: number) => request<ShiftSnapshot>(`/api/projects/${projectId}/shift/snapshot`),
  shiftHandovers: (projectId: number) => request<ShiftHandover[]>(`/api/projects/${projectId}/shift/handovers`),
  shiftHandover: (projectId: number, notes: string, acknowledge_warnings: boolean) => request<ShiftHandover>(`/api/projects/${projectId}/shift/handover`, { method: "POST", body: json({ notes, acknowledge_warnings }) }),
  shiftReceive: (id: number, notes: string) => request<ShiftHandover>(`/api/shift/handovers/${id}/receive`, { method: "POST", body: json({ notes }) }),
  shiftFeed: (projectId: number, hours = 12) => request<SoeEvent[]>(`/api/projects/${projectId}/shift/feed?hours=${hours}`),
  alarmKpi: (projectId: number, hours = 24) => request<AlarmKpi>(`/api/projects/${projectId}/alarms/kpi?hours=${hours}`),
  adminRationalization: () => request<RationalizationReport>(`/api/admin/alarms/rationalization`),
  dashboard: (projectId: number) => request<Dashboard>(`/api/projects/${projectId}/dashboard`),
  saveDashboard: (projectId: number, body: { mimic: Record<string, number | null>; tiles: number[]; scheme?: Scheme | null; pen_groups?: PenGroup[] }) => request<Dashboard["mimic"]>(`/api/projects/${projectId}/dashboard`, { method: "PUT", body: json(body) }),
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
  validation: (projectId: number) => request<ValidationState>(`/api/projects/${projectId}/validation`),
  createValidation: (projectId: number, body: { days?: number; criteria?: Record<string, number>; note?: string }) => request<ValidationRecord>(`/api/projects/${projectId}/validation`, { method: "POST", body: json(body) }),
  estimator: (projectId: number) => request<EstimatorState>(`/api/projects/${projectId}/estimator`),
  runEstimator: (projectId: number) => request<EstimatorState>(`/api/projects/${projectId}/estimator/run`, { method: "POST" }),
  calibration: (projectId: number) => request<CalibrationState>(`/api/projects/${projectId}/calibration`),
  runCalibration: (projectId: number, body: { days?: number; targets?: string[]; apply?: boolean }) => request<CalibrationRun>(`/api/projects/${projectId}/calibration/run`, { method: "POST", body: json(body) }),
  applyCalibration: (runId: number) => request<{ current: Record<string, unknown>; run: CalibrationRun }>(`/api/calibration/${runId}/apply`, { method: "POST" }),
  revertCalibration: (projectId: number) => request<{ current: Record<string, unknown> }>(`/api/projects/${projectId}/calibration`, { method: "DELETE" }),
  twinRun: (projectId: number) => request<TwinState>(`/api/projects/${projectId}/twin/run`, { method: "POST" }),
  commands: (projectId: number, hours = 168) => request<Command[]>(`/api/projects/${projectId}/commands?hours=${hours}`),
  /** Select-before-operate: 1) select → 30 s li token, 2) execute token bilan */
  selectCommand: (projectId: number, sensor_id: number, value: number, note = "", override?: { reason: string }) => request<SelectResult>(`/api/projects/${projectId}/commands/select${override ? `?override=true&override_reason=${encodeURIComponent(override.reason)}` : ""}`, { method: "POST", body: json({ sensor_id, value, note }) }),
  interlocks: (projectId: number) => request<Interlock[]>(`/api/projects/${projectId}/interlocks`),
  createInterlock: (projectId: number, body: { sensor_id: number; name: string; condition: string; message?: string; enabled?: boolean }) => request<Interlock>(`/api/projects/${projectId}/interlocks`, { method: "POST", body: json(body) }),
  updateInterlock: (id: number, body: Partial<{ name: string; condition: string; message: string; enabled: boolean }>) => request<Interlock>(`/api/interlocks/${id}`, { method: "PATCH", body: json(body) }),
  deleteInterlock: (id: number) => request<void>(`/api/interlocks/${id}`, { method: "DELETE" }),
  executeCommand: (projectId: number, select_token: string, note = "") => request<Command>(`/api/projects/${projectId}/commands/execute`, { method: "POST", body: json({ select_token, note }) }),
  approveCommand: (id: number) => request<Command>(`/api/commands/${id}/approve`, { method: "POST" }),
  cancelCommand: (id: number) => request<Command>(`/api/commands/${id}/cancel`, { method: "POST" }),
  journal: (projectId: number, hours = 168) => request<JournalEntry[]>(`/api/projects/${projectId}/journal?hours=${hours}`),
  addJournal: (projectId: number, text: string, kind: JournalEntry["kind"] = "note") => request<JournalEntry>(`/api/projects/${projectId}/journal`, { method: "POST", body: json({ text, kind }) }),
  assets: (projectId: number) => request<AssetState[]>(`/api/projects/${projectId}/assets`),
  createAsset: (projectId: number, body: { name: string; element_guid?: string | null; power_sensor_id?: number | null; base_run_hours?: number; maintenance_interval_hours?: number | null; parent_id?: number | null; kks_code?: string; taxonomy_level?: string; function_location?: string }) => request<AssetState>(`/api/projects/${projectId}/assets`, { method: "POST", body: json(body) }),
  assetTree: (projectId: number) => request<AssetTree>(`/api/projects/${projectId}/assets/tree`),
  importKks: (projectId: number, file: File) => { const fd = new FormData(); fd.append("file", file); return request<{ created: number; updated: number; errors: string[] }>(`/api/projects/${projectId}/assets/import-kks`, { method: "POST", body: fd }); },
  updateAsset: (id: number, body: { name?: string; power_sensor_id?: number | null; maintenance_interval_hours?: number | null; notes?: string; config?: Record<string, unknown>; parent_id?: number | null; kks_code?: string; taxonomy_level?: string; function_location?: string }) => request<AssetState>(`/api/assets/${id}`, { method: "PATCH", body: json(body) }),
  // H3 — ISO 13374 holat monitoringi
  assetCm: (assetId: number) => request<AssetHealth>(`/api/assets/${assetId}/cm`),
  spectra: (projectId: number, assetId?: number) => request<SpectrumRow[]>(`/api/projects/${projectId}/cm/spectra${assetId ? `?asset_id=${assetId}` : ""}`),
  spectrum: (id: number) => request<SpectrumRow>(`/api/cm/spectra/${id}`),
  cmResults: (projectId: number, assetId?: number) => request<CmExternal[]>(`/api/projects/${projectId}/cm/results${assetId ? `?asset_id=${assetId}` : ""}`),
  health: (projectId: number) => request<HealthReport>(`/api/projects/${projectId}/health`),
  workOrders: (projectId: number, status?: string) => request<WorkOrder[]>(`/api/projects/${projectId}/work-orders${status ? `?status=${status}` : ""}`),
  workOrderKpi: (projectId: number) => request<WorkOrderKpi>(`/api/projects/${projectId}/work-orders/kpi`),
  createWorkOrder: (projectId: number, body: { title: string; description?: string; asset_id?: number | null; assignee_id?: number | null; priority?: string; source?: string; due_at?: string | null; tasks?: WorkOrderTask[]; permit_required?: boolean; labor_rate?: number }) => request<WorkOrder>(`/api/projects/${projectId}/work-orders`, { method: "POST", body: json(body) }),
  updateWorkOrder: (id: number, body: Partial<{ title: string; description: string; assignee_id: number | null; priority: string; status: WorkOrderStatus; due_at: string | null; downtime_hours: number; cost: number; resolution: string; tasks: WorkOrderTask[]; failure_mode: string; failure_cause: string; detection_method: string; labor_rate: number; extra_cost: number; permit_required: boolean }>) => request<WorkOrder>(`/api/work-orders/${id}`, { method: "PATCH", body: json(body) }),
  // H2 — CMMS: rejalar, mehnat, qismlar, ruxsatnoma/LOTO, tarix
  maintenancePlans: (projectId: number) => request<MaintenancePlan[]>(`/api/projects/${projectId}/maintenance-plans`),
  createPlan: (projectId: number, body: { name: string; description?: string; asset_id?: number | null; tasks?: string[]; interval_days?: number | null; interval_hours?: number | null; priority?: string; lead_days?: number; permit_required?: boolean; last_generated_at?: string | null; last_run_hours?: number }) => request<MaintenancePlan>(`/api/projects/${projectId}/maintenance-plans`, { method: "POST", body: json(body) }),
  updatePlan: (id: number, body: Partial<{ name: string; description: string; asset_id: number | null; tasks: string[]; interval_days: number | null; interval_hours: number | null; priority: string; lead_days: number; permit_required: boolean; active: boolean; last_generated_at: string | null; last_run_hours: number }>) => request<MaintenancePlan>(`/api/maintenance-plans/${id}`, { method: "PATCH", body: json(body) }),
  deletePlan: (id: number) => request<void>(`/api/maintenance-plans/${id}`, { method: "DELETE" }),
  runPlans: (projectId: number) => request<WorkOrder[]>(`/api/projects/${projectId}/maintenance-plans/run`, { method: "POST" }),
  workOrderLabor: (id: number) => request<LaborEntry[]>(`/api/work-orders/${id}/labor`),
  addLabor: (id: number, body: { hours: number; note?: string; user_id?: number | null; rate?: number | null }) => request<WorkOrder>(`/api/work-orders/${id}/labor`, { method: "POST", body: json(body) }),
  deleteLabor: (id: number, entryId: number) => request<WorkOrder>(`/api/work-orders/${id}/labor/${entryId}`, { method: "DELETE" }),
  workOrderParts: (id: number) => request<WorkOrderPart[]>(`/api/work-orders/${id}/parts`),
  reserveWorkOrderPart: (id: number, body: { part_id: number; qty: number }) => request<WorkOrderPart[]>(`/api/work-orders/${id}/parts/reserve`, { method: "POST", body: json(body) }),
  consumeWorkOrderPart: (id: number, body: { part_id: number; qty: number; note?: string }) => request<WorkOrderPart[]>(`/api/work-orders/${id}/parts/consume`, { method: "POST", body: json(body) }),
  setPermit: (id: number, body: { status: "none" | "requested" | "issued" | "closed"; note?: string }) => request<WorkOrder>(`/api/work-orders/${id}/permit`, { method: "POST", body: json(body) }),
  setLoto: (id: number, body: { active: boolean; points?: { label?: string; sensor_id?: number }[]; note?: string }) => request<WorkOrder>(`/api/work-orders/${id}/loto`, { method: "POST", body: json(body) }),
  activeLoto: (projectId: number) => request<{ items: LotoEntry[] }>(`/api/projects/${projectId}/loto`),
  cmmsCodes: () => request<CmmsCodes>("/api/cmms/codes"),
  assetHistory: (assetId: number) => request<AssetHistory>(`/api/assets/${assetId}/history`),
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
  assetRegister: (versionId: number) => request<AssetRegister>(`/api/versions/${versionId}/assets/register`),
  assetsFromIfc: (projectId: number, versionId: number) => request<{ created: number; updated: number; components: number; assets: AssetState[] }>(`/api/projects/${projectId}/assets/from-ifc`, { method: "POST", body: json({ version_id: versionId }) }),
  assetDocuments: (assetId: number) => request<AssetDocument[]>(`/api/assets/${assetId}/documents`),
  uploadAssetDocument: (assetId: number, file: File, kind: AssetDocKind, title: string) => {
    const fd = new FormData();
    fd.append("file", file); fd.append("kind", kind); fd.append("title", title);
    return request<AssetDocument>(`/api/assets/${assetId}/documents`, { method: "POST", body: fd });
  },
  deleteAssetDocument: (assetId: number, id: number) => request<void>(`/api/assets/${assetId}/documents/${id}`, { method: "DELETE" }),
  snapshot: (projectId: number, at: string) => request<Snapshot>(`/api/projects/${projectId}/snapshot?at=${encodeURIComponent(at)}`),
  notifications: (unread = false, limit = 50) => request<Notification[]>(`/api/notifications?unread=${unread}&limit=${limit}`),
  notificationCount: () => request<{ unread: number }>("/api/notifications/count"),
  markRead: (ids: number[] | null) => request<{ read: number }>("/api/notifications/read", { method: "POST", body: json({ ids }) }),
  audit: (q: { project_id?: number | undefined; action?: string | undefined; user_id?: number | undefined; limit?: number; before_id?: number | undefined }) => {
    const qs = Object.entries(q).filter(([, v]) => v != null && v !== "").map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`).join("&");
    return request<AuditRow[]>(`/api/audit${qs ? `?${qs}` : ""}`);
  },
  ingestKey: (projectId: number) => request<{ ingest_key: string; url: string }>(`/api/projects/${projectId}/ingest-key`),
  rotateIngestKey: (projectId: number) => request<{ ingest_key: string }>(`/api/projects/${projectId}/ingest-key`, { method: "POST" }),
  /** Gateway kalitlari (B3): ingest — faqat o'lchov (X-Ingest-Key); command — buyruq kanali (X-Command-Key) */
  projectKey: (projectId: number, kind: GatewayKeyKind) => request<GatewayKey>(`/api/projects/${projectId}/keys/${kind}`),
  rotateProjectKey: (projectId: number, kind: GatewayKeyKind, ttlDays = 365) => request<GatewayKey>(`/api/projects/${projectId}/keys/${kind}?ttl_days=${ttlDays}`, { method: "POST" }),
  pushReadings: (projectId: number, items: { key?: string; sensor_id?: number; value: number; ts?: string }[]) =>
    request<{ accepted: number; unknown: unknown[] }>(`/api/projects/${projectId}/readings`, { method: "POST", body: json(items) }),
  importReadings: (sensorId: number, file: File) => { const fd = new FormData(); fd.append("file", file); return request<{ accepted: number }>(`/api/sensors/${sensorId}/import`, { method: "POST", body: fd }); },
  /** Jonli oqim: avval 60 s li chipta (sessiya tokeni URL ga tushmaydi, L2), keyin soket. */
  async liveSocket(projectId: number): Promise<WebSocket> {
    const { ticket } = await api.wsTicket();
    const proto = location.protocol === "https:" ? "wss" : "ws";
    return new WebSocket(`${proto}://${location.host}/api/projects/${projectId}/live?ticket=${encodeURIComponent(ticket)}`);
  },
};
