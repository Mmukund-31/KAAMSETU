# Device test (real phone, real microphone)

The automated harness (`e2e/`) proves the full chain with the app's real recorder in a browser. Only a phone can
prove the last mile: the phone's own microphone and encoder, Expo Go, Wi-Fi to the laptop, and the loudspeaker.
This checklist takes about 20 minutes. Fill in the Result column and keep the sheet with the submission.

## Setup

1. Laptop and phone(s) on the same Wi-Fi. Find the laptop's LAN IP: `ipconfig`, the IPv4 address of the Wi-Fi
   adapter (for example 192.168.1.20).
2. Backend reachable from the network:
   `cd backend ; .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8001`.
   Allow Python through the Windows firewall for private networks when asked. From the phone's browser,
   `http://<LAN-IP>:8001/health` should show `"status":"ok"`.
3. `technician-app/.env`: `EXPO_PUBLIC_API_URL=http://<LAN-IP>:8001`. Then `cd technician-app ; npx expo start`
   and scan the QR code with Expo Go (Android: the Expo Go app; iOS: the Camera app).
4. Supervisor console on the laptop: `cd supervisor-web ; npm run dev`, then http://localhost:5173.

## Checklist

| # | Step | Expected | Result (pass / fail / notes) |
|---|---|---|---|
| 1 | Sign in as `tech1@kaamsetu.demo` / `Kaamsetu@2026` | Language screen preselects Hinglish | |
| 2 | First mic tap | OS asks for microphone permission once; after "Allow", the timer runs | |
| 3 | Say the demo sentence (DEMO_SCRIPT.md) at arm's length, quiet room | Transcript within about 3–5 s, M-204 matched, production running, Timbre reply plays from the loudspeaker | |
| 4 | Same sentence in factory-like noise (fan, music, or a video of machinery) | Transcript usable, or a follow-up question for what was missed; note what Prisma heard | |
| 5 | Send report | Work-order number plus spoken acknowledgement; the order appears on the laptop | |
| 6 | Say only "Machine M-305 garam ho raha hai" | Follow-up about production; answer by voice: "band hai" | |
| 7 | Telugu: sign in as `tech2`, say "ఎం రెండు వందల నాలుగు మోటార్ లో వైబ్రేషన్ ఉంది, ప్రొడక్షన్ నడుస్తోంది" | M-204 matched from spoken Telugu numbers | |
| 8 | Hindi: sign in as `tech3`, say "मशीन एम दो सौ चार में तेल लीक है, उत्पादन चल रहा है" | M-204 matched, oil leak | |
| 9 | Speak for more than 30 s without stopping | Recorder stops itself just before 30 s and the report is processed | |
| 10 | Deny the microphone permission (OS settings), then tap the mic | "Mic ki permission chahiye…", typing works | |
| 11 | Laptop: approve and assign to tech2; phone (tech2): open My work | Task announced in Telugu, checklist steps, complete with the spoken confirmation | |
| 12 | Turn off the laptop's Wi-Fi for a moment, then send a typed report | "Server tak nahi pahunch paye", the text is kept; send again after reconnecting | |
| 13 | Spoken handover (Handover tab) | Transcript stored as the notes; summary shown | |

## After the test

- Report failures with what Prisma heard (the app shows the transcript) and the phone model and OS version.
- Run `cd e2e ; node run.mjs demo` if anything was changed, to confirm the automated chain still passes.
- Test records created on the phone stay in the dev DB. Reseed with `docker compose down -v ; docker compose up -d db`,
  then `alembic upgrade head` and `python scripts/seed.py`, or keep them as demo history.
