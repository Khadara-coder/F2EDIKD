# EXECUTION TRACKER WEEK 1 TO 4

Date baseline: 2026-06-26
Program: EDIFACT standalone stack without n8n orchestration
Reference: docs/STANDALONE_EDIFACT_HANDOVER.md
Project: /Workspace/Users/rsr1dy@bosch.com/EDIFACT

## Governance
- Program Sponsor: Sales Operations Lead
- Delivery Owner: Integration Tech Lead
- Platform Owner: Infrastructure and Runtime Lead
- Data Owner: Master Data Owner
- Operations Owner: Run and Support Lead
- Security Owner: IAM and Secret Management Lead

## Milestones
1. M1 End Week 1: Parallel environment ready, parity test pack agreed
2. M2 End Week 2: Standalone persistence active, duplicate behavior validated
3. M3 End Week 3: Notification and SFTP path fully standalone
4. M4 End Week 4: Production cutover complete, rollback window opened

## Workstream Tracker

### Week 1: Parallel Validation and Environment Setup (due 2026-07-03)

| # | Task | Owner | Status | Deliverable |
|---|------|-------|--------|-------------|
| 1 | Finalize runtime mode (API or hybrid) | Delivery Owner | Not Started | Approved architecture note |
| 2 | Provision standalone runtime and network access | Platform Owner | Not Started | Running API + worker with firewall routes |
| 3 | Baseline test corpus and parity matrix | Delivery Owner | Not Started | n8n vs standalone comparison sheet |
| 4 | Master data completeness check (incl. Materials) | Data Owner | Not Started | Signed data source and refresh plan |

Gate: environment healthy + test corpus approved + data ownership confirmed

### Week 2: Persistence and Idempotency (due 2026-07-10)

| # | Task | Owner | Status | Deliverable |
|---|------|-------|--------|-------------|
| 1 | Deploy SQLite schema and initialize database | Delivery Owner | Not Started | Initialized DB and backup strategy |
| 2 | Validate duplicate handling and replay-safe behavior | Delivery Owner | Not Started | Duplicate test evidence and replay logs |
| 3 | Add status lifecycle reporting | Operations Owner | Not Started | Job lifecycle dashboard or extract |
| 4 | Security hardening and secret handling | Security Owner | Not Started | Secret rotation evidence |

Gate: duplicate behavior validated + replay safety + security sign-off

### Week 3: Standalone Notification and Delivery (due 2026-07-17)

| # | Task | Owner | Status | Deliverable |
|---|------|-------|--------|-------------|
| 1 | SFTP delivery flow and retry policy | Delivery Owner | Not Started | Successful SFTP tests with retry logs |
| 2 | Incident runbook dry run | Operations Owner | Not Started | Simulated failure drill report |
| 3 | Supervised parallel run (2-3 days) | Delivery Owner | Not Started | Comparison report and discrepancy closure |

Gate: end-to-end standalone success + alerting reliability + incident playbook validated

### Week 4: Cutover and Stabilization (due 2026-07-24)

| # | Task | Owner | Status | Deliverable |
|---|------|-------|--------|-------------|
| 1 | Production cutover approval + n8n change freeze | Program Sponsor | Not Started | Approved change ticket |
| 2 | Switch intake trigger to standalone | Platform Owner | Not Started | Production intake on standalone |
| 3 | Rollback window operations | Operations Owner | Not Started | Daily stabilization logs |
| 4 | Final acceptance and handover close | Program Sponsor | Not Started | Signed production acceptance |

## RAID Log

| # | Type | Description | Owner | Mitigation |
|---|------|-------------|-------|------------|
| 1 | Risk | Missing materials source blocks article validation | Data Owner | Confirm source + refresh SLA before cutover |
| 2 | Risk | SFTP credentials not set in production | Security Owner | SFTP_ENABLED=false until credentials confirmed |
| 3 | Risk | SQLite concurrent writes in multi-instance | Platform Owner | WAL mode enabled; migrate to PostgreSQL if needed |
| 4 | Dependency | Secret rotation across SFTP credentials | Security Owner | Target: 2026-07-10 |
| 5 | Issue | PDF_INBOX UNC share not accessible from cloud | Platform Owner | API mode (POST /jobs) for cloud intake |

## Baseline Status (2026-06-26)
- Standalone handover document: Completed
- Standalone stack scaffold: Completed (EDIFACT/src/)
- Engine merge into project: Completed (65 tests passing)
- FastAPI + worker + SQLite layer merged: Completed (this tracking cycle)
- Execution tracker: Active
