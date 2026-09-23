import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { useAuth } from "../store/auth";
import { focusOnMount } from "../ui/focus";

export default function Login() {
  const login = useAuth((s) => s.login);
  const nav = useNavigate();
  const loc = useLocation() as { state?: { from?: string } };
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [otp, setOtp] = useState("");
  const [needOtp, setNeedOtp] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await login(username, password, otp || undefined);
      nav(loc.state?.from ?? "/", { replace: true });
    } catch (err) {
      if (err instanceof ApiError && err.mfaRequired) { setNeedOtp(true); if (otp) setError(err.message); return; }
      setError(err instanceof Error ? err.message : "Kirish amalga oshmadi");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login">
      <form onSubmit={submit}>
        <h1>Sath</h1>
        <p className="muted mt-0">Modellar, versiyalar va tasdiqlash</p>
        <label className="field">
          <span>Login</span>
          <input className="input" value={username} onChange={(e) => setUsername(e.target.value)} ref={focusOnMount} autoComplete="username" />
        </label>
        <label className="field">
          <span>Parol</span>
          <input className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
        </label>
        {needOtp && (
          <label className="field">
            <span>MFA kodi (ilovadan)</span>
            <input className="input" inputMode="numeric" autoComplete="one-time-code" value={otp} onChange={(e) => setOtp(e.target.value)} ref={focusOnMount} data-testid="login-otp" />
          </label>
        )}
        {error && <p className="error small">{error}</p>}
        <button className="btn primary w-full" type="submit" disabled={busy || !username || !password || (needOtp && otp.length < 6)}>
          {busy ? "Tekshirilmoqda…" : "Kirish"}
        </button>
      </form>
    </div>
  );
}
