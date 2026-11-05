import { vi } from "vitest";
import type { Product } from "../api/types";

export type Handler = (body: unknown, url: string) => { status?: number; json?: unknown } | Promise<{ status?: number; json?: unknown }>;

/** Routes keyed by "METHOD /path" (query string ignored). */
export function mockFetch(routes: Record<string, Handler>) {
  const calls: { key: string; body: unknown; url: string }[] = [];
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    const key = `${method} ${url.split("?")[0]}`;
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    calls.push({ key, body, url });
    const h = routes[key];
    if (!h) return new Response(JSON.stringify({ detail: `no mock for ${key}` }), { status: 500 });
    const r = await h(body, url);
    const status = r.status ?? 200;
    if (status === 204) return new Response(null, { status });
    return new Response(JSON.stringify(r.json ?? {}), { status, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fn);
  return { fn, calls };
}

export const product = (n: number, over: Partial<Product> = {}): Product => ({
  set_num: `${1000 + n}-1`, name: `Set ${n}`, year: 2020, theme: "City", root_theme: "City",
  num_parts: 100 * n, image_url: `/images/${1000 + n}-1.jpg`, ...over,
});
