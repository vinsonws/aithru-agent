export interface MigrationExecutor {
  exec(sql: string): void;
}

/**
 * Run all table DDL. Safe to call multiple times (CREATE IF NOT EXISTS).
 */
export function runMigrations(adapter: MigrationExecutor): void {
  adapter.exec(`
    DROP TABLE IF EXISTS agent_documents;
    DROP TABLE IF EXISTS workspace_files;
    DROP TABLE IF EXISTS workspace_file_versions;

    CREATE TABLE IF NOT EXISTS threads (
      id TEXT PRIMARY KEY, org_id TEXT NOT NULL, owner_user_id TEXT NOT NULL,
      title TEXT, status TEXT NOT NULL DEFAULT 'active',
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    );

	    CREATE TABLE IF NOT EXISTS messages (
	      id TEXT PRIMARY KEY, org_id TEXT, actor_user_id TEXT,
	      thread_id TEXT NOT NULL, role TEXT NOT NULL,
	      content TEXT NOT NULL, run_id TEXT,
      workspace_paths TEXT NOT NULL DEFAULT '[]',
      created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS runs (
      id TEXT PRIMARY KEY, org_id TEXT NOT NULL, actor_user_id TEXT NOT NULL,
      source TEXT NOT NULL, thread_id TEXT,
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
	      id TEXT PRIMARY KEY, org_id TEXT, actor_user_id TEXT,
	      run_id TEXT NOT NULL, thread_id TEXT,
      sequence INTEGER NOT NULL, timestamp TEXT NOT NULL,
      type TEXT NOT NULL,
      source_kind TEXT NOT NULL, source_id TEXT, source_name TEXT,
      visibility TEXT NOT NULL DEFAULT 'user',
      redaction TEXT NOT NULL DEFAULT 'none',
      summary TEXT, payload TEXT NOT NULL DEFAULT '{}'
    );

    CREATE TABLE IF NOT EXISTS settings (
      org_id TEXT NOT NULL DEFAULT '',
      key TEXT NOT NULL,
      value TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      PRIMARY KEY (org_id, key)
    );

	    CREATE TABLE IF NOT EXISTS context_summaries (
	      id TEXT PRIMARY KEY,
	      org_id TEXT NOT NULL,
	      actor_user_id TEXT,
	      thread_id TEXT NOT NULL,
      run_id TEXT NOT NULL,
      summary TEXT NOT NULL,
      source_message_count INTEGER NOT NULL,
      created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS secrets (
      org_id TEXT NOT NULL DEFAULT '',
      secret_ref TEXT NOT NULL,
      encrypted_value TEXT NOT NULL,
      iv TEXT NOT NULL,
      tag TEXT NOT NULL,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      PRIMARY KEY (org_id, secret_ref)
    );

    CREATE TABLE IF NOT EXISTS model_profiles (
      id TEXT PRIMARY KEY,
      org_id TEXT,
      owner_user_id TEXT,
      key TEXT,
      payload TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS skill_registry_entries (
      id TEXT PRIMARY KEY,
      org_id TEXT,
      owner_user_id TEXT,
      key TEXT,
      payload TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS skill_package_users (
      id TEXT PRIMARY KEY,
      org_id TEXT,
      owner_user_id TEXT,
      key TEXT,
      payload TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS subagent_specs (
      id TEXT PRIMARY KEY,
      org_id TEXT,
      owner_user_id TEXT,
      key TEXT,
      payload TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS external_tool_configs (
      id TEXT PRIMARY KEY,
      org_id TEXT,
      owner_user_id TEXT,
      key TEXT,
      payload TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS tool_call_records (
      id TEXT PRIMARY KEY,
      org_id TEXT,
      owner_user_id TEXT,
      key TEXT,
      payload TEXT NOT NULL
    );

	    CREATE TABLE IF NOT EXISTS todos (
	      id TEXT PRIMARY KEY, org_id TEXT, actor_user_id TEXT,
	      thread_id TEXT, run_id TEXT NOT NULL, title TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'pending',
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    );

	    CREATE TABLE IF NOT EXISTS approvals (
	      id TEXT PRIMARY KEY, org_id TEXT, actor_user_id TEXT,
	      run_id TEXT NOT NULL,
      tool_call_id TEXT NOT NULL, tool_name TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'pending',
      created_at TEXT NOT NULL, resolved_at TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_events_run ON events(run_id, sequence);
    CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(thread_id);
    CREATE INDEX IF NOT EXISTS idx_runs_thread ON runs(thread_id);
    CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);
    CREATE INDEX IF NOT EXISTS idx_context_summaries_thread
      ON context_summaries(thread_id, created_at);
    CREATE INDEX IF NOT EXISTS idx_todos_run ON todos(run_id);
    CREATE INDEX IF NOT EXISTS idx_model_profiles_org_key ON model_profiles(org_id, key);
    CREATE INDEX IF NOT EXISTS idx_skill_registry_org_key ON skill_registry_entries(org_id, key);
    CREATE INDEX IF NOT EXISTS idx_skill_package_users_org_owner_key
      ON skill_package_users(org_id, owner_user_id, key);
    CREATE INDEX IF NOT EXISTS idx_subagent_specs_org_key ON subagent_specs(org_id, key);
    CREATE INDEX IF NOT EXISTS idx_external_tool_configs_org_key ON external_tool_configs(org_id, key);
    CREATE INDEX IF NOT EXISTS idx_tool_call_records_org_key ON tool_call_records(org_id, key);
  `);
}
