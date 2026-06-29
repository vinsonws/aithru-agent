export interface AgentTraceSpan {
  id: string;
  run_id: string;
  parent_id?: string;
  kind: string;           // "run" | "message" | "tool" | "approval"
  name: string;
  started_at: string;
  completed_at?: string;
  status: "ok" | "error" | "cancelled";
  metadata?: Record<string, unknown>;
  children: AgentTraceSpan[];
}
