import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { EvaluationReport } from "../api/types";
import { useAsync } from "../hooks/useAsync";
import { Bar, ErrorBox, Loading, PageTitle } from "../components/ui";

const NAMES: Record<string, string> = { logreg: "Taste model (logistic regression)", similarity: "Similarity to likes", random: "Random baseline" };
const COLORS: Record<string, string> = { logreg: "bg-kiln", similarity: "bg-moss", random: "bg-muted" };

export function ReportView({ report }: { report: EvaluationReport }) {
  const entries = (["logreg", "similarity", "random"] as const).filter((k) => report.methods[k]);
  return (
    <section aria-labelledby="report-h" className="card p-5" data-testid={report.simulated ? "report-simulated" : "report-real"}>
      <div className="flex flex-wrap items-center gap-3">
        <h2 id="report-h" className="font-display text-xl font-bold">{report.simulated ? "Simulated user report" : "Your held-out report"}</h2>
        {report.simulated
          ? <span className="rounded-full border-2 border-amber bg-amber/20 px-3 py-0.5 text-xs font-extrabold uppercase tracking-wide text-amber" data-testid="simulated-badge">Simulated — not your data</span>
          : <span className="rounded-full bg-moss/20 px-3 py-0.5 text-xs font-extrabold uppercase tracking-wide text-moss">Real ratings</span>}
      </div>
      {report.simulated && <p className="mt-2 rounded-lg bg-amber/10 p-3 text-sm">These numbers come from a synthetic user whose likes are a chosen theme. They show the pipeline works, and say nothing about how well it fits you.</p>}

      {!report.sufficient ? (
        <div className="mt-4" data-testid="insufficient">
          <p className="font-semibold">Not enough data to evaluate yet.</p>
          <p className="mt-1 text-muted">{report.reason ?? "More ratings are needed."} You have {report.n_ratings} ratings ({report.n_likes} likes, {report.n_passes} passes); a real evaluation needs at least 10 with 4 of each kind.</p>
          <Link to="/" className="btn btn-primary mt-4">Rate more sets</Link>
        </div>
      ) : (
        <>
          <p className="mt-3 text-sm text-muted">Precision@{report.k}: of the {report.k} top-ranked held-out sets, the share you actually liked. Mean ± std over {report.n_splits} splits.</p>
          <ul className="mt-4 space-y-4">
            {entries.map((k) => {
              const s = report.methods[k]!;
              return (
                <li key={k}>
                  <div className="mb-1 flex justify-between text-sm">
                    <span className="font-medium">{NAMES[k]}{report.winner === k && <span className="ml-2 chip">winner</span>}</span>
                    <span>{(s.precision_at_k * 100).toFixed(0)}% <span className="text-muted">± {(s.std * 100).toFixed(0)}</span></span>
                  </div>
                  <Bar value={s.precision_at_k} max={1} label={`${NAMES[k]} precision at ${report.k}`} color={COLORS[k]} />
                </li>
              );
            })}
          </ul>
          <p className="mt-4 text-sm"><span className="font-semibold">Base rate:</span> {(report.base_rate * 100).toFixed(0)}% of rated sets are liked, so that is what picking at random would score.</p>
        </>
      )}
      <details className="mt-4 text-sm" open={!report.sufficient ? false : undefined}>
        <summary className="cursor-pointer font-semibold">Protocol</summary>
        <p className="mt-2 text-muted">{report.protocol}</p>
      </details>
    </section>
  );
}

export default function Evaluation() {
  const real = useAsync(() => api.evaluation(), []);
  const [sim, setSim] = useState<EvaluationReport | null>(null);
  const [simLoading, setSimLoading] = useState(false);
  const [simError, setSimError] = useState<string | null>(null);

  const runSim = async () => {
    setSimLoading(true); setSimError(null);
    try { setSim(await api.simulate()); }
    catch (e) { setSimError(e instanceof Error ? e.message : "Simulation failed"); }
    finally { setSimLoading(false); }
  };

  return (
    <div className="space-y-6">
      <PageTitle title="How good are the recommendations?" subtitle="Honest held-out evaluation on your own ratings, compared to simple baselines." />
      {real.loading ? <Loading label="Loading evaluation…" />
        : real.error ? <ErrorBox message={real.error.message} onRetry={real.reload} />
        : real.data && <ReportView report={real.data} />}

      <section className="card p-5" aria-labelledby="sim-h">
        <h2 id="sim-h" className="font-display text-lg font-bold">Try a simulation</h2>
        <p className="mt-1 text-sm text-muted">No ratings to spare? Run the evaluation on a synthetic user. Results are labelled SIMULATED and never mixed with your real report.</p>
        <button className="btn btn-ghost mt-3" onClick={() => void runSim()} disabled={simLoading}>{simLoading ? "Simulating…" : "Run simulated evaluation"}</button>
        {simError && <p role="alert" className="mt-2 text-sm text-danger">{simError}</p>}
      </section>
      {sim && <ReportView report={sim} />}
    </div>
  );
}
