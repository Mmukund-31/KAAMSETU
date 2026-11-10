import * as SecureStore from "expo-secure-store";
import { Platform } from "react-native";

/**
 * Small key-value storage. On iOS and Android values go to the OS keychain / keystore (expo-secure-store).
 * The web preview has no secure store, so it falls back to localStorage, which is acceptable for development only.
 */
export const storage = {
  async get(key: string): Promise<string | null> {
    try {
      if (Platform.OS === "web") return globalThis.localStorage?.getItem(key) ?? null;
      return await SecureStore.getItemAsync(key);
    } catch {
      return null;
    }
  },
  async set(key: string, value: string | null): Promise<void> {
    try {
      if (Platform.OS === "web") {
        if (value === null) globalThis.localStorage?.removeItem(key);
        else globalThis.localStorage?.setItem(key, value);
        return;
      }
      if (value === null) await SecureStore.deleteItemAsync(key);
      else await SecureStore.setItemAsync(key, value);
    } catch {
      // storage unavailable: the session lasts until the app closes
    }
  },
};

export const KEYS = {
  token: "kaamsetu.token",
  language: "kaamsetu.language",
} as const;
