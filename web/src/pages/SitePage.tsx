import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, type GenericParams, type MaterialsCatalog, type Project, type SimField, type SiteRisk } from "../api/client";
import TopBar from "../ui/TopBar";
import Icon from "../ui/Icon";
import SimForm from "./model/sim/SimForm";

/** Maydon pasporti: yer/grunt, seysmiklik, ombor, to'g'on, quvur, quyi byef, inshoot belgilari, yonbag'irlar.
    Bir marta to'ldiriladi — simulyatsiyalar va egizak xavfsizlik ko'rsatkichlari shu yerdan oladi. */
export default function SitePage() {
  const { projectId } = useParams();
  const pid = Number(projectId);
  const nav = useNavigate();
  const [project, setProject] = useState<Project | null>(null);
  const [fields, setFields] = useState<SimField[]>([]);
  const [values, setValues] = useState<GenericParams>({});
  const [filled, setFilled] = useState(false);
  const [risks, setRisks] = useState<SiteRisk[]>([]);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");
  const [busy, setBusy] = useState(false);
  const [mats, setMats] = useState<MaterialsCatalog | null>(null);
  const canEdit = project?.my_role === "engineer" || project?.my_role === "approver";

  useEffect(() => {
    (async () => {
      try {
        const [p, cat, st] = await Promise.all([api.project(pid), api.simCatalog(), api.site(pid)]);
        setProject(p); setFields(cat.site_fields); setValues(st.values); setFilled(st.filled); setRisks(st.risks);
      } catch (e) { setError(e instanceof Error ? e.message : "Xatolik"); }
    })();
  }, [pid]);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(""); setSaved("");
    try {
      const st = await api.saveSite(pid, values);
      setValues(st.values); setFilled(true); setRisks(st.risks); setSaved("Saqlandi");
    } catch (err) { setError(err instanceof Error ? err.message : "Xatolik"); } finally { setBusy(false); }
  }

  return (
    <div className="page">
      <TopBar crumbs={[{ label: "Loyihalar", to: "/" }, { label: project?.name ?? "…", to: `/projects/${pid}` }, { label: "Maydon pasporti" }]}>
        <button className="btn sm" onClick={() => nav(`/projects/${pid}`)}>Loyiha</button>
        <button className="btn sm" onClick={() => nav(`/projects/${pid}/dashboard`)}>Dispetcher paneli</button>
      </TopBar>
      <div className="page-body" style={{ maxWidth: 1100 }}>
        <h1 className="row" style={{ alignItems: "center", gap: 10 }}><Icon name="mountain" size={22} /> Maydon pasporti</h1>
        <p className="muted small">GES joylashgan yer va inshootlar sharoitlari: tuproq va seysmiklik, suv ombori sathlari va hajmi, to'g'on va suv tashlagich o'lchamlari,
          bosimli quvur, quyi byef va daryo o'zani, inshootlarning suv sathidan balandligi, yonbag'irlar (ko'chki xavfi). Bir marta kiriting — barcha simulyatsiyalar
          («Modeldan / Jonli holatdan» bilan birga) va dispetcher panelidagi xavfsizlik ko'rsatkichlari shu ma'lumotlardan foydalanadi.
          {!filled && <b> Hali to'ldirilmagan — standart qiymatlar ko'rsatilmoqda.</b>}</p>
        {error && <p className="error">{error}</p>}
        {risks.length > 0 && (
          <div className="section-box">
            <b>Tezkor xavf ko'rsatkichlari</b>
            <table className="grid small" style={{ marginTop: 6 }}>
              <tbody>{risks.map((r) => (
                <tr key={r.name}><td><Icon name={r.ok ? "check-circle" : "alert-triangle"} size={13} style={{ color: r.ok ? "var(--ok)" : "var(--danger)" }} /></td><td>{r.name}</td><td className="mono">{r.value} {r.unit}</td><td className="dim">{r.note}</td></tr>
              ))}</tbody>
            </table>
          </div>
        )}
        <details className="section-box" onToggle={(e) => { if ((e.target as HTMLDetailsElement).open && !mats) api.materials().then(setMats).catch(() => undefined); }}>
          <summary><b>Materiallar ma'lumotnomasi</b> — beton klasslari (KMK 2.03.01), zonalar bo'yicha tavsiya, po'lat markalari, gruntlar</summary>
          {mats ? (
            <div className="small" style={{ marginTop: 8 }}>
              <table className="grid small"><thead><tr><th>Beton</th><th>R_b, MPa</th><th>R_bt, MPa</th><th>E, MPa</th><th>γ, kN/m³</th><th>Qo'llanish</th></tr></thead>
                <tbody>{mats.concrete.map((c) => <tr key={c.id}><td><b>{c.name}</b></td><td className="mono">{c.Rb}</td><td className="mono">{c.Rbt}</td><td className="mono">{c.E}</td><td className="mono">{c.gamma}</td><td className="dim">{c.use}</td></tr>)}</tbody></table>
              <table className="grid small" style={{ marginTop: 8 }}><thead><tr><th>Zona</th><th>Tavsiya</th><th>Sabab</th></tr></thead>
                <tbody>{mats.zones.map((z) => <tr key={z.zone}><td><b>{z.zone}</b></td><td>{z.concrete}</td><td className="dim">{z.why}</td></tr>)}</tbody></table>
              <table className="grid small" style={{ marginTop: 8 }}><thead><tr><th>Po'lat</th><th>σ_T, MPa</th><th>σ_B, MPa</th><th>Izoh</th></tr></thead>
                <tbody>{mats.steel.map((s) => <tr key={s.id}><td><b>{s.name}</b></td><td className="mono">{s.yield}</td><td className="mono">{s.ult}</td><td className="dim">{s.note}</td></tr>)}</tbody></table>
              <table className="grid small" style={{ marginTop: 8 }}><thead><tr><th>Grunt</th><th>γ</th><th>φ°</th><th>c, kPa</th><th>k, m/s</th><th>Izoh</th></tr></thead>
                <tbody>{mats.soil.map((s) => <tr key={s.id}><td><b>{s.name}</b></td><td className="mono">{s.gamma}</td><td className="mono">{s.phi}</td><td className="mono">{s.c}</td><td className="mono">{s.k}</td><td className="dim">{s.note}</td></tr>)}</tbody></table>
              <p className="dim">Sement: {mats.cement.map((c) => `${c.name} — ${c.q} °C/(kg/m³), ${c.note}`).join("; ")}</p>
            </div>
          ) : <p className="muted small">Yuklanmoqda…</p>}
        </details>
        <form onSubmit={save}>
          <div className="site-form">
            <SimForm fields={fields} values={values} onChange={(k, v) => setValues((p) => ({ ...p, [k]: v }))} />
          </div>
          {canEdit ? (
            <div className="row" style={{ marginTop: 10, alignItems: "center" }}>
              <button className="btn primary" type="submit" disabled={busy}>{busy ? "…" : "Saqlash"}</button>
              {saved && <span className="muted small"><Icon name="check" size={12} /> {saved}</span>}
              <span className="grow" />
              <button className="btn sm" type="button" onClick={() => nav(`/projects/${pid}`)}>Loyihaga qaytish</button>
            </div>
          ) : <p className="muted small">Faqat muhandis/tasdiqlovchi o'zgartira oladi.</p>}
        </form>
      </div>
    </div>
  );
}
