import { useCallback, useEffect, useRef, useState } from "react";

export interface AsyncState<T> {
  data: T | null;
  error: Error | null;
  loading: boolean;
  reload: () => void;
  setData: (d: T | null) => void;
}

/** Runs `fn` on mount and whenever `deps` change; ignores stale responses. */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  const token = useRef(0);
  const reload = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    const mine = ++token.current;
    setLoading(true);
    setError(null);
    fn().then(
      (d) => { if (mine === token.current) { setData(d); setLoading(false); } },
      (e) => { if (mine === token.current) { setError(e instanceof Error ? e : new Error(String(e))); setLoading(false); } },
    );
    return () => { token.current++; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  return { data, error, loading, reload, setData };
}
