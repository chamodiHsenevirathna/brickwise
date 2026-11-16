import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { DemoInfo } from "../api/types";
import { isDemo } from "../demo";

/** Demo metadata from the demo backend (banner, footer, catalogue kind). null outside demo mode or on error. */
export function useDemoInfo(): DemoInfo | null {
  const [info, setInfo] = useState<DemoInfo | null>(null);
  useEffect(() => {
    if (!isDemo()) return;
    let live = true;
    api.demoInfo().then((i) => { if (live) setInfo(i); }).catch(() => { /* DemoBar reports the error */ });
    return () => { live = false; };
  }, []);
  return info;
}
