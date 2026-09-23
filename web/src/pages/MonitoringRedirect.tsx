import { useEffect, useState } from "react";
import { Navigate, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api/client";

/** Bildirishnoma havolasi `/projects/{id}/monitoring?unlinked={versionId}` (SCADA-13, server) — shu versiyaning
 * modelida Monitoring panelini ochadi (bog'lanmagan sensorlar ro'yxati). Versiya noma'lum — loyiha sahifasi. */
export default function MonitoringRedirect() {
  const pid = Number(useParams().projectId);
  const [params] = useSearchParams();
  const vid = Number(params.get("unlinked"));
  const [to, setTo] = useState<string | null>(null);
  useEffect(() => {
    if (!vid) { setTo(`/projects/${pid}`); return; }
    api.version(vid).then((v) => setTo(`/models/${v.model_id}?v=${v.id}&tab=mon`)).catch(() => setTo(`/projects/${pid}`));
  }, [pid, vid]);
  return to ? <Navigate to={to} replace /> : <div className="page-body muted">Yuklanmoqda…</div>;
}
