import { describe, it, expect, beforeEach } from "vitest";
import { LocalMemoryProvider } from "@aithru-agent/memory";

describe("LocalMemoryProvider", () => {
  let mem: LocalMemoryProvider;
  const scope = "org_1:user_1:thread:t1";
  const otherScope = "org_1:user_2:thread:t1";

  beforeEach(() => {
    mem = new LocalMemoryProvider();
  });

  it("remembers and recalls values", () => {
    mem.remember(scope, "key1", "value1");
    expect(mem.recall(scope, "key1")).toBe("value1");
  });

  it("returns undefined for missing keys", () => {
    expect(mem.recall(scope, "nonexistent")).toBeUndefined();
  });

  it("forgets keys", () => {
    mem.remember(scope, "key1", "value1");
    expect(mem.forget(scope, "key1")).toBe(true);
    expect(mem.recall(scope, "key1")).toBeUndefined();
    expect(mem.forget(scope, "key1")).toBe(false);
  });

  it("respects TTL expiration", async () => {
    mem.remember(scope, "temp", "data", 10); // 10ms TTL
    expect(mem.recall(scope, "temp")).toBe("data");

    // Wait for expiration
    await new Promise((r) => setTimeout(r, 20));
    expect(mem.recall(scope, "temp")).toBeUndefined();
  });

  it("clears all entries", () => {
    mem.remember(scope, "a", "1");
    mem.remember(otherScope, "b", "2");
    expect(mem.size).toBe(2);

    mem.clear();
    expect(mem.size).toBe(0);
    expect(mem.recall(scope, "a")).toBeUndefined();
  });

  it("searches by key and value", () => {
    mem.remember(scope, "alpha", "first");
    mem.remember(scope, "beta", "second");

    const results = mem.search(scope, "first");
    expect(results.length).toBe(1);
    expect(results[0].key).toBe("alpha");

    // Search by key
    const results2 = mem.search(scope, "beta");
    expect(results2.length).toBe(1);
    expect(results2[0].value).toBe("second");

    // Case insensitive
    const results3 = mem.search(scope, "FIRST");
    expect(results3.length).toBe(1);
  });

  it("isolates entries by scope", () => {
    mem.remember(scope, "shared", "first");
    mem.remember(otherScope, "shared", "second");

    expect(mem.recall(scope, "shared")).toBe("first");
    expect(mem.recall(otherScope, "shared")).toBe("second");
    expect(mem.search(scope, "second")).toEqual([]);

    mem.clear(scope);
    expect(mem.recall(scope, "shared")).toBeUndefined();
    expect(mem.recall(otherScope, "shared")).toBe("second");
  });

  it("tracks size correctly", () => {
    expect(mem.size).toBe(0);
    mem.remember(scope, "a", "1");
    mem.remember(otherScope, "b", "2");
    expect(mem.size).toBe(2);
    mem.forget(scope, "a");
    expect(mem.size).toBe(1);
  });
});
