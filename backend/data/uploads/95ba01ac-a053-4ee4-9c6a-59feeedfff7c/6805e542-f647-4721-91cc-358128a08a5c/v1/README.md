# MediFlow Pre-Operative Platform

Healthcare-grade, event-sourced perioperative workflow system.

## Architecture

```
newmed/
├── main.py                     # FastAPI app entry point + lifespan seeding
├── core/
│   ├── config.py               # Pydantic settings (env-driven)
│   ├── database.py             # SQLAlchemy async engine (SQLite dev / PostgreSQL prod)
│   ├── security.py             # JWT, bcrypt, TOTP MFA, HMAC signatures
│   ├── audit.py                # Append-only event emitter
│   ├── ids.py                  # Prefixed unique ID generation
│   └── deps.py                 # FastAPI dependency injectors (auth, RBAC)
│
├── fsm/                        # Flat state machine files (one per workflow)
│   ├── base.py                 # BaseStateMachine engine
│   ├── patient_fsm.py          # Patient Intake & Registration FSM
│   ├── pac_fsm.py              # PAC Assessment FSM
│   ├── pac_review_fsm.py       # PAC Review & Approval FSM
│   ├── rpac_fsm.py             # rPAC Reassessment / Delta FSM
│   ├── risk_fsm.py             # Risk Stratification FSM
│   └── consent_fsm.py          # Consent Workflow FSM
│
├── models/                     # SQLAlchemy ORM (JSONB clinical sections)
│   ├── user.py                 # User + UserSession
│   ├── patient.py              # Patient + Encounter
│   ├── pac.py                  # PACRecord + PACReview
│   ├── rpac.py                 # RPACRecord (delta + snapshot)
│   ├── risk.py                 # RiskRecord
│   ├── consent.py              # ConsentRecord (25-yr retention)
│   ├── lineage.py              # LineageGraph (nodes + edges)
│   └── audit.py                # WorkflowEvent (immutable) + AuditLog
│
├── schemas/                    # Pydantic v2 request/response models
├── services/                   # Business logic + FSM orchestration
│   ├── auth_service.py
│   ├── patient_service.py
│   ├── pac_service.py
│   ├── rpac_service.py
│   ├── risk_service.py
│   ├── consent_service.py
│   └── audit_service.py
│
├── routers/                    # FastAPI route handlers
│   ├── auth.py                 # POST /login, /mfa/verify, /refresh, /logout, GET /me
│   ├── patients.py             # CRUD + advance-state + timeline + lineage
│   ├── pac.py                  # Create, update (tab-level), submit, SR review, lock
│   ├── rpac.py                 # Trigger, update, approve, compare
│   ├── risk.py                 # Compute, get, override
│   ├── consent.py              # Create, sign, revoke, get
│   └── audit.py                # Events, logs, timeline, lineage
│
└── data/                       # Flat JSON reference files
    ├── risk_formulas.json      # ASA, SOFA, APACHE-II, RCRI, Difficult Airway
    ├── consent_templates.json  # Multilingual consent templates (en, hi, kn, ta ...)
    ├── procedure_codes.json    # ICD procedure reference
    └── seed_data.json          # Demo users & patients (auto-seeded on first run)
```

## Quick Start

```bash
cd /home/divya/WORK/newmed

# Create virtual environment
python -m venv .venv && source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy env (SQLite used by default — no DB setup needed)
cp .env.example .env

# Run (auto-creates tables + seeds demo data)
python main.py
# or
uvicorn main:app --reload --port 8000
```

API Docs: http://localhost:8000/api/docs

## Demo Credentials

All users have password `Demo@1234`:

| Role | Email |
|------|-------|
| JR Resident | jr.resident@mediflow.dev |
| SR Resident | sr.resident@mediflow.dev |
| Consultant | consultant@mediflow.dev |
| PAC Nurse | nurse@mediflow.dev |
| ICU Clinician | icu.doc@mediflow.dev |
| Admin | admin@mediflow.dev |

## Workflow API Flow

### 1. Login
```
POST /api/v1/auth/login
{ "email": "jr.resident@mediflow.dev", "password": "Demo@1234" }
→ { access_token, refresh_token, role }
```

### 2. Create Patient
```
POST /api/v1/patients
Authorization: Bearer <access_token>
{ demographics, surgical_context, clinical_context }
→ { patient_id, workflow_state: "REGISTRATION_STARTED" }
```

### 3. Create PAC
```
POST /api/v1/pac
{ patient_id, encounter_id }
→ { pac_id, workflow_state: "INTAKE_STARTED" }
```

### 4. Fill PAC (tab-level saves)
```
PATCH /api/v1/pac/{pac_id}
{ "history": {...}, "transition_event": "SAVE_HISTORY" }
→ { workflow_state: "HISTORY_COMPLETED" }

PATCH /api/v1/pac/{pac_id}
{ "examination": {...}, "transition_event": "SAVE_EXAM" }
→ { workflow_state: "EXAM_COMPLETED" }
```

### 5. Compute Risk
```
POST /api/v1/risk/compute
{ "pac_id": "PAC-..." }
→ { risk_id, asa_class, sofa_score, rcri_score, disposition }
```

### 6. Submit for Review
```
POST /api/v1/pac/{pac_id}/submit
→ { review_state: "SR_REVIEW_PENDING" }
```

### 7. SR Review (login as sr.resident@...)
```
POST /api/v1/pac/{pac_id}/review/sr
{ "action": "APPROVED", "comments": "Plan appropriate" }
```

### 8. Consultant Lock (login as consultant@...)
```
POST /api/v1/pac/{pac_id}/lock
{ "comments": "Cleared for CABG", "digital_signature": "sig-..." }
→ { workflow_state: "PAC_LOCKED" }
```

### 9. Generate Consent
```
POST /api/v1/consent
{ "pac_id": "PAC-...", "procedure_code": "CABG", "language": "hi" }
```

### 10. Trigger rPAC (after clinical change)
```
POST /api/v1/rpac
{ "patient_id", "parent_pac_id", "trigger_type": "ABNORMAL_LABS", "trigger_reason": "Creatinine spike" }
```

### 11. View Lineage Graph
```
GET /api/v1/audit/patient/{patient_id}/lineage
→ { nodes: [...], edges: [...] }
```

## FSM Design

Each workflow is a flat Python file in `fsm/` with:
- `State` class — string constants for all states
- `Event` class — string constants for all triggerable events
- `TRANSITIONS` dict — `(state, event) → next_state`
- `ALLOWED_ROLES` dict — `(state, event) → [role_list]`
- `STATE_META` dict — UI labels, progress %, tab hints

The `BaseStateMachine` engine in `fsm/base.py` enforces:
- Invalid transition → `InvalidTransitionError`
- Unauthorized role → `UnauthorizedTransitionError`
- Terminal state guard
- Available events per role

## Security

- JWT RS256 access tokens (15 min) + refresh tokens (8 hr)
- TOTP MFA (pyotp) — toggle per user
- RBAC enforced in every service call via `ALLOWED_ROLES`
- Immutable `workflow_events` table — application INSERT only
- SHA-256 record hashes on all locked/finalized records
- 25-year consent retention policy on `ConsentRecord`
