import { Ionicons } from "@expo/vector-icons";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useSession } from "../auth/SessionContext";
import { MAX_RECORDING_SECONDS } from "../lib/config";
import { colors } from "./ui";

/** One large target: tap to start, tap again to stop. Shows elapsed seconds against the 30 s limit. */
export function MicButton({
  recording,
  seconds,
  disabled,
  onPress,
  size = 150,
  testID = "mic-button",
}: {
  recording: boolean;
  seconds: number;
  disabled?: boolean;
  onPress: () => void;
  size?: number;
  testID?: string;
}) {
  const { t } = useSession();
  const label = recording ? t("tapToStop") : t("tapToSpeak");
  return (
    <View style={styles.wrap}>
      <Pressable
        testID={testID}
        accessibilityRole="button"
        accessibilityLabel={label}
        accessibilityState={{ disabled: !!disabled }}
        disabled={disabled}
        onPress={onPress}
        style={({ pressed }) => [
          styles.button,
          { width: size, height: size, borderRadius: size / 2 },
          recording && styles.recording,
          disabled && { opacity: 0.4 },
          pressed && { transform: [{ scale: 0.97 }] },
        ]}
      >
        <Ionicons name={recording ? "stop" : "mic"} size={size * 0.42} color="#fff" />
      </Pressable>
      <Text style={styles.caption}>{label}</Text>
      {recording ? (
        <Text style={styles.timer} accessibilityLiveRegion="polite">
          {t("recordingSeconds", { s: seconds, max: MAX_RECORDING_SECONDS })}
        </Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { alignItems: "center", marginVertical: 16 },
  button: { backgroundColor: colors.primary, alignItems: "center", justifyContent: "center", elevation: 3 },
  recording: { backgroundColor: colors.danger },
  caption: { marginTop: 12, fontSize: 18, fontWeight: "700", color: colors.ink },
  timer: { marginTop: 4, fontSize: 16, color: colors.danger, fontWeight: "600" },
});
