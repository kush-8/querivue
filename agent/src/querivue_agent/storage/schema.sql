-- Querivue SQLite Ledger Schema v1
-- Single authority for standalone ownership, budgets, deletion and publication
-- Moves together to Postgres later; no Django import, dual-write, or Redis/file authority

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = FULL;
PRAGMA busy_timeout = 1000;

-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

INSERT OR IGNORE INTO schema_version (version, applied_at) VALUES (1, datetime('now'));

-- Scopes and sources
CREATE TABLE IF NOT EXISTS projects (
    project_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chats (
    chat_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS datasets (
    dataset_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id),
    upload_ref TEXT NOT NULL,
    upload_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('staged', 'inspecting', 'awaiting_confirmation', 'preparing', 'validated', 'transferred', 'ready', 'failed', 'invalidated', 'deleted')),
    attempt_number INTEGER NOT NULL DEFAULT 1,
    settings_hash TEXT,
    environment_manifest_id TEXT,
    limits_profile TEXT,
    deadline TEXT,
    prepared_ref TEXT,
    prepared_hash TEXT,
    publication_ref TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dataset_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL REFERENCES datasets(dataset_id),
    catalog_json TEXT NOT NULL,
    prepared_ref TEXT,
    prepared_hash TEXT,
    publication_ref TEXT,
    created_at TEXT NOT NULL
);

-- Runs and ownership
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id),
    chat_id TEXT NOT NULL REFERENCES chats(chat_id),
    question TEXT NOT NULL,
    scope_hash TEXT NOT NULL,
    eligible_dataset_ids TEXT NOT NULL, -- JSON array
    status TEXT NOT NULL CHECK (status IN ('admitted', 'running', 'waiting', 'review', 'finalizing', 'completed', 'failed', 'invalidated', 'cancelled', 'expired')),
    owner_id TEXT,
    generation INTEGER NOT NULL DEFAULT 1,
    attempt INTEGER NOT NULL DEFAULT 1,
    queue_revision INTEGER NOT NULL DEFAULT 0,
    run_revision INTEGER NOT NULL DEFAULT 1,
    budget_json TEXT NOT NULL,
    configuration_hash TEXT NOT NULL,
    deadline TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS run_owners (
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    owner_id TEXT NOT NULL,
    generation INTEGER NOT NULL,
    lease_expires_at TEXT NOT NULL,
    claimed_at TEXT NOT NULL,
    PRIMARY KEY (run_id, owner_id, generation)
);

-- Immutable payloads and dependencies
CREATE TABLE IF NOT EXISTS payloads (
    payload_id TEXT PRIMARY KEY,
    family TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    canonical_bytes BLOB NOT NULL,
    digest TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dependencies (
    payload_id TEXT NOT NULL REFERENCES payloads(payload_id),
    dataset_id TEXT NOT NULL,
    snapshot_id TEXT NOT NULL,
    PRIMARY KEY (payload_id, dataset_id, snapshot_id)
);

-- Intake, wait, reply
CREATE TABLE IF NOT EXISTS intakes (
    intake_id TEXT PRIMARY KEY,
    submission_key TEXT NOT NULL UNIQUE,
    project_id TEXT NOT NULL REFERENCES projects(project_id),
    input_json TEXT NOT NULL,
    original_hash TEXT NOT NULL,
    fence_json TEXT NOT NULL,
    entry_question_id TEXT,
    outcome_json TEXT,
    status TEXT NOT NULL CHECK (status IN ('pending', 'waiting', 'admitted', 'rejected', 'unavailable', 'expired', 'cancelled')),
    invocation_ids TEXT NOT NULL, -- JSON array
    charge_ref TEXT,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS intake_admissions (
    admission_id TEXT PRIMARY KEY,
    intake_id TEXT NOT NULL REFERENCES intakes(intake_id),
    submission_hash TEXT NOT NULL,
    scope_json TEXT NOT NULL,
    assessment_json TEXT NOT NULL,
    context_hash TEXT NOT NULL,
    configuration_hash TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    target_json TEXT NOT NULL,
    fence_json TEXT NOT NULL,
    accepted_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS admission_receipts (
    receipt_id TEXT PRIMARY KEY,
    admission_id TEXT NOT NULL REFERENCES intake_admissions(admission_id),
    intake_id TEXT NOT NULL,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    scope_json TEXT NOT NULL,
    cutoff_sequence INTEGER NOT NULL,
    budget_json TEXT NOT NULL,
    configuration_hash TEXT NOT NULL,
    accepted_at TEXT NOT NULL
);

-- Tasks, actions, outcomes
CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    task_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'dispatched', 'completed', 'failed')),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS actions (
    action_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(task_id),
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    action_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed', 'blocked')),
    attempt INTEGER NOT NULL DEFAULT 1,
    execution_generation INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS outcomes (
    outcome_id TEXT PRIMARY KEY,
    action_id TEXT NOT NULL REFERENCES actions(action_id),
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    attempt INTEGER NOT NULL,
    execution_generation INTEGER NOT NULL,
    outcome_json TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    UNIQUE (action_id, attempt, execution_generation)
);

-- Invocations and physical requests
CREATE TABLE IF NOT EXISTS invocations (
    invocation_id TEXT PRIMARY KEY,
    run_id TEXT REFERENCES runs(run_id),
    intake_id TEXT REFERENCES intakes(intake_id),
    role TEXT NOT NULL,
    attempt INTEGER NOT NULL,
    invocation_key TEXT NOT NULL,
    packet_hash TEXT NOT NULL,
    request_json TEXT NOT NULL,
    completion_json TEXT,
    status TEXT NOT NULL CHECK (status IN ('reserved', 'dispatched', 'completed', 'incomplete', 'unknown', 'failed')),
    created_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS model_reservations (
    reservation_id TEXT PRIMARY KEY,
    invocation_id TEXT NOT NULL REFERENCES invocations(invocation_id),
    max_input_tokens INTEGER NOT NULL,
    max_output_tokens INTEGER NOT NULL,
    cost_usd TEXT NOT NULL,
    admitted_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS model_completions (
    completion_id TEXT PRIMARY KEY,
    reservation_id TEXT NOT NULL REFERENCES model_reservations(reservation_id),
    request_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('completed', 'incomplete', 'unknown', 'failed')),
    response_ref TEXT,
    provider_request_id TEXT,
    observed_model_revision TEXT,
    stop_reason TEXT,
    usage_json TEXT NOT NULL,
    error_ref TEXT,
    recorded_at TEXT NOT NULL
);

-- Operations and incarnations
CREATE TABLE IF NOT EXISTS operations (
    operation_id TEXT PRIMARY KEY,
    run_id TEXT REFERENCES runs(run_id),
    task_id TEXT REFERENCES tasks(task_id),
    action_id TEXT REFERENCES actions(action_id),
    attempt INTEGER NOT NULL,
    execution_generation INTEGER NOT NULL,
    invocation_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('sql_query', 'python_code', 'ingestion_inspect', 'ingestion_prepare')),
    request_json TEXT NOT NULL,
    input_artifacts_json TEXT NOT NULL,
    deadline TEXT NOT NULL,
    environment_manifest_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS operation_outcomes (
    outcome_id TEXT PRIMARY KEY,
    operation_id TEXT NOT NULL REFERENCES operations(operation_id),
    attempt INTEGER NOT NULL,
    execution_generation INTEGER NOT NULL,
    request_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('succeeded', 'failed', 'blocked')),
    evidence_json TEXT NOT NULL, -- JSON array of TabularEvidence
    charts_json TEXT NOT NULL, -- JSON array of ChartArtifact
    diagnostics_json TEXT NOT NULL,
    completed_at TEXT NOT NULL,
    UNIQUE (operation_id, attempt, execution_generation)
);

-- Draft and review
CREATE TABLE IF NOT EXISTS drafts (
    draft_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    action_id TEXT NOT NULL REFERENCES actions(action_id),
    draft_json TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    input_packet_hash TEXT NOT NULL,
    dependencies_json TEXT NOT NULL,
    source_input_hash TEXT NOT NULL,
    completeness TEXT NOT NULL CHECK (completeness IN ('complete', 'partial')),
    rendering_policy_version TEXT NOT NULL,
    originating_invocation_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reviews (
    review_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    draft_id TEXT NOT NULL REFERENCES drafts(draft_id),
    review_pass INTEGER NOT NULL CHECK (review_pass IN (1, 2)),
    assessment_json TEXT NOT NULL,
    verdict TEXT NOT NULL CHECK (verdict IN ('approved', 'rejected', 'failed')),
    draft_content_hash TEXT NOT NULL,
    draft_input_packet_hash TEXT NOT NULL,
    rendering_policy_version TEXT NOT NULL,
    reserved_at TEXT NOT NULL,
    deadline TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (run_id, review_pass)
);

CREATE TABLE IF NOT EXISTS review_reservations (
    reservation_id TEXT PRIMARY KEY,
    review_id TEXT NOT NULL REFERENCES reviews(review_id),
    max_physical_requests INTEGER NOT NULL,
    max_input_tokens INTEGER NOT NULL,
    max_output_tokens INTEGER NOT NULL,
    cost_usd TEXT NOT NULL,
    reserved_at TEXT NOT NULL,
    deadline TEXT NOT NULL
);

-- Accounting and progress
CREATE TABLE IF NOT EXISTS budget_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    budget_json TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS progress_accounting (
    accounting_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    action_id TEXT REFERENCES actions(action_id),
    invocation_id TEXT REFERENCES invocations(invocation_id),
    operation_id TEXT REFERENCES operations(operation_id),
    counter_name TEXT NOT NULL,
    counter_value INTEGER NOT NULL,
    recorded_at TEXT NOT NULL
);

-- Final receipts
CREATE TABLE IF NOT EXISTS final_results (
    result_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    route TEXT NOT NULL CHECK (route IN ('reviewed', 'direct')),
    candidate_id TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    completeness TEXT NOT NULL CHECK (completeness IN ('complete', 'partial')),
    rendered_text TEXT NOT NULL,
    rendering_policy_version TEXT NOT NULL,
    evidence_ids TEXT NOT NULL, -- JSON array
    chart_artifact_ids TEXT NOT NULL, -- JSON array
    dependencies_json TEXT NOT NULL,
    review_status TEXT NOT NULL CHECK (review_status IN ('approved', 'not_required_direct')),
    published_at TEXT NOT NULL
);

-- Deletion receipts
CREATE TABLE IF NOT EXISTS deletion_receipts (
    deletion_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id),
    dataset_id TEXT NOT NULL REFERENCES datasets(dataset_id),
    tombstone_revision INTEGER NOT NULL,
    invalidated_run_ids TEXT NOT NULL, -- JSON array
    removed_result_ids TEXT NOT NULL, -- JSON array
    deferred_artifact_ids TEXT NOT NULL, -- JSON array
    retirement_pending_incarnation_ids TEXT NOT NULL, -- JSON array
    committed_at TEXT NOT NULL
);

-- Queue receipts
CREATE TABLE IF NOT EXISTS queue_receipts (
    receipt_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    invocation_id TEXT NOT NULL REFERENCES invocations(invocation_id),
    proposal_hash TEXT NOT NULL,
    decision_type TEXT NOT NULL CHECK (decision_type IN ('propose_queue', 'stop')),
    previous_queue_revision INTEGER NOT NULL,
    queue_revision INTEGER NOT NULL,
    run_revision INTEGER NOT NULL,
    task_mapping_json TEXT NOT NULL,
    action_mapping_json TEXT NOT NULL,
    tasks_json TEXT NOT NULL,
    withdrawn_task_ids_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- Resume receipts
CREATE TABLE IF NOT EXISTS resume_receipts (
    resume_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    question_id TEXT NOT NULL,
    reply_id TEXT NOT NULL,
    entry_intake_id TEXT NOT NULL,
    run_revision INTEGER NOT NULL,
    owner_generation INTEGER NOT NULL,
    accepted_at TEXT NOT NULL,
    original_deadline TEXT NOT NULL,
    scope_json TEXT NOT NULL
);

-- Linked replies
CREATE TABLE IF NOT EXISTS linked_replies (
    reply_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    question_id TEXT NOT NULL,
    entry_intake_id TEXT NOT NULL,
    submission_key TEXT NOT NULL,
    message_json TEXT NOT NULL,
    selected_option_ids TEXT NOT NULL,
    question_content_hash TEXT NOT NULL,
    accepted_at TEXT NOT NULL,
    entry_admission_ref TEXT NOT NULL
);

-- Sandbox tickets
CREATE TABLE IF NOT EXISTS sandbox_tickets (
    ticket_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    sandbox_id TEXT NOT NULL,
    command_id TEXT,
    incarnation_id TEXT NOT NULL,
    action_id TEXT NOT NULL REFERENCES actions(action_id),
    operation_id TEXT REFERENCES operations(operation_id),
    attempt INTEGER NOT NULL,
    generation INTEGER NOT NULL,
    environment_manifest_id TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('prepared', 'running', 'executed', 'validated', 'published', 'retiring', 'retired', 'unreachable')),
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

-- Retirement proofs
CREATE TABLE IF NOT EXISTS retirement_proofs (
    retirement_id TEXT PRIMARY KEY,
    sandbox_id TEXT NOT NULL,
    incarnation_id TEXT NOT NULL,
    confirmed_at TEXT NOT NULL,
    method TEXT NOT NULL CHECK (method IN ('provider_termination', 'process_tree_reaped')),
    process_tree_terminated INTEGER NOT NULL CHECK (process_tree_terminated = 1),
    proof_ref TEXT NOT NULL,
    environment_manifest_id TEXT NOT NULL
);

-- Preparation attempts
CREATE TABLE IF NOT EXISTS preparation_attempts (
    attempt_id TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL REFERENCES datasets(dataset_id),
    attempt_number INTEGER NOT NULL,
    settings_json TEXT NOT NULL,
    settings_hash TEXT NOT NULL,
    upload_ref TEXT NOT NULL,
    upload_hash TEXT NOT NULL,
    owner_generation INTEGER NOT NULL,
    phase TEXT NOT NULL CHECK (phase IN ('staged', 'inspecting', 'awaiting_confirmation', 'preparing', 'validated', 'transferred', 'ready', 'failed', 'invalidated', 'deleted')),
    environment_manifest_id TEXT,
    incarnation_id TEXT,
    retirement_state TEXT NOT NULL CHECK (retirement_state IN ('not_started', 'active', 'retirement_pending', 'retired')),
    limits_profile TEXT,
    deadline TEXT NOT NULL,
    diagnostic_ref TEXT,
    candidate_ref TEXT,
    publication_ref TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_datasets_project ON datasets(project_id);
CREATE INDEX IF NOT EXISTS idx_runs_project ON runs(project_id);
CREATE INDEX IF NOT EXISTS idx_runs_chat ON runs(chat_id);
CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);
CREATE INDEX IF NOT EXISTS idx_tasks_run ON tasks(run_id);
CREATE INDEX IF NOT EXISTS idx_actions_task ON actions(task_id);
CREATE INDEX IF NOT EXISTS idx_actions_run ON actions(run_id);
CREATE INDEX IF NOT EXISTS idx_outcomes_action ON outcomes(action_id);
CREATE INDEX IF NOT EXISTS idx_invocations_run ON invocations(run_id);
CREATE INDEX IF NOT EXISTS idx_operations_run ON operations(run_id);
CREATE INDEX IF NOT EXISTS idx_payloads_digest ON payloads(digest);
CREATE INDEX IF NOT EXISTS idx_preparation_dataset ON preparation_attempts(dataset_id);