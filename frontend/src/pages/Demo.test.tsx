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
const FOOTER = "Brickwise independent demo: fictional products, original generated artwork and synthetic example preferences. No Rebrickable or LEGO data or images.";
const REAL_BANNER = "Demo catalogue · Real LEGO® sets from your local Rebrickable data · Simulated example ratings";
const REAL_FOOTER = "Brickwise local demo: a small selection of real LEGO® sets from your own local Rebrickable download. Set data and images: Rebrickable.com.";
const info = (mode: "fresh" | "example"): DemoInfo => ({
  demo: true, catalogue: "fictional", banner: BANNER, footer: FOOTER, product_count: 12, profile_mode: mode, provenance: "Fictional.",
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

describe("demo mode on, real local catalogue", () => {
  const realInfo = (): DemoInfo => ({ ...info("fresh"), catalogue: "real", banner: REAL_BANNER, footer: REAL_FOOTER, product_count: 16,
    example_profile: { ...info("fresh").example_profile, warning: "Simulated ratings generated from a stated rule." } });

  it("labels the real catalogue (not fictional) and shows real set details and photo paths", async () => {
    vi.stubEnv("VITE_DEMO_MODE", "1");
    mockFetch({
      "GET /api/demo/info": () => ({ json: realInfo() }),
      "GET /api/products/next": () => ({ json: { items: [product(1, { set_num: "8284-1", name: "Tractor", theme: "Technic", num_parts: 872, image_url: "/images/8284-1.jpg" })], remaining: 1, total: 16 } }),
    });
    app();
    expect(await screen.findByTestId("demo-banner")).toHaveTextContent(REAL_BANNER);
    expect(screen.getByTestId("demo-banner")).not.toHaveTextContent(/Fictional/);
    expect(await screen.findByText(/real LEGO® sets from your own local Rebrickable download/)).toBeInTheDocument();
    expect(screen.queryByText(/No Rebrickable or LEGO data or images/)).not.toBeInTheDocument();
    expect(await screen.findByRole("img", { name: /Tractor/ })).toHaveAttribute("src", "/images/8284-1.jpg");
    expect(screen.getByRole("heading", { name: "Tractor" })).toBeInTheDocument();
  });

  it("describes the example profile as simulated and sizes the evaluation note from the server", async () => {
    vi.stubEnv("VITE_DEMO_MODE", "1");
    const user = userEvent.setup();
    let mode: "fresh" | "example" = "fresh";
    mockFetch({
      "GET /api/demo/info": () => ({ json: { ...realInfo(), profile_mode: mode } }),
      "GET /api/products/next": () => ({ json: { items: [], remaining: 0, total: 16 } }),
      "POST /api/demo/example-profile": () => { mode = "example"; return { json: { profile_mode: "example", seeded: 12 } }; },
    });
    app();
    await user.click(await screen.findByRole("button", { name: /Load example profile \(simulated\)/ }));
    const label = await screen.findByTestId("example-label");
    expect(label).toHaveTextContent("Example profile loaded (simulated)");
    expect(label).toHaveTextContent("Simulated ratings generated from a stated rule.");
  });

  it("does not badge simulated example ratings as real ratings", async () => {
    vi.stubEnv("VITE_DEMO_MODE", "1");
    const sufficient = { simulated: false, k: 5, sufficient: true, reason: null, n_ratings: 12, n_likes: 4, n_passes: 8, n_splits: 20, protocol: "p", winner: null, base_rate: 0.33,
      methods: { logreg: { precision_at_k: 0.25, std: 0 }, similarity: { precision_at_k: 0.25, std: 0 }, random: { precision_at_k: 0.25, std: 0 } } };
    mockFetch({
      "GET /api/demo/info": () => ({ json: { ...realInfo(), profile_mode: "example" } }),
      "GET /api/evaluation": () => ({ json: sufficient }),
    });
    app("/evaluation");
    const badge = await screen.findByTestId("ratings-badge");
    expect(badge).toHaveTextContent("Includes simulated example ratings");
    expect(badge).not.toHaveTextContent(/^Real ratings$/);
  });

  it("evaluation note says how many real sets the demo has", async () => {
    vi.stubEnv("VITE_DEMO_MODE", "1");
    mockFetch({
      "GET /api/demo/info": () => ({ json: realInfo() }),
      "GET /api/evaluation": () => ({ json: { simulated: false, k: 5, sufficient: false, reason: "Need at least 10 ratings.", n_ratings: 0, n_likes: 0, n_passes: 0, n_splits: 0, protocol: "", methods: {}, winner: null, base_rate: 0 } }),
    });
    app("/evaluation");
    expect(await screen.findByTestId("demo-eval-note")).toHaveTextContent(/16 real sets/);
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
