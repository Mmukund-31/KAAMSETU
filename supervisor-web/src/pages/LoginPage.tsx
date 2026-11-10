import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth, useLogoutNotice } from "../auth/AuthContext";
import { Button, InlineError, TextField } from "../components/ui";

export function LoginPage() {
  const { state, login } = useAuth();
  const notice = useLogoutNotice();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? "/";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  if (state.status === "authenticated") return <Navigate to={from} replace />;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(email.trim(), password);
      navigate(from, { replace: true });
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface-subtle px-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-center gap-2.5">
          <img src="/favicon.svg" alt="" className="h-9 w-9" />
          <div>
            <p className="text-lg font-semibold tracking-wide text-ink">KAAMSETU</p>
            <p className="text-sm text-ink-muted">Supervisor console</p>
          </div>
        </div>
        <form onSubmit={onSubmit} className="space-y-4 rounded-lg border border-line bg-white p-6 shadow-card" noValidate>
          <h1 className="text-base font-semibold text-ink">Sign in</h1>
          {notice && !error && (
            <p className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">{notice}</p>
          )}
          <InlineError error={error} />
          <TextField
            label="Email"
            type="email"
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
          <TextField
            label="Password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
          <Button type="submit" variant="primary" className="w-full" loading={busy} disabled={!email || !password}>
            Sign in
          </Button>
        </form>
        <p className="mt-4 text-center text-xs text-ink-muted">
          For supervisors and managers. Technicians report work from the KAAMSETU mobile app.
        </p>
      </div>
    </div>
  );
}
