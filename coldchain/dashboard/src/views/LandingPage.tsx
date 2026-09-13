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
  eyebrow: { fr: "Chaîne du froid pharmaceutique", en: "Pharmaceutical cold chain", ar: "سلسلة التبريد الدوائية" },
  live: { fr: "SURVEILLANCE EN DIRECT", en: "LIVE MONITORING", ar: "مراقبة مباشرة" },
  shipmentSafe: { fr: "Expédition protégée", en: "Shipment protected", ar: "الشحنة محمية" },
  route: { fr: "Tunis → Sfax", en: "Tunis → Sfax", ar: "تونس ← صفاقس" },
  cargo: { fr: "Température cargaison", en: "Cargo temperature", ar: "درجة حرارة الشحنة" },
  unit: { fr: "Groupe froid", en: "Refrigeration unit", ar: "وحدة التبريد" },
  unitHealthy: { fr: "Fonctionnement nominal", en: "Operating normally", ar: "تعمل بشكل طبيعي" },
  prediction: { fr: "Marge avant excursion", en: "Margin before excursion", ar: "الهامش قبل الانحراف" },
  predictionValue: { fr: "> 4 heures", en: "> 4 hours", ar: "> 4 ساعات" },
  trust1: { fr: "Alerte hors réseau", en: "Offline alerting", ar: "تنبيه دون اتصال" },
  trust2: { fr: "Données signées", en: "Signed telemetry", ar: "بيانات موقّعة" },
  trust3: { fr: "Conformité vérifiable", en: "Verifiable compliance", ar: "امتثال قابل للتحقق" },
} satisfies Record<string, Record<Locale, string>>;

function FeatureCard({ icon, title, body }: { icon: string; title: string; body: string }) {
  return (
    <article className="landing-feature-card">
      <span className="landing-feature-icon" aria-hidden="true">{icon}</span>
      <h3>{title}</h3>
      <p>{body}</p>
    </article>
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
    <div className="landing">
      <header className="landing-header">
        <div className="landing-nav">
          <Logo height={30} />
          <div className="landing-nav-actions">
            <button className="secondary" onClick={onSignIn}>
              {t.signIn[locale]}
            </button>
            <button onClick={onSignUp}>{t.signUp[locale]}</button>
          </div>
        </div>
      </header>

      <main>
        <section className="landing-hero">
          <div className="landing-hero-copy">
            <div className="landing-eyebrow"><span />{t.eyebrow[locale]}</div>
            <h1>{t.slogan[locale]}</h1>
            <p>{t.subhead[locale]}</p>
            <div className="landing-hero-actions">
              <button onClick={onSignUp}>{t.ctaPrimary[locale]} <span aria-hidden="true">→</span></button>
              <button className="secondary" onClick={onSignIn}>{t.ctaSecondary[locale]}</button>
            </div>
            <div className="landing-trust-row">
              {[t.trust1[locale], t.trust2[locale], t.trust3[locale]].map((item) => (
                <span key={item}><b aria-hidden="true">✓</b>{item}</span>
              ))}
            </div>
          </div>

          <div className="landing-monitor" aria-label={t.live[locale]}>
            <p className="insight-note" style={{ paddingInline: "1.35rem" }}>{locale === "fr" ? "Aperçu illustratif · données simulées" : locale === "ar" ? "معاينة توضيحية · بيانات محاكاة" : "Illustrative preview · simulated data"}</p>
            <div className="landing-monitor-top">
              <span><i />{t.live[locale]}</span>
              <span className="numeric">ESP32-TN-0042</span>
            </div>
            <div className="landing-monitor-title">
              <div><strong>{t.shipmentSafe[locale]}</strong><span>{t.route[locale]}</span></div>
              <span className="landing-shield" aria-hidden="true">✓</span>
            </div>
            <div className="landing-temp-block">
              <span>{t.cargo[locale]}</span>
              <strong className="numeric">4.6<small>°C</small></strong>
              <div className="landing-band"><i /></div>
              <div className="landing-band-labels numeric"><span>2°C</span><b>2–8°C</b><span>8°C</span></div>
            </div>
            <div className="landing-monitor-grid">
              <div><span>{t.unit[locale]}</span><strong><i />{t.unitHealthy[locale]}</strong></div>
              <div><span>{t.prediction[locale]}</span><strong>{t.predictionValue[locale]}</strong></div>
            </div>
          </div>
        </section>

        <section className="landing-process">
          <div className="landing-section-heading">
            <span>01 — 03</span>
            <h2>{t.howItWorksTitle[locale]}</h2>
          </div>
          <div className="landing-process-grid">
            <FeatureCard icon="01" title={t.step1Title[locale]} body={t.step1Body[locale]} />
            <FeatureCard icon="02" title={t.step2Title[locale]} body={t.step2Body[locale]} />
            <FeatureCard icon="03" title={t.step3Title[locale]} body={t.step3Body[locale]} />
          </div>
        </section>

        <section className="landing-features">
          <div className="landing-section-heading">
            <span>VALLUM</span>
            <h2>{t.featuresTitle[locale]}</h2>
          </div>
          <div className="landing-feature-grid">
            <FeatureCard icon="⚡" title={t.featureAlerts[locale]} body={t.featureAlertsBody[locale]} />
            <FeatureCard icon="⌁" title={t.featureFleet[locale]} body={t.featureFleetBody[locale]} />
            <FeatureCard icon="↗" title={t.featureDriver[locale]} body={t.featureDriverBody[locale]} />
            <FeatureCard icon="✓" title={t.featureCompliance[locale]} body={t.featureComplianceBody[locale]} />
            <FeatureCard icon="文" title={t.featureLocale[locale]} body={t.featureLocaleBody[locale]} />
            <FeatureCard icon="↻" title={t.featureResilience[locale]} body={t.featureResilienceBody[locale]} />
          </div>
        </section>
      </main>

      <footer className="landing-footer">
        <Logo height={24} />
        <span>{t.footer[locale]}</span>
      </footer>
    </div>
  );
}
