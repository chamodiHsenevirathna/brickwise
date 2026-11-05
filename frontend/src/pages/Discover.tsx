import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useDiscover } from "../hooks/useDiscover";
import { EmptyState, ErrorBox, PageTitle, ProductImage, ProductMeta } from "../components/ui";

const SWIPE_THRESHOLD = 110;

export default function Discover() {
  const d = useDiscover();
  const { rate, undo } = d;
  const [dx, setDx] = useState(0);
  const [dragging, setDragging] = useState(false);
  const start = useRef<number | null>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
      const k = e.key.toLowerCase();
      if (k === "arrowright" || k === "l") { e.preventDefault(); void rate(1); }
      else if (k === "arrowleft" || k === "p") { e.preventDefault(); void rate(0); }
      else if (k === "z" || k === "backspace") { e.preventDefault(); void undo(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [rate, undo]);

  const onDown = (e: React.PointerEvent) => {
    if (d.busy) return;
    start.current = e.clientX; setDragging(true);
    (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
  };
  const onMove = (e: React.PointerEvent) => { if (start.current != null) setDx(e.clientX - start.current); };
  const onUp = () => {
    if (start.current == null) return;
    const moved = dx;
    start.current = null; setDragging(false); setDx(0);
    if (moved > SWIPE_THRESHOLD) void rate(1);
    else if (moved < -SWIPE_THRESHOLD) void rate(0);
  };

  const pct = d.total > 0 ? Math.round((d.rated / d.total) * 100) : 0;
  const intent = Math.min(1, Math.abs(dx) / SWIPE_THRESHOLD);

  let body;
  if (d.loading) {
    body = (
      <div role="status" aria-live="polite" className="card overflow-hidden">
        <span className="sr-only">Loading sets…</span>
        <div className="skeleton aspect-[4/3] w-full" />
        <div className="space-y-3 p-5"><div className="skeleton h-6 w-2/3 rounded" /><div className="skeleton h-4 w-1/2 rounded" /></div>
      </div>
    );
  } else if (d.error) {
    body = <ErrorBox message={d.error} onRetry={d.retry} />;
  } else if (d.empty) {
    body = (
      <EmptyState title="You have rated everything" cta={{ to: "/recommendations", label: "See your recommendations" }}>
        <p>Every set has a verdict. Check what the model thinks you will love, or undo the last rating below.</p>
        <button className="btn btn-ghost mt-3" onClick={() => void d.undo()} disabled={d.busy || !d.canUndo}>Undo last rating</button>
      </EmptyState>
    );
  } else if (!d.current) {
    body = <div role="status" className="skeleton aspect-[4/3] w-full rounded-2xl"><span className="sr-only">Loading next set…</span></div>;
  } else {
    const p = d.current;
    body = (
      <article
        aria-label={`${p.name}, set ${p.set_num}`}
        className={`card swipe-card relative overflow-hidden ${dragging ? "dragging" : ""}`}
        style={{ transform: `translateX(${dx}px) rotate(${dx / 25}deg)`, opacity: 1 - intent * 0.25 }}
        onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerCancel={onUp}
        data-testid="card"
      >
        <div className="relative">
          <ProductImage product={p} className="aspect-[4/3] w-full" />
          <span aria-hidden="true" className="absolute left-4 top-4 rotate-[-8deg] rounded-lg border-4 border-moss px-3 py-1 text-xl font-extrabold text-moss" style={{ opacity: dx > 0 ? intent : 0 }}>LIKE</span>
          <span aria-hidden="true" className="absolute right-4 top-4 rotate-[8deg] rounded-lg border-4 border-danger px-3 py-1 text-xl font-extrabold text-danger" style={{ opacity: dx < 0 ? intent : 0 }}>PASS</span>
        </div>
        <div className="space-y-2 p-5">
          <h2 className="font-display text-2xl font-extrabold leading-tight">{p.name}</h2>
          <p className="text-sm text-muted">Set {p.set_num}</p>
          <ProductMeta product={p} />
        </div>
      </article>
    );
  }

  const showControls = !d.loading && !d.error && !d.empty;

  return (
    <div className="mx-auto max-w-xl">
      <PageTitle title="Discover" subtitle="Rate sets so Brickwise can learn your taste." />
      {!d.loading && !d.error && d.total > 0 && (
        <div className="mb-4">
          <div className="mb-1 flex justify-between text-sm text-muted">
            <span data-testid="remaining">{d.remaining} left to rate</span>
            <span>{d.rated} / {d.total} rated</span>
          </div>
          <div role="progressbar" aria-label="Rating progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct} className="h-2 overflow-hidden rounded-full bg-line/60">
            <div className="h-full bg-moss transition-[width]" style={{ width: `${pct}%` }} />
          </div>
        </div>
      )}
      {body}
      {d.actionError && <p role="alert" className="mt-3 rounded-lg bg-danger/10 p-3 text-sm text-danger">{d.actionError}</p>}
      {showControls && (
        <>
          <div className="mt-5 grid grid-cols-[1fr_auto_1fr] items-center gap-3">
            <button className="btn btn-ghost border-danger/60 text-danger" onClick={() => void d.rate(0)} disabled={!d.current || d.busy} aria-label="Pass (left arrow or P)">
              ✕ Pass
            </button>
            <button className="btn btn-ghost" onClick={() => void d.undo()} disabled={d.busy || !d.canUndo} aria-label="Undo last rating (Z or Backspace)">
              ↶ Undo
            </button>
            <button className="btn btn-moss" onClick={() => void d.rate(1)} disabled={!d.current || d.busy} aria-label="Like (right arrow or L)">
              ♥ Like
            </button>
          </div>
          <p className="mt-4 hidden text-center text-xs text-muted sm:block">
            <span className="kbd">←</span>/<span className="kbd">P</span> pass · <span className="kbd">→</span>/<span className="kbd">L</span> like · <span className="kbd">Z</span> undo · or drag the card
          </p>
        </>
      )}
      {d.rated >= 6 && <p className="mt-6 text-center text-sm"><Link className="font-semibold text-kiln underline" to="/recommendations">See recommendations →</Link></p>}
    </div>
  );
}
