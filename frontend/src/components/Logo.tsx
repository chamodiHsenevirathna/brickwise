/** Original brick-stud inspired mark: a rounded block with two studs. */
export function LogoMark({ size = 36 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" aria-hidden="true" focusable="false">
      <rect x="2" y="12" width="36" height="24" rx="6" fill="rgb(var(--kiln))" />
      <rect x="2" y="26" width="36" height="10" rx="5" fill="rgb(var(--ink) / .18)" />
      <circle cx="13" cy="10" r="6" fill="rgb(var(--amber))" />
      <circle cx="27" cy="10" r="6" fill="rgb(var(--amber))" />
      <circle cx="13" cy="9" r="2.2" fill="rgb(255 255 255 / .55)" />
      <circle cx="27" cy="9" r="2.2" fill="rgb(255 255 255 / .55)" />
    </svg>
  );
}
export function Logo() {
  return (
    <span className="flex items-center gap-2">
      <LogoMark />
      <span className="font-display text-xl font-extrabold tracking-tight">Brickwise</span>
    </span>
  );
}
