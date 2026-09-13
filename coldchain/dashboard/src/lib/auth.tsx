import type { Session, User } from "@supabase/supabase-js";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { supabase } from "./supabase";
import type { Locale, Role, UserProfile } from "./types";

interface AuthContextValue {
  session: Session | null;
  profile: UserProfile | null;
  loading: boolean;
  /** The view currently shown -- defaults to profile.role but can be
   * changed in one tap via the role switcher without touching the
   * database or signing out (see App.tsx / RoleSwitcher). */
  activeView: Role | null;
  setActiveView: (role: Role) => void;
  signUp: (opts: {
    email: string;
    password: string;
    role: Role;
    locale: Locale;
    displayName: string;
  }) => Promise<void>;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
}

/** Thrown by signUp() when the project requires email confirmation before
 * a session exists. AuthView catches this specifically to show a "check
 * your email" message instead of a generic error. */
export class NeedsEmailConfirmationError extends Error {
  constructor() {
    super("check your email to confirm your account, then sign in");
    this.name = "NeedsEmailConfirmationError";
  }
}

const AuthContext = createContext<AuthContextValue | null>(null);

async function fetchProfile(user: User): Promise<UserProfile> {
  const { data, error } = await supabase.from("profiles").select("*").eq("id", user.id).maybeSingle();
  if (error) throw error;
  if (data) return data as UserProfile;
  const metadata = user.user_metadata ?? {};
  const row = {
    id: user.id,
    role: ["driver", "dispatcher", "quality"].includes(metadata.role) ? metadata.role : "driver",
    locale: ["fr", "en", "ar"].includes(metadata.locale) ? metadata.locale : "fr",
    display_name: metadata.display_name || user.email?.split("@")[0] || "Utilisateur",
  };
  const { error: insertError } = await supabase.from("profiles").upsert(row, { onConflict: "id", ignoreDuplicates: true });
  if (insertError) throw insertError;
  const result = await supabase.from("profiles").select("*").eq("id", user.id).single();
  if (result.error) throw result.error;
  return result.data as UserProfile;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeView, setActiveViewState] = useState<Role | null>(null);
  const [authError, setAuthError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    let revision = 0;
    const { data: sub } = supabase.auth.onAuthStateChange((_event, newSession) => {
      const current = ++revision;
      // Run outside the auth callback: database requests also acquire the auth lock.
      setTimeout(async () => {
        if (cancelled || current !== revision) return;
        setSession(newSession);
        setAuthError(null);
        try {
          const p = newSession ? await fetchProfile(newSession.user) : null;
          if (cancelled || current !== revision) return;
          setProfile(p);
          setActiveViewState(p?.role ?? null);
        } catch (err) {
          if (!cancelled && current === revision) {
            setProfile(null);
            setAuthError(err instanceof Error ? err.message : String((err as { message?: string }).message ?? err));
          }
        } finally {
          if (!cancelled && current === revision) setLoading(false);
        }
      }, 0);
    });

    return () => {
      cancelled = true;
      sub.subscription.unsubscribe();
    };
  }, []);

  const signUp = useCallback<AuthContextValue["signUp"]>(
    async ({ email, password, role, locale, displayName }) => {
      const { data, error } = await supabase.auth.signUp({ email: email.trim(), password,
        options: { data: { role, locale, display_name: displayName.trim() },
          emailRedirectTo: window.location.origin + import.meta.env.BASE_URL },
      });
      if (error) throw error;
      if (!data.session) {
        // The project's Auth settings require confirming the email before
        // a session exists (Authentication -> Sign In / Providers -> Email
        // -> "Confirm email"). data.user can be truthy here even though
        // there's no session yet -- session, not user, is what RLS's
        // auth.uid() depends on, so the profile insert below would be
        // silently rejected without this check. For a walk-up demo where
        // people scan a QR and expect to be in immediately, turning that
        // setting off is the fix; this throw is the graceful fallback
        // either way.
        throw new NeedsEmailConfirmationError();
      }
      const p = await fetchProfile(data.session.user);
      setProfile(p);
      setActiveViewState(p?.role ?? role);
    },
    [],
  );

  const signIn = useCallback(async (email: string, password: string) => {
    const { error } = await supabase.auth.signInWithPassword({ email: email.trim(), password });
    if (error) throw error;
  }, []);

  const signOut = useCallback(async () => {
    const { error } = await supabase.auth.signOut();
    if (error) throw error;
  }, []);

  const setActiveView = useCallback((role: Role) => {
    setActiveViewState(role);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ session, profile, loading, activeView, setActiveView, signUp, signIn, signOut }),
    [session, profile, loading, activeView, setActiveView, signUp, signIn, signOut],
  );

  return <AuthContext.Provider value={value}>{authError ? (
    <div className="page stack"><p role="alert">Impossible de charger le profil : {authError}</p>
      <button onClick={() => window.location.reload()}>Réessayer</button>
      <button onClick={() => void signOut()}>Se déconnecter</button></div>
  ) : children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return ctx;
}
