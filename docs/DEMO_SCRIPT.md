# Demo Script (60-90 s)

Scenario: a factory technician reports a motor fault in Hinglish. Every step uses
the real backend, real Gnani calls and persisted database rows. Nothing is mocked.

| Time | Screen | Action / narration |
|---|---|---|
| 0-10 s | Title + factory floor still | "Maintenance teams run on calls and WhatsApp. Reports get lost, language gets in the way, supervisors see problems late." |
| 10-25 s | Technician app | Login as tech1, language: Hinglish, tap mic, say: "Motor ka pressure abnormal hai. Bearing mein vibration aa raha hai. Machine number M-204 hai. Production abhi chal raha hai." |
| 25-40 s | Technician app | Prisma transcript appears (show `request_id` badge). Extracted panel: Equipment M-204 registered; Category Mechanical; Symptoms bearing vibration, abnormal pressure; Production running; Priority High. |
| 40-55 s | Technician app | Timbre speaks: "M-204 ke liye maintenance request taiyaar hai. Supervisor review ke liye submit karein?" Tap Confirm. "Request supervisor review ke liye submit ho gayi hai." Work order ID shown. |
| 55-75 s | Supervisor web | Approvals queue shows the new request within seconds. Open it: transcript vs extracted side by side. Approve, then assign to tech2. Audit timeline updates. |
| 75-90 s | Both | Tech2 sees the task, opens the approved checklist, completes it, reports completion; supervisor closes. Overview dashboard counts change. Close: "Speak the work. Structure the action. Keep operations moving. Powered by Gnani Prisma and Timbre." |

Pre-demo checklist: Docker DB up; backend running with real key; seed loaded; phone and
laptop on same LAN; dashboard refresh interval 15 s; volume up for Timbre playback.
