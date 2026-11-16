import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { Layout } from "../components/Layout";
import Discover from "./Discover";
import Evaluation from "./Evaluation";
import { mockFetch, product } from "../test/mockFetch";
import type { DemoInfo } from "../api/types";

const BANNER = "Independent demo catalogue · Fictional products · Synthetic data";
const info = (mode: "fresh" | "example"): DemoInfo => ({
  demo: true, banner: BANNER, profile_mode: mode, provenance: "Fictional.",
  example_profile: { profile_id: "demo-vehicle-space-fan", description: "d", warning: "Illustrative synthetic preferences only.", n_ratings: 10, held_out: ["BW-009", "BW-011"] },
});
const demoProduct = (n: number) => product(n, { set_num: `BW-00${n}`, name: `Demo ${n}`, theme: "Vehicles", image_url: `/images/bw-00${n}.jpg` });

const app = (path = "/") => render(
  <MemoryRouter initialEntries={[path]}>
    <Routes><Route element={<Layout />}><Route index element={<Discover />} /><Route path="evaluation" element={<Evaluation />} /></Route></Routes>
  </MemoryRouter>);

afterEach(() => { vi.unstubAllEnvs(); });

describe("demo mode off (personal app)", () => {
  it("shows no demo controls and keeps the Rebrickable attribution", async () => {
    mockFetch({ "GET /api/products/next": () => ({ json: { items: [product(1)], remaining: 1, total: 1 } }) });
    app();
    await screen.findByRole("heading", { name: "Set 1" });
    expect(screen.queryByTestId("demo-banner")).not.toBeInTheDocument();
    expect(screen.getByText(/Set data & images from Rebrickable/)).toBeInTheDocument();
  });
});

describe("demo mode on", () => {
  it("shows the synthetic label, demo images, and supports like and undo", async () => {
    vi.stubEnv("VITE_DEMO_MODE", "1");
    const user = userEvent.setup();
    const { calls } = mockFetch({
      "GET /api/demo/info": () => ({ json: info("fresh") }),
      "GET /api/products/next": () => ({ json: { items: [demoProduct(1), demoProduct(2)], remaining: 2, total: 2 } }),
      "POST /api/feedback": (b) => ({ status: 201, json: { feedback: b, remaining: 1 } }),
      "POST /api/feedback/undo": () => ({ json: { undone: { set_num: "BW-001", rating: 1 }, remaining: 2 } }),
    });
    app();
    expect(await screen.findByTestId("demo-banner")).toHaveTextContent(BANNER);
    expect(screen.queryByText(/Set data & images from Rebrickable/)).not.toBeInTheDocument();
    expect(screen.getByText(/No Rebrickable or LEGO data or images/)).toBeInTheDocument();
    const img = await screen.findByRole("img", { name: /Demo 1/ });
    expect(img).toHaveAttribute("src", "/images/bw-001.jpg");
    await user.click(screen.getByRole("button", { name: /^Like/ }));
    await screen.findByRole("heading", { name: "Demo 2" });
    expect(calls.find((c) => c.key === "POST /api/feedback")!.body).toEqual({ set_num: "BW-001", rating: 1 });
    await waitFor(() => expect(screen.getByRole("button", { name: /Undo/ })).toBeEnabled());
    await user.click(screen.getByRole("button", { name: /Undo/ }));
    await screen.findByRole("heading", { name: "Demo 1" });
  });

  it("loads the labelled example profile and resets back to fresh", async () => {
    vi.stubEnv("VITE_DEMO_MODE", "1");
    const user = userEvent.setup();
    let mode: "fresh" | "example" = "fresh";
    const { calls } = mockFetch({
      "GET /api/demo/info": () => ({ json: info(mode) }),
      "GET /api/products/next": () => ({ json: { items: [demoProduct(1)], remaining: 1, total: 1 } }),
      "POST /api/demo/example-profile": () => { mode = "example"; return { json: { profile_mode: "example", seeded: 10 } }; },
      "POST /api/demo/reset": () => { mode = "fresh"; return { json: { profile_mode: "fresh" } }; },
    });
    app();
    await screen.findByTestId("demo-banner");
    expect(screen.queryByTestId("example-label")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Load example profile/ }));
    const label = await screen.findByTestId("example-label");
    expect(label).toHaveTextContent(/synthetic/i);
    expect(label).toHaveTextContent("Illustrative synthetic preferences only.");
    expect(calls.some((c) => c.key === "POST /api/demo/example-profile")).toBe(true);
    // the page refetches its data after the profile changes
    await waitFor(() => expect(calls.filter((c) => c.key === "GET /api/products/next").length).toBeGreaterThan(1));
    await user.click(screen.getByRole("button", { name: /Reset demo/ }));
    await waitFor(() => expect(screen.queryByTestId("example-label")).not.toBeInTheDocument());
    expect(calls.some((c) => c.key === "POST /api/demo/reset")).toBe(true);
  });

  it("surfaces a demo-server error instead of failing silently", async () => {
    vi.stubEnv("VITE_DEMO_MODE", "1");
    mockFetch({
      "GET /api/demo/info": () => ({ status: 500, json: { detail: "demo db missing" } }),
      "GET /api/products/next": () => ({ json: { items: [], remaining: 0, total: 0 } }),
    });
    app();
    expect(await screen.findByRole("alert")).toHaveTextContent("demo db missing");
  });

  it("explains evaluation limits and hides the simulated-user card", async () => {
    vi.stubEnv("VITE_DEMO_MODE", "1");
    mockFetch({
      "GET /api/demo/info": () => ({ json: info("fresh") }),
      "GET /api/evaluation": () => ({ json: { simulated: false, k: 5, sufficient: false, reason: "Need at least 10 ratings.", n_ratings: 2, n_likes: 1, n_passes: 1, n_splits: 0, protocol: "", methods: {}, winner: null, base_rate: 0 } }),
    });
    app("/evaluation");
    expect(await screen.findByTestId("demo-eval-note")).toHaveTextContent(/12 fictional products/);
    expect(await screen.findByTestId("insufficient")).toBeInTheDocument();
    expect(screen.getByTestId("demo-no-sim")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Run simulated evaluation/ })).not.toBeInTheDocument();
  });
});
