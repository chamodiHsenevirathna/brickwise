/** Independent demo mode (`vite --mode demo`): fictional catalogue served by a separate backend. */
export const DEMO_BANNER = "Independent demo catalogue · Fictional products · Synthetic data";

export function isDemo(): boolean {
  return import.meta.env.VITE_DEMO_MODE === "1";
}
