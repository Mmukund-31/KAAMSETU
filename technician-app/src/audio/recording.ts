import { Platform } from "react-native";

/** A finished recording, ready to upload. */
export interface Recording {
  uri: string;
  /** e.g. audio/m4a. Phones record AAC in an MPEG-4 container (.m4a). */
  mimeType: string;
  name: string;
  durationSeconds: number;
}

/**
 * Adds a recording to multipart form data.
 * Native: React Native's FormData reads the file from {uri, name, type}.
 * Web: the recorder returns a blob: URL, so the blob itself is appended.
 * The backend detects the format from the file's bytes, not from the name or type.
 */
export async function appendRecording(form: FormData, field: string, recording: Recording): Promise<void> {
  if (Platform.OS === "web") {
    const blob = await (await fetch(recording.uri)).blob();
    form.append(field, blob, recording.name);
    return;
  }
  form.append(field, { uri: recording.uri, name: recording.name, type: recording.mimeType } as unknown as Blob);
}
