import { Platform } from "react-native";

/**
 * Backend URL. EXPO_PUBLIC_API_URL is inlined at build time; set it in technician-app/.env.
 * Defaults: Android emulator reaches the host as 10.0.2.2, web and iOS simulator use localhost.
 * A real phone needs the dev machine's LAN IP (and the backend started with --host 0.0.0.0).
 */
function defaultBaseUrl(): string {
  if (Platform.OS === "android") return "http://10.0.2.2:8001";
  return "http://localhost:8001";
}

export const API_BASE_URL = (process.env.EXPO_PUBLIC_API_URL || defaultBaseUrl()).replace(/\/$/, "");

/** Prisma accepts at most 30 seconds per request; the recorder stops itself at this limit. */
export const MAX_RECORDING_SECONDS = 30;
