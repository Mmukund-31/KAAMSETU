import {
  RecordingPresets,
  requestRecordingPermissionsAsync,
  setAudioModeAsync,
  useAudioRecorder,
  useAudioRecorderState,
  type RecordingOptions,
} from "expo-audio";
import { useCallback, useEffect, useRef, useState } from "react";
import { Platform } from "react-native";
import { MAX_RECORDING_SECONDS } from "../lib/config";
import type { Recording } from "./recording";

/** Web recording must produce AAC in MP4 (the same as phones): the backend and Prisma do not take WebM. */
export function webMimeType(): string | null {
  if (Platform.OS !== "web") return null;
  const recorder = (globalThis as { MediaRecorder?: { isTypeSupported(t: string): boolean } }).MediaRecorder;
  if (!recorder) return null;
  for (const type of ["audio/mp4;codecs=mp4a.40.2", "audio/mp4"]) {
    if (recorder.isTypeSupported(type)) return type;
  }
  return null;
}

// AAC in MPEG-4 (.m4a), mono: speech needs one channel and the upload stays small.
const OPTIONS: RecordingOptions = {
  ...RecordingPresets.HIGH_QUALITY,
  numberOfChannels: 1,
  bitRate: 64000,
  web: { mimeType: webMimeType() ?? "audio/mp4", bitsPerSecond: 64000 },
};

/** When the recorder stops itself (29.5 s): inside Prisma's 30 s limit after stop latency. */
export const AUTO_STOP_MILLIS = (MAX_RECORDING_SECONDS - 0.5) * 1000;

export type RecorderError ="mic_denied" | "mic_unavailable" | "too_short";

export interface RecorderApi {
  supported: boolean;
  isRecording: boolean;
  seconds: number;
  error: RecorderError | null;
  start: () => Promise<boolean>;
  /** Stops and returns the file, or null if nothing usable was recorded. */
  stop: () => Promise<Recording | null>;
  cancel: () => Promise<void>;
}

export function useRecorder(onAutoStop?: (recording: Recording | null) => void): RecorderApi {
  const recorder = useAudioRecorder(OPTIONS);
  const state = useAudioRecorderState(recorder, 200);
  const [error, setError] = useState<RecorderError | null>(null);
  const [active, setActive] = useState(false);
  const stopping = useRef(false);
  const supported = Platform.OS !== "web" || webMimeType() !== null;

  const start = useCallback(async () => {
    setError(null);
    if (!supported) {
      setError("mic_unavailable");
      return false;
    }
    try {
      const permission = await requestRecordingPermissionsAsync();
      if (!permission.granted) {
        setError("mic_denied");
        return false;
      }
      await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
      await recorder.prepareToRecordAsync();
      recorder.record();
      stopping.current = false;
      setActive(true);
      return true;
    } catch {
      setError("mic_unavailable");
      return false;
    }
  }, [recorder, supported]);

  const stop = useCallback(async (): Promise<Recording | null> => {
    if (stopping.current) return null;
    stopping.current = true;
    const seconds = (state.durationMillis ?? 0) / 1000;
    try {
      await recorder.stop();
    } finally {
      setActive(false);
      // Back to playback mode so spoken replies use the loudspeaker on iOS.
      await setAudioModeAsync({ allowsRecording: false, playsInSilentMode: true }).catch(() => undefined);
    }
    const uri = recorder.uri;
    if (!uri) {
      setError("mic_unavailable");
      return null;
    }
    if (seconds > 0 && seconds < 0.5) {
      setError("too_short");
      return null;
    }
    return { uri, mimeType: "audio/m4a", name: "report.m4a", durationSeconds: seconds };
  }, [recorder, state.durationMillis]);

  const cancel = useCallback(async () => {
    stopping.current = true;
    if (active) await recorder.stop().catch(() => undefined);
    setActive(false);
    await setAudioModeAsync({ allowsRecording: false, playsInSilentMode: true }).catch(() => undefined);
  }, [active, recorder]);

  // Prisma takes at most 30 s per request. Stopping takes a moment and the status is polled every 200 ms,
  // so stop half a second early: a file that ends up longer than 30 s would be refused.
  const millis = state.durationMillis ?? 0;
  const seconds = Math.floor(millis / 1000);
  const limitReached = millis >= AUTO_STOP_MILLIS;
  useEffect(() => {
    if (active && limitReached) {
      void stop().then((r) => onAutoStop?.(r));
    }
  }, [active, limitReached, stop, onAutoStop]);

  return { supported, isRecording: active, seconds: active ? seconds : 0, error, start, stop, cancel };
}
