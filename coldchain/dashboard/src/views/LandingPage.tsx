import type { CSSProperties } from "react";
import { Logo } from "../components/Logo";
import type { Locale } from "../lib/types";

const TEXT = {
  signIn: { fr: "Connexion", en: "Sign in", ar: "تسجيل الدخول" },
  signUp: { fr: "Créer un compte", en: "Sign up", ar: "إنشاء حساب" },
  slogan: {
    fr: "On surveille la machine, pas seulement la caisse.",
    en: "We watch the machine, not just the box.",
    ar: "نراقب الآلة، لا الصندوق فقط.",
  },
  subhead: {
    fr: "Vallum détecte la panne du groupe froid des heures avant que la température ne bouge — et le prouve.",
    en: "Vallum catches a failing refrigeration unit hours before the temperature ever moves — and proves it.",
    ar: "تكتشف Vallum عطل وحدة التبريد قبل ساعات من تغيّر درجة الحرارة — وتثبت ذلك.",
  },
  ctaPrimary: { fr: "Créer un compte gratuit", en: "Create a free account", ar: "أنشئ حسابًا مجانيًا" },
  ctaSecondary: { fr: "J'ai déjà un compte", en: "I already have an account", ar: "لدي حساب بالفعل" },
  howItWorksTitle: { fr: "Trois mots : prédire, intervenir, prouver", en: "Three words: predict, intervene, prove", ar: "ثلاث كلمات: توقّع، تدخّل، أثبِت" },
  step1Title: { fr: "Prédire", en: "Predict", ar: "توقّع" },
  step1Body: {
    fr: "Le courant électrique du groupe froid trahit une panne bien avant que le froid ne faiblisse. On le mesure en continu.",
    en: "Electrical draw gives up a failing compressor long before the cold does. We watch it continuously.",
    ar: "يكشف التيار الكهربائي عن عطل الضاغط قبل أن يضعف التبريد بوقت طويل. نراقبه باستمرار.",
  },
  step2Title: { fr: "Intervenir", en: "Intervene", ar: "تدخّل" },
  step2Body: {
    fr: "Le chauffeur reçoit une instruction claire, pas un chiffre à interpréter. Le répartiteur voit la flotte entière d'un coup d'œil.",
    en: "The driver gets one clear instruction, not a number to interpret. The dispatcher sees the whole fleet at a glance.",
    ar: "يحصل السائق على تعليمات واضحة بدلاً من رقم يحتاج إلى تفسير. يرى المرسل الأسطول بأكمله بنظرة واحدة.",
  },
  step3Title: { fr: "Prouver", en: "Prove", ar: "أثبِت" },
  step3Body: {
    fr: "Température moyenne cinétique, minutes hors plage, couverture des données : un dossier de conformité, pas une promesse.",
    en: "Mean kinetic temperature, minutes out of band, data coverage: a compliance record, not a promise.",
    ar: "متوسط درجة الحرارة الحركية، الدقائق خارج النطاق، تغطية البيانات: سجل امتثال لا مجرد وعد.",
  },
  featuresTitle: { fr: "Ce que fait la plateforme", en: "What the platform does", ar: "ما تقوم به المنصة" },
  featureAlerts: { fr: "Alertes prédictives", en: "Predictive alerts", ar: "تنبيهات تنبؤية" },
  featureAlertsBody: {
    fr: "La dérive électrique est signalée avant toute dérive thermique -- des heures d'avance, pas des minutes.",
    en: "Electrical drift is flagged before any thermal drift -- hours of lead time, not minutes.",
    ar: "يتم رصد الانحراف الكهربائي قبل أي انحراف حراري -- بفارق ساعات لا دقائق.",
  },
  featureFleet: { fr: "Flotte en direct", en: "Live fleet view", ar: "عرض الأسطول المباشر" },
  featureFleetBody: {
    fr: "Chaque véhicule, sa température, son état électrique et ses alertes actives, en temps réel.",
    en: "Every vehicle, its temperature, electrical state, and active alerts, updating in real time.",
    ar: "كل مركبة، درجة حرارتها، حالتها الكهربائية وتنبيهاتها النشطة، بتحديث لحظي.",
  },
  featureDriver: { fr: "Conçu pour la route", en: "Built for the road", ar: "مصمم للطريق" },
  featureDriverBody: {
    fr: "Écran simplifié en mouvement, détail complet à l'arrêt. Une seule action à la fois.",
    en: "One line while moving, full detail once stopped. One action at a time.",
    ar: "سطر واحد أثناء القيادة، وتفاصيل كاملة عند التوقف. إجراء واحد في كل مرة.",
  },
  featureCompliance: { fr: "Conformité mesurable", en: "Measurable compliance", ar: "امتثال قابل للقياس" },
  featureComplianceBody: {
    fr: "TCM, temps hors plage et couverture calculés pour chaque expédition, pas estimés après coup.",
    en: "MKT, time out of band, and coverage computed for every shipment, not estimated after the fact.",
    ar: "يتم حساب MKT والوقت خارج النطاق والتغطية لكل شحنة، لا تقديرها لاحقًا.",
  },
  featureLocale: { fr: "Français, anglais, arabe", en: "French, English, Arabic", ar: "فرنسية، إنجليزية، عربية" },
  featureLocaleBody: {
    fr: "La même alerte, dans la langue de chacun -- interface adaptée de droite à gauche pour l'arabe.",
    en: "The same alert, in each reader's own language -- full right-to-left layout for Arabic.",
    ar: "نفس التنبيه، بلغة كل مستخدم -- تخطيط كامل من اليمين إلى اليسار للعربية.",
  },
  featureResilience: { fr: "Résilient hors ligne", en: "Resilient offline", ar: "مرن دون اتصال" },
  featureResilienceBody: {
    fr: "Les données mises en mémoire tampon pendant une coupure reviennent avec leur horodatage réel, sans trou dans le dossier.",
    en: "Data buffered through a connectivity gap comes back with its real timestamp -- no gap in the record.",
    ar: "تعود البيانات المخزنة مؤقتًا أثناء انقطاع الاتصال بطابعها الزمني الحقيقي -- دون أي فجوة في السجل.",
  },
  footer: {
    fr: "Vallum -- surveillance de la chaîne du froid pour le transport pharmaceutique.",
    en: "Vallum -- cold chain integrity monitoring for pharmaceutical transport.",
    ar: "Vallum -- مراقبة سلامة سلسلة التبريد لنقل المستحضرات الصيدلانية.",
  },
} satisfies Record<string, Record<Locale, string>>;

const CARD_STYLE: CSSProperties = {
  background: "var(--panel)",
  border: "1px solid var(--rule)",
  borderRadius: "1rem",
  padding: "1.25rem",
};

function FeatureCard({ title, body }: { title: string; body: string }) {
  return (
    <div style={CARD_STYLE}>
      <div style={{ fontWeight: 700, marginBlockEnd: "0.4rem" }}>{title}</div>
      <div className="muted" style={{ fontSize: "0.9rem", lineHeight: 1.5 }}>
        {body}
      </div>
    </div>
  );
}

export function LandingPage({
  locale,
  onSignIn,
  onSignUp,
}: {
  locale: Locale;
  onSignIn: () => void;
  onSignUp: () => void;
}) {
  const t = TEXT;

  return (
    <div>
      <header
        style={{
          position: "sticky",
          insetBlockStart: 0,
          zIndex: 10,
          background: "var(--panel)",
          borderBlockEnd: "1px solid var(--rule)",
        }}
      >
        <div className="page wide row space-between" style={{ paddingBlock: "0.75rem" }}>
          <Logo height={30} />
          <div className="row">
            <button className="secondary" onClick={onSignIn}>
              {t.signIn[locale]}
            </button>
            <button onClick={onSignUp}>{t.signUp[locale]}</button>
          </div>
        </div>
      </header>

      <section className="page wide stack" style={{ paddingBlockStart: "3rem", paddingBlockEnd: "3rem", textAlign: "center" }}>
        <h1 style={{ fontSize: "2rem", lineHeight: 1.25, margin: 0 }}>{t.slogan[locale]}</h1>
        <p className="muted" style={{ fontSize: "1.05rem", maxWidth: "560px", marginInline: "auto" }}>
          {t.subhead[locale]}
        </p>
        <div className="row" style={{ justifyContent: "center", marginBlockStart: "0.5rem" }}>
          <button onClick={onSignUp} style={{ fontSize: "1rem", padding: "0.85rem 1.5rem" }}>
            {t.ctaPrimary[locale]}
          </button>
          <button className="secondary" onClick={onSignIn} style={{ fontSize: "1rem", padding: "0.85rem 1.5rem" }}>
            {t.ctaSecondary[locale]}
          </button>
        </div>
      </section>

      <section className="page wide stack" style={{ paddingBlockEnd: "3rem" }}>
        <h2 style={{ textAlign: "center", fontSize: "1.4rem" }}>{t.howItWorksTitle[locale]}</h2>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
            gap: "1rem",
          }}
        >
          <FeatureCard title={`1. ${t.step1Title[locale]}`} body={t.step1Body[locale]} />
          <FeatureCard title={`2. ${t.step2Title[locale]}`} body={t.step2Body[locale]} />
          <FeatureCard title={`3. ${t.step3Title[locale]}`} body={t.step3Body[locale]} />
        </div>
      </section>

      <section className="page wide stack" style={{ paddingBlockEnd: "3rem" }}>
        <h2 style={{ textAlign: "center", fontSize: "1.4rem" }}>{t.featuresTitle[locale]}</h2>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
            gap: "1rem",
          }}
        >
          <FeatureCard title={t.featureAlerts[locale]} body={t.featureAlertsBody[locale]} />
          <FeatureCard title={t.featureFleet[locale]} body={t.featureFleetBody[locale]} />
          <FeatureCard title={t.featureDriver[locale]} body={t.featureDriverBody[locale]} />
          <FeatureCard title={t.featureCompliance[locale]} body={t.featureComplianceBody[locale]} />
          <FeatureCard title={t.featureLocale[locale]} body={t.featureLocaleBody[locale]} />
          <FeatureCard title={t.featureResilience[locale]} body={t.featureResilienceBody[locale]} />
        </div>
      </section>

      <footer className="page wide muted" style={{ textAlign: "center", fontSize: "0.8rem", paddingBlockEnd: "2rem" }}>
        {t.footer[locale]}
      </footer>
    </div>
  );
}
