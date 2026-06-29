import { afterAll, beforeAll, describe, expect, it } from "vitest";
import type { FastifyInstance } from "fastify";
import { createApp, getRuntime } from "@aithru-agent/api";

let app: FastifyInstance;

beforeAll(async () => {
  app = await createApp();
  await app.ready();
});

afterAll(async () => {
  await app.close();
});

describe("Capability audit API", () => {
  it("projects tool events into an audit log", async () => {
    const create = await app.inject({
      method: "POST",
      url: "/api/runs",
      payload: {
        org_id: "org_1",
        actor_user_id: "user_1",
        source: "api",
        task_msg: "audit",
      },
    });
    const run = JSON.parse(create.body);
    const runtime = getRuntime();
    runtime.eventWriter.write(run.id, null, "tool.denied", {
      tool_call_id: "tc_1",
      name: "danger.tool",
      reason: "nope",
    });

    const response = await app.inject({
      method: "GET",
      url: `/api/runs/${run.id}/capability-audit`,
    });

    expect(response.statusCode).toBe(200);
    const body = JSON.parse(response.body);
    expect(body[0]).toMatchObject({
      tool_call_id: "tc_1",
      tool_name: "danger.tool",
      decision: "denied",
      reason: "nope",
    });
  });
});
