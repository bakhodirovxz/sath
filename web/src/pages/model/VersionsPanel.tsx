import { useState } from "react";
import { dialogs } from "../../ui/dialogs";
import Icon from "../../ui/Icon";
import { api, type Diff, type Model, type Version } from "../../api/client";
import { fmtDate, fmtSize, ifcLabel, label } from "../../ui/format";
import Dialog from "../../ui/Dialog";
import { BBadge, BList, BOps, BPanel, BRow } from "../../ui/BlenderUI";

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
  // Blender: ro'yxatda tanlash (faol) — ochishdan alohida; ikki marta bosish/Enter/«Ochish» — modelni yuklaydi
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const selected = versions.find((v) => v.id === selectedId) ?? current ?? versions[0] ?? null;
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
      <BPanel id="versions" title="Versiyalar" count={versions.length} right={canEdit && (
        <>
          <button className="btn sm primary" onClick={() => setUploading(true)} title="IFC / CAD / mesh / rasm yuklash — yangi versiya"><Icon name="upload" size={12} /> Yangi</button>
          <button className="btn sm" title="Haqiqiy relyef (SRTM/ASTER, internet kerak) — yangi versiya" onClick={() => setDemOpen(true)}><Icon name="layers" size={12} /> DEM</button>
        </>
      )}>
        <BList
          items={versions} keyOf={(v) => v.id} activeKey={selected?.id ?? null} rows={6}
          onSelect={(v) => setSelectedId(v.id)} onActivate={(v) => onOpen(v)}
          empty={canEdit ? "Hali versiya yo'q — IFC yoki Blender/AutoCAD fayl yuklang" : "Hali versiya yo'q"}
          render={(v) => (
            <>
              <b style={{ minWidth: 28 }}>v{v.number}</b>
              {current?.id === v.id && <Icon name="eye" size={12} title="ochiq" />}
              <span className="grow">{v.message || <span className="dim">izohsiz</span>}</span>
              {v.suitability_code && <BBadge kind={v.state === "published" ? "approved" : "open"} title={`ISO 19650 yaroqlilik: ${v.suitability_label ?? ""}`}>{v.suitability_code}{v.revision_code ? ` ${v.revision_code}` : ""}</BBadge>}
              {v.tag && <BBadge kind="open" title="Yorliq">{v.tag}</BBadge>}
              {v.ids_status && <BBadge kind={v.ids_status === "pass" ? "approved" : v.ids_status === "fail" ? "rejected" : "open"} title="IDS tekshiruvi (G2)">IDS {v.ids_status === "pass" ? "✓" : v.ids_status === "fail" ? "✗" : "?"}</BBadge>}
              <BBadge kind={v.state}>{label(v.state)}</BBadge>
              <span className="dim mono">{fmtDate(v.created_at).slice(0, 10)}</span>
            </>
          )}
        />
      </BPanel>
      {selected && (
        <BPanel id="version-detail" title={`v${selected.number}${current?.id === selected.id ? " (ochiq)" : ""}`}>
          <BRow label="Izoh" value={selected.message || ""} />
          <BRow label="Muallif" value={selected.author_username} />
          <BRow label="Sana" value={fmtDate(selected.created_at)} />
          <BRow label="Fayl" value={`${fmtSize(selected.file_size)} · ${selected.meta.element_count ?? "?"} element · ${selected.meta.schema ?? "IFC"}`} />
          <BRow label="ISO 19650" value={selected.suitability_code ? `${selected.suitability_code} — ${selected.suitability_label ?? ""}${selected.revision_code ? ` · reviziya ${selected.revision_code}` : ""}` : "—"} />
          <BRow label="Klassifikatsiya" value={selected.meta.classification?.classified ? `${selected.meta.classification.classified} element · ${Object.keys(selected.meta.classification.systems).join(", ")}` : "yo'q"} />
          <BRow label="Georeferensiya" value={selected.meta.georef?.epsg ? `EPSG:${selected.meta.georef.epsg} · E ${selected.meta.georef.origin_e?.toFixed(1)} N ${selected.meta.georef.origin_n?.toFixed(1)}${selected.meta.georef.rotation_deg ? ` · ${selected.meta.georef.rotation_deg}°` : ""}` : selected.meta.georef?.site_lat != null ? `faqat IfcSite ${selected.meta.georef.site_lat.toFixed(4)}, ${selected.meta.georef.site_lon?.toFixed(4)}` : "yo'q"} />
          {selected.meta.warnings?.map((w, i) => <p key={i} className="verdict warn small" data-testid="version-warning">{w}</p>)}
          {selected.parent_id && <BRow label="Ota" value={`v${versions.find((p) => p.id === selected.parent_id)?.number ?? "?"}`} />}
          <BOps>
            {current?.id !== selected.id && <button className="btn sm primary" onClick={() => onOpen(selected)}><Icon name="eye" size={12} /> Ochish</button>}
            <button className="btn sm" onClick={() => void download(selected)} title="IFC faylini yuklab olish"><Icon name="download" size={12} /> IFC</button>
            <button className="btn sm" title="Blender / 3ds Max uchun (glTF, nom va GUID saqlanadi)" onClick={() => api.downloadCsv(`/api/versions/${selected.id}/export?fmt=glb`, `${model.name}_v${selected.number}.glb`).catch((er) => setError(er.message))}><Icon name="download" size={12} /> glb</button>
            {canEdit && versions[0]?.id !== selected.id && <button className="btn sm" title="Shu versiya faylidan yangi (oxirgi) versiya yaratiladi — tarix saqlanadi" onClick={() => void dialogs.confirm("Versiyani qayta tiklash", { text: `v${selected.number} dan yangi (oxirgi) versiya yaratiladi`, ok: "Qayta tiklash" }).then((ok) => { if (ok) api.restoreVersion(selected.id).then(onUploaded).catch((e) => dialogs.alert("Xato", e.message)); })}><Icon name="history" size={12} /> Qayta tiklash</button>}
            {canEdit && versions[0]?.id === selected.id && <button className="btn sm" title="GES turi bo'yicha IfcClassificationReference (SATH-KSI yoki Uniclass 2015) — yangi versiya" data-testid="classify-btn" onClick={() => void (async () => { const sys = await dialogs.prompt("Klassifikator", "SATH-KSI", { text: "SATH-KSI (mahalliy) yoki Uniclass2015" }); if (!sys) return; api.classifyVersion(selected.id, sys).then(onUploaded).catch((e) => dialogs.alert("Klassifikatsiya", e.message)); })()}><Icon name="tag" size={12} /> Klassifikatsiya</button>}
            {canEdit && versions[0]?.id === selected.id && !selected.meta.georef?.epsg && <button className="btn sm" title="Loyiha CRS (EPSG, origin) dan IfcMapConversion/IfcProjectedCRS qo'shib yangi versiya yozadi" data-testid="georef-btn" onClick={() => api.georeference(model.id).then(onUploaded).catch((e) => dialogs.alert("Georeferensiya", e.message))}><Icon name="map" size={12} /> Georeferensiyalash</button>}
            {canEdit && <button className="btn sm" title="ISO 19650 yaroqlilik va reviziya kodi (tasdiqlovchi): wip → S0, shared → S1–S7, published → A1–An/B1–Bn/CR/PR; P01…/C01…" data-testid="iso-codes" onClick={() => void (async () => { const suitability_code = await dialogs.prompt("Yaroqlilik kodi (S0–S7, A1–An, B1–Bn, CR, PR)", selected.suitability_code ?? ""); if (suitability_code == null) return; const revision_code = await dialogs.prompt("Reviziya kodi (P01… / C01…)", selected.revision_code ?? ""); if (revision_code == null) return; api.updateVersion(selected.id, { suitability_code, revision_code }).then(() => onUploaded(selected)).catch((e) => dialogs.alert("ISO 19650", e.message)); })()}><Icon name="check" size={12} /> ISO 19650</button>}
            {canEdit && <button className="btn sm" title="Izoh / yorliq" onClick={() => void (async () => { const message = await dialogs.prompt("Izoh", selected.message); if (message == null) return; const tag = await dialogs.prompt("Yorliq", selected.tag ?? "", { text: "bo'sh — yo'q; faqat tasdiqlovchi" }); api.updateVersion(selected.id, { message, ...(tag != null && tag !== (selected.tag ?? "") ? { tag } : {}) }).then(() => onUploaded(selected)).catch((e) => dialogs.alert("Xato", e.message)); })()}><Icon name="tag" size={12} /> Izoh/yorliq</button>}
          </BOps>
          <BOps>
            {selected.parent_id && !diff && <button className="btn sm" onClick={() => onDiff(selected)} title="Ota versiya bilan farq — 3D da rang (yashil/sariq)"><Icon name="git-branch" size={12} /> Ota bilan farq</button>}
            {versions.length > 1 && !diff && (
              <select className="select" value={compareFrom} title="Boshqa versiya bilan solishtirish"
                onChange={(e) => { setCompareFrom(""); if (e.target.value) onDiff(selected, Number(e.target.value)); }}>
                <option value="">Solishtirish…</option>
                {versions.filter((o) => o.id !== selected.id).map((o) => <option key={o.id} value={o.id}>v{o.number}</option>)}
              </select>
            )}
            {diff && <button className="btn sm" onClick={onClearDiff}><Icon name="x" size={12} /> Farqni yopish</button>}
          </BOps>
        </BPanel>
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
      {diff && (
        <BPanel id="diff" title={`Farq: v${versions.find((x) => x.id === diff.from_version_id)?.number} → v${versions.find((x) => x.id === diff.to_version_id)?.number}`} icon="git-branch">
          <div className="diff-legend">
            <span><i style={{ background: "#2ecc71" }} />Qo'shilgan {diff.summary.added}</span>
            <span><i style={{ background: "#f1c40f" }} />O'zgargan {diff.summary.changed}</span>
            <span><i style={{ background: "#e74c3c" }} />O'chirilgan {diff.summary.deleted}</span>
          </div>
          <div className="diff-list">
            {diff.added.map((d) => <button type="button" key={d.guid} className="diff-row" onClick={() => onPickGuid(d.guid)}><span style={{ color: "#2ecc71" }}>+</span>{ifcLabel(d.type)} {d.name}<span className="g">{d.guid}</span></button>)}
            {diff.changed.map((d) => <button type="button" key={d.guid} className="diff-row" onClick={() => onPickGuid(d.guid)}><span style={{ color: "#f1c40f" }}>~</span>{ifcLabel(d.type)} {d.name}<span className="g">{d.changes?.join(", ")}</span></button>)}
            {diff.deleted.map((d) => <div key={d.guid} title="Joriy modelda yo'q"><span style={{ color: "#e74c3c" }}>−</span>{ifcLabel(d.type)} {d.name}<span className="g">{d.guid}</span></div>)}
          </div>
        </BPanel>
      )}
      {error && <p className="error small">{error}</p>}

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
