# OpenRouter BYOK and Ollama Cloud setup

Status: proposal for review, 27 November 2026. Planning only; no live requests, credential changes or implementation authorized by this document. This task-specific plan extends the existing agent integration agenda rather than replacing it. Implementation slices below can become GitHub Issues when implementation is authorized; no external issues were created during planning.

## Recommendation

Extend Querivue's existing Python ModelGateway with two transport routes: OpenRouter and direct Ollama Cloud. Keep role prompts, tool execution, output validation and budget authority in Querivue. Avoid adding a separately deployed proxy for this first version.

```text
Role request -> gateway admission and route policy
  -> OpenRouter -> allowed upstream provider -> prioritized BYOK keys
  -> Ollama Cloud -> local credential selector -> configured cloud model
Response -> route verification -> schema/tool validation -> accounting
```

OpenRouter owns its upstream key failover. Querivue owns transitions between OpenRouter and Ollama Cloud, plus Ollama credential selection. Neither layer receives an unlimited retry allowance.

## Existing contracts and implementation gaps

- The approved provider menu in architecture/role-prompts-models.md retains pinned evaluation endpoints, zero-paid-spend development restrictions and protocol/privacy gates. This proposal does not silently enable paid OpenRouter or equate BYOK with a free tier.
- runtime/models.py caches adapters by provider alone and generally constructs them without the role's selected model. Replace that with explicit route configuration and cache identity including model, endpoint and credential reference/revision. Resolve the differing role names against config.ALL_ROLES once at the boundary.
- providers/ollama.py is a local /api/generate adapter that flattens messages and sends no cloud credential. Cloud needs authenticated Chat Completions with preserved messages and tool-call identities. Keep local Ollama explicitly separate.
- OpenRouter currently inserts system messages into the original messages list. Build an independent payload so retries cannot duplicate instructions or mutate another attempt.
- Existing provider identities contain placeholder verification/rate fields; runtime/models.py records zero cost. Neither is valid evidence for enabling the new routes.
- Code-review-graph MCP narrowed gateway consumers to graph.py, specialists/reviewer.py and tests/unit/test_gateway.py. Source inspection remains authoritative; graph HEAD matched at inspection.

## Configuration and ownership

| Record | Required information | Owner |
| --- | --- | --- |
| Credential reference | Stable nonsecret ID, environment variable, account/quota group, priority, enabled flag | Operator; secret resolved in backend memory |
| Route | Transport, exact remote model ID, base URL, OpenRouter provider/endpoint allowlist, capabilities, token/context limits, rates, privacy and spending eligibility | Versioned configuration |
| Role policy | Ordered route IDs, pinned/resilient mode, required capabilities, existing role limits | Versioned configuration |
| Attempt | Logical invocation ID, attempt ID, config digest, selected/observed route, nonsecret credential ID where known, timing, usage, cost status and outcome | Existing authoritative ledger/trace boundary |

Secrets stay out of TOML, browser responses, prompts, checkpoints, hashes and traces. Resolve environment references through the explicit configuration loader rather than ambient provider constructors. Do not put OpenRouter management credentials in the inference runtime.

Use one OpenRouter application key per environment by default. Multiple OpenRouter application keys do not automatically create more upstream quota. Store supported upstream keys in OpenRouter's BYOK settings; store Ollama keys in backend environment/secrets. Verify account setup requirements for each provider, including account/project/region fields, before marking it eligible.

Ollama cloud base URL: https://ollama.com/v1; authenticated POST /chat/completions. OpenRouter base URL: https://openrouter.ai/api/v1. Never infer identical capabilities or identical model IDs from compatible request syntax.

## Routing policy

1. Resolve the role's explicit candidate list and capability requirements. Validate tools, structured output, context, output accounting, privacy and spend eligibility before selecting a route. Never discover and substitute a model during dispatch.
2. Pinned mode remains the evaluation/default safety baseline: one exact upstream route, provider.only allowlist, allow_fallbacks=false, require_parameters=true. Pin endpoint variant where available and verify observed metadata. Credential substitution is allowed only among predeclared equivalent identities; exact-key experiments need an isolated key mapping.
3. Proposed resilient mode permits an ordered, prevalidated route list. Prefer same-model routes first; a different model is a separately declared candidate. An Ollama-first policy is equally configurable. OpenRouter provider.order prioritizes providers but does not itself restrict eligibility: pair it with provider.only. Configure require_parameters=true.
4. OpenRouter BYOK keys use its priority/failover mechanism. Configure prioritized keys and disable shared-capacity fallback on every allowed provider by default. Appending a key to OpenRouter's Fallback section places it after shared capacity; that is unsuitable for the initial BYOK-only setup.
5. Querivue initially sends one OpenRouter request per route visit. It does not repeat the whole OpenRouter key cascade on a 429. If policy permits, it moves to the next eligible transport candidate within the same invocation budget.
6. Ollama selects the highest-priority healthy credential. A key-specific throttle can cool down that key; an account-wide quota/concurrency limit cools down the entire configured quota group. Respect Retry-After; do not immediately cycle through keys sharing the exhausted group.

For example, a role can explicitly allow OpenRouter model A on Groq/NVIDIA (only if that exact model is available there), followed by Ollama model B after capability and privacy validation. Google and Cloudflare can have separate role candidates; one model need not exist on every provider.

## Errors, accounting and concurrency

| Outcome | Proposed handling |
| --- | --- |
| Invalid/auth-expired key | Disable that credential locally until operator reload/rotation; try a separately eligible key only within the attempt cap |
| Permission/policy denial | Stop; do not use fallback to bypass the denial |
| Rate limit | Classify key versus quota-group scope; honor cooldown; select another eligible group/route or return bounded unavailability |
| 5xx / known pre-dispatch connection failure | Bounded retry or next configured route within remaining time and counters |
| Timeout/disconnect after possible dispatch | Mark outcome/usage uncertain; retain reservation; no blind replay or refund. Another attempt requires policy permission and a separate reservation |
| Unsupported parameter/context/schema | Configuration error or existing bounded output-repair path; never strip evidence/tools or invent another model |
| Failure after streaming output or tool-call exposure | End with recoverable error; no transparent replay, mixed-provider stream or repeated tool effect |

Use existing role physical-request limits, transient retry limits, run deadlines and spend reservations. Initial product behavior remains non-streaming, matching the current gateway; streaming must meet the same boundary before enablement. Reserve before every locally dispatched attempt, settle once, and retain unknown charges. Tool calls execute only after complete validation through existing trusted wrappers.

OpenRouter's hidden upstream attempts are not automatically observable as individual physical requests. Record local submissions and upstream work separately. Before enablement, establish a finite provider-side bound and conservative cost reservation; if the existing physical-request invariant requires exact upstream accounting and this cannot be supplied, disable hidden cascading for that profile. Do not claim that one HTTP submission proves one upstream attempt.

BYOK inference may generate provider charges and OpenRouter fees; shared capacity disabled does not prove zero cost. Resolve current pricing/allowances before enablement, include BYOK spend in configured OpenRouter budgets where supported, and retain local admission as authority. Treat subscription quotas and unexposed token prices as explicit accounting policies, not invented zero-dollar verified rates.

Key health is backend-owned operational state. For the local process use synchronized selection/semaphores; for concurrent workers use a shared bounded cooldown/lease store (existing Redis is a candidate, not accounting authority). Release leases in finally blocks; expiry/restart must not reset durable counters or unknown dispatch reservations. If health state is unavailable, fail closed for pooled dispatch. Never persist raw upstream error bodies without redaction. Provider identities cannot automatically inherit local Ollama privacy/free-tier flags.

Retain attempt metadata through the existing retention/deletion lifecycle. Do not add provider-managed conversation state. On resume, keep the invocation configuration snapshot and prior attempts; recheck revoked credentials and current authorization before a fresh attempt. Key rotation changes secret revision without copying the secret into history.

## Implementation slices

Each slice is proposed, not started. Follow the repository's spec-driven workflow and focused verification after implementation.

| Order | Slice and likely files | Acceptance / verification |
| --- | --- | --- |
| 1 | Route configuration: config.py, contracts/manifests.py, example config | Nonsecret route/credential/policy records; reject unknown references and incomplete eligibility. Focused config tests, redaction and legacy profile tests. |
| 2 | Exact model dispatch: runtime/models.py, providers/base.py, tests/unit/test_gateway.py | Selected role model reaches the wire; clients cannot reuse another route/credential; input messages stay unchanged across attempts. |
| 3 | OpenRouter BYOK policy: providers/openrouter.py, test_provider_protocols.py | Correct only/order/fallback/parameter controls and response-route metadata; isolated mock failures do not repeat a hidden cascade. Operator checklist verifies provider BYOK configuration before use. |
| 4 | Ollama Cloud adapter: new providers/ollama_cloud.py, providers/__init__.py, protocol tests | Bearer authentication and exact model, messages, tools and schema preserved; local adapter stays separately selectable. Cloud verification flags start unverified. |
| 5 | Ollama credential pool: new runtime/credentials.py, focused pool tests | Concurrent priority selection, group-wide cooldown, auth revocation and rotation; all-unavailable returns a finite error. |
| 6 | Route orchestration: runtime/models.py and existing reservation integration | Pinned mode cannot substitute routes; resilient mode only follows declared candidates; every local attempt obeys remaining limits; unknown outcomes retain reserves. |
| 7 | Attempt observability: runtime/trace.py and relevant attempt contracts | Selected versus observed identity, usage, known/estimated/unknown cost and error category are visible without secrets; retention/deletion works. |
| 8 | Qualification and operator guide | Mock outage, throttle, account exhaustion, wrong-model, schema/tool mismatch, concurrency, cancellation and resume cases pass. Existing gateway/config/protocol suites remain green. Live qualification uses a separately forecast, bounded synthetic-data run only when authorized. |

Dependencies: 2 follows 1; 3 and 4 follow 2; 5 follows 4; 6 follows 3–5 and accounting design; 7 integrates with 6; 8 follows all. Checkpoints after 2 (correct dispatch), 5 (both transports), and 8 (readiness evidence). Groq needs no direct adapter for the proposed OpenRouter path. Preserve existing direct adapters for approved free-development profiles.

## Review choices and enablement gates

Recommended choices for review: prioritize BYOK keys; disable paid shared-capacity fallback; priority failover rather than round-robin; retain pinned evaluation mode; add opt-in resilient operation; allow different-model fallback only through explicit role candidates. OpenRouter remains the proposed primary route; Ollama Cloud can be backup or an explicitly selected primary.

Before implementation/enablement: settle those consequential policy choices, select exact role/model/provider mappings from available account catalogs, identify independent quota groups, establish upstream retry/accounting bounds, and confirm privacy/cost eligibility. Exact finite cooldowns/concurrency/attempt ceilings are implementation configuration bounded by existing contracts and tuned through measurement. Model quality remains unmeasured. If strict free usage through OpenRouter cannot be established, retain direct free-development adapters for that profile.

After review, transfer settled contracts into architecture/role-prompts-models.md and the decision log, then remove this temporary plan when the work closes. Do not mark the phase complete based on this proposal.

## Sources

- [OpenRouter BYOK: multiple keys, ordering, shared-capacity controls and budgets](https://openrouter.ai/docs/guides/overview/auth/byok), checked 27 November 2026.
- [OpenRouter provider selection](https://openrouter.ai/docs/guides/routing/provider-selection), queried through Context7 official documentation.
- [Ollama OpenAI compatibility and direct cloud authentication](https://docs.ollama.com/api/openai-compatibility), checked 27 November 2026.
- Existing approved provider menu: architecture/role-prompts-models.md, provider configurations and remaining pins before execution.
