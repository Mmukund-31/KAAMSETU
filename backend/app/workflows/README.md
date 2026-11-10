# workflows/

- `orchestrator.py` validate extraction, resolve equipment, decide next action (follow-up / preview / fix equipment)
- `work_order.py`   create work order from a confirmed draft (re-validates server-side, writes evidence + audit)
- `assignment.py`   assign / reassign technicians
- `escalation.py`   SLA due dates, overdue detection, manual escalation

All state changes go through `services/state_machine.py`. Implemented in Phases 3–4.
