# technician-app

Technician mobile app (React Native + Expo SDK 58 + TypeScript).
Initialised in **Phase 6**. Planned layout:

```
src/
  screens/      Login, LanguageSelect, Home, Record, TranscriptReview, FollowUp,
                WorkOrderPreview, MyTasks, TaskDetail, Checklist, ProgressUpdate, Handover
  navigation/   root stack + bottom tabs
  components/   MicButton, RecordingIndicator, FieldRow, StatusChip, ...
  hooks/        useRecorder (expo-audio, 30 s cap), useAuth, usePlayer
  services/     api.ts, audio.ts (FormData upload), player.ts (TTS playback)
  types/
```
