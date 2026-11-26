# Triage Labels Configuration

The following labels are used for issue triage and agent workflow. These are the
canonical labels used by the `triage` skill to route issues to the appropriate
workflow.

## Label Definitions

### `needs-triage`
Issue has been triaged and needs assignment to a development track.
Use when: New issues have been acknowledged but not yet prioritized.

### `needs-info`
Issue requires additional information from the reporter or stakeholders.
Use when: The issue description is incomplete or ambiguous.

### `ready-for-agent`
Issue is ready for agent implementation with clear requirements.
Use when: All information is available and the issue can be picked up by an agent.

### `ready-for-human`
Issue requires human judgment or creative problem-solving.
Use when: The solution involves design decisions, prioritization, or UX considerations.

### `wontfix`
Issue will not be addressed.
Use when: The issue is not actionable, a duplicate, or out of scope.

## Default Usage

These labels match the default triage vocabulary. If your issue tracker
already uses different label names, update this file to map the existing
labels to the triage roles.