import { useState } from "react";
import { api } from "../api/client";
import { useAsync } from "../hooks/useAsync";
import { Bar, EmptyState, ErrorBox, Loading, PageTitle } from "../components/ui";

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="card p-4">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted">{label}</p>
      <p className="mt-1 font-display text-2xl font-extrabold">{value}</p>
    </div>
  );
}
const fmt = (n: number | null) => (n == null ? "—" : Math.round(n).toLocaleString());

export default function Profile() {
  const { data, error, loading, reload } = useAsync(() => api.preferences(), []);
  const [confirming, setConfirming] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [resetError, setResetError] = useState<string | null>(null);

  const doReset = async () => {
    setResetting(true); setResetError(null);
    try { await api.resetProfile(); setConfirming(false); reload(); }
    catch (e) { setResetError(e instanceof Error ? e.message : "Reset failed"); }
    finally { setResetting(false); }
  };

  if (loading) return <Loading label="Loading profile…" />;
  if (error) return <ErrorBox message={error.message} onRetry={reload} />;
  if (!data) return null;
  const m = data.model;

  return (
    <div>
      <PageTitle title="Your taste profile" subtitle="What Brickwise has learned from your ratings." />
      {data.total_rated === 0 ? (
        <EmptyState title="No ratings yet" cta={{ to: "/", label: "Start discovering" }}>Like or pass a few sets to build your profile.</EmptyState>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Stat label="Likes" value={data.likes} />
            <Stat label="Passes" value={data.passes} />
            <Stat label="Avg pieces liked" value={fmt(data.avg_parts_liked)} />
            <Stat label="Avg pieces passed" value={fmt(data.avg_parts_passed)} />
          </div>
          <section className="card mt-6 p-5" aria-labelledby="themes-h">
            <h2 id="themes-h" className="font-display text-lg font-bold">Top themes</h2>
            {data.top_themes.length === 0 ? <p className="mt-2 text-muted">No theme data yet.</p> : (
              <ul className="mt-3 space-y-3">
                {data.top_themes.map((t) => (
                  <li key={t.theme}>
                    <div className="mb-1 flex justify-between text-sm">
                      <span className="font-medium">{t.theme}</span>
                      <span className="text-muted">{t.likes} liked · {t.passes} passed · {Math.round(t.like_rate * 100)}%</span>
                    </div>
                    <Bar value={t.like_rate} max={1} label={`${t.theme} like rate`} />
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}

      <section className="card mt-6 p-5" aria-labelledby="model-h">
        <h2 id="model-h" className="font-display text-lg font-bold">Model status</h2>
        <p className="mt-2" data-testid="model-status">
          {m.ready ? <span className="font-semibold text-moss">Ready — trained on your ratings.</span>
            : <span className="font-semibold text-amber">Not ready yet.</span>}
          {" "}{!m.ready && m.reason ? <span className="text-muted">{m.reason}</span> : null}
        </p>
        {"min_likes" in m && <p className="mt-1 text-sm text-muted">Needs {m.min_likes} likes and {m.min_passes} passes (you have {m.likes} / {m.passes}). Search backend: {m.backend}.</p>}
      </section>

      <section className="mt-6" aria-labelledby="reset-h">
        <h2 id="reset-h" className="sr-only">Reset profile</h2>
        {!confirming ? (
          <button className="btn btn-ghost text-danger" onClick={() => setConfirming(true)} disabled={data.total_rated === 0}>Reset profile</button>
        ) : (
          <div role="alertdialog" aria-labelledby="reset-q" className="card border-danger/60 p-5">
            <p id="reset-q" className="font-semibold">Delete all {data.total_rated} ratings? This cannot be undone.</p>
            {resetError && <p role="alert" className="mt-2 text-sm text-danger">{resetError}</p>}
            <div className="mt-4 flex gap-3">
              <button className="btn btn-danger" onClick={() => void doReset()} disabled={resetting}>{resetting ? "Resetting…" : "Yes, reset"}</button>
              <button className="btn btn-ghost" onClick={() => setConfirming(false)} disabled={resetting}>Cancel</button>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
