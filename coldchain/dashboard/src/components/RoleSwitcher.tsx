import { useAuth } from "../lib/auth";
import type { Locale, Role } from "../lib/types";

const LABEL: Record<Role, Record<Locale, string>> = {
  driver: { fr: "Chauffeur", en: "Driver", ar: "السائق" },
  dispatcher: { fr: "Répartiteur", en: "Dispatcher", ar: "المرسل" },
  quality: { fr: "Qualité", en: "Quality", ar: "الجودة" },
};

const ROLES: Role[] = ["driver", "dispatcher", "quality"];

/** Changes which view is shown in one tap, without signing out or writing
 * to the database -- built for the stage: three views in under 90s, no
 * password typed while presenting. */
export function RoleSwitcher({ locale }: { locale: Locale }) {
  const { activeView, setActiveView } = useAuth();

  return (
    <div className="row" role="tablist" aria-label="role switcher">
      {ROLES.map((role) => (
        <button
          key={role}
          role="tab"
          aria-selected={activeView === role}
          className={activeView === role ? "" : "secondary"}
          style={{ flex: 1, fontSize: "0.85rem", padding: "0.5rem" }}
          onClick={() => setActiveView(role)}
        >
          {LABEL[role][locale]}
        </button>
      ))}
    </div>
  );
}
