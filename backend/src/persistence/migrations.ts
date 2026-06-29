export interface MigrationExecutor {
  exec(sql: string): void;
}

/**
 * Run all table DDL. Safe to call multiple times (CREATE IF NOT EXISTS).
 */
export function runMigrations(adapter: MigrationExecutor): void {
  adapter.exec(`
    CREATE TABLE IF NOT EXISTS threads (
      id TEXT PRIMARY KEY, org_id TEXT NOT NULL, owner_user_id TEXT NOT NULL,
      title TEXT, status TEXT NOT NULL DEFAULT 'active',
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS messages (
      id TEXT PRIMARY KEY, thread_id TEXT NOT NULL, role TEXT NOT NULL,
      content TEXT NOT NULL, run_id TEXT,
      workspace_paths TEXT NOT NULL DEFAULT '[]',
      created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS runs (
      id TEXT PRIMARY KEY, org_id TEXT NOT NULL, actor_user_id TEXT NOT NULL,
      source TEXT NOT NULL, thread_id TEXT, skill_id TEXT,
      workspace_id TEXT NOT NULL, task_msg TEXT NOT NULL,
      scopes TEXT NOT NULL DEFAULT '[]',
      harness_options TEXT, status TEXT NOT NULL DEFAULT 'queued',
      started_at TEXT NOT NULL, completed_at TEXT,
      current_approval_id TEXT,
      claim_worker_id TEXT, claim_claimed_at TEXT,
      claim_heartbeat_at TEXT, claim_lease_expires_at TEXT,
      claim_attempt INTEGER,
      retry_policy TEXT, retry_state TEXT,
      result TEXT, error TEXT
    );

    CREATE TABLE IF NOT EXISTS events (
      id TEXT PRIMARY KEY, run_id TEXT NOT NULL, thread_id TEXT,
      sequence INTEGER NOT NULL, timestamp TEXT NOT NULL,
      type TEXT NOT NULL,
      source_kind TEXT NOT NULL, source_id TEXT, source_name TEXT,
      visibility TEXT NOT NULL DEFAULT 'user',
      redaction TEXT NOT NULL DEFAULT 'none',
      summary TEXT, payload TEXT NOT NULL DEFAULT '{}'
    );

    CREATE TABLE IF NOT EXISTS workspace_files (
      workspace_id TEXT NOT NULL, path TEXT NOT NULL,
      content TEXT NOT NULL, size INTEGER NOT NULL,
      version INTEGER NOT NULL DEFAULT 1,
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
      PRIMARY KEY (workspace_id, path)
    );

    CREATE TABLE IF NOT EXISTS todos (
      id TEXT PRIMARY KEY, run_id TEXT NOT NULL, title TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'pending',
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS approvals (
      id TEXT PRIMARY KEY, run_id TEXT NOT NULL,
      tool_call_id TEXT NOT NULL, tool_name TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'pending',
      created_at TEXT NOT NULL, resolved_at TEXT
    );

    CREATE TABLE IF NOT EXISTS artifacts (
      id TEXT PRIMARY KEY, run_id TEXT NOT NULL,
      title TEXT NOT NULL, content_type TEXT NOT NULL,
      content TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'draft',
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_events_run ON events(run_id, sequence);
    CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(thread_id);
    CREATE INDEX IF NOT EXISTS idx_runs_thread ON runs(thread_id);
    CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);
  `);
}
