# Demo video: shot list (60–90 s)

For recording the submission video. The narration and timing follow `docs/DEMO_SCRIPT.md`; this page is what to
point the camera at. Every shot has a matching screenshot in `docs/screenshots/` from the automated run, so the
frames can be checked in advance.

## Setup

- Laptop screen recording (1920×1080, browser at 100%) for the console; a phone screen recording, or a second
  camera on the phone, for the technician app.
- Phone volume high: the Timbre replies are part of the story. Record room audio or the phone's internal audio.
- Seeded database, both technicians signed in with their languages chosen, the console on **Approvals**.
- One rehearsal report first, to check microphone distance in the room.

## Shots

| # | Time | Device | Shot | Reference |
|---|---|---|---|---|
| 1 | 0–8 s | title card | "KAAMSETU: speak the work, structure the action." Factory photo or plain card | — |
| 2 | 8–20 s | phone (tech1) | Report screen, tap the mic, speak the Hinglish M-204 sentence, tap to stop | `demo-01-report-home.png` |
| 3 | 20–32 s | phone | Spoken reply plays; the preview shows M-204, symptoms, production running and priority high with its reason | `demo-02-preview.png` |
| 4 | 32–40 s | phone | Tap **Report bhejein**; the work-order number and spoken acknowledgement | `demo-03-submitted.png` |
| 5 | 40–48 s | laptop | Approvals queue shows the new order | `demo-04-approvals.png` |
| 6 | 48–58 s | laptop | Detail: verbatim transcript, Prisma request id, structured order side by side; **Approve**, **Assign technician** → Lakshmi (Telugu) | `demo-05-detail.png` |
| 7 | 58–70 s | phone (tech2) | Task opens, the Telugu announcement plays; **Start work**; tick the checklist | `demo-06-task-telugu.png`, `demo-07-checklist.png` |
| 8 | 70–78 s | phone | **Mark complete**; Telugu spoken confirmation | `demo-08-complete.png` |
| 9 | 78–86 s | laptop | Completion review → **Close work order**; history timeline; Overview counts | `demo-09-closed.png`, `demo-10-overview.png` |
| 10 | 86–90 s | end card | "Powered by Gnani Prisma and Timbre." Repository link | — |

Optional 10-second insert for resilience: Timbre turned off, with the reply shown as text and the work continuing
(`err-07-tts-down.png`), or the "speech service busy" message (`err-05-busy.png`).

## What to keep honest on camera

- Say it is synthetic demo data (the seed) and a prototype.
- If the live report misses a field, let the follow-up question happen. It is the designed behaviour, and it
  shows the app asking instead of guessing.
