import type { SimCatalog as Catalog, SimJob, SimKind } from "../../../api/client";
import Icon from "../../../ui/Icon";

interface Props {
  catalog: Catalog;
  jobs: SimJob[];
  onPick: (kind: SimKind) => void;
  siteFilled: boolean | null;
  onSite?: () => void;
}

const GROUP_ORDER = ["gidrologiya", "gidravlika", "mustahkamlik", "favqulodda", "ekspluatatsiya", "custom"];

/** Simulyatsiyalar katalogi — guruhlar bo'yicha kartochkalar (ikonka, nom, tavsif, oxirgi hisob holati). */
export default function SimCatalog({ catalog, jobs, onPick, siteFilled, onSite }: Props) {
  const groups = GROUP_ORDER.filter((g) => catalog.kinds.some((k) => k.group === g));
  const last = (id: string) => jobs.find((j) => j.kind === id);
  return (
    <div className="sim-catalog">
      {siteFilled === false && (
        <div className="section-box small row" style={{ alignItems: "center" }}>
          <Icon name="alert-circle" size={14} />
          <span className="grow">Maydon pasporti to'ldirilmagan — tuproq, seysmiklik, sathlar, inshoot belgilari bir marta kiritilsa, barcha simulyatsiyalar aniqroq bo'ladi.</span>
          {onSite && <button className="btn sm" onClick={onSite}>To'ldirish</button>}
        </div>
      )}
      {groups.map((g) => (
        <div key={g} className="sim-group">
          <h3>{catalog.groups[g] ?? g}</h3>
          <div className="sim-cards">
            {catalog.kinds.filter((k) => k.group === g).map((k) => {
              const j = last(k.id);
              const n = jobs.filter((x) => x.kind === k.id).length;
              return (
                <button key={k.id} className="sim-card" onClick={() => onPick(k)} title={k.description}>
                  <span className="sim-card-icon"><Icon name={k.icon} size={22} /></span>
                  <span className="sim-card-body">
                    <b>{k.title}</b>
                    <span className="dim small">{k.description.length > 110 ? `${k.description.slice(0, 110)}…` : k.description}</span>
                    {n > 0 && (
                      <span className="small row" style={{ gap: 6 }}>
                        <span className="muted">{n} hisob</span>
                        {j?.status === "done" && j.summary.ok !== undefined && <Icon name={j.summary.ok === false ? "alert-triangle" : "check-circle"} size={12} style={{ color: j.summary.ok === false ? "var(--danger)" : "var(--ok)" }} />}
                      </span>
                    )}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
