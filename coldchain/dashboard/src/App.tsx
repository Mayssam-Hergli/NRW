import { useState } from "react";
import { useAuth } from "./lib/auth";
import { useDocumentLocale } from "./lib/useDocumentLocale";
import { AuthView } from "./views/AuthView";
import { CertificateView } from "./views/CertificateView";
import { DispatcherView } from "./views/DispatcherView";
import { DriverView } from "./views/DriverView";
import { LandingPage } from "./views/LandingPage";
import { QualityView } from "./views/QualityView";

type UnauthPage = "landing" | "signIn" | "signUp";

export function App() {
  const { session, profile, loading, activeView } = useAuth();
  const [unauthPage, setUnauthPage] = useState<UnauthPage>("landing");
  const [certificateShipmentId, setCertificateShipmentId] = useState<string | null>(null);

  // ar needs dir="rtl" on the document, set from the start (not applied
  // reactively after render) so logical CSS properties actually flip.
  useDocumentLocale(profile?.locale ?? "fr");

  if (loading) {
    return <div className="page">…</div>;
  }

  if (!session || !profile) {
    if (unauthPage === "landing") {
      return (
        <div className="app-shell">
          <LandingPage
            locale="fr"
            onSignIn={() => setUnauthPage("signIn")}
            onSignUp={() => setUnauthPage("signUp")}
          />
        </div>
      );
    }
    return (
      <div className="app-shell">
        <AuthView initialMode={unauthPage} onBack={() => setUnauthPage("landing")} />
      </div>
    );
  }

  const locale = profile.locale;

  if (certificateShipmentId) {
    return (
      <div className="app-shell">
        <CertificateView
          shipmentId={certificateShipmentId}
          locale={locale}
          onBack={() => setCertificateShipmentId(null)}
        />
      </div>
    );
  }

  return (
    <div className="app-shell">
      {activeView === "dispatcher" && <DispatcherView locale={locale} />}
      {activeView === "quality" && (
        <QualityView locale={locale} onOpenCertificate={setCertificateShipmentId} />
      )}
      {(activeView === "driver" || activeView === null) && <DriverView locale={locale} />}
    </div>
  );
}
