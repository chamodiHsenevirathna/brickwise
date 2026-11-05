import { describe, expect, it } from "vitest";
import { api, ApiError } from "./client";
import { mockFetch } from "../test/mockFetch";

describe("api client", () => {
  it("parses JSON and sends rating body", async () => {
    const { calls } = mockFetch({ "POST /api/feedback": () => ({ status: 201, json: { feedback: { id: 1 }, remaining: 4 } }) });
    const r = await api.rate("1001-1", 1);
    expect(r.remaining).toBe(4);
    expect(calls[0].body).toEqual({ set_num: "1001-1", rating: 1 });
  });

  it("flags 409 duplicates", async () => {
    mockFetch({ "POST /api/feedback": () => ({ status: 409, json: { detail: "already rated" } }) });
    const err = await api.rate("x", 0).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.isDuplicate).toBe(true);
    expect(err.message).toBe("already rated");
  });

  it("flattens 422 validation detail", async () => {
    mockFetch({ "POST /api/feedback": () => ({ status: 422, json: { detail: [{ msg: "bad rating" }] } }) });
    await expect(api.rate("x", 1)).rejects.toMatchObject({ status: 422, message: "bad rating" });
  });

  it("handles 204 and 404", async () => {
    mockFetch({ "DELETE /api/feedback": () => ({ status: 204 }), "POST /api/feedback/undo": () => ({ status: 404, json: { detail: "nothing" } }) });
    await expect(api.resetProfile()).resolves.toBeUndefined();
    await expect(api.undo()).rejects.toMatchObject({ isNotFound: true });
  });

  it("wraps network failures", async () => {
    const { fn } = mockFetch({});
    fn.mockRejectedValueOnce(new TypeError("fail"));
    await expect(api.health()).rejects.toMatchObject({ status: 0 });
  });
});
