import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { useAuth } from "../lib/auth";
import type { Locale, Role } from "../lib/types";
import "../styles/workspace-shell.css";

export const ROLE_LABELS: Record<Role, Record<Locale, string>> = {
  driver: { fr: "Chauffeur", en: "Driver", ar: "السائق" },
  dispatcher: { fr: "Répartiteur", en: "Dispatcher", ar: "المشرف" },
  quality: { fr: "Qualité", en: "Quality", ar: "الجودة" },
};

const ROLES: Role[] = ["driver", "dispatcher", "quality"];
let restoreKeyboardFocus: Role | null = null;

const TEXT = {
  label: { fr: "Espaces de travail", en: "Workspaces", ar: "مساحات العمل" },
  preview: { fr: "Aperçu des espaces", en: "Workspace preview", ar: "معاينة مساحات العمل" },
  hint: {
    fr: "Changer de vue ne modifie pas le rôle de votre compte.",
    en: "Switching views does not change your account role.",
    ar: "تغيير العرض لا يغير دور حسابك.",
  },
} satisfies Record<string, Record<Locale, string>>;

/** Workspace preview only. The account's role and database permissions do not change. */
export function RoleSwitcher({ locale }: { locale: Locale }) {
  const { activeView, setActiveView } = useAuth();
  const selectedRole = activeView ?? "driver";
  const [focusRole, setFocusRole] = useState<Role>(selectedRole);
  const buttons = useRef<Partial<Record<Role, HTMLButtonElement | null>>>({});

  useEffect(() => {
    setFocusRole(selectedRole);
    if (restoreKeyboardFocus === selectedRole) {
      buttons.current[selectedRole]?.focus();
      restoreKeyboardFocus = null;
    }
  }, [selectedRole]);

  function handleKeyDown(event: KeyboardEvent<HTMLButtonElement>, role: Role) {
    const index = ROLES.indexOf(role);
    const direction = locale === "ar" ? -1 : 1;
    let next: number | null = null;
    if (event.key === "ArrowRight") next = (index + direction + ROLES.length) % ROLES.length;
    if (event.key === "ArrowLeft") next = (index - direction + ROLES.length) % ROLES.length;
    if (event.key === "Home") next = 0;
    if (event.key === "End") next = ROLES.length - 1;
    if (next !== null) {
      event.preventDefault();
      setFocusRole(ROLES[next]);
      buttons.current[ROLES[next]]?.focus();
    }
    if (event.key === "Enter" || event.key === " ") restoreKeyboardFocus = role;
  }

  return (
    <div className="workspace-navigation">
      <div className="workspace-tabs" role="tablist" aria-label={TEXT.label[locale]} aria-describedby="workspace-preview-hint">
      {ROLES.map((role) => (
        <button
          key={role}
          ref={(node) => { buttons.current[role] = node; }}
          id={`workspace-tab-${role}`}
          type="button"
          role="tab"
          aria-selected={selectedRole === role}
          aria-controls="workspace-panel"
          tabIndex={focusRole === role ? 0 : -1}
          className="workspace-tab"
          onKeyDown={(event) => handleKeyDown(event, role)}
          onClick={() => { setFocusRole(role); setActiveView(role); }}
        >
          {ROLE_LABELS[role][locale]}
        </button>
      ))}
      </div>
      <span className="workspace-preview" title={TEXT.hint[locale]}>{TEXT.preview[locale]}</span>
      <span className="workspace-sr-only" id="workspace-preview-hint">{TEXT.hint[locale]}</span>
    </div>
  );
}
