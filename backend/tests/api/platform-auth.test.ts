import { describe, expect, it } from "vitest";
import {
  actorCanAccessOwnedResource,
  bodyWithPlatformActor,
  requestActorUserId,
  requestOrgId,
  requiredScopeForRequest,
} from "../../apps/api/src/platform-auth.js";

const actor = {
  actorType: "user" as const,
  userId: "user_from_token",
  orgId: "org_from_token",
  scopes: ["agent.app.runs.execute"],
  roles: [],
  tokenType: "hosted_access" as const,
  claims: {},
};

describe("platform auth helpers", () => {
  it("uses the verified token actor instead of caller-supplied identity fields", () => {
    expect(
      bodyWithPlatformActor(
        {
          org_id: "spoofed_org",
          actor_user_id: "spoofed_user",
          owner_user_id: "spoofed_owner",
          task_msg: "hello",
        },
        actor,
      ),
    ).toMatchObject({
      org_id: "org_from_token",
      actor_user_id: "user_from_token",
      owner_user_id: "user_from_token",
    });
  });

  it("falls back to existing local defaults when no platform actor is present", () => {
    expect(requestOrgId(null, { org_id: "org_body" }, { org_id: "org_query" })).toBe("org_body");
    expect(requestActorUserId(null, { owner_user_id: "user_body" })).toBe("user_body");
  });

  it("maps protected API paths to stable manifest scopes", () => {
    expect(requiredScopeForRequest("GET", "/api/runs/run_1/stream?follow=true")).toBe("agent.app.runs.read");
    expect(requiredScopeForRequest("POST", "/api/runs")).toBe("agent.app.runs.execute");
    expect(requiredScopeForRequest("POST", "/api/approvals/aprv_1/resolve")).toBe("agent.app.approvals.resolve");
    expect(requiredScopeForRequest("PUT", "/api/workspaces/ws_1/files/report.md")).toBe("agent.app.workspaces.write");
    expect(requiredScopeForRequest("GET", "/api/health")).toBeNull();
  });

  it("matches authenticated actors to owned resources", () => {
    expect(actorCanAccessOwnedResource(null, { org_id: "org_any", owner_user_id: "user_any" })).toBe(true);
    expect(actorCanAccessOwnedResource(actor, { org_id: "org_from_token", owner_user_id: "user_from_token" })).toBe(true);
    expect(actorCanAccessOwnedResource(actor, { org_id: "org_from_token", actor_user_id: "user_from_token" })).toBe(true);
    expect(actorCanAccessOwnedResource({ ...actor, orgId: null }, { org_id: "org_from_token", owner_user_id: "user_from_token" })).toBe(false);
    expect(actorCanAccessOwnedResource(actor, { org_id: "other_org", owner_user_id: "user_from_token" })).toBe(false);
    expect(actorCanAccessOwnedResource(actor, { org_id: "org_from_token", owner_user_id: "other_user" })).toBe(false);
    expect(actorCanAccessOwnedResource({ ...actor, scopes: ["*"] }, { org_id: "other_org", owner_user_id: "other_user" })).toBe(true);
  });
});
