import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import type { Product } from "../api/types";

const BATCH = 6;
const LOW_WATER = 3;

export interface DiscoverState {
  current: Product | null;
  upcoming: Product[];
  remaining: number;
  total: number;
  rated: number;
  loading: boolean;
  error: string | null;
  actionError: string | null;
  busy: boolean;
  canUndo: boolean;
  empty: boolean;
  rate: (rating: 0 | 1) => Promise<void>;
  undo: () => Promise<void>;
  retry: () => void;
}

export function useDiscover(): DiscoverState {
  const [queue, setQueue] = useState<Product[]>([]);
  const [remaining, setRemaining] = useState(0);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState<Product[]>([]);
  const busyRef = useRef(false);
  const fetching = useRef(false);
  const seen = useRef(new Set<string>()); // rated this session (server may lag)
  const queueRef = useRef<Product[]>([]);
  queueRef.current = queue;

  const load = useCallback(async (initial: boolean) => {
    if (fetching.current) return;
    fetching.current = true;
    if (initial) { setLoading(true); setError(null); }
    try {
      const res = await api.nextProducts(BATCH);
      setTotal(res.total);
      if (initial) setRemaining(res.remaining);
      setQueue((q) => {
        const have = new Set(q.map((p) => p.set_num));
        const fresh = res.items.filter((p) => !have.has(p.set_num) && !seen.current.has(p.set_num));
        return [...q, ...fresh];
      });
    } catch (e) {
      if (initial) setError(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      fetching.current = false;
      if (initial) setLoading(false);
    }
  }, []);

  useEffect(() => { void load(true); }, [load]);

  // Top up the queue when it runs low and the server still has more.
  useEffect(() => {
    if (!loading && !error && queue.length < LOW_WATER && remaining > queue.length) void load(false);
  }, [queue.length, remaining, loading, error, load]);

  // Prefetch images of upcoming cards.
  useEffect(() => {
    queue.slice(1, 4).forEach((p) => { const i = new Image(); i.src = p.image_url; });
  }, [queue]);

  const rate = useCallback(async (rating: 0 | 1) => {
    const cur = queueRef.current[0];
    if (!cur || busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setActionError(null);
    // optimistic
    seen.current.add(cur.set_num);
    setQueue((q) => q.filter((p) => p.set_num !== cur.set_num));
    setHistory((h) => [...h, cur]);
    setRemaining((r) => Math.max(0, r - 1));
    try {
      const res = await api.rate(cur.set_num, rating);
      setRemaining(res.remaining);
    } catch (e) {
      if (e instanceof ApiError && e.isDuplicate) {
        // already rated elsewhere: keep it removed, no scary error
      } else {
        // rollback
        seen.current.delete(cur.set_num);
        setQueue((q) => [cur, ...q.filter((p) => p.set_num !== cur.set_num)]);
        setHistory((h) => h.filter((p) => p.set_num !== cur.set_num));
        setRemaining((r) => r + 1);
        setActionError(e instanceof Error ? `Could not save your rating: ${e.message}` : "Could not save your rating.");
      }
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }, []);

  const undo = useCallback(async () => {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setActionError(null);
    try {
      const res = await api.undo();
      setRemaining(res.remaining);
      const sn = res.undone.set_num;
      seen.current.delete(sn);
      const local = history.find((p) => p.set_num === sn);
      if (local) {
        setHistory((h) => h.filter((p) => p.set_num !== sn));
        setQueue((q) => [local, ...q.filter((p) => p.set_num !== sn)]);
      } else {
        setQueue([]);
        fetching.current = false;
        await load(false);
      }
    } catch (e) {
      if (e instanceof ApiError && e.isNotFound) setActionError("Nothing to undo.");
      else setActionError(e instanceof Error ? `Could not undo: ${e.message}` : "Could not undo.");
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }, [history, load]);

  const retry = useCallback(() => { fetching.current = false; void load(true); }, [load]);

  const current = queue[0] ?? null;
  return {
    current, upcoming: queue.slice(1), remaining, total,
    rated: Math.max(0, total - remaining),
    loading, error, actionError, busy,
    canUndo: history.length > 0 || (total > 0 && remaining < total),
    empty: !loading && !error && !current && remaining === 0,
    rate, undo, retry,
  };
}
