# Standalone agent implementation planning — working document

20 November 2026. Started at the user's request to complete implementation planning before coding. Agent architecture is approved and closed. This phase authorizes repository inspection, official-source research and reversible planning-document edits only; no production code, dependency installation, inference, sandbox session or paid run.

## Objective

Prepare one reviewable implementation plan for the standalone agent/CLI milestones, preserving approved ingestion, graph/state, specialist, provider, persistence, isolation and evaluation contracts. Pin ownership, file placement, internal interfaces, dependency order, verification and stop gates. Application API/worker/UI work remains separate.

## Work sequence

1. Retrieve approved milestone/acceptance contracts and inspect the starter agent package, relevant configuration and graph inventory.
2. Define the smallest complete package layout, dependency/build strategy and task interfaces. Distinguish architectural decisions already approved from implementation proposals and measured external gates.
3. Order independently verifiable tasks through local scripted execution, isolated provider integration, persistence/recovery and reproducible comparisons. Map requirements and failure modes to their owning task/checks.
4. Self-review coverage, type/interface consistency, safety/cost boundaries and worker handoff context. Prepare a coherent plan for user review, preserving the existing coding-agent requirements.
5. On approved completion, transfer the executable plan/rationale/open gates to a durable implementation guide and decision log, remove this temporary planning document and repair references. Refresh the existing blueprint only at that phase boundary, then update/verify QMD and the code graph.

## Scope and stopping rule

The plan ends at the standalone agent capability and evaluation/report handoff. It does not invent backend routes, redesign approved agent behavior, claim live compatibility/safety or authorize coding. Exact built identities and enforcement are verified in bounded implementation tasks before dependent capabilities; unsupported controls stop those capabilities. Further architecture discussion is needed only if implementation evidence contradicts an approved contract.

## Review and evidence

Pending repository/specification audit. Record consequential implementation proposals and official-source checks here as they arise; the user has not yet approved a file layout, dependency lock, implementation sequence or execution start for this plan.
