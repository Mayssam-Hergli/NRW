import { RoleSwitcher } from "./RoleSwitcher";
import { ConnectionBadge } from "./ConnectionBadge";
import { Logo } from "./Logo";
import { useAuth } from "../lib/auth";
import type { ConnectionState } from "../hooks/useTelemetryHistory";
import type { Locale } from "../lib/types";

const SIGN_OUT_LABEL: Record<Locale, string> = {
  fr: "Déconnexion",
  en: "Sign out",
  ar: "تسجيل الخروج",
};

export function AppHeader({ connection, locale }: { connection: ConnectionState; locale: Locale }) {
  const { signOut } = useAuth();

  return (
    <header
      style={{
        position: "sticky",
        insetBlockStart: 0,
        zIndex: 10,
        background: "var(--panel)",
        borderBlockEnd: "1px solid var(--rule)",
        paddingBlock: "0.6rem",
      }}
    >
      <div className="page wide" style={{ paddingBlock: 0 }}>
        <div className="row space-between" style={{ marginBlockEnd: "0.6rem" }}>
          <Logo height={26} />
          <div className="row" style={{ gap: "0.75rem" }}>
            <ConnectionBadge state={connection} locale={locale} />
            <button className="secondary" style={{ padding: "0.35rem 0.75rem", fontSize: "0.8rem" }} onClick={() => void signOut()}>
              {SIGN_OUT_LABEL[locale]}
            </button>
          </div>
        </div>
        <RoleSwitcher locale={locale} />
      </div>
    </header>
  );
}
