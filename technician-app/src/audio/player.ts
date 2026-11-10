import { createAudioPlayer, setAudioModeAsync, type AudioPlayer } from "expo-audio";
import { File, Paths } from "expo-file-system";
import { Platform } from "react-native";
import type { SpokenResponse } from "../types/api";

/**
 * Plays Gnani Timbre audio returned by the backend as base64.
 * Web uses a data: URI. On phones the audio is written to the cache directory first,
 * because data: URIs are not supported by the native players.
 * Only one clip plays at a time; a new clip stops the previous one.
 */

let current: { player: AudioPlayer; file: File | null } | null = null;

function extension(contentType: string): string {
  if (contentType.includes("mpeg") || contentType.includes("mp3")) return "mp3";
  if (contentType.includes("ogg")) return "ogg";
  return "wav";
}

export function stopPlayback(): void {
  if (!current) return;
  const { player, file } = current;
  current = null;
  try {
    player.pause();
    player.remove();
  } catch {
    // already released
  }
  try {
    file?.delete();
  } catch {
    // cache cleanup is best effort
  }
}

export async function playAudio(base64: string, contentType: string): Promise<void> {
  stopPlayback();
  let uri: string;
  let file: File | null = null;
  if (Platform.OS === "web") {
    uri = `data:${contentType};base64,${base64}`;
  } else {
    file = new File(Paths.cache, `kaamsetu-reply-${Date.now()}.${extension(contentType)}`);
    file.create({ overwrite: true });
    file.write(base64, { encoding: "base64" });
    uri = file.uri;
  }
  await setAudioModeAsync({ playsInSilentMode: true, allowsRecording: false }).catch(() => undefined);
  const player = createAudioPlayer({ uri });
  const entry = { player, file };
  current = entry;
  player.addListener("playbackStatusUpdate", (status) => {
    if (status.didJustFinish && current === entry) stopPlayback();
  });
  player.play();
}

/** Plays a spoken reply when Timbre produced audio. Returns false when only text is available. */
export async function playSpoken(response: SpokenResponse | null | undefined): Promise<boolean> {
  if (!response?.audio_base64 || !response.content_type) return false;
  try {
    await playAudio(response.audio_base64, response.content_type);
    return true;
  } catch {
    return false; // the text is always on screen, so a playback failure never blocks the flow
  }
}
