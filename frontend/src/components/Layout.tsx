import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { Logo } from "./Logo";
import { DemoBar } from "./DemoBar";
import { isDemo } from "../demo";
import { useDemoInfo } from "../hooks/useDemoInfo";

const links = [
  { to: "/", label: "Discover", end: true },
  { to: "/recommendations", label: "For you" },
  { to: "/profile", label: "Profile" },
  { to: "/evaluation", label: "Evaluation" },
];

export function Layout() {
  const demo = isDemo();
  const demoInfo = useDemoInfo();
  const [epoch, setEpoch] = useState(0); // bumping it remounts the page so it re-fetches after demo changes
  return (
    <div className="flex min-h-screen flex-col">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-surface focus:p-2">Skip to content</a>
      <header className="border-b border-line bg-surface/80 backdrop-blur">
        <div className="mx-auto flex max-w-4xl flex-wrap items-center justify-between gap-x-6 gap-y-2 px-4 py-3">
          <NavLink to="/" aria-label="Brickwise home"><Logo /></NavLink>
          <nav aria-label="Main" className="flex gap-1">
            {links.map((l) => (
              <NavLink key={l.to} to={l.to} end={l.end}
                className={({ isActive }) => `rounded-lg px-3 py-2 text-sm font-semibold ${isActive ? "bg-kiln text-kiln-ink" : "text-muted hover:bg-line/60 hover:text-ink"}`}>
                {l.label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>
      {demo && <DemoBar onChanged={() => setEpoch((n) => n + 1)} />}
      <main id="main" className="mx-auto w-full max-w-4xl flex-1 px-4 py-6"><Outlet key={epoch} /></main>
      <footer className="border-t border-line px-4 py-6 text-center text-xs text-muted">
        <p className="mx-auto max-w-2xl">
          {demo
            ? (demoInfo?.footer ?? "Brickwise demo. Not affiliated with the LEGO Group or Rebrickable.")
            : <>Brickwise is an independent project, not affiliated with the LEGO Group. LEGO® is a trademark of the LEGO Group. Set data &amp; images from Rebrickable.</>}
        </p>
      </footer>
    </div>
  );
}
