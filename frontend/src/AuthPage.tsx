import { useEffect, useState } from "react";
import { authClient } from "./auth";

type AuthPageProps = {
  onSignedIn: () => void;
  onBack?: () => void;
  initialMode?: "signin" | "signup";
};

export function AuthPage({ onSignedIn, onBack, initialMode = "signin" }: AuthPageProps) {
  const [mode, setMode] = useState<"signin" | "signup">(initialMode);

  useEffect(() => {
    setMode(initialMode);
  }, [initialMode]);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const result =
        mode === "signup"
          ? await authClient.signUp.email({
              name: name.trim() || email.split("@")[0] || "User",
              email,
              password,
            })
          : await authClient.signIn.email({ email, password });
      if (result.error) {
        setError(result.error.message || "Authentication failed");
        return;
      }
      onSignedIn();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Authentication failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-shell">
      <form className="auth-card" onSubmit={onSubmit}>
        {onBack && (
          <button type="button" className="link" onClick={onBack}>
            ← Back to ResearchLM
          </button>
        )}
        <h1>ResearchLM</h1>
        <p>{mode === "signup" ? "Create an account to start researching." : "Sign in to continue."}</p>
        {mode === "signup" && (
          <label>
            Name
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Your name" />
          </label>
        )}
        <label>
          Email
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            required
          />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
            required
            minLength={8}
          />
        </label>
        {error && <div className="error">{error}</div>}
        <button className="btn primary block" type="submit" disabled={busy}>
          {mode === "signup" ? "Create account" : "Sign in"}
        </button>
        <p className="auth-switch">
          {mode === "signup" ? "Already have an account? " : "Need an account? "}
          <button
            type="button"
            className="link"
            onClick={() => setMode(mode === "signup" ? "signin" : "signup")}
          >
            {mode === "signup" ? "Sign in" : "Sign up"}
          </button>
        </p>
      </form>
    </div>
  );
}
