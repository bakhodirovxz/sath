import { useState } from "react";
import { api, ApiError } from "../api/client";
import { useAuth } from "../store/auth";
import Dialog from "./Dialog";

/** Profil (L1): parolni o'zgartirish va TOTP MFA (RFC 6238) sozlash/o'chirish. */
export default function ProfileDialog({ onClose }: { onClose: () => void }) {
  const { user, refresh } = useAuth();
  const [oldPw, setOldPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [msg, setMsg] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [setup, setSetup] = useState<{ secret: string; otpauth_url: string } | null>(null);
  const [code, setCode] = useState("");
  const [pw, setPw] = useState("");
  const [busy, setBusy] = useState(false);

  async function run(fn: () => Promise<void>, okText: string) {
    setBusy(true); setMsg(null);
    try { await fn(); setMsg({ kind: "ok", text: okText }); } catch (e) { setMsg({ kind: "error", text: e instanceof ApiError ? e.message : String(e) }); } finally { setBusy(false); }
  }
  if (!user) return null;
  return (
    <Dialog title="Profil" onClose={onClose}>
      <p className="small muted">{user.full_name || user.username} · {user.is_admin ? "administrator" : "foydalanuvchi"}</p>
      {user.mfa_required && <p className="verdict warn small">Administrator uchun ikki bosqichli kirish (MFA) majburiy — quyida yoqing.</p>}
      <form onSubmit={(e) => { e.preventDefault(); void run(async () => { await api.changePassword(oldPw, newPw); setOldPw(""); setNewPw(""); }, "Parol o'zgartirildi"); }}>
        <h3>Parol</h3>
        <label className="field"><span>Joriy parol</span><input className="input" type="password" value={oldPw} onChange={(e) => setOldPw(e.target.value)} autoComplete="current-password" /></label>
        <label className="field"><span>Yangi parol</span><input className="input" type="password" value={newPw} onChange={(e) => setNewPw(e.target.value)} autoComplete="new-password" minLength={4} /></label>
        <div className="actions"><button className="btn" type="submit" disabled={busy || !oldPw || !newPw}>O'zgartirish</button></div>
      </form>
      <h3>Ikki bosqichli kirish (MFA)</h3>
      {user.mfa_enabled ? (
        <form onSubmit={(e) => { e.preventDefault(); void run(async () => { await api.mfaDisable(pw, code); setPw(""); setCode(""); await refresh(); }, "MFA o'chirildi"); }}>
          <p className="small">Yoqilgan. O'chirish uchun parol va ilovadagi joriy kod:</p>
          <div className="row" style={{ gap: 8 }}>
            <input className="input" type="password" placeholder="Parol" value={pw} onChange={(e) => setPw(e.target.value)} autoComplete="current-password" />
            <input className="input" placeholder="Kod" inputMode="numeric" value={code} onChange={(e) => setCode(e.target.value)} style={{ width: 100 }} />
            <button className="btn danger" type="submit" disabled={busy || !pw || code.length < 6}>O'chirish</button>
          </div>
        </form>
      ) : setup ? (
        <form onSubmit={(e) => { e.preventDefault(); void run(async () => { await api.mfaEnable(code); setSetup(null); setCode(""); await refresh(); }, "MFA yoqildi"); }}>
          <p className="small">Google Authenticator / Aegis / FreeOTP ilovasiga kalitni kiriting (yoki havolani oching), so'ng ilovadagi 6 raqamli kodni tasdiqlang:</p>
          <p className="mono" style={{ wordBreak: "break-all", userSelect: "all" }} data-testid="mfa-secret">{setup.secret}</p>
          <p className="small"><a href={setup.otpauth_url}>otpauth havolasi</a></p>
          <div className="row" style={{ gap: 8 }}>
            <input className="input" placeholder="6 raqamli kod" inputMode="numeric" value={code} onChange={(e) => setCode(e.target.value)} autoFocus style={{ width: 140 }} data-testid="mfa-code" />
            <button className="btn primary" type="submit" disabled={busy || code.length < 6}>Tasdiqlash va yoqish</button>
            <button className="btn" type="button" onClick={() => { setSetup(null); setCode(""); }}>Bekor</button>
          </div>
        </form>
      ) : (
        <div className="actions"><button className="btn primary" disabled={busy} onClick={() => void run(async () => { setSetup(await api.mfaSetup()); }, "Kalit yaratildi — ilovaga kiriting")}>MFA ni yoqish</button></div>
      )}
      {msg && <p className={`small ${msg.kind === "ok" ? "verdict ok" : "error"}`} role="status">{msg.text}</p>}
      <div className="actions"><button className="btn" onClick={onClose}>Yopish</button></div>
    </Dialog>
  );
}
