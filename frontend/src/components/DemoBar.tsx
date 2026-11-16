import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { DemoInfo } from "../api/types";
import { DEMO_BANNER } from "../demo";

/** Demo-only strip: always-visible synthetic-data label, plus example-profile and reset controls. */
export function DemoBar({ onChanged }: { onChanged: () => void }) {
  const [info, setInfo] = useState<DemoInfo | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try { setInfo(await api.demoInfo()); setError(null); }
    catch (e) { setError(e instanceof Error ? e.message : "Demo server unavailable"); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const run = async (action: () => Promise<unknown>) => {
    setBusy(true); setError(null);
    try { await action(); await load(); onChanged(); }
    catch (e) { setError(e instanceof Error ? e.message : "Action failed"); }
    finally { setBusy(false); }
  };

  const example = info?.profile_mode === "example";
  return (
    <section aria-label="Demo controls" className="border-b border-amber/50 bg-amber/15">
      <div className="mx-auto max-w-4xl px-4 py-2 text-sm">
        <p className="font-bold" data-testid="demo-banner">{DEMO_BANNER}</p>
        {example && (
          <p className="mt-1" data-testid="example-label">
            <span className="font-semibold">Example profile loaded (synthetic).</span>{" "}
            {info?.example_profile.warning} Anything you rate now is added on top.
          </p>
        )}
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <button className="btn btn-ghost !min-h-0 !px-3 !py-1.5 text-sm" disabled={busy || !info}
            onClick={() => void run(api.demoSeedExample)}>
            {example ? "Reload example profile" : "Load example profile (synthetic)"}
          </button>
          <button className="btn btn-ghost !min-h-0 !px-3 !py-1.5 text-sm" disabled={busy || !info}
            onClick={() => void run(api.demoReset)}>
            Reset demo (start fresh)
          </button>
          {!example && info && <span className="text-xs text-muted">Fresh demo: no ratings yet. Like and Pass to build your own profile.</span>}
        </div>
        {error && <p role="alert" className="mt-1 text-danger">{error}</p>}
      </div>
    </section>
  );
}
