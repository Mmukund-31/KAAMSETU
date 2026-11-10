import "@testing-library/react-native/matchers";

// ── native modules replaced with controllable fakes ─────────────────────

// expo-audio: a recorder whose duration the test can drive, and a player that records what was played.
jest.mock("expo-audio", () => {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const React = require("react");
  let snapshot = { durationMillis: 0, isRecording: false };
  const listeners = new Set<() => void>();
  const set = (patch: Partial<typeof snapshot>) => {
    snapshot = { ...snapshot, ...patch };
    listeners.forEach((l) => l());
  };
  const recorder = {
    uri: null as string | null,
    prepareToRecordAsync: jest.fn(async () => undefined),
    record: jest.fn(() => set({ isRecording: true })),
    stop: jest.fn(async () => {
      set({ isRecording: false });
      recorder.uri = "file:///cache/recording-1.m4a";
    }),
  };
  const played: string[] = [];
  return {
    __recorder: recorder,
    __set: set,
    __reset: () => {
      snapshot = { durationMillis: 0, isRecording: false };
      recorder.uri = null;
      played.length = 0;
    },
    __played: played,
    RecordingPresets: { HIGH_QUALITY: { extension: ".m4a", sampleRate: 44100, numberOfChannels: 2, bitRate: 128000 } },
    useAudioRecorder: () => recorder,
    // like the real hook: the component re-renders when the recorder status changes
    useAudioRecorderState: () =>
      React.useSyncExternalStore(
        (l: () => void) => {
          listeners.add(l);
          return () => listeners.delete(l);
        },
        () => snapshot,
      ),
    requestRecordingPermissionsAsync: jest.fn(async () => ({ granted: true })),
    setAudioModeAsync: jest.fn(async () => undefined),
    createAudioPlayer: jest.fn((source: { uri: string }) => {
      played.push(source.uri);
      return { play: jest.fn(), pause: jest.fn(), remove: jest.fn(), addListener: jest.fn() };
    }),
  };
});

jest.mock("expo-secure-store", () => {
  const store = new Map<string, string>();
  return {
    __store: store,
    getItemAsync: jest.fn(async (k: string) => store.get(k) ?? null),
    setItemAsync: jest.fn(async (k: string, v: string) => void store.set(k, v)),
    deleteItemAsync: jest.fn(async (k: string) => void store.delete(k)),
  };
});

jest.mock("expo-crypto", () => {
  let n = 0;
  return { randomUUID: jest.fn(() => `00000000-0000-4000-8000-${String(++n).padStart(12, "0")}`) };
});

jest.mock("expo-file-system", () => {
  class File {
    uri: string;
    written: string | null = null;
    constructor(dir: { uri: string }, name: string) {
      this.uri = `${dir.uri}/${name}`;
    }
    create() {}
    write(content: string) {
      this.written = content;
    }
    delete() {}
  }
  return { File, Paths: { cache: { uri: "file:///cache" } } };
});

afterEach(() => {
  jest.clearAllMocks();
});
