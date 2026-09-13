import { useState } from "react";
import { RoleSwitcher, ROLE_LABELS } from "./RoleSwitcher";
import { ConnectionBadge } from "./ConnectionBadge";
import { Logo } from "./Logo";
import { useAuth } from "../lib/auth";
import type { ConnectionState } from "../hooks/useTelemetryHistory";
import type { Locale } from "../lib/types";
import "../styles/workspace-shell.css";

const TEXT = {
  signOut: { fr: "Déconnexion", en: "Sign out", ar: "تسجيل الخروج" },
  signingOut: { fr: "Déconnexion…", en: "Signing out…", ar: "جارٍ تسجيل الخروج…" },
  failed: {
    fr: "Déconnexion impossible. Vérifiez votre connexion et réessayez.",
    en: "Could not sign out. Check your connection and try again.",
    ar: "تعذر تسجيل الخروج. تحقق من اتصالك وحاول مرة أخرى.",
  },
  skip: { fr: "Aller au contenu", en: "Skip to content", ar: "انتقل إلى المحتوى" },
  account: { fr: "Compte", en: "Account", ar: "الحساب" },
} satisfies Record<string, Record<Locale, string>>;

export function AppHeader({ connection, locale }: { connection: ConnectionState; locale: Locale }) {
  const { profile, signOut } = useAuth();
  const [signingOut, setSigningOut] = useState(false);
  const [signOutError, setSignOutError] = useState(false);

  async function handleSignOut() {
    if (signingOut) return;
    setSigningOut(true);
    setSignOutError(false);
    try {
      await signOut();
    } catch {
      setSignOutError(true);
    } finally {
      setSigningOut(false);
    }
  }

  return (
    <header className="workspace-header">
      <a className="workspace-skip-link" href="#workspace-panel">{TEXT.skip[locale]}</a>
      <div className="page wide workspace-header-inner">
        <div className="workspace-toolbar">
          <div className="workspace-brand"><Logo height={29} /></div>
          <div className="workspace-account-tools">
            <ConnectionBadge state={connection} locale={locale} />
            {profile && (
              <div className="workspace-account" aria-label={TEXT.account[locale]}>
                <span className="workspace-avatar" aria-hidden="true">
                  {profile.display_name?.trim().slice(0, 1).toLocaleUpperCase(locale) || "V"}
                </span>
                <span className="workspace-account-copy">
                  <strong><bdi>{profile.display_name}</bdi></strong>
                  <span>{ROLE_LABELS[profile.role][locale]}</span>
                </span>
              </div>
            )}
            <button
              className="secondary workspace-signout"
              type="button"
              disabled={signingOut}
              aria-busy={signingOut}
              onClick={() => void handleSignOut()}
            >
              <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
                <path d="M9 5H5v14h4M13 8l4 4-4 4M9 12h12" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              {signingOut ? TEXT.signingOut[locale] : TEXT.signOut[locale]}
            </button>
          </div>
        </div>
        <RoleSwitcher locale={locale} />
        {signOutError && <p className="workspace-signout-error" role="alert">{TEXT.failed[locale]}</p>}
      </div>
    </header>
  );
}
