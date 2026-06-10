/** Module-level monotonic counters.  NOT run-scoped. */
export let runCounter = 0;
export let messageCounter = 0;
export let todoCounter = 0;
export let toolCallCounter = 0;
export let artifactCounter = 0;
export let approvalCounter = 0;

export function nextRunId(): string { return `run_${++runCounter}`; }
export function nextMessageId(): string { return `msg_${++messageCounter}`; }
export function nextTodoId(): string { return `todo_${++todoCounter}`; }
export function nextToolCallId(): string { return `tc_${++toolCallCounter}`; }
export function nextArtifactId(): string { return `art_${++artifactCounter}`; }
export function nextApprovalId(): string { return `approval_${++approvalCounter}`; }
