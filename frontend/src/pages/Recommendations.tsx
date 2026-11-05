import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { Method, Recommendation, RecommendationsResponse } from "../api/types";
import { useAsync } from "../hooks/useAsync";
import { Bar, EmptyState, ErrorBox, Loading, PageTitle, ProductImage, ProductMeta } from "../components/ui";

const METHODS: { id: Method; label: string; blurb: string }[] = [
  { id: "logreg", label: "Taste model", blurb: "Logistic regression trained on your likes and passes using image embeddings." },
  { id: "similarity", label: "Similar to likes", blurb: "Nearest neighbours of the sets you liked, no training needed." },
];

export function InsufficientFeedback({ r }: { r: RecommendationsResponse }) {
  const likesPct = (Math.min(r.likes, r.min_likes) / Math.max(1, r.min_likes)) * 100;
  const passesPct = (Math.min(r.passes, r.min_passes) / Math.max(1, r.min_passes)) * 100;
  return (
    <section className="card p-6" aria-labelledby="need-more">
      <h2 id="need-more" className="font-display text-xl font-bold">Not enough ratings yet</h2>
      <p className="mt-1 text-muted">{r.message}</p>
      <div className="mt-5 space-y-4">
        <div>
          <div className="mb-1 flex justify-between text-sm"><span>Likes</span><span data-testid="likes-progress">{r.likes} / {r.min_likes}</span></div>
          <Bar value={Math.min(r.likes, r.min_likes)} max={r.min_likes} label="Likes progress" color="bg-moss" />
          <span className="sr-only">{Math.round(likesPct)}%</span>
        </div>
        <div>
          <div className="mb-1 flex justify-between text-sm"><span>Passes</span><span data-testid="passes-progress">{r.passes} / {r.min_passes}</span></div>
          <Bar value={Math.min(r.passes, r.min_passes)} max={r.min_passes} label="Passes progress" color="bg-danger" />
          <span className="sr-only">{Math.round(passesPct)}%</span>
        </div>
      </div>
      <Link to="/" className="btn btn-primary mt-6">Keep rating on Discover</Link>
    </section>
  );
}

function RecCard({ rec, rank }: { rec: Recommendation; rank: number }) {
  const pct = Math.round(rec.score * 100);
  return (
    <li className="card flex flex-col overflow-hidden sm:flex-row">
      <ProductImage product={rec.product} className="aspect-[4/3] w-full sm:aspect-square sm:w-56" />
      <div className="flex-1 space-y-3 p-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-muted">#{rank} · Set {rec.product.set_num}</p>
            <h3 className="font-display text-xl font-extrabold leading-tight">{rec.product.name}</h3>
          </div>
          <span className="shrink-0 rounded-full bg-moss px-3 py-1 text-sm font-bold text-kiln-ink" aria-label={`${pct} percent match`}>{pct}% match</span>
        </div>
        <ProductMeta product={rec.product} />
        <p className="text-sm">{rec.explanation}</p>
        {rec.similar_to.length > 0 && (
          <div>
            <p className="mb-1 text-xs font-semibold text-muted">Similar to your liked:</p>
            <ul className="flex flex-wrap gap-2">
              {rec.similar_to.map((s) => (
                <li key={s.product.set_num} className="flex w-20 flex-col items-center text-center">
                  <ProductImage product={s.product} className="h-14 w-20 rounded-lg border border-line" />
                  <span className="mt-0.5 line-clamp-2 text-[11px] leading-tight text-muted">{s.product.name}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </li>
  );
}

export default function Recommendations() {
  const [method, setMethod] = useState<Method>("logreg");
  const { data, error, loading, reload } = useAsync(() => api.recommendations(method, 5), [method]);

  return (
    <div>
      <PageTitle title="Recommended for you" subtitle="Top 5 unrated sets, ranked by predicted taste match." />
      <div role="group" aria-label="Recommendation method" className="mb-2 inline-flex rounded-xl border border-line bg-surface p-1">
        {METHODS.map((m) => (
          <button key={m.id} aria-pressed={method === m.id} onClick={() => setMethod(m.id)}
            className={`rounded-lg px-4 py-2 text-sm font-semibold ${method === m.id ? "bg-kiln text-kiln-ink" : "text-muted hover:text-ink"}`}>
            {m.label}
          </button>
        ))}
      </div>
      <p className="mb-5 text-sm text-muted">{METHODS.find((m) => m.id === method)?.blurb}</p>

      {loading ? <Loading label="Loading recommendations…" />
        : error ? <ErrorBox message={error.message} onRetry={reload} />
        : data?.status === "insufficient_feedback" ? <InsufficientFeedback r={data} />
        : data?.status === "unavailable" ? <EmptyState title="Recommendations unavailable">{data.message}</EmptyState>
        : data && data.items.length === 0 ? <EmptyState title="No recommendations" cta={{ to: "/", label: "Back to Discover" }}>There is nothing left to recommend.</EmptyState>
        : data && <ol className="space-y-4" aria-label="Recommendations">{data.items.map((r, i) => <RecCard key={r.product.set_num} rec={r} rank={i + 1} />)}</ol>}
    </div>
  );
}
