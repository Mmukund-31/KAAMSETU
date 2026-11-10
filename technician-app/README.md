# technician-app

The KAAMSETU technician app (React Native 0.88, Expo SDK 58, TypeScript, expo-audio, expo-secure-store,
React Navigation 7, TanStack Query 5). Voice-first: a technician reports a fault by speaking, answers any follow-up
question, checks the preview and sends it. They then receive and carry out assigned work, with the SOP checklist and
a spoken handover at the end of the shift. Technicians only; supervisors use `supervisor-web`.

## Run

```powershell
# 1. backend reachable from the phone: listen on all interfaces (Windows may ask to allow it through the firewall)
cd backend ; .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8001

# 2. app
cd technician-app
npm install
Copy-Item .env.example .env      # set EXPO_PUBLIC_API_URL=http://<your-LAN-IP>:8001 for a real phone
npx expo start                   # scan the QR code with Expo Go (same Wi-Fi)
```

`EXPO_PUBLIC_API_URL` is inlined at build time. Without it, Android uses `http://10.0.2.2:8001` (emulator host) and
web and the iOS simulator use `http://localhost:8001`. For the web preview (`npx expo start --web`, port 8081), the
backend's default `CORS_ORIGINS` already includes `http://localhost:8081`.

| Command | What it does |
|---|---|
| `npx expo start` | dev server for Expo Go, an emulator or web |
| `npm test` | Jest (jest-expo) + React Native Testing Library 14, native modules mocked |
| `npm run typecheck` | `tsc --noEmit`, strict |
| `npm run export:web` | static web build in `dist/` |
| `npm run export:native` | Android and iOS Hermes bundles in `dist-native/` (proves the native bundle compiles) |

Demo sign-in: `tech1@kaamsetu.demo` (Hinglish), `tech2@kaamsetu.demo` (Telugu), `tech3@kaamsetu.demo` (Hindi),
password `Kaamsetu@2026` (synthetic seed accounts).

## Screens

| Screen | What happens | API |
|---|---|---|
| Sign in | technicians only. The token is stored in the iOS Keychain or Android Keystore (expo-secure-store) | `/auth/login`, `/auth/me` |
| Language | chosen once per device, preselected from the account. It sets the Prisma language, the Timbre voice and the UI labels | — |
| Report | tap the mic, speak (stops itself at 30 s), or type instead | `/voice/process-report`, `/voice/process-text` |
| Review | KAAMSETU's reply as text and Timbre audio, plus what you said, with "correct the text". Then one of three things: pick a registered machine, answer the follow-up (one-tap production choice, voice, or text), or check the preview | `/voice/process-text` (correction), `/voice/follow-up`, `/voice/evaluate-draft` |
| Preview → Send | edit the description, symptoms, production, safety and location; the priority is shown with its rule explanation. Send uses one idempotency key per report, so a double tap or a retry never creates two orders | `POST /work-orders` |
| My work | assigned open work, priority order, refresh every 30 s and on pull-down; also "my reports" | `/work-orders?mine=true` |
| Task | the task announcement shown and spoken in the technician's language; start, blocked or waiting for parts (reason), SOP checklist (done, or N/A / failed with a note), complete (blocked until the mandatory steps are done) with a spoken confirmation | `/work-orders/{id}`, `/status`, `/complete`, `/checklists/{id}/items/{item}`, `/voice/synthesize` |
| Handover | spoken (Prisma transcript stored verbatim) or typed notes; shows the record-based summary | `/handovers/voice`, `/handovers` |
| Profile | language switch, server address, sign out | — |

## Audio

- **Recording:** `expo-audio`, AAC in MPEG-4 (`.m4a`), mono, 64 kbit/s, capped at 30 s, which is Prisma's limit per
  request. Microphone permission is asked on first use. If it is refused, the app explains and offers typing.
- **Web preview:** recording uses `MediaRecorder` with `audio/mp4;codecs=mp4a.40.2`, the same AAC/MP4 as phones.
  Browsers that can only record WebM get "recording not available, you can type instead", because Prisma and the
  backend do not accept WebM.
- **Playback:** Timbre audio arrives as base64. On phones it is written to the cache directory and played with
  `createAudioPlayer`. On web it plays from a `data:` URI. One clip plays at a time. Every reply is also on screen,
  so a speech failure never blocks the flow.
- The app never talks to Gnani. It has no Gnani key; the backend makes every Prisma and Timbre call.

## Layout

```
App.tsx                      providers + navigation
src/
  lib/          api.ts (fetch wrapper, ApiError, 401), config.ts (API URL, 30 s), storage.ts (secure store), i18n.ts
  types/        api.ts, which mirrors backend/app/schemas
  services/     index.ts, one function per endpoint (multipart uploads included)
  audio/        useRecorder.ts, recording.ts (FormData part), player.ts (Timbre playback)
  auth/         SessionContext.tsx (session restore, technician-only, language, t())
  report/       useReportFlow.ts (idle → processing → review → submitting → submitted)
  screens/      Report, Tasks, TaskDetail, Handover, Auth (login, language, profile)
  navigation/   RootNavigator.tsx (sign-in → language → tabs; tasks stack)
  components/   ui.tsx (Button, Card, Field, Chip, badges, ErrorBanner, SpokenReply), MicButton.tsx
  test/         setup.ts (native module fakes), harness.tsx (fetch route table, fixtures), *.test.ts(x)
```

The interface text is in English, Hinglish, Hindi and Telugu (`src/lib/i18n.ts`). Hindi and Telugu were written for
this prototype and need review by native speakers before a pilot.
