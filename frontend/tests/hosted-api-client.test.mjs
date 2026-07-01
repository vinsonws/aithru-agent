import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { test } from "node:test";
import esbuild from "esbuild";

async function loadApiClientModule() {
  const result = await esbuild.build({
    absWorkingDir: fileURLToPath(new URL("..", import.meta.url)),
    bundle: true,
    format: "esm",
    platform: "node",
    write: false,
    entryPoints: ["src/lib/api/client.ts"],
  });

  return import(`data:text/javascript,${encodeURIComponent(result.outputFiles[0].text)}`);
}

test("apiRequest delegates hosted calls to the Aithru hosted app SDK fetch", async () => {
  const { apiRequest, setHostedApiFetch } = await loadApiClientModule();
  let called = false;

  setHostedApiFetch(async (input, _init, scopes) => {
    called = true;
    assert.equal(input, "/api/threads");
    assert.deepEqual(scopes, ["agent.app.threads.read"]);
    return new Response(JSON.stringify([{ id: "thread_1" }]), {
      headers: { "content-type": "application/json" },
    });
  });

  assert.deepEqual(await apiRequest("/api/threads"), [{ id: "thread_1" }]);
  assert.equal(called, true);
});

test("apiRequest never sends user or org identity headers", async () => {
  const { apiRequest, setHostedApiFetch, setRequestContext } = await loadApiClientModule();
  const originalFetch = globalThis.fetch;
  let capturedHeaders = null;

  setHostedApiFetch(null);
  setRequestContext({ token: "token_1", orgId: "org_spoof", userId: "user_spoof" });
  globalThis.fetch = async (_path, init) => {
    capturedHeaders = new Headers(init.headers);
    return new Response(JSON.stringify({ ok: true }), {
      headers: { "content-type": "application/json" },
    });
  };

  try {
    assert.deepEqual(await apiRequest("/api/threads"), { ok: true });
    assert.equal(capturedHeaders.get("authorization"), "Bearer token_1");
    assert.equal(capturedHeaders.has("x-aithru-org-id"), false);
    assert.equal(capturedHeaders.has("x-aithru-user-id"), false);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
