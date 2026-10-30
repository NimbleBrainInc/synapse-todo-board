# Task Triage

Help classify, prioritize, and organize tasks during a requested review.

## When to Use

Use this guidance when the person requests triage or an explicitly configured host workflow
invokes it. The server does not install an automatic event hook or daily scheduler.

- Review a new task's priority and possible due date.
- Review a column change and its completion state.
- Review overdue work, stalled tasks, and WIP limits across the requested boards.

Use the current selected board from visible state and the flat arguments in the root tool guide.
Saved changes are shared with the UI through MCP resource-list notifications.

## Process

### Step 1 — Review New Tasks

During a requested review, analyze the title and description of tasks with priority set to "none"
and suggest a priority level. Explain the reason before making an agreed change.

Look for signals of urgency: mentions of deadlines, blockers, production issues, customer-facing problems, or time-sensitive language like "ASAP", "before launch", or "breaking". These warrant critical or high priority.

Routine or exploratory work — research spikes, documentation updates, minor refactors, nice-to-haves — should receive medium or low priority.

If the text is ambiguous and you cannot confidently assign a priority, leave it as "none" and ask the user. A wrong priority is worse than no priority because it erodes trust in the triage system.

### Step 2 — Suggest Due Dates

When a task has no due date, infer a reasonable one from the combination of priority and effort.

A critical task with trivial or small effort should be due today or tomorrow. The whole point of critical priority is that it demands immediate attention, and if the work is small there is no reason to delay.

A high priority task with medium effort should be due within three days. This gives enough room to do the work well without letting it drift.

Everything else should default to within one week. Tasks without urgency signals still benefit from a deadline to prevent them from languishing forever.

Never silently set a due date. Always suggest the date and let the user confirm or adjust. People have context about their schedules that the triage system does not.

### Step 3 — Column-Move Side Effects

Use `move_task` for column changes. The tool sets `completed_at` when the destination column key
contains "done", "complete", or "closed", and clears it when moving out of a done-like column.
Do not duplicate those changes with a second raw task update.

If the board has an archive policy, consider archiving the task after completion. Completed tasks that sit in done columns clutter the board and make it harder to see active work.

### Step 4 — Board Review

Review the requested boards when asked. A daily review needs an explicitly configured host
schedule; the app does not create one. The review covers three concerns.

First, flag overdue tasks. Any task where the due date is earlier than today and completed_at is not set is overdue. Surface these prominently so the user can decide whether to push the date, reprioritize, or get them done.

Second, identify stalled tasks. A task that has sat in the same column for more than three days without any update may be blocked, forgotten, or poorly scoped. Flag these for the user to investigate.

Third, check WIP limits. When a column has more tasks than its WIP limit allows, suggest that the user move or defer tasks to restore flow. Exceeding WIP limits is a signal that work is being started faster than it is being finished.

## Decision Criteria

| Signal | Action |
|--------|--------|
| New task with priority set to none | Analyze title and description, suggest an appropriate priority |
| New task with no due date | Suggest a due date based on the priority and effort combination |
| Task moved to a column whose key contains done, complete, or closed | Set completed_at to now and consider archiving |
| Task moved out of a done-like column to an active column | Clear completed_at |
| Task with due date earlier than today and no completed_at | Flag as overdue in the daily review |
| Column task count exceeds wip_limit | Warn the user and suggest moving or deferring tasks |
| Task unchanged in the same column for more than three days | Flag as potentially stalled in the daily review |
| Priority cannot be confidently determined from title and description | Leave as none and ask the user rather than guessing |

## Rules

Never delete tasks. If a task is no longer relevant, archive it. Deletion destroys history and makes it impossible to understand what happened on a board over time.

Never change a task's priority without telling the user why. Every priority change should come with a brief explanation of what signal triggered it. Silent priority changes undermine the user's sense of control.

Keep task titles actionable by starting with a verb. "Fix login timeout" is better than "Login timeout issue". "Write API documentation" is better than "API docs". Verb-first titles make it immediately clear what needs to happen.

Respect WIP limits by warning rather than silently blocking. WIP limits are guardrails, not walls. The user may have a legitimate reason to exceed them temporarily. Surface the violation clearly and let the user decide.
