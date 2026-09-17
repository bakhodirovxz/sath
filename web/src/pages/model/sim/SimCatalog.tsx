import type { SimCatalog as Catalog, SimJob, SimKind } from "../../../api/client";
import Icon from "../../../ui/Icon";
import { BList, BPanel } from "../../../ui/BlenderUI";
import { fmtDate } from "../../../ui/format";

interface Props {
  catalog: Catalog;
  jobs: SimJob[];
  onPick: (kind: SimKind) => void;
  siteFilled: boolean | null;
  onSite?: () => void;
}

const GROUP_ORDER = ["gidrologiya", "gidravlika", "mustahkamlik", "favqulodda", "ekspluatatsiya", "custom"];

/** Simulyatsiyalar katalogi (Blender): har guruh — panel, ichida UIList (ikonka, nom, oxirgi hisob holati);
 *  qator bosilsa — forma ochiladi. */
export default function SimCatalog({ catalog, jobs, onPick, siteFilled, onSite }: Props) {
  const groups = GROUP_ORDER.filter((g) => catalog.kinds.some((k) => k.group === g));
  const last = (id: string) => jobs.find((j) => j.kind === id);
  return (
    <div className="sim-catalog">
      {siteFilled === false && (
        <div className="section-box small row" style={{ alignItems: "center" }}>
          <Icon name="alert-circle" size={14} />
          <span className="grow small">Maydon pasporti to'ldirilmagan — tuproq, seysmiklik, sathlar, inshoot belgilari bir marta kiritilsa, barcha simulyatsiyalar aniqroq bo'ladi.</span>
          {onSite && <button className="btn sm" onClick={onSite}>To'ldirish</button>}
        </div>
      )}
      {groups.map((g) => {
        const kinds = catalog.kinds.filter((k) => k.group === g);
        return (
          <BPanel key={g} id={`simcat:${g}`} title={catalog.groups[g] ?? g} count={kinds.length}>
            <BList
              items={kinds} keyOf={(k) => k.id} rows={Math.min(kinds.length, 8)}
              onSelect={(k) => onPick(k)}
              render={(k) => {
                const j = last(k.id);
                const n = jobs.filter((x) => x.kind === k.id).length;
                return (
                  <>
                    <span className="dim" style={{ display: "inline-flex" }}><Icon name={k.icon} size={14} /></span>
                    <span className="grow" title={k.description}>{k.title}</span>
                    {n > 0 && <span className="dim">{n} hisob{j ? ` · ${fmtDate(j.created_at).slice(0, 10)}` : ""}</span>}
                    {j?.status === "done" && j.summary.ok !== undefined && <Icon name={j.summary.ok === false ? "alert-triangle" : "check-circle"} size={12} style={{ color: j.summary.ok === false ? "var(--danger)" : "var(--ok)" }} />}
                    {j && (j.status === "queued" || j.status === "running") && <span className="dim">hisoblanmoqda…</span>}
                  </>
                );
              }}
            />
          </BPanel>
        );
      })}
    </div>
  );
}
