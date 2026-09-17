import { useState } from "react";
import Icon from "../../ui/Icon";
import { api, type Diff, type Model, type Version } from "../../api/client";
import { fmtDate, fmtSize, ifcLabel, label } from "../../ui/format";
import Dialog from "../../ui/Dialog";

interface Props {
  model: Model;
  versions: Version[];
  current: Version | null;
  canEdit: boolean;
  diff: Diff | null;
  onOpen: (v: Version) => void;
  onUploaded: (v: Version) => void;
  onDiff: (v: Version, from?: number) => void;
  onClearDiff: () => void;
  onPickGuid: (guid: string) => void;
}

export default function VersionsPanel({ model, versions, current, canEdit, diff, onOpen, onUploaded, onDiff, onClearDiff, onPickGuid }: Props) {
  const [uploading, setUploading] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [demOpen, setDemOpen] = useState(false);
  const [dem, setDem] = useState({ lat: 41.622, lon: 69.981, width_m: 1500, height_m: 3000, rotation_deg: 0, zoom: 13, nx: 120, z_offset_m: 0 });
  const [error, setError] = useState("");
  const [compareFrom, setCompareFrom] = useState<string>("");
  const [meshOpts, setMeshOpts] = useState({ unit: "m", y_up: false, merge: false, onto_current: true, extrude_m: 0 });
  const isCad = !!file && /\.(dxf|dwg)$/i.test(file.name);
  const isImage = !!file && /\.(png|jpe?g|tiff?|bmp|webp)$/i.test(file.name);
  const isMesh = !!file && !isImage && !file.name.toLowerCase().endsWith(".ifc");
  const [imgOpts, setImgOpts] = useState<{ mode: "drawing" | "heightmap" | "photo"; width_m: number; extrude_m: number; z_min: number; z_max: number; grid: number; min_area_px: number; invert: boolean; onto_current: boolean }>({ mode: "drawing", width_m: 100, extrude_m: 3, z_min: 0, z_max: 100, grid: 160, min_area_px: 40, invert: false, onto_current: true });

  async function upload(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      const v = isImage
        ? await api.importImageVersion(model.id, file, { message, ...imgOpts })
        : isMesh
          ? await api.importMeshVersion(model.id, file, { message, ...meshOpts })
          : await api.uploadVersion(model.id, file, message, current?.id);
      setUploading(false);
      setFile(null);
      setMessage("");
      onUploaded(v);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Yuklash amalga oshmadi");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      {canEdit && (
        <div className="row" style={{ marginBottom: 8, gap: 6 }}>
          <button className="btn sm primary" onClick={() => setUploading(true)}>Yangi versiya yuklash</button>
          <button className="btn sm" title="Haqiqiy relyef (SRTM/ASTER, AWS Terrain Tiles, internet kerak): markaz lat/lon, maydon va burilish — parametrik relyef o'rniga yangi versiya" onClick={() => setDemOpen(true)}><Icon name="layers" size={12} /> Relyef (DEM)</button>
        </div>
      )}
      {demOpen && (
        <Dialog title="Haqiqiy relyef (DEM) import" onClose={() => setDemOpen(false)}>
          <form onSubmit={async (e) => { e.preventDefault(); setBusy(true); setError(""); try { const v = await api.importDem(model.id, { ...dem, message: `Haqiqiy relyef (DEM): ${dem.lat}, ${dem.lon}` }); setDemOpen(false); onUploaded(v); } catch (err) { setError(err instanceof Error ? err.message : "Xatolik"); } finally { setBusy(false); } }}>
            <div className="dim small" style={{ marginBottom: 6 }}>Manba: AWS Terrain Tiles (Mapzen terrarium — SRTM/ASTER/GMTED), zoom 12 ≈ 30 m, 13 ≈ 15 m, 14 ≈ 7 m piksel. X o'qi — to'g'on gerbi yo'nalishi (burilish sharqdan gradus), +Y — yuqori byef. «Relyef (vodiy)» / eski DEM o'rniga qo'yiladi. Chorvoq to'g'oni ≈ 41.622, 69.981.</div>
            <div className="row wrap">
              <label className="field" style={{ width: 120 }}><span>Kenglik (lat)</span><input className="input" type="number" step="any" value={dem.lat} onChange={(e) => setDem({ ...dem, lat: Number(e.target.value) })} /></label>
              <label className="field" style={{ width: 120 }}><span>Uzunlik (lon)</span><input className="input" type="number" step="any" value={dem.lon} onChange={(e) => setDem({ ...dem, lon: Number(e.target.value) })} /></label>
              <label className="field" style={{ width: 110 }}><span>X o'lcham, m</span><input className="input" type="number" min="200" value={dem.width_m} onChange={(e) => setDem({ ...dem, width_m: Number(e.target.value) })} /></label>
              <label className="field" style={{ width: 110 }}><span>Y o'lcham, m</span><input className="input" type="number" min="200" value={dem.height_m} onChange={(e) => setDem({ ...dem, height_m: Number(e.target.value) })} /></label>
              <label className="field" style={{ width: 100 }}><span>Burilish, °</span><input className="input" type="number" step="any" value={dem.rotation_deg} onChange={(e) => setDem({ ...dem, rotation_deg: Number(e.target.value) })} /></label>
              <label className="field" style={{ width: 80 }}><span>Zoom</span><input className="input" type="number" min="8" max="14" value={dem.zoom} onChange={(e) => setDem({ ...dem, zoom: Number(e.target.value) })} /></label>
              <label className="field" style={{ width: 90 }}><span>Panjara</span><input className="input" type="number" min="8" max="400" value={dem.nx} onChange={(e) => setDem({ ...dem, nx: Number(e.target.value) })} /></label>
              <label className="field" style={{ width: 100 }}><span>Z siljish, m</span><input className="input" type="number" step="any" value={dem.z_offset_m} onChange={(e) => setDem({ ...dem, z_offset_m: Number(e.target.value) })} /></label>
            </div>
            {error && <p className="error small">{error}</p>}
            <div className="actions">
              <button type="button" className="btn" onClick={() => setDemOpen(false)}>Bekor qilish</button>
              <button type="submit" className="btn primary" disabled={busy}>{busy ? "Yuklanmoqda…" : "Import"}</button>
            </div>
          </form>
        </Dialog>
      )}
      {versions.length === 0 && <p className="muted">Hali versiya yo'q. {canEdit ? "IFC yoki Blender/3ds Max/AutoCAD (OBJ, glTF, STL, DXF) fayl yuklang." : ""}</p>}
      {versions.map((v) => (
        <div key={v.id} className={`list-item${current?.id === v.id ? " selected" : ""}`} onClick={() => onOpen(v)}>
          <div className="title">
            <b>v{v.number}</b>
            <span className={`badge ${v.state}`}>{label(v.state)}</span>
            {v.tag && <span className="badge open" title="Yorliq"><Icon name="tag" size={11} /> {v.tag}</span>}
            <button className="btn sm" title="Blender / 3ds Max uchun yuklab olish (glTF, nom va GUID saqlanadi)" onClick={(e) => { e.stopPropagation(); api.downloadCsv(`/api/versions/${v.id}/export?fmt=glb`, `${model.name}_v${v.number}.glb`).catch((er) => setError(er.message)); }}><Icon name="download" size={11} /> glb</button>
            <span className="grow">{v.message || <span className="dim">izohsiz</span>}</span>
          </div>
          <div className="meta">
            {v.author_username} · {fmtDate(v.created_at)} · {fmtSize(v.file_size)} · {v.meta.element_count ?? "?"} element
            {v.parent_id && <> · ota: v{versions.find((p) => p.id === v.parent_id)?.number ?? "?"}</>}
          </div>
          {current?.id === v.id && (
            <div className="row wrap" style={{ marginTop: 6 }} onClick={(e) => e.stopPropagation()}>
              <a className="btn sm" href={api.versionFileUrl(v.id)} onClick={(e) => { e.preventDefault(); void download(v); }}>IFC yuklab olish</a>
              {canEdit && versions[0]?.id !== v.id && <button className="btn sm" title="Shu versiya faylidan yangi (oxirgi) versiya yaratiladi — tarix saqlanadi" onClick={() => confirm(`v${v.number} ni qayta tiklab, yangi versiya yaratilsinmi?`) && api.restoreVersion(v.id).then(onUploaded).catch((e) => alert(e.message))}>Qayta tiklash</button>}
              {canEdit && <button className="btn sm" title="Izoh / yorliq" onClick={() => { const message = prompt("Izoh:", v.message); if (message == null) return; const tag = prompt("Yorliq (bo'sh — yo'q; faqat tasdiqlovchi):", v.tag ?? ""); api.updateVersion(v.id, { message, ...(tag != null && tag !== (v.tag ?? "") ? { tag } : {}) }).then(() => onUploaded(v)).catch((e) => alert(e.message)); }}>Izoh/yorliq</button>}
              {v.parent_id && !diff && <button className="btn sm" onClick={() => onDiff(v)}>Ota bilan farq</button>}
              {versions.length > 1 && !diff && (
                <select className="select" style={{ width: "auto" }} value={compareFrom}
                  onChange={(e) => { setCompareFrom(""); if (e.target.value) onDiff(v, Number(e.target.value)); }}>
                  <option value="">Solishtirish…</option>
                  {versions.filter((o) => o.id !== v.id).map((o) => <option key={o.id} value={o.id}>v{o.number}</option>)}
                </select>
              )}
              {diff && <button className="btn sm" onClick={onClearDiff}>Farqni yopish</button>}
            </div>
          )}
        </div>
      ))}

      {diff && (
        <div className="section-box" style={{ marginTop: 10 }}>
          <b>Farq: v{versions.find((x) => x.id === diff.from_version_id)?.number} → v{versions.find((x) => x.id === diff.to_version_id)?.number}</b>
          <div className="diff-legend">
            <span><i style={{ background: "#2ecc71" }} />Qo'shilgan {diff.summary.added}</span>
            <span><i style={{ background: "#f1c40f" }} />O'zgargan {diff.summary.changed}</span>
            <span><i style={{ background: "#e74c3c" }} />O'chirilgan {diff.summary.deleted}</span>
          </div>
          <div className="diff-list">
            {diff.added.map((d) => <div key={d.guid} onClick={() => onPickGuid(d.guid)}><span style={{ color: "#2ecc71" }}>+</span>{ifcLabel(d.type)} {d.name}<span className="g">{d.guid}</span></div>)}
            {diff.changed.map((d) => <div key={d.guid} onClick={() => onPickGuid(d.guid)}><span style={{ color: "#f1c40f" }}>~</span>{ifcLabel(d.type)} {d.name}<span className="g">{d.changes?.join(", ")}</span></div>)}
            {diff.deleted.map((d) => <div key={d.guid} title="Joriy modelda yo'q"><span style={{ color: "#e74c3c" }}>−</span>{ifcLabel(d.type)} {d.name}<span className="g">{d.guid}</span></div>)}
          </div>
        </div>
      )}

      {uploading && (
        <Dialog title={`Yangi versiya — ${model.name}`} onClose={() => setUploading(false)}>
          <form onSubmit={upload}>
            <label className="field">
              <span>Fayl — IFC, CAD (STEP, IGES, BREP), Blender / 3ds Max / Maya (FBX, 3DS, OBJ, glTF/GLB, DAE, LWO, X, 3MF, STL, PLY, AMF, X3D…), AutoCAD (DWG, DXF), ZIP (obj+mtl, gltf+bin), <b>rasm</b> (PNG/JPG/TIFF — skanerlangan chizma, balandlik xaritasi, foto)</span>
              <input className="input" type="file" accept=".ifc,.obj,.stl,.ply,.gltf,.glb,.dae,.3mf,.off,.dxf,.zae,.zip,.fbx,.3ds,.lwo,.lws,.x,.ase,.ac,.ms3d,.cob,.ogex,.b3d,.md2,.md3,.md5mesh,.smd,.nff,.amf,.irrmesh,.x3d,.dwg,.blend,.step,.stp,.iges,.igs,.brep,.brp,.png,.jpg,.jpeg,.tif,.tiff,.bmp,.webp" onChange={(e) => setFile(e.target.files?.[0] ?? null)} required />
            </label>
            {isMesh && (
              <div className="section-box small">
                <div className="dim" style={{ marginBottom: 6 }}>Fayl IFC ga aylantiriladi: har obyekt — alohida element (nomi, rangi saqlanadi); obyekt nomida «togon/dam», «penstock/quvur», «turbina», «spillway» bo'lsa GES turi va Pset avtomatik. Birlik glTF/DXF dan avto aniqlanadi. Rang uchun OBJ ni MTL bilan ZIP qilib yuklang. STEP/IGES — har jism alohida, nomi va rangi bilan (mm). FBX/3DS/LWO — obyekt nomlari va materiallar (assimp). .max/.skp — dasturdan FBX/glTF/OBJ ga eksport qiling. AutoCAD DXF/DWG: 3DFACE/MESH/polyface o'qiladi (qatlam = element nomi, rangi), 3DSOLID (ACIS) — AutoCAD da MESHSMOOTH yoki EXPORT → OBJ; 2D chizma (plan/kesim) AutoCAD dagidek — o'lchamlar, matn, shtrix, ranglar bilan — tekis varaq bo'lib chiqadi; devor/plita qilish uchun «ko'tarish» balandligini kiriting.</div>
                <div className="row wrap">
                  <label className="field" style={{ width: 120 }}><span>Fayl birligi</span><select className="select" value={meshOpts.unit} onChange={(e) => setMeshOpts({ ...meshOpts, unit: e.target.value })}><option value="m">metr</option><option value="cm">santimetr</option><option value="mm">millimetr</option><option value="in">dyuym</option><option value="ft">fut</option></select></label>
                  <label className="row small field-check"><input type="checkbox" checked={meshOpts.y_up} onChange={(e) => setMeshOpts({ ...meshOpts, y_up: e.target.checked })} /> Y yuqoriga (glTF, ba'zi eksportlar)</label>
                  <label className="row small field-check"><input type="checkbox" checked={meshOpts.merge} onChange={(e) => setMeshOpts({ ...meshOpts, merge: e.target.checked })} /> bitta elementga birlashtirish</label>
                  <label className="row small field-check"><input type="checkbox" checked={meshOpts.onto_current} onChange={(e) => setMeshOpts({ ...meshOpts, onto_current: e.target.checked })} /> joriy model ustiga qo'shish</label>
                  {isCad && <label className="field" style={{ width: 200 }}><span>2D konturlarni ko'tarish (m; 0 — faqat 3D)</span><input className="input" type="number" step="any" min="0" value={meshOpts.extrude_m} onChange={(e) => setMeshOpts({ ...meshOpts, extrude_m: Number(e.target.value) || 0 })} /></label>}
                </div>
              </div>
            )}
            {isImage && (
              <div className="section-box small">
                <div className="dim" style={{ marginBottom: 6 }}><b>Rasmdan raqamli egizak.</b> Chizma (skanerlangan plan/kesim): qora chiziqlar konturlarga ajratilib berilgan balandlikka ko'tariladi — devor/to'g'on konturi bo'ladi (har kontur alohida element). Balandlik xaritasi (DEM, kulrang): yorug'lik → balandlik, relyef yuzasi. Foto: taxminiy relyef (faqat ko'rgazma). Masshtab — rasm kengligi metrda.</div>
                <div className="row wrap">
                  <label className="field" style={{ width: 200 }}><span>Rejim</span><select className="select" value={imgOpts.mode} onChange={(e) => setImgOpts({ ...imgOpts, mode: e.target.value as "drawing" | "heightmap" | "photo" })}><option value="drawing">Chizma (plan/kesim) → devorlar</option><option value="heightmap">Balandlik xaritasi (DEM) → relyef</option><option value="photo">Foto → taxminiy relyef</option></select></label>
                  <label className="field" style={{ width: 150 }}><span>Rasm kengligi, m</span><input className="input" type="number" step="any" min="0.1" value={imgOpts.width_m} onChange={(e) => setImgOpts({ ...imgOpts, width_m: Number(e.target.value) || 100 })} /></label>
                  {imgOpts.mode === "drawing" && <label className="field" style={{ width: 150 }}><span>Ko'tarish balandligi, m</span><input className="input" type="number" step="any" min="0.01" value={imgOpts.extrude_m} onChange={(e) => setImgOpts({ ...imgOpts, extrude_m: Number(e.target.value) || 3 })} /></label>}
                  {imgOpts.mode === "drawing" && <label className="field" style={{ width: 150 }}><span>Minimal kontur, px²</span><input className="input" type="number" min="1" value={imgOpts.min_area_px} onChange={(e) => setImgOpts({ ...imgOpts, min_area_px: Number(e.target.value) || 40 })} /></label>}
                  {imgOpts.mode !== "drawing" && <label className="field" style={{ width: 120 }}><span>Z min, m</span><input className="input" type="number" step="any" value={imgOpts.z_min} onChange={(e) => setImgOpts({ ...imgOpts, z_min: Number(e.target.value) || 0 })} /></label>}
                  {imgOpts.mode !== "drawing" && <label className="field" style={{ width: 120 }}><span>Z max, m</span><input className="input" type="number" step="any" value={imgOpts.z_max} onChange={(e) => setImgOpts({ ...imgOpts, z_max: Number(e.target.value) || 100 })} /></label>}
                  {imgOpts.mode !== "drawing" && <label className="field" style={{ width: 120 }}><span>Panjara (8–400)</span><input className="input" type="number" min="8" max="400" value={imgOpts.grid} onChange={(e) => setImgOpts({ ...imgOpts, grid: Number(e.target.value) || 160 })} /></label>}
                  <label className="row small field-check"><input type="checkbox" checked={imgOpts.invert} onChange={(e) => setImgOpts({ ...imgOpts, invert: e.target.checked })} /> teskari (oq chiziqlar / pastlik och)</label>
                  <label className="row small field-check"><input type="checkbox" checked={imgOpts.onto_current} onChange={(e) => setImgOpts({ ...imgOpts, onto_current: e.target.checked })} /> joriy model ustiga qo'shish</label>
                </div>
              </div>
            )}
            <label className="field">
              <span>Nima o'zgardi (commit izohi)</span>
              <textarea className="textarea" value={message} onChange={(e) => setMessage(e.target.value)} placeholder="Masalan: mashina zali devorlari qayta chizildi" />
            </label>
            {current && <p className="dim small">Ota versiya: v{current.number}</p>}
            {error && <p className="error small">{error}</p>}
            <div className="actions">
              <button type="button" className="btn" onClick={() => setUploading(false)}>Bekor qilish</button>
              <button type="submit" className="btn primary" disabled={busy || !file}>{busy ? "Yuklanmoqda…" : "Yuklash"}</button>
            </div>
          </form>
        </Dialog>
      )}
    </div>
  );
}

async function download(v: Version) {
  const bytes = await api.versionFile(v.id);
  const url = URL.createObjectURL(new Blob([bytes.buffer as ArrayBuffer], { type: "application/x-step" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = `v${v.number}_${v.file_name}`;
  a.click();
  URL.revokeObjectURL(url);
}
