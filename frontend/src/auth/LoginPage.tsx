import React, { FormEvent, useState } from "react";
import { useAppConfig } from "../config";
import { useAuth } from "./AuthProvider";

export const LoginPage: React.FC = () => {
  const { organization } = useAppConfig();
  const { login, error } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const submit = async (event: FormEvent) => { event.preventDefault(); setSubmitting(true); try { await login(email, password); } finally { setSubmitting(false); } };
  return <main className="app-main"><form className="status-card auth-form" onSubmit={submit} aria-label="Sign in">
    <h1>{organization.name}</h1><p>Sign in to continue.</p>
    {error && <div className="error-banner" role="alert">{error}</div>}
    <label>Email<input type="email" value={email} onChange={e => setEmail(e.target.value)} required autoComplete="email" /></label>
    <label>Password<input type="password" value={password} onChange={e => setPassword(e.target.value)} required autoComplete="current-password" /></label>
    <button className="refresh-button" disabled={submitting}>{submitting ? "Signing in…" : "Sign in"}</button>
  </form></main>;
};
