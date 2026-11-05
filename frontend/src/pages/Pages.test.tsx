import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import Recommendations from "./Recommendations";
import Evaluation from "./Evaluation";
import Profile from "./Profile";
import { mockFetch, product } from "../test/mockFetch";
import type { EvaluationReport } from "../api/types";

const wrap = (el: React.ReactElement) => render(<MemoryRouter>{el}</MemoryRouter>);

const report = (over: Partial<EvaluationReport> = {}): EvaluationReport => ({
  simulated: false, k: 5, sufficient: true, reason: null, n_ratings: 30, n_likes: 12, n_passes: 18, n_splits: 20,
  protocol: "Repeated 70/30 stratified hold-out.", winner: "logreg", base_rate: 0.4,
  methods: { logreg: { precision_at_k: 0.8, std: 0.1 }, similarity: { precision_at_k: 0.6, std: 0.1 }, random: { precision_at_k: 0.4, std: 0.2 } },
  ...over,
});

describe("Recommendations", () => {
  it("renders insufficient-feedback progress with link", async () => {
    mockFetch({ "GET /api/recommendations": () => ({ json: { status: "insufficient_feedback", method: "logreg", message: "Rate more sets.", min_likes: 3, min_passes: 3, likes: 1, passes: 2, items: [] } }) });
    wrap(<Recommendations />);
    expect(await screen.findByText("Not enough ratings yet")).toBeInTheDocument();
    expect(screen.getByTestId("likes-progress")).toHaveTextContent("1 / 3");
    expect(screen.getByTestId("passes-progress")).toHaveTextContent("2 / 3");
    expect(screen.getByRole("link", { name: /Keep rating/ })).toHaveAttribute("href", "/");
  });

  it("renders recommendations and switches method", async () => {
    const user = userEvent.setup();
    const { calls } = mockFetch({
      "GET /api/recommendations": (_b, url) => ({ json: { status: "ok", method: url.includes("similarity") ? "similarity" : "logreg", message: "", min_likes: 3, min_passes: 3, likes: 5, passes: 5,
        items: [{ product: product(7), score: 0.87, explanation: "Looks like Set 1.", similar_to: [{ product: product(1), similarity: 0.8 }] }] } }),
    });
    wrap(<Recommendations />);
    expect(await screen.findByText("87% match")).toBeInTheDocument();
    expect(screen.getByText("Looks like Set 1.")).toBeInTheDocument();
    expect(screen.getByText(/Similar to your liked/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Similar to likes" }));
    await screen.findByText("87% match");
    expect(calls.some((c) => c.url.includes("method=similarity"))).toBe(true);
  });
});

describe("Evaluation", () => {
  it("labels simulated reports and keeps real ones separate", async () => {
    const user = userEvent.setup();
    mockFetch({
      "GET /api/evaluation": () => ({ json: report() }),
      "POST /api/evaluation/simulate": () => ({ json: report({ simulated: true }) }),
    });
    wrap(<Evaluation />);
    expect(await screen.findByTestId("report-real")).toBeInTheDocument();
    expect(screen.queryByTestId("simulated-badge")).toBeNull();
    await user.click(screen.getByRole("button", { name: /simulated evaluation/i }));
    expect(await screen.findByTestId("simulated-badge")).toHaveTextContent(/simulated/i);
    expect(screen.getByTestId("report-real")).toBeInTheDocument();
  });

  it("shows insufficient-data explanation", async () => {
    mockFetch({ "GET /api/evaluation": () => ({ json: report({ sufficient: false, reason: "Need 10 ratings.", n_ratings: 4, n_likes: 2, n_passes: 2, methods: {}, winner: null }) }) });
    wrap(<Evaluation />);
    const box = await screen.findByTestId("insufficient");
    expect(box).toHaveTextContent("Need 10 ratings.");
  });
});

describe("Profile", () => {
  const prefs = { likes: 3, passes: 4, total_rated: 7, remaining: 10, top_themes: [{ theme: "Space", likes: 3, passes: 1, like_rate: 0.75 }], avg_parts_liked: 500, avg_parts_passed: 120, model: { ready: false, reason: "Need more." } };
  it("shows stats and confirms reset", async () => {
    const user = userEvent.setup();
    const { calls } = mockFetch({ "GET /api/preferences": () => ({ json: prefs }), "DELETE /api/feedback": () => ({ status: 204 }) });
    wrap(<Profile />);
    expect(await screen.findByText("Space")).toBeInTheDocument();
    expect(screen.getByTestId("model-status")).toHaveTextContent("Need more.");
    await user.click(screen.getByRole("button", { name: "Reset profile" }));
    expect(calls.some((c) => c.key === "DELETE /api/feedback")).toBe(false);
    await user.click(screen.getByRole("button", { name: "Yes, reset" }));
    expect(calls.some((c) => c.key === "DELETE /api/feedback")).toBe(true);
  });
});
