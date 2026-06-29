import { describe, expect, it } from "vitest";
import { ControlledWebProvider } from "@aithru-agent/external";

describe("ControlledWebProvider", () => {
  it("allows fetches only to configured hosts", async () => {
    const provider = new ControlledWebProvider({
      allowedHosts: ["allowed.test"],
      fetcher: async (url) => ({
        status: 200,
        text: async () => `fetched:${url}`,
      }),
    });

    const result = await provider.fetchUrl("https://allowed.test/page");
    expect(result.content).toContain("https://allowed.test/page");
    await expect(provider.fetchUrl("https://blocked.test/page")).rejects.toThrow(
      "WEB_HOST_DENIED",
    );
  });

  it("requires an explicitly configured search endpoint", async () => {
    const provider = new ControlledWebProvider({
      allowedHosts: ["search.test"],
      searchEndpoint: "https://search.test/search",
      fetcher: async (url) => ({
        status: 200,
        text: async () => url,
      }),
    });

    const result = await provider.search("agent");
    expect(result.url).toContain("q=agent");
  });
});
