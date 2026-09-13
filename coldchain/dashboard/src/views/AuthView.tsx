import { useState } from "react";
import type { FormEvent } from "react";
import { useAuth } from "../lib/auth";
import type { Locale, Role } from "../lib/types";

const ROLE_OPTIONS: Array<{ value: Role; label: Record<Locale, string> }> = [
  { value: "driver", label: { fr: "Chauffeur", en: "Driver", ar: "السائق" } },
  { value: "dispatcher", label: { fr: "Répartiteur", en: "Dispatcher", ar: "المرسل" } },
  { value: "quality", label: { fr: "Qualité", en: "Quality", ar: "الجودة" } },
];

const LOCALE_OPTIONS: Array<{ value: Locale; label: string }> = [
  { value: "fr", label: "Français" },
  { value: "en", label: "English" },
  { value: "ar", label: "العربية" },
];

// The sign-up/sign-in form itself is shown before a profile locale is
// known, so its own chrome is bilingual-by-toggle rather than driven by
// the (not yet loaded) profile -- pick a display locale for the form UI
// independent of which locale the account will be created with.
const FORM_TEXT = {
  signIn: { fr: "Connexion", en: "Sign in", ar: "تسجيل الدخول" },
  signUp: { fr: "Créer un compte", en: "Sign up", ar: "إنشاء حساب" },
  email: { fr: "E-mail", en: "Email", ar: "البريد الإلكتروني" },
  password: { fr: "Mot de passe", en: "Password", ar: "كلمة المرور" },
  displayName: { fr: "Nom affiché", en: "Display name", ar: "الاسم المعروض" },
  role: { fr: "Rôle", en: "Role", ar: "الدور" },
  locale: { fr: "Langue", en: "Language", ar: "اللغة" },
  submitSignIn: { fr: "Se connecter", en: "Sign in", ar: "دخول" },
  submitSignUp: { fr: "Créer le compte", en: "Create account", ar: "إنشاء الحساب" },
  switchToSignUp: { fr: "Pas de compte ? Créer un compte", en: "No account? Sign up", ar: "لا يوجد حساب؟ أنشئ واحدًا" },
  switchToSignIn: { fr: "Déjà un compte ? Se connecter", en: "Already have an account? Sign in", ar: "لديك حساب؟ سجل الدخول" },
} satisfies Record<string, Record<Locale, string>>;

export function AuthView() {
  const { signUp, signIn } = useAuth();
  const [mode, setMode] = useState<"signIn" | "signUp">("signUp");
  const [formLocale, setFormLocale] = useState<Locale>("fr");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [role, setRole] = useState<Role>("driver");
  const [accountLocale, setAccountLocale] = useState<Locale>("fr");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const t = FORM_TEXT;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      if (mode === "signUp") {
        await signUp({ email, password, role, locale: accountLocale, displayName });
      } else {
        await signIn(email, password);
      }
    } catch (err) {
      // Supabase's error objects (rate limits, validation errors, etc.)
      // don't always satisfy `instanceof Error` depending on how they
      // cross a module boundary -- checking for a `message` property
      // directly is what actually catches those; `instanceof Error` alone
      // was observed to fall through to `String(err)` -> "[object Object]"
      // during manual testing against a real rate-limit response.
      const message =
        typeof err === "object" && err !== null && "message" in err
          ? String((err as { message: unknown }).message)
          : String(err);
      setError(message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="page">
      <div className="row space-between" style={{ marginBlockEnd: "1rem" }}>
        <h1 style={{ fontSize: "1.25rem" }}>{mode === "signUp" ? t.signUp[formLocale] : t.signIn[formLocale]}</h1>
        <select value={formLocale} onChange={(e) => setFormLocale(e.target.value as Locale)} style={{ width: "auto" }}>
          {LOCALE_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      <form onSubmit={handleSubmit} className="stack">
        <div className="field">
          <label>{t.email[formLocale]}</label>
          <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
        <div className="field">
          <label>{t.password[formLocale]}</label>
          <input
            type="password"
            required
            minLength={6}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>

        {mode === "signUp" && (
          <>
            <div className="field">
              <label>{t.displayName[formLocale]}</label>
              <input required value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
            </div>
            <div className="field">
              <label>{t.role[formLocale]}</label>
              <select value={role} onChange={(e) => setRole(e.target.value as Role)}>
                {ROLE_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label[formLocale]}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label>{t.locale[formLocale]}</label>
              <select value={accountLocale} onChange={(e) => setAccountLocale(e.target.value as Locale)}>
                {LOCALE_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>
          </>
        )}

        {error && <div className="error-text">{error}</div>}

        <button type="submit" disabled={submitting}>
          {mode === "signUp" ? t.submitSignUp[formLocale] : t.submitSignIn[formLocale]}
        </button>

        <button
          type="button"
          className="secondary"
          onClick={() => setMode(mode === "signUp" ? "signIn" : "signUp")}
        >
          {mode === "signUp" ? t.switchToSignIn[formLocale] : t.switchToSignUp[formLocale]}
        </button>
      </form>
    </div>
  );
}
