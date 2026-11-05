import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import type { Product } from "../api/types";

export function PageTitle({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="mb-5">
      <h1 className="font-display text-3xl font-extrabold tracking-tight">{title}</h1>
      {subtitle && <p className="mt-1 text-muted">{subtitle}</p>}
    </div>
  );
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="card border-danger/50 p-5 text-center">
      <p className="font-semibold text-danger">Something went wrong</p>
      <p className="mt-1 text-sm text-muted">{message}</p>
      {onRetry && <button className="btn btn-primary mt-4" onClick={onRetry}>Try again</button>}
    </div>
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div role="status" aria-live="polite" className="space-y-3">
      <span className="sr-only">{label}</span>
      <div className="skeleton h-24 rounded-2xl" /><div className="skeleton h-24 rounded-2xl" />
    </div>
  );
}

export function Bar({ value, max = 1, label, color = "bg-kiln" }: { value: number; max?: number; label: string; color?: string }) {
  const pct = max > 0 ? Math.min(100, Math.max(0, (value / max) * 100)) : 0;
  return (
    <div role="meter" aria-label={label} aria-valuemin={0} aria-valuemax={max} aria-valuenow={value} className="h-3 w-full overflow-hidden rounded-full bg-line/60">
      <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

export function ProductImage({ product, className = "" }: { product: Product; className?: string }) {
  return (
    <img src={product.image_url} alt={`${product.name} (set ${product.set_num})`} loading="lazy" draggable={false}
      className={`bg-white object-contain ${className}`} />
  );
}

export function ProductMeta({ product }: { product: Product }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      <span className="chip">{product.theme}</span>
      {product.num_parts != null && <span className="chip">{product.num_parts.toLocaleString()} pieces</span>}
      {product.year != null && <span className="chip">{product.year}</span>}
    </div>
  );
}

export function EmptyState({ title, children, cta }: { title: string; children?: ReactNode; cta?: { to: string; label: string } }) {
  return (
    <div className="card p-8 text-center">
      <h2 className="font-display text-xl font-bold">{title}</h2>
      {children && <div className="mt-2 text-muted">{children}</div>}
      {cta && <Link to={cta.to} className="btn btn-primary mt-5">{cta.label}</Link>}
    </div>
  );
}
