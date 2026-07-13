# Tool-Selection Behavior per Model (from n8n execution data)

Called tools per interaction, scored against the minimal expected set.
'clean' = no-tool interaction answered without tools; datetime calls are not penalized.
Note: runs predate the v2.1 numCtx fix — #12 failures for qwen3 were context overflow, not selection.


## edge-llama32-1b-r2  (12 executions in window, 12/12 matched to harness by duration)

| # | expected | called | verdict |
|---|---|---|---|
| 1 | — | create_event | unneeded:create_event |
| 2 | — | — | clean [workflow-error] |
| 3 | — | current_datetime | clean |
| 4 | read_emails | read_emails | correct |
| 5 | read_emails | — | none called [workflow-error] |
| 6 | list_events | list_events | correct |
| 7 | create_event, read_emails | read_emails, current_datetime | partial (missing create_event) |
| 8 | create_task, read_emails | read_emails | partial (missing create_task) |
| 9 | — | create_event | unneeded:create_event |
| 10 | send_email | — | none called [workflow-error] |
| 11 | create_event | create_event | correct |
| 12 | list_tasks | list_tasks | correct |

**Selection score: 6/12**

## edge-llama32-3b-r2  (12 executions in window, 12/12 matched to harness by duration)

| # | expected | called | verdict |
|---|---|---|---|
| 1 | — | read_emails, list_events | unneeded:list_events,read_emails |
| 2 | — | read_emails | unneeded:read_emails |
| 3 | — | current_datetime | clean |
| 4 | read_emails | read_emails | correct |
| 5 | read_emails | read_emails | correct |
| 6 | list_events | list_events | correct |
| 7 | create_event, read_emails | read_emails, list_events | partial (missing create_event) |
| 8 | create_task, read_emails | list_tasks, read_emails, create_task | correct+extra:list_tasks |
| 9 | — | create_event | unneeded:create_event |
| 10 | send_email | send_email | correct |
| 11 | create_event | create_event | correct |
| 12 | list_tasks | list_tasks | correct |

**Selection score: 8/12**

## edge-qwen3-4b-r2  (12 executions in window, 12/12 matched to harness by duration)

| # | expected | called | verdict |
|---|---|---|---|
| 1 | — | — | clean |
| 2 | — | — | clean |
| 3 | — | — | clean |
| 4 | read_emails | read_emails | correct |
| 5 | read_emails | read_emails | correct |
| 6 | list_events | current_datetime, list_events | correct |
| 7 | create_event, read_emails | read_emails, list_events | partial (missing create_event) |
| 8 | create_task, read_emails | read_emails, create_task | correct |
| 9 | — | — | clean |
| 10 | send_email | — | none called |
| 11 | create_event | current_datetime, create_event | correct |
| 12 | list_tasks | list_tasks | correct |

**Selection score: 10/12**

## edge-smollm2-17b-r2  (12 executions in window, 12/12 matched to harness by duration)

| # | expected | called | verdict |
|---|---|---|---|
| 1 | — | list_tasks | unneeded:list_tasks |
| 2 | — | — | clean |
| 3 | — | — | clean |
| 4 | read_emails | read_emails | correct |
| 5 | read_emails | read_emails | correct |
| 6 | list_events | list_events | correct |
| 7 | create_event, read_emails | read_emails | partial (missing create_event) |
| 8 | create_task, read_emails | list_tasks | wrong (list_tasks) |
| 9 | — | — | clean |
| 10 | send_email | — | none called |
| 11 | create_event | — | none called [workflow-error] |
| 12 | list_tasks | list_tasks | correct |

**Selection score: 7/12**

## edge-gemma4-12b-r2  (12 executions in window, 12/12 matched to harness by duration)

| # | expected | called | verdict |
|---|---|---|---|
| 1 | — | — | clean |
| 2 | — | — | clean |
| 3 | — | — | clean |
| 4 | read_emails | read_emails | correct |
| 5 | read_emails | read_emails | correct |
| 6 | list_events | list_events | correct |
| 7 | create_event, read_emails | read_emails, list_events | partial (missing create_event) |
| 8 | create_task, read_emails | read_emails, create_task | correct |
| 9 | — | — | clean |
| 10 | send_email | read_emails, send_email | correct+extra:read_emails |
| 11 | create_event | create_event | correct |
| 12 | list_tasks | list_tasks | correct |

**Selection score: 11/12**

## Summary

| Model | correct/clean selections |
|---|---|
| edge-llama32-1b-r2 | 6/12 |
| edge-llama32-3b-r2 | 8/12 |
| edge-qwen3-4b-r2 | 10/12 |
| edge-smollm2-17b-r2 | 7/12 |
| edge-gemma4-12b-r2 | 11/12 |
