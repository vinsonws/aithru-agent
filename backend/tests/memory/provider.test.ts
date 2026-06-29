import { describe, it, expect, beforeEach } from "vitest";
import { LocalMemoryProvider } from "@aithru-agent/memory";

describe("LocalMemoryProvider", () => {
  let mem: LocalMemoryProvider;

  beforeEach(() => {
    mem = new LocalMemoryProvider();
  });

  it("remembers and recalls values", () => {
    mem.remember("key1", "value1");
    expect(mem.recall("key1")).toBe("value1");
  });

  it("returns undefined for missing keys", () => {
    expect(mem.recall("nonexistent")).toBeUndefined();
  });

  it("forgets keys", () => {
    mem.remember("key1", "value1");
    expect(mem.forget("key1")).toBe(true);
    expect(mem.recall("key1")).toBeUndefined();
    expect(mem.forget("key1")).toBe(false);
  });

  it("respects TTL expiration", async () => {
    mem.remember("temp", "data", 10); // 10ms TTL
    expect(mem.recall("temp")).toBe("data");

    // Wait for expiration
    await new Promise((r) => setTimeout(r, 20));
    expect(mem.recall("temp")).toBeUndefined();
  });

  it("clears all entries", () => {
    mem.remember("a", "1");
    mem.remember("b", "2");
    expect(mem.size).toBe(2);

    mem.clear();
    expect(mem.size).toBe(0);
    expect(mem.recall("a")).toBeUndefined();
  });

  it("searches by key and value", () => {
    mem.remember("alpha", "first");
    mem.remember("beta", "second");

    const results = mem.search("first");
    expect(results.length).toBe(1);
    expect(results[0].key).toBe("alpha");

    // Search by key
    const results2 = mem.search("beta");
    expect(results2.length).toBe(1);
    expect(results2[0].value).toBe("second");

    // Case insensitive
    const results3 = mem.search("FIRST");
    expect(results3.length).toBe(1);
  });

  it("tracks size correctly", () => {
    expect(mem.size).toBe(0);
    mem.remember("a", "1");
    mem.remember("b", "2");
    expect(mem.size).toBe(2);
    mem.forget("a");
    expect(mem.size).toBe(1);
  });
});
