# Controlled AI Assistant Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a local-first, evidence-backed AI assistant that creates confirmation-gated operation drafts without exposing raw project data to cloud providers.

**Architecture:** An engine-side orchestrator constructs minimal project context, sanitizes cloud payloads, routes only to an authorized provider, and returns a structured response. The existing right-side React panel renders evidence, transfer previews, and action drafts; existing engine handlers remain the only write path after confirmation.

**Tech Stack:** Python 3.12, aiohttp, pytest, React 18, TypeScript, Zustand, Ant Design, Tauri JSON-RPC.

**Spec:** `docs/superpowers/specs/2026-09-08-v050-controlled-ai-assistant-design.md`

## Global Constraints

- Ollama is default; an unavailable local model must never auto-fallback to cloud.
- Cloud requests require provider enablement, per-project consent, and a visible de-identification preview.
- Numbers remain unchanged by default; identifiers and enterprise identifiers are masked.
- Unsupported content is labelled `ai_guess` or `unverified`.
- Assistant drafts cannot mutate state before user confirmation.
- Existing version-chain and audit paths are the only write path after confirmation.

---

## File Structure

| File | Responsibility |
| --- | --- |
| `engine/src/process_intelligence_engine/ai/contracts.py` | Assistant request, response, evidence, draft, and transfer-preview contracts. |
| `engine/src/process_intelligence_engine/ai/context.py` | Minimal, current-project-only evidence context. |
| `engine/src/process_intelligence_engine/ai/sanitizer.py` | Identifier masking and numeric policies. |
| `engine/src/process_intelligence_engine/ai/orchestrator.py` | Provider policy, structured output validation, and drafts. |
| `engine/src/process_intelligence_engine/project/manifest.py` | Per-project consent and sanitization rules. |
| `engine/src/process_intelligence_engine/main.py` | Assistant JSON-RPC endpoints and confirmed-draft execution. |
| `engine/tests/test_ai_context.py` | Context and manifest tests. |
| `engine/tests/test_ai_sanitizer.py` | Sanitizer tests. |
| `engine/tests/test_ai_orchestrator.py` | Provider, response, draft, and confirmation tests. |
| `src/lib/engine.ts` | TypeScript contracts and RPC wrappers. |
| `src/stores/assistantContextStore.ts` | Typed page context and active project identity. |
| `src/components/assistant/*.tsx` | Evidence, transfer-preview, and action-draft cards. |
| `src/components/layout/AssistantPanel.tsx` | Structured assistant UI. |

## Task 1: Persist assistant policy and define contracts

**Files:**
- Create: `engine/src/process_intelligence_engine/ai/contracts.py`
- Modify: `engine/src/process_intelligence_engine/project/manifest.py`
- Test: `engine/tests/test_ai_context.py`

**Interfaces:** Produces `AssistantEvidence`, `AssistantActionDraft`, `AssistantRequest`, `AssistantResponse`, and `CloudTransferPreview`, each with `to_dict()`. Adds manifest `assistant_policy` with `cloud_consent`, `sanitization_rules`, and `consented_at`.

- [ ] **Step 1: Write a failing manifest test.**

```python
def test_assistant_policy_round_trips_without_sensitive_values(tmp_path):
    manifest = ProjectManifest.create(tmp_path, "demo")
    manifest.assistant_policy = {"cloud_consent": True, "sanitization_rules": {"operator": "mask"}, "consented_at": "2026-09-08T00:00:00+00:00"}
    manifest.save()
    assert ProjectManifest.load(tmp_path).assistant_policy["cloud_consent"] is True
```

- [ ] **Step 2: Verify RED.** Run `cd engine && .venv/bin/python -m pytest tests/test_ai_context.py -q`; expect failure because `assistant_policy` is absent.
- [ ] **Step 3: Add contracts and the manifest default** `{"cloud_consent": False, "sanitization_rules": {}, "consented_at": None}` to creation, serialization, and load migration. `AssistantActionDraft` has `draft_id`, `method`, `params`, `impact`, and `expected_result`.
- [ ] **Step 4: Verify GREEN.** Run `cd engine && .venv/bin/python -m pytest tests/test_ai_context.py -q`; expect pass.
- [ ] **Step 5: Commit.** Run `git add engine/src/process_intelligence_engine/ai/contracts.py engine/src/process_intelligence_engine/project/manifest.py engine/tests/test_ai_context.py && git commit -m "feat: persist assistant consent policy"`.

## Task 2: Build bounded evidence context

**Files:**
- Create: `engine/src/process_intelligence_engine/ai/context.py`
- Test: `engine/tests/test_ai_context.py`

**Interfaces:** Produces `build_assistant_context(project_id: str, page: str, page_summary: dict, chain: VersionChain) -> dict`.

- [ ] **Step 1: Write failing scope tests.**

```python
def test_context_excludes_another_project(chain):
    context = build_assistant_context("project-a", "modelCenter", {"selected_model_id": "md-a"}, chain)
    assert all(item["project_id"] == "project-a" for item in context["evidence"])

def test_context_marks_missing_evidence_unverified(chain):
    assert build_assistant_context("project-a", "report", {}, chain)["evidence_status"] == "unverified"
```

- [ ] **Step 2: Verify RED.** Run `cd engine && .venv/bin/python -m pytest tests/test_ai_context.py -q`; expect missing function failure.
- [ ] **Step 3: Implement the bounded builder.** Include only project ID, page, approved summary keys, entity IDs, entity types, versions, and evidence statuses. Raise `ValueError("Assistant context exceeds the local summary limit")` for `raw_rows`, `dataframe`, or serialized summaries over 32 KiB.
- [ ] **Step 4: Verify GREEN and commit.** Run `cd engine && .venv/bin/python -m pytest tests/test_ai_context.py -q`; then run `git add engine/src/process_intelligence_engine/ai/context.py engine/tests/test_ai_context.py && git commit -m "feat: build project-scoped assistant context"`.

## Task 3: Sanitize cloud assistant context

**Files:**
- Create: `engine/src/process_intelligence_engine/ai/sanitizer.py`
- Test: `engine/tests/test_ai_sanitizer.py`

**Interfaces:** Produces `sanitize_context(context: dict, rules: dict[str, str], numeric_policy: Literal["raw", "bucketed", "standardized"] = "raw") -> CloudTransferPreview`.

- [ ] **Step 1: Write failing privacy tests.**

```python
def test_sanitizer_masks_identifiers_and_keeps_numbers_raw():
    preview = sanitize_context({"operator": "Ada", "station": "Line-A", "temperature": 150.2}, {})
    assert preview.payload["operator"] == "MASKED"
    assert preview.payload["station"] == "MASKED"
    assert preview.payload["temperature"] == 150.2

def test_bucketed_policy_removes_exact_value():
    assert sanitize_context({"temperature": 150.2}, {}, "bucketed").payload["temperature"] != 150.2
```

- [ ] **Step 2: Verify RED.** Run `cd engine && .venv/bin/python -m pytest tests/test_ai_sanitizer.py -q`; expect missing sanitizer failure.
- [ ] **Step 3: Implement recursive masking.** Mask keys matching `name`, `email`, `phone`, `ip`, `path`, `customer`, `supplier`, `part`, `station`, `line`, `machine`, `operator`, `account`, `serial`, and `lot`. Use `MASKED`; bucket values into deterministic ten-unit ranges; standardize only with explicit nonzero mean and standard deviation.
- [ ] **Step 4: Verify GREEN and commit.** Run `cd engine && .venv/bin/python -m pytest tests/test_ai_sanitizer.py -q`; then run `git add engine/src/process_intelligence_engine/ai/sanitizer.py engine/tests/test_ai_sanitizer.py && git commit -m "feat: sanitize assistant cloud context"`.

## Task 4: Enforce local-first provider policy

**Files:**
- Create: `engine/src/process_intelligence_engine/ai/orchestrator.py`
- Modify: `engine/src/process_intelligence_engine/settings/__init__.py`
- Test: `engine/tests/test_ai_orchestrator.py`

**Interfaces:** Produces `AssistantOrchestrator.respond(request: AssistantRequest) -> AssistantResponse`, `preview_cloud(request) -> CloudTransferPreview`, and `grant_project_cloud_consent(project_root: str, preview_hash: str) -> dict`.

- [ ] **Step 1: Write failing policy tests.**

```python
def test_unhealthy_ollama_never_falls_back_to_cloud(orchestrator):
    result = orchestrator.respond(local_request())
    assert result.error_code == "local_model_unavailable"
    assert result.provider is None

def test_cloud_requires_provider_consent_and_preview(orchestrator):
    with pytest.raises(PermissionError, match="Cloud assistant use requires project consent"):
        orchestrator.respond(cloud_request())
```

- [ ] **Step 2: Verify RED.** Run `cd engine && .venv/bin/python -m pytest tests/test_ai_orchestrator.py -q`.
- [ ] **Step 3: Implement routing and validation.** Add `cloud_enabled: bool = False` to `AIProviderConfig`. Ollama health/request failures return only `local_model_unavailable`. Cloud requires `cloud_enabled`, persisted consent, and a current preview hash. Require JSON with `explanation`, `evidence_ids`, `evidence_status`, `recommendations`, `action_draft`, and `limitations`; return `invalid_assistant_response` if decoding fails.
- [ ] **Step 4: Add draft allow-list validation.** Permit only `modeling/fit`, `validation/experiment/create`, and `report/generate`; reject all others with `ValueError("Assistant action is not allowed")`. Validate required parameters before returning a draft.
- [ ] **Step 5: Verify GREEN and commit.** Run `cd engine && .venv/bin/python -m pytest tests/test_ai_orchestrator.py -q`; then run `git add engine/src/process_intelligence_engine/ai/orchestrator.py engine/src/process_intelligence_engine/settings/__init__.py engine/tests/test_ai_orchestrator.py && git commit -m "feat: enforce local-first assistant orchestration"`.

## Task 5: Expose confirmation-gated RPCs

**Files:**
- Modify: `engine/src/process_intelligence_engine/main.py`
- Modify: `engine/tests/test_main_handlers.py`

**Interfaces:** Adds `assistant/respond`, `assistant/cloud_preview`, `assistant/cloud_consent`, and `assistant/draft/execute`. The execute endpoint consumes `{draft_id, confirmed: true}`.

- [ ] **Step 1: Write failing handler tests.**

```python
def test_execute_draft_rejects_missing_confirmation(project):
    result = handle_request("assistant/draft/execute", {"draft_id": "draft-1", "confirmed": False})
    assert result["error_code"] == "confirmation_required"

def test_cloud_consent_is_persisted_per_project(project):
    assert handle_request("assistant/cloud_consent", {"preview_hash": "abc", "confirmed": True})["cloud_consent"] is True
```

- [ ] **Step 2: Verify RED.** Run `cd engine && .venv/bin/python -m pytest tests/test_main_handlers.py -k assistant -q`.
- [ ] **Step 3: Implement handlers.** Store server-created drafts by draft ID and active project ID. Require `confirmed is True`, then delegate to the existing handler dispatcher for the validated allow-listed method. Remove a draft only after success, and record `assistant_draft_confirmed` using the existing audit manager.
- [ ] **Step 4: Verify GREEN and commit.** Run `cd engine && .venv/bin/python -m pytest tests/test_main_handlers.py -k assistant tests/test_trust_chain_integration.py -q`; then run `git add engine/src/process_intelligence_engine/main.py engine/tests/test_main_handlers.py && git commit -m "feat: add confirmed assistant RPC actions"`.

## Task 6: Add typed client contracts and structured cards

**Files:**
- Modify: `src/lib/engine.ts`
- Modify: `src/stores/assistantContextStore.ts`
- Create: `src/components/assistant/EvidenceCard.tsx`
- Create: `src/components/assistant/TransferPreviewCard.tsx`
- Create: `src/components/assistant/ActionDraftCard.tsx`
- Modify: `src/components/layout/AssistantPanel.tsx`
- Modify: `src/App.tsx`
- Modify: `src/features/project/ProjectOverview.tsx`

**Interfaces:** Adds `assistantRespond`, `previewAssistantCloudTransfer`, `grantAssistantCloudConsent`, and `executeAssistantDraft`. `AssistantPanel` receives `activeProject` and never sends project context when it is null.

- [ ] **Step 1: Add matching TypeScript response types.**

```ts
export interface AssistantResponse {
  success: boolean
  explanation: string
  evidence: AssistantEvidence[]
  evidence_status: string
  recommendations: string[]
  action_draft?: AssistantActionDraft
  limitations: string[]
  error_code?: string
}
```

- [ ] **Step 2: Extend the context store.** Keep existing textual summaries, then add `activeProjectId`, `setActiveProjectId`, and `getCurrentContext(tab): { tab: AppTab; summary: string; project_id: string | null }`.
- [ ] **Step 3: Implement pure cards.** `EvidenceCard` renders IDs/statuses. `TransferPreviewCard` renders provider, masked paths, numeric policy, and payload hash but never raw values. `ActionDraftCard` renders impact and invokes `executeAssistantDraft(draft_id, true)` only on Confirm; Cancel removes only local card state.
- [ ] **Step 4: Adapt panel requests.** Replace direct `aiChat(messages)` with `assistantRespond({ message, tab: activeTab, context: getCurrentContext(activeTab) })`. Keep transcript behavior, render structured cards, and display the explicit local-model setup state for `local_model_unavailable`.
- [ ] **Step 5: Wire active project identity.** Pass `activeProject` from `App.tsx` to the panel; after project create/open, set the store ID in `ProjectOverview`.
- [ ] **Step 6: Verify build and commit.** Run `npm run build`; then run `git add src/lib/engine.ts src/stores/assistantContextStore.ts src/components/assistant src/components/layout/AssistantPanel.tsx src/App.tsx src/features/project/ProjectOverview.tsx && git commit -m "feat: render controlled assistant responses"`.

## Task 7: Localize, document, and verify release quality

**Files:**
- Modify: `src/i18n/en.json`
- Modify: `src/i18n/zh-TW.json`
- Modify: `src/i18n/es-MX.json`
- Modify: `README.md`
- Modify: `docs/deployment.md`

- [ ] **Step 1: Add identical locale keys.** Add `localModelUnavailable`, `openSettings`, `evidence`, `aiGuess`, `unverified`, `cloudConsent`, `transferPreview`, `maskedFields`, `confirmAndRun`, `cancelDraft`, `cloudDisabled`, and `sanitizationFailed` in each locale.
- [ ] **Step 2: Document safety and setup.** Document Ollama setup, no automatic cloud fallback, per-project consent, de-identification preview, and consent revocation. Do not include provider keys.
- [ ] **Step 3: Run full verification.**

```bash
cd engine && .venv/bin/python -m pytest tests/ -q
cd .. && npm run build
cargo check --manifest-path src-tauri/Cargo.toml
git diff --check
```

Expected: engine tests pass with only documented existing warnings; build and Cargo check exit 0; diff check has no output.

- [ ] **Step 4: Run manual acceptance.** Verify local explanation with evidence IDs, cloud preview with masked identifiers, cancelled draft with no mutation, confirmed draft with version-chain/audit record, and unavailable-Ollama behavior on macOS, Windows, and Linux.
- [ ] **Step 5: Commit.** Run `git add src/i18n README.md docs/deployment.md && git commit -m "docs: explain controlled AI assistant setup"`.

## Plan Self-Review

- Tasks 1–2 cover project scope and evidence; Task 3 covers de-identification; Tasks 4–5 cover provider policy, consent, drafts, and confirmation; Task 6 covers the right-panel UI; Task 7 covers localization, deployment, and automated/manual acceptance.
- No task adds automatic Gate confirmation, autonomous execution, raw data upload, MES, image learning, or multi-agent behavior.
- `AssistantResponse`, `AssistantActionDraft`, `CloudTransferPreview`, and project consent are introduced before their later engine or UI consumers.

