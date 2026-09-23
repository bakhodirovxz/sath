import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type { AlarmEvent, Role } from "../../api/client";
import { can } from "../../api/permissions";
import { alarmLabel } from "../../i18n/labels";
import { applyEvent, useAlarmEvents, useProjectLive } from "../../store/live";
import AlarmMark from "../../ui/AlarmMark";
import { fmtTime, fmtValue } from "../../ui/format";
import { notify } from "../../ui/notice";
import { alarmStyle } from "../../ui/tokens";
import AlarmActionDialog from "./AlarmActionDialog";
import { unackedTop } from "./alarms";

/** Doimiy alarm banneri (UX-03, ISA-18.2): loyihaning HAR sahifasida (BIM, dispetcher, operator) — kvitlanmagan
 * eng muhim 3 ta alarm, belgi kvitlanguncha miltillaydi (ovoz — annunciator, kvitlanguncha takror), sahifa ichida
 * kvitlash dialogi (izoh bilan), alarm sahifasiga havola. Kvitlanmagan alarm yo'q — banner yo'q (joy egallamaydi). */
export default function AlarmBanner({ pid, role }: { pid: number; role?: Role | null | undefined }) {
  useProjectLive(pid); // jonli oqim — yangi alarm darhol ko'rinadi (loyiha uchun bitta soket, UX-11)
  const events = useAlarmEvents(pid);
  const list = useMemo(() => unackedTop(events), [events]);
  const [dlg, setDlg] = useState<AlarmEvent | null>(null);
  if (!list.length) return null;
  const canAck = can(role, "scada.ack");
  const top = list.slice(0, 3);
  const prio = alarmStyle(top[0].state, top[0].priority ?? "medium").priority ?? "low";
  const alarmsPath = `/projects/${pid}/ops/alarms`;
  return (
    <section className={`alarm-banner prio-${prio}`} aria-label="Kvitlanmagan alarmlar" data-testid="alarm-banner">
      <Link to={alarmsPath} className="ab-count" title="Alarm sahifasi">
        <b data-testid="alarm-banner-count">{list.length}</b> kvitlanmagan
      </Link>
      <ul className="ab-list">
        {top.map((e) => (
          <li key={e.id} className="ab-item" data-testid="alarm-banner-item" data-prio={e.priority}>
            <AlarmMark state={e.state} priority={e.priority} unacked size={18} />
            <Link to={`/projects/${pid}/ops/sensor/${e.sensor_id}`} className="ab-name">{e.sensor_name}</Link>
            <span className="ab-state">{alarmLabel(e.state)}{e.ended_at ? " · me'yorga qaytdi" : ""}</span>
            {e.value != null && <span className="mono">{fmtValue(e.value)} {e.unit}</span>}
            <span className="dim mono">{fmtTime(e.started_at)}</span>
            {canAck && <button type="button" className="btn sm" onClick={() => setDlg(e)} data-testid="alarm-banner-ack">Kvitlash</button>}
          </li>
        ))}
      </ul>
      {list.length > top.length && <Link to={alarmsPath} className="ab-more">+{list.length - top.length} boshqa</Link>}
      <Link to={alarmsPath} className="btn sm ab-link">Alarm sahifasi →</Link>
      {dlg && (
        <AlarmActionDialog kind="ack" event={dlg} onClose={() => setDlg(null)}
          onDone={(u) => { if (u) applyEvent(pid, u); setDlg(null); notify(`Kvitlandi: ${dlg.sensor_name}`); }} />
      )}
    </section>
  );
}
