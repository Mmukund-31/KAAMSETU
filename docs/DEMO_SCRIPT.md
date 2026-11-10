# Demo Script (about 90 s)

A technician reports a motor fault by voice in Hinglish. A supervisor approves it and assigns it to a
Telugu-speaking technician, who hears the task, works the SOP checklist and completes it. The supervisor then closes
it. Every step uses the real backend, real Gnani Prisma and Timbre calls and real PostgreSQL rows.

This exact scenario is automated in `e2e/` (`node run.mjs demo`). The timings below are from that run, so the live
demo can be paced on measured numbers rather than guesses.

## Measured on the dev machine (2026-11-10, two runs)

| Step | Measured | What it includes |
|---|---|---|
| Stop recording → preview on screen | 2.4–2.9 s | upload of the `.m4a`, Prisma STT, extraction, register match, priority, Timbre reply |
| Send → work-order number and spoken acknowledgement | 1.1–1.5 s | re-validation, database write, audit rows, Timbre |
| Report visible in the supervisor's approval queue | 0.8–1.3 s in the runs | the queue polls every 15 s, so allow up to 15 s; "Refresh" on Overview is instant |
| Task appears in the assignee's list | under 1 s after opening the tab | the list also refreshes every 30 s and on pull-down |

Evidence of one run (WO-1034, removed afterwards):

- `work_order_evidence.prisma_request_id` = `01a1c671-9b79-79b9-a64b-38482242fda5`, and the transcript is stored
  verbatim: "motor ka pressure abnormal hai, bearing mein vibration aa raha hai, machine number M-204 hai,
  production abhi chal raha hai."
- Extracted: M-204 (register match), mechanical (from symptoms), bearing vibration and abnormal pressure, production
  running, priority high (`critical_equipment_fault`). Timbre voice Poorvi.
- `audit_logs`, seq 179–193:
  - create, then reported → under review (Ravi Kumar);
  - under review → approved, approved → assigned, checklist attached (Priya Sharma);
  - assigned → in progress, 7 checklist steps, in progress → completion review (Lakshmi Reddy);
  - completion review → closed (Priya Sharma).

## Script

| Time | Screen | Action and narration |
|---|---|---|
| 0–10 s | Title | "Maintenance teams run on phone calls and WhatsApp. Reports are incomplete, mixed-language and reach supervisors late." |
| 10–22 s | Phone, technician app (tech1, Hinglish) | Tap the mic and say: "Motor ka pressure abnormal hai. Bearing mein vibration aa raha hai. Machine number M-204 hai. Production abhi chal raha hai." Tap to stop. |
| 22–35 s | Phone | About 3 s later: the Timbre reply plays ("M-204 ke liye maintenance request taiyaar hai. Priority high hai…"). The preview shows M-204 Hydraulic Press Main Motor, symptoms, production running, priority high and why. "Gnani Prisma heard it; our rules structured it; it matched the register." |
| 35–45 s | Phone | Tap **Report bhejein**. The work-order number appears and Timbre confirms: "Request supervisor review ke liye submit kar di gayi hai." |
| 45–62 s | Laptop, supervisor console | The Approvals queue shows it (press Refresh if you do not want to wait for the 15 s poll). Open it: the verbatim transcript and the Prisma request id sit next to the structured order. **Approve**, then **Assign technician**, then Lakshmi (Telugu). "The SOP checklist is attached automatically." |
| 62–80 s | Second phone, tech2 (Telugu) | My work, then the task. The announcement is spoken in Telugu. **Start work**, tick the 7 steps (Complete stays locked until the mandatory ones are done), **Mark complete**; Timbre confirms in Telugu. |
| 80–90 s | Laptop | Approvals, Completion review, open the order, **Close work order**. The history shows every step. Overview: the closed count goes up. "Speak the work. Structure the action. Keep operations moving. Powered by Gnani Prisma and Timbre." |

Screenshots of each step from the automated run are in `docs/screenshots/` (`demo-02-preview.png` …
`demo-10-overview.png`).

## If something goes wrong on stage

All of these were triggered for real in `e2e/` (`node run.mjs errors`). The apps handle them, so carry on:

| Symptom | What the app does | What to say or do |
|---|---|---|
| Prisma busy (429) | "Speech service busy hai…", mic still there | Tap the mic again a few seconds later; it recovered on the next try in the test |
| Prisma down | "Speech service abhi uplabdh nahi hai. Aap type kar sakte hain." | Tap **Type karein**, type the sentence; the same pipeline runs without STT |
| Timbre down | Reply shown as text with "Awaaz mein jawab nahi mil paya" | Read the text; the work order is still created |
| Nothing heard (silence, mic too far) | "Koi awaaz nahi suni. Phone ke paas bolein." | Speak closer and try again |
| Machine misheard (for example M-240) | "Yeh code equipment register mein nahi hai" plus registered suggestions | Tap M-204 in the suggestions |
| Production not mentioned | One follow-up question with one-tap answers | Tap "Chal raha hai" or answer by voice |
| Double tap on Send | One request, one work order | Nothing to do |
| Laptop backend unreachable | "KAAMSETU server tak nahi pahunch paye…"; the typed text is kept | Fix the Wi-Fi, then tap Send again |

## Pre-demo checklist

- Docker Desktop running; `docker compose up -d db`; `python scripts/seed.py` (idempotent).
- Backend with the real key, reachable from the phones: `python -m uvicorn app.main:app --host 0.0.0.0 --port 8001`
  (allow it through the Windows firewall on the private network).
- `technician-app/.env`: `EXPO_PUBLIC_API_URL=http://<laptop-LAN-IP>:8001`, then `npx expo start`; both phones on
  the same Wi-Fi, in Expo Go, signed in as tech1 and tech2 with the language already chosen.
- Supervisor console `npm run dev`, signed in as `supervisor@kaamsetu.demo`, Approvals tab open.
- Phone volume up, silent switch off (iOS plays in silent mode, but volume still matters). Do one rehearsal report
  in the room to check the microphone distance in that noise level.
- Run `node e2e/run.mjs demo` the day before: it proves the whole chain on that machine in about 2 minutes and puts
  the database back as it was.
