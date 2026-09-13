import { useAuth } from "./lib/auth";
import { useDocumentLocale } from "./lib/useDocumentLocale";
import { AuthView } from "./views/AuthView";
import { DispatcherView } from "./views/DispatcherView";
import { DriverView } from "./views/DriverView";
import { QualityView } from "./views/QualityView";

export function App() {
  const { session, profile, loading, activeView } = useAuth();

  // ar needs dir="rtl" on the document, set from the start (not applied
  // reactively after render) so logical CSS properties actually flip.
  useDocumentLocale(profile?.locale ?? "fr");

  if (loading) {
    return <div className="page">…</div>;
  }

  if (!session || !profile) {
    return (
      <div className="app-shell">
        <AuthView />
      </div>
    );
  }

  return (
    <div className="app-shell">
      {activeView === "dispatcher" && <DispatcherView />}
      {activeView === "quality" && <QualityView />}
      {(activeView === "driver" || activeView === null) && <DriverView />}
    </div>
  );
}
