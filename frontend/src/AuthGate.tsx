import { useEffect, useState } from "react";
import { App } from "./App";
import { AuthPage } from "./AuthPage";
import { LandingPage } from "./LandingPage";
import { authClient } from "./auth";

type SessionUser = {
  email?: string;
  name?: string;
};

type GuestView = "landing" | "auth";
type AuthMode = "signin" | "signup";

export function AuthGate() {
  const [loading, setLoading] = useState(true);
  const [user, setUser] = useState<SessionUser | null>(null);
  const [guestView, setGuestView] = useState<GuestView>("landing");
  const [authMode, setAuthMode] = useState<AuthMode>("signin");

  async function refresh() {
    const result = await authClient.getSession();
    const next = result.data?.user ?? null;
    setUser(next);
    setLoading(false);
  }

  useEffect(() => {
    refresh();
  }, []);

  if (loading) {
    return (
      <div className="auth-shell">
        <p>Loading…</p>
      </div>
    );
  }

  if (!user) {
    if (guestView === "landing") {
      return (
        <LandingPage
          onSignIn={() => {
            setAuthMode("signin");
            setGuestView("auth");
          }}
          onStart={() => {
            setAuthMode("signup");
            setGuestView("auth");
          }}
        />
      );
    }
    return (
      <AuthPage
        initialMode={authMode}
        onSignedIn={refresh}
        onBack={() => setGuestView("landing")}
      />
    );
  }

  return (
    <App
      userEmail={user.email}
      onSignOut={async () => {
        await authClient.signOut();
        setUser(null);
        setGuestView("landing");
      }}
    />
  );
}
