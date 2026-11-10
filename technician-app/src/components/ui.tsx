import { useEffect, useRef, type ReactNode } from "react";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
  type TextInputProps,
  type ViewStyle,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { playSpoken } from "../audio/player";
import { useSession } from "../auth/SessionContext";
import { errorKey, priorityLabel, statusLabel } from "../lib/i18n";
import { ApiError } from "../lib/api";
import type { Language, Priority, SpokenResponse, WorkOrderStatus } from "../types/api";

// Field use: large targets (>= 52 px), strong contrast, colour never the only signal.
export const colors = {
  ink: "#0f172a",
  muted: "#475569",
  faint: "#94a3b8",
  line: "#e2e8f0",
  surface: "#ffffff",
  background: "#f1f5f9",
  primary: "#0f766e",
  primaryDark: "#115e59",
  primarySoft: "#ccfbf1",
  danger: "#b91c1c",
  dangerSoft: "#fee2e2",
  warning: "#92400e",
  warningSoft: "#fef3c7",
};

export function Screen({ children, scroll = true }: { children: ReactNode; scroll?: boolean }) {
  return (
    <SafeAreaView style={styles.screen} edges={["top", "left", "right"]}>
      {scroll ? (
        <ScrollView contentContainerStyle={styles.screenContent} keyboardShouldPersistTaps="handled">
          {children}
        </ScrollView>
      ) : (
        <View style={[styles.screenContent, { flex: 1 }]}>{children}</View>
      )}
    </SafeAreaView>
  );
}

export function Title({ children }: { children: ReactNode }) {
  return (
    <Text style={styles.title} accessibilityRole="header">
      {children}
    </Text>
  );
}

export function Muted({ children, style }: { children: ReactNode; style?: object }) {
  return <Text style={[styles.muted, style]}>{children}</Text>;
}

export function Card({ children, style }: { children: ReactNode; style?: ViewStyle }) {
  return <View style={[styles.card, style]}>{children}</View>;
}

export function Label({ children }: { children: ReactNode }) {
  return <Text style={styles.label}>{children}</Text>;
}

type Variant = "primary" | "secondary" | "danger" | "ghost";

export function Button({
  label,
  onPress,
  variant = "primary",
  disabled,
  loading,
  testID,
  style,
}: {
  label: string;
  onPress: () => void;
  variant?: Variant;
  disabled?: boolean;
  loading?: boolean;
  testID?: string;
  style?: ViewStyle;
}) {
  const inactive = disabled || loading;
  return (
    <Pressable
      testID={testID}
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ disabled: !!inactive, busy: !!loading }}
      disabled={inactive}
      onPress={onPress}
      style={({ pressed }) => [
        styles.button,
        styles[`button_${variant}`],
        pressed && !inactive && { opacity: 0.85 },
        inactive && styles.buttonDisabled,
        style,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={variant === "primary" || variant === "danger" ? "#fff" : colors.primary} />
      ) : (
        <Text style={[styles.buttonText, styles[`buttonText_${variant}`]]}>{label}</Text>
      )}
    </Pressable>
  );
}

export function Field({ label, ...props }: { label: string } & TextInputProps) {
  return (
    <View style={{ marginBottom: 12 }}>
      <Label>{label}</Label>
      <TextInput
        accessibilityLabel={label}
        placeholderTextColor={colors.faint}
        style={[styles.input, props.multiline && { minHeight: 96, textAlignVertical: "top" }]}
        {...props}
      />
    </View>
  );
}

export function Chip({
  label,
  selected,
  onPress,
  testID,
}: {
  label: string;
  selected?: boolean;
  onPress?: () => void;
  testID?: string;
}) {
  return (
    <Pressable
      testID={testID}
      accessibilityRole={onPress ? "button" : "text"}
      accessibilityState={{ selected: !!selected }}
      accessibilityLabel={label}
      onPress={onPress}
      disabled={!onPress}
      style={[styles.chip, selected && styles.chipSelected]}
    >
      <Text style={[styles.chipText, selected && styles.chipTextSelected]}>{label}</Text>
    </Pressable>
  );
}

export function Row({ children, style }: { children: ReactNode; style?: ViewStyle }) {
  return <View style={[styles.row, style]}>{children}</View>;
}

const STATUS_TONE: Partial<Record<WorkOrderStatus, "warn" | "danger" | "ok" | "info">> = {
  under_review: "warn",
  assigned: "info",
  in_progress: "ok",
  blocked: "danger",
  awaiting_parts: "warn",
  completion_review: "warn",
  escalated: "danger",
  reopened: "warn",
};

export function StatusBadge({ status, language }: { status: WorkOrderStatus; language: Language }) {
  const tone = STATUS_TONE[status] ?? "neutral";
  return <Badge text={statusLabel(language, status)} tone={tone} />;
}

export function PriorityBadge({ priority, language }: { priority: Priority; language: Language }) {
  const tone = priority === "critical" || priority === "high" ? "danger" : priority === "medium" ? "warn" : "neutral";
  return <Badge text={priorityLabel(language, priority)} tone={tone} strong={priority === "critical"} />;
}

export function Badge({
  text,
  tone = "neutral",
  strong,
}: {
  text: string;
  tone?: "neutral" | "warn" | "danger" | "ok" | "info";
  strong?: boolean;
}) {
  const palette = {
    neutral: [colors.background, colors.muted],
    warn: [colors.warningSoft, colors.warning],
    danger: [strong ? colors.danger : colors.dangerSoft, strong ? "#fff" : colors.danger],
    ok: [colors.primarySoft, colors.primaryDark],
    info: ["#e0f2fe", "#075985"],
  }[tone];
  return (
    <View style={[styles.badge, { backgroundColor: palette[0] }]}>
      <Text style={[styles.badgeText, { color: palette[1] }]}>{text}</Text>
    </View>
  );
}

/** Error in the technician's language, with the server message for anything unexpected. */
export function ErrorBanner({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const { t } = useSession();
  if (!error) return null;
  const code = error instanceof ApiError ? error.code : typeof error === "string" ? error : undefined;
  const key = errorKey(code);
  const detail = key === "err_generic" && error instanceof ApiError ? error.message : null;
  return (
    <View style={styles.error} accessibilityRole="alert" testID="error-banner">
      <Text style={styles.errorText}>{t(key)}</Text>
      {detail ? <Text style={[styles.errorText, { fontSize: 14, marginTop: 4 }]}>{detail}</Text> : null}
      {onRetry ? <Button label={t("retry")} variant="secondary" onPress={onRetry} style={{ marginTop: 10 }} /> : null}
    </View>
  );
}

/**
 * Shows KAAMSETU's reply as text and plays the Timbre audio once when it arrives.
 * The text is always visible: a speech failure never hides the information.
 */
export function SpokenReply({ response, autoPlay = true }: { response: SpokenResponse | null | undefined; autoPlay?: boolean }) {
  const { t } = useSession();
  const played = useRef<string | null>(null);
  useEffect(() => {
    if (!autoPlay || !response?.audio_base64) return;
    const id = response.gnani_request_id ?? response.text;
    if (played.current === id) return;
    played.current = id;
    void playSpoken(response);
  }, [response, autoPlay]);
  if (!response) return null;
  return (
    <View style={styles.reply} testID="spoken-reply">
      <Text style={styles.replyText}>{response.text}</Text>
      {response.audio_base64 ? (
        <Pressable accessibilityRole="button" onPress={() => void playSpoken(response)} style={styles.replyButton}>
          <Text style={styles.replyButtonText}>▶ {t("playAgain")}</Text>
        </Pressable>
      ) : response.tts_available === false ? (
        <Text style={styles.replyNote}>{t("voiceUnavailable")}</Text>
      ) : null}
    </View>
  );
}

export function Loading() {
  const { t } = useSession();
  return (
    <View style={{ padding: 32, alignItems: "center" }} accessibilityRole="progressbar">
      <ActivityIndicator color={colors.primary} size="large" />
      <Muted style={{ marginTop: 8 }}>{t("loading")}</Muted>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  screenContent: { padding: 16, paddingBottom: 40 },
  // Telugu and Devanagari need extra line height or the top strokes are clipped
  title: { fontSize: 24, lineHeight: 34, fontWeight: "700", color: colors.ink, marginBottom: 6, paddingTop: 2 },
  muted: { fontSize: 16, color: colors.muted, lineHeight: 22 },
  label: { fontSize: 13, fontWeight: "600", color: colors.muted, textTransform: "uppercase", marginBottom: 4 },
  card: {
    backgroundColor: colors.surface,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: colors.line,
    padding: 16,
    marginBottom: 12,
  },
  button: {
    minHeight: 52,
    borderRadius: 10,
    paddingHorizontal: 18,
    alignItems: "center",
    justifyContent: "center",
  },
  button_primary: { backgroundColor: colors.primary },
  button_secondary: { backgroundColor: colors.surface, borderWidth: 1.5, borderColor: colors.primary },
  button_danger: { backgroundColor: colors.danger },
  button_ghost: { backgroundColor: "transparent" },
  buttonDisabled: { opacity: 0.45 },
  buttonText: { fontSize: 17, fontWeight: "700" },
  buttonText_primary: { color: "#fff" },
  buttonText_secondary: { color: colors.primary },
  buttonText_danger: { color: "#fff" },
  buttonText_ghost: { color: colors.muted },
  input: {
    minHeight: 52,
    borderWidth: 1.5,
    borderColor: colors.line,
    borderRadius: 10,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 17,
    color: colors.ink,
    backgroundColor: colors.surface,
  },
  chip: {
    minHeight: 44,
    paddingHorizontal: 14,
    borderRadius: 22,
    borderWidth: 1.5,
    borderColor: colors.line,
    backgroundColor: colors.surface,
    justifyContent: "center",
    marginRight: 8,
    marginBottom: 8,
  },
  chipSelected: { backgroundColor: colors.primary, borderColor: colors.primary },
  chipText: { fontSize: 16, color: colors.ink, fontWeight: "500" },
  chipTextSelected: { color: "#fff" },
  row: { flexDirection: "row", flexWrap: "wrap", alignItems: "center" },
  badge: { borderRadius: 999, paddingHorizontal: 10, paddingVertical: 4, marginRight: 6, marginBottom: 4 },
  badgeText: { fontSize: 13, fontWeight: "700" },
  error: { backgroundColor: colors.dangerSoft, borderRadius: 10, padding: 14, marginBottom: 12 },
  errorText: { color: colors.danger, fontSize: 16, fontWeight: "600" },
  reply: {
    backgroundColor: colors.primarySoft,
    borderRadius: 12,
    padding: 14,
    marginBottom: 12,
    borderLeftWidth: 4,
    borderLeftColor: colors.primary,
  },
  replyText: { fontSize: 17, color: colors.ink, lineHeight: 24 },
  replyButton: { marginTop: 8, minHeight: 40, justifyContent: "center", alignSelf: "flex-start" },
  replyButtonText: { color: colors.primaryDark, fontWeight: "700", fontSize: 16 },
  replyNote: { marginTop: 6, color: colors.muted, fontSize: 14 },
});
