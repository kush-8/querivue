# LangChain integration research

27 November 2026. Source inspection and current official documentation. Subsequent user-approved memory scopes and the two-layer guardrail approach are now recorded in the [authoritative architecture](../architecture/agent-integration.md#memory-lifetimes-and-scopes) and [decision log](../memory.md). Provider/middleware implementation choices below remain recommendations unless explicitly identified as approved there. No code, dependency or live-readiness changes.

## Existing decision and implementation

Subsequent user direction makes LangChain reuse the default wherever requirements can be met, including memory, context and guardrails. The [authoritative reuse policy](../architecture/overall.md#langchain-reuse-policy) supersedes any optional wording here that would allow custom plumbing without a concrete capability/contract gap. Exact packages and unapproved behavioral changes remain subject to their owning contracts.

The [standalone plan](standalone-agent.md#implementation-decisions-for-review) already records the user's 21 November selection of LangChain model integrations, messages, tool schemas and structured outputs. Its T06 contract keeps the gateway as the sole graph-facing model boundary and provider files as integration/profile configuration, rather than parallel HTTP transports. This is an existing decision, not a new proposal.

Observed source:

- `agent/pyproject.toml` declares LangChain 1.5.2, langchain-core 1.8.4, LangGraph 1.2.24 and the Redis checkpoint package. No provider integration packages are declared there.
- `graph.py` builds a LangGraph StateGraph; `runtime/checkpoints.py` uses LangChain RunnableConfig.
- `runtime/models.py` selects six custom ModelProvider adapters. Google, NVIDIA, OpenRouter, Cloudflare, Ollama and Ollama Cloud adapters issue requests through httpx, rather than LangChain chat models.
- Answer and Reviewer currently parse response text with json.loads. Provider-independent message and structured-output integration is therefore unfinished.
- `runtime/trace.py` writes local JSONL. Source inspection found no explicit LangSmith SDK client or traceable integration. LangSmith is in the intended stack, and its SDK is transitive in the lockfile; that does not demonstrate active hosted observability. T06 explicitly keeps automatic raw tracing off and gates optional hosted export.

## Applicable documented components

| Component | Fit for Querivue | Official documentation |
| --- | --- | --- |
| ChatGoogleGenerativeAI / langchain-google-genai | Configure our Google route using the maintained integration; explicitly retain the selected backend and provider metadata. | [Google](https://docs.langchain.com/oss/python/integrations/chat/google_generative_ai) |
| ChatNVIDIA / langchain-nvidia-ai-endpoints | Configure the NVIDIA route with a maintained chat-model integration. | [NVIDIA](https://docs.langchain.com/oss/python/integrations/chat/nvidia_ai_endpoints) |
| ChatOpenRouter / langchain-openrouter | Configure OpenRouter using its dedicated integration, including documented provider filtering and routing controls. BYOK/shared-capacity behavior still needs separate verification. | [OpenRouter](https://docs.langchain.com/oss/python/integrations/chat/openrouter) |
| ChatOllama / langchain-ollama | Candidate for local Ollama. Cloud authentication, endpoint behavior and our credential-pool handling need independent compatibility checks. | [Ollama](https://docs.langchain.com/oss/python/integrations/chat/ollama) |
| ChatCloudflareWorkersAI | Listed in the Python integration catalog. Exact package/import/version and async/usage capabilities remain to be verified; the former Python guide redirects to the catalog, and Context7 also surfaced a JavaScript-only guide. | [Python catalog](https://docs.langchain.com/oss/python/integrations/chat) |
| Standard messages and tool binding | Preserve role-local system/user/assistant/tool messages and tool-call linkage. Bind existing approved schemas; runtime retains permission and execution checks. | [Messages](https://docs.langchain.com/oss/python/langchain/messages), [tools](https://docs.langchain.com/oss/python/langchain/tools), [models](https://docs.langchain.com/oss/python/langchain/models) |
| with_structured_output(schema, include_raw=True) | Candidate for typed Supervisor, Entry, Answer, Reviewer and Clarification responses, using each integration's supported method. Preserve raw AIMessage, parsing errors and response metadata. Existing strict local/reference/semantic validation remains necessary. | [Models: structured output](https://docs.langchain.com/oss/python/langchain/models#structured-output) |
| AIMessage usage_metadata and response_metadata | Normalize reported usage and keep provider details available to accounting. Missing usage remains unknown; reported tokens do not establish full-payload preflight counting or billed cost. | [Messages](https://docs.langchain.com/oss/python/langchain/messages) |
| init_chat_model | Optional construction convenience behind the existing gateway. Explicit provider classes may make route-specific configuration easier to inspect. Model calls can be standalone; adopting create_agent is unnecessary for these integrations. | [Models](https://docs.langchain.com/oss/python/langchain/models) |

The catalog warns that ChatOpenAI with a third-party base_url only preserves OpenAI-standard fields. Prefer dedicated integrations where provider-specific reasoning or response fields matter. See the [catalog compatibility guidance](https://docs.langchain.com/oss/python/integrations/chat#chat-completions-api).

## Recommendation and limits

Complete the already selected T06 integration behind ModelGateway, starting with one configured route. Keep provider modules thin and translate integration responses into existing domain contracts. Retain Markdown prompt loading and hashing; message construction can use LangChain without changing prompt ownership.

Keep the existing LangGraph topology, private role contexts, ledger, budget reservations, source guards, evidence/artifact validation, sandbox execution and mandatory review edges. Generic SQL agents, Python REPLs and provider-hosted code tools are not drop-in implementations of those contracts. This is an architectural fit assessment, not a claim that every toolkit was compatibility-tested.

Retrieval/embeddings/vector-store integrations are optional future work when a concrete document or semantic-search requirement exists; tabular computation still needs SQL/Python evidence. No new retrieval or memory store is selected here.

Before treating a route as ready, verify locked-package compatibility, actual async/streaming behavior, strict schema support, refusal/truncation handling, preserved thought/tool metadata, exact token accounting, and one admitted physical request per wire call. Disable or explicitly account for integration/SDK retries and fallback. Preserve pinned routing and credential policies. Automatic raw tracing remains off under the existing T06 policy.

No dependencies were installed and no provider calls or runtime tests were run for this documentation review. Current online documentation is not proof of compatibility with the repository's locked versions.

## Follow-up: memory, context and guardrails

Reviewed on 27 November against the [memory/context contracts](../architecture/agent-integration.md#conversational-memory-and-follow-ups). This research informed the later approved scope amendment; the architecture owns final contracts, while this note retains sources and implementation options.

### Memory

LangChain's [short-term memory](https://docs.langchain.com/oss/python/langchain/short-term-memory) uses graph state and checkpointers. Continue using LangGraph/Redis for run recovery. Our graph thread identity is run-scoped; cross-run Chat continuity must be constructed from eligible durable Chat records, rather than assumed to come from the same checkpoint thread.

Its [long-term memory](https://docs.langchain.com/oss/python/langchain/long-term-memory) uses LangGraph stores with namespaces and keys, optionally database-backed. This could support a future explicitly scoped memory adapter, but does not itself implement our confirmation, supersession, source-dependency, deletion or visibility-cutoff rules. Initial contracts exclude cross-Chat/user-global analytical memory and a new vector-memory service. The subsequent user decision includes persistent source-independent presentation preferences across that user's sessions/Chats; these do not import analytical history. Project-shared analytical definitions remain a future deliberate feature. A new store would need a defined ownership/persistence contract rather than a second authority beside the ledger.

### Context

The [context-engineering documentation](https://docs.langchain.com/oss/python/langchain/context-engineering) describes controlling messages, prompts, tool availability and response format using state, stores and runtime context. Apply the standard message/model interfaces to our explicit role packets. Keep trusted execution dependencies separate from model-visible context and enforce permissions at the tool boundary.

Our approved compaction reconstructs packets deterministically, protects original obligations and required evidence/feedback, and preserves whole tool exchanges. [SummarizationMiddleware](https://docs.langchain.com/oss/python/langchain/middleware/built-in) is a possible future alternative, but adds model calls and derived prose. It conflicts with the current no-extra-summarizer contract unless that decision is revised and accounting, provenance and deletion behavior are specified.

Source inspection of context.py shows packet-building functions, but _build_base_snapshot currently supplies cutoff_sequence=0 and empty prior context/interpretation/thread/conflict collections. This is evidence of unfinished analytical continuity, not a complete memory implementation. Other acceptance behavior was not tested in this review.

### Guardrails

The [guardrail documentation](https://docs.langchain.com/oss/python/langchain/guardrails) offers deterministic and model-based checks, including PIIMiddleware, human approval and custom hooks around model/tool execution. PII detection is a candidate additional content check, not proof of complete redaction. Keep the existing hosted-trace allowlist and exact published evidence/content contracts; redaction must not silently change analytical meaning or a reviewed answer.

Source/tool authorization, SQL policy, sandbox isolation, budgets, evidence integrity, source invalidation and mandatory review remain runtime-enforced rules. Model-based input/output checks can supplement them only through accounted and specified calls. Existing entry assessment and Reviewer roles already own relevant semantic checks; avoid adding a duplicate safety/review call by default. Human approval middleware is relevant only if a product operation actually requires approval; our linked analytical clarification remains its own contract.

These middleware hooks run in the graph compiled by create_agent. The [middleware overview](https://docs.langchain.com/oss/python/langchain/middleware/overview) documents embedding that whole agent as a node/subgraph in a larger StateGraph. They are not automatically activated by using a standalone chat model in our custom graph. A specialist-local create_agent integration is technically possible, but would need deliberate ownership of tool execution, physical calls, state and stopping behavior before adoption.
