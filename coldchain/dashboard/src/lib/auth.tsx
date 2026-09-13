import type { Session } from "@supabase/supabase-js";
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

const AuthContext = createContext<AuthContextValue | null>(null);

async function fetchProfile(userId: string): Promise<UserProfile | null> {
  const { data, error } = await supabase.from("profiles").select("*").eq("id", userId).single();
  if (error) {
    // PGRST116 = no row found -- expected right after sign-up before the
    // profile insert has landed, not a real error.
    if (error.code !== "PGRST116") {
      console.error("fetchProfile failed", error);
    }
    return null;
  }
  return data as UserProfile;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeView, setActiveViewState] = useState<Role | null>(null);

  useEffect(() => {
    let cancelled = false;

    supabase.auth.getSession().then(async ({ data }) => {
      if (cancelled) return;
      setSession(data.session);
      if (data.session) {
        const p = await fetchProfile(data.session.user.id);
        if (!cancelled) {
          setProfile(p);
          setActiveViewState(p?.role ?? null);
        }
      }
      setLoading(false);
    });

    const { data: sub } = supabase.auth.onAuthStateChange(async (_event, newSession) => {
      setSession(newSession);
      if (newSession) {
        const p = await fetchProfile(newSession.user.id);
        setProfile(p);
        setActiveViewState((current) => current ?? p?.role ?? null);
      } else {
        setProfile(null);
        setActiveViewState(null);
      }
    });

    return () => {
      cancelled = true;
      sub.subscription.unsubscribe();
    };
  }, []);

  const signUp = useCallback<AuthContextValue["signUp"]>(
    async ({ email, password, role, locale, displayName }) => {
      const { data, error } = await supabase.auth.signUp({ email, password });
      if (error) throw error;
      const userId = data.user?.id;
      if (!userId) {
        // Email confirmation is required by the project's auth settings --
        // there's no session yet, so the profile row can't be written
        // under RLS (profiles_insert_own needs auth.uid()). Confirming and
        // signing in is the only path forward.
        throw new Error(
          "Sign-up succeeded but no session was returned -- check the project's email " +
            "confirmation setting if this is unexpected for a live demo.",
        );
      }
      const { error: profileError } = await supabase.from("profiles").insert({
        id: userId,
        role,
        locale,
        display_name: displayName,
      });
      if (profileError) throw profileError;
      const p = await fetchProfile(userId);
      setProfile(p);
      setActiveViewState(p?.role ?? role);
    },
    [],
  );

  const signIn = useCallback(async (email: string, password: string) => {
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) throw error;
  }, []);

  const signOut = useCallback(async () => {
    await supabase.auth.signOut();
  }, []);

  const setActiveView = useCallback((role: Role) => {
    setActiveViewState(role);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ session, profile, loading, activeView, setActiveView, signUp, signIn, signOut }),
    [session, profile, loading, activeView, setActiveView, signUp, signIn, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return ctx;
}
