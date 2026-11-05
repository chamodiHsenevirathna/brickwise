import { describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import Discover from "./Discover";
import { mockFetch, product } from "../test/mockFetch";

const wrap = () => render(<MemoryRouter><Discover /></MemoryRouter>);
const items = [product(1), product(2), product(3)];
const nextRoute = (list = items, remaining = list.length, total = 3) => () => ({ json: { items: list, remaining, total } });

describe("Discover", () => {
  it("likes, passes and undoes", async () => {
    const user = userEvent.setup();
    const { calls } = mockFetch({
      "GET /api/products/next": nextRoute(),
      "POST /api/feedback": (b) => ({ status: 201, json: { feedback: b, remaining: 2 } }),
      "POST /api/feedback/undo": () => ({ json: { undone: { set_num: "1002-1", rating: 0 }, remaining: 3 } }),
    });
    wrap();
    expect(await screen.findByRole("heading", { name: "Set 1" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^Like/ }));
    expect(await screen.findByRole("heading", { name: "Set 2" })).toBeInTheDocument();
    expect(calls.find((c) => c.key === "POST /api/feedback")!.body).toEqual({ set_num: "1001-1", rating: 1 });
    await waitFor(() => expect(screen.getByTestId("remaining")).toHaveTextContent("2 left"));
    await user.click(screen.getByRole("button", { name: /^Pass/ }));
    expect(await screen.findByRole("heading", { name: "Set 3" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: /Undo/ })).toBeEnabled());
    await user.click(screen.getByRole("button", { name: /Undo/ }));
    expect(await screen.findByRole("heading", { name: "Set 2" })).toBeInTheDocument();
  });

  it("supports keyboard shortcuts", async () => {
    const user = userEvent.setup();
    const { calls } = mockFetch({
      "GET /api/products/next": nextRoute(),
      "POST /api/feedback": (b) => ({ status: 201, json: { feedback: b, remaining: 1 } }),
      "POST /api/feedback/undo": () => ({ json: { undone: { set_num: "1002-1", rating: 0 }, remaining: 2 } }),
    });
    wrap();
    await screen.findByRole("heading", { name: "Set 1" });
    await user.keyboard("{ArrowRight}");
    await screen.findByRole("heading", { name: "Set 2" });
    await waitFor(() => expect(screen.getByRole("button", { name: /^Pass/ })).toBeEnabled());
    await user.keyboard("p");
    await screen.findByRole("heading", { name: "Set 3" });
    const posts = calls.filter((c) => c.key === "POST /api/feedback").map((c) => c.body);
    expect(posts).toEqual([{ set_num: "1001-1", rating: 1 }, { set_num: "1002-1", rating: 0 }]);
    await waitFor(() => expect(screen.getByRole("button", { name: /Undo/ })).toBeEnabled());
    await user.keyboard("z");
    await screen.findByRole("heading", { name: "Set 2" });
  });

  it("rolls back on error", async () => {
    const user = userEvent.setup();
    mockFetch({
      "GET /api/products/next": nextRoute(),
      "POST /api/feedback": () => ({ status: 500, json: { detail: "boom" } }),
    });
    wrap();
    await screen.findByRole("heading", { name: "Set 1" });
    await user.click(screen.getByRole("button", { name: /^Like/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("boom");
    expect(screen.getByRole("heading", { name: "Set 1" })).toBeInTheDocument();
  });

  it("treats 409 as success without an error", async () => {
    const user = userEvent.setup();
    mockFetch({
      "GET /api/products/next": nextRoute(),
      "POST /api/feedback": () => ({ status: 409, json: { detail: "dup" } }),
    });
    wrap();
    await screen.findByRole("heading", { name: "Set 1" });
    await user.click(screen.getByRole("button", { name: /^Like/ }));
    expect(await screen.findByRole("heading", { name: "Set 2" })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("blocks double submission", async () => {
    const user = userEvent.setup();
    let release!: () => void;
    const gate = new Promise<void>((r) => { release = r; });
    const { calls } = mockFetch({
      "GET /api/products/next": nextRoute(),
      "POST /api/feedback": async (b) => { await gate; return { status: 201, json: { feedback: b, remaining: 2 } }; },
    });
    wrap();
    await screen.findByRole("heading", { name: "Set 1" });
    await user.keyboard("l");
    await user.keyboard("l");
    release();
    await screen.findByRole("heading", { name: "Set 2" });
    expect(calls.filter((c) => c.key === "POST /api/feedback")).toHaveLength(1);
  });

  it("shows the empty state", async () => {
    mockFetch({ "GET /api/products/next": nextRoute([], 0, 3) });
    wrap();
    expect(await screen.findByText("You have rated everything")).toBeInTheDocument();
  });

  it("shows error with retry", async () => {
    const user = userEvent.setup();
    let fail = true;
    mockFetch({ "GET /api/products/next": () => (fail ? { status: 500, json: { detail: "down" } } : { json: { items: items, remaining: 3, total: 3 } }) });
    wrap();
    expect(await screen.findByRole("alert")).toHaveTextContent("down");
    fail = false;
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("heading", { name: "Set 1" })).toBeInTheDocument();
  });

  it("shows a loading skeleton first", () => {
    mockFetch({ "GET /api/products/next": nextRoute() });
    wrap();
    expect(screen.getByRole("status")).toHaveTextContent("Loading sets");
  });
});
