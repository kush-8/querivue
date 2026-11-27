# Database implementation

Started 27 November 2026 at the user's request: implement the database using local Docker Postgres now, with Supabase migration later. The approved [storage architecture](../architecture/database-storage.md) remains authoritative. Existing unrelated changes must be preserved; work stays on main.

User steering during S1a: use Cloudflare for blob storage, interpreted as private Cloudflare R2 object storage. Durable blobs move from the earlier shared-volume deployment choice to R2; local Postgres and the planned Supabase database move remain unchanged. Schema object keys stay provider-neutral. This batch adds no cloud credentials, bucket, SDK or remote object effects. The storage transport slice owns bounded S3 requests, conditional immutable writes, multipart retirement, private access, verified local DuckDB scratch materialization and object cleanup proof.

## Delivery order

1. Local infrastructure foundation: Docker Compose Postgres with a named persistent volume and loopback-only port; explicit Django Postgres environment configuration, bounded connection/lock/statement settings, driver lock and setup instructions. Run fresh schema migrations, Django checks and a persistence probe if Docker is available. Do not silently fall back to SQLite.
2. S1: extract the framework-free atomic authority operation boundary, add Django-owned domain/ledger migrations and shared SQLite/Postgres conformance fixtures. Inspect ownership constraints and canonical binary round trips against real Postgres.
3. S2–S5: upload/preparation, Chat/intake/run operations, access/revocation/cleanup, then quiesced maintenance handoff, in the approved architecture order and acceptance scenarios.

The first coding batch is infrastructure only; completing it does not establish S1 adapter conformance or enable the integrated agent against Postgres. No existing SQLite authority is copied or switched implicitly. Local service startup is authorized by the implementation request; external services, providers and Supabase provisioning are outside this batch.

## Foundation choices

Use the existing Django 5.2 line and psycopg 3, pinned in uv.lock. The selected local image is `postgres:17.12-bookworm`. The Postgres 17 family is supported by Django 5.2 and used by Supabase; the actual future hosted project's version/extensions must still be checked before migration. Credentials remain in ignored environment files; committed examples contain local development placeholders only. Hosted connectivity later supplies host/user/password/database/port and TLS configuration through the same settings. Ordinary startup never resets volumes or automatically migrates application content.

### Foundation task

- [x] Inspect approved ownership, migration and standalone authority boundaries.
- [x] Delegate one bounded infrastructure batch under the project's coding supervision rules.
- [x] Review `compose.yaml`, root `.env.example`, backend settings/driver lock and README setup instructions.
- [x] Start the service, apply existing Django migrations and inspect database/timeouts.
- [x] Verify all 18 committed Django migration records survive container recreation; no temporary test table is needed.
- [x] Record measured versions/results in the storage guide and current resume.

Batch closure refreshes the existing local QMD and code graph indexes after documentation edits; failures must be reported explicitly. Floorplan waits until completion of the database implementation phase.

Local port 5432 was unavailable and responded as a different Postgres service during the first connection probe. Switched this project's defaults and ignored local configuration to 55432; did not alter the existing service. Fresh successful checks used 55432. A combined verification command's automatic approval review timed out; smaller independent checks subsequently succeeded, leaving no foundation verification blocker.

## Verification and open gates

Docker's Linux daemon was unavailable during initial inspection. Sandbox launch failed with WSL access denied; an authorized host launch succeeded, and Docker engine 29.9.2 responded. Schema constraints, race tests, exact adapter behavior, authority handoff and all S1–S5 gates remain pending until implemented and measured. Record exact server/image/driver versions and chosen finite settings when the foundation is verified.

## S1a: domain schema prerequisites

The user's continuation authorizes the next implementation batch from the approved storage architecture. Create one Django `storage` app owning Project, Chat, Blob, Upload, Dataset, PreparationAttempt, Snapshot, TableCatalog, ColumnCatalog, ContentRecord, SourceDependency and RecordDependency. Keep runtime Run/action/invocation/publication/accounting tables and adapter extraction in the following S1 batch; do not invent unconstrained run UUID fields or claim shared-adapter conformance.

Model files belong under `backend/storage/models/`; migrations belong under `backend/storage/migrations/`; focused real-Postgres acceptance tests belong under `backend/storage/tests/`. Register the app in backend settings. No API/admin registration, filesystem effects or existing SQLite authority switch occurs.

Use UUID identities, restrictive foreign keys, lifecycle checks, nonnegative revisions/counters and the exact 52,428,800-byte Project raw quota check. Store content/name/title/filename metadata as exact binary payloads where necessary; canonical content digests are indexed rather than globally unique. Add explicit named reversible composite foreign keys for Project/Chat, Project/Blob/Upload, Project/Dataset/attempt/snapshot and catalog/content/dependency ownership. Optional scoped references need implication checks so nulls cannot skip ownership enforcement.

Implementation choice: a Snapshot row represents a committed published immutable snapshot; unpublished preparation candidates stay on attempts. A Dataset has at most one published Snapshot. Its ready pointer must reference its own current attempt's Snapshot. Current attempt and replacement pointers must stay within their Dataset/Project ownership. Lifecycle/service publication rules and content dependency cycle admission remain later service gates; this schema must not claim to enforce them all.

- [ ] Implement models and generated initial migration, then explicit reversible ownership constraints.
- [ ] Verify fresh migration and reversal/reapplication in an isolated test database.
- [ ] Check invalid direct inserts, quota, duplicate scoped identities, cross-owner/null-escape cases and lossless binary round trips with actual Postgres.
- [ ] Run Django system/migration drift checks, review generated SQL and catalog constraints.
- [ ] Update durable status and existing local indexes once the batch passes.
