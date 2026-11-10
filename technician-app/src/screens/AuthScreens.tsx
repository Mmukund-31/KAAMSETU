import { useState } from "react";
import { Text, View } from "react-native";
import { useSession } from "../auth/SessionContext";
import { Button, Card, Chip, ErrorBanner, Field, Muted, Row, Screen, Title, colors } from "../components/ui";
import { ApiError } from "../lib/api";
import { API_BASE_URL } from "../lib/config";
import { LANGUAGE_NAME } from "../lib/i18n";
import type { Language } from "../types/api";

export function LoginScreen() {
  const { login, t, notice } = useSession();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      await login(email.trim(), password);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  const technicianOnly = error instanceof ApiError && error.code === "technician_only";
  return (
    <Screen>
      <View style={{ marginTop: 24, marginBottom: 24 }}>
        <Text style={{ fontSize: 30, fontWeight: "800", color: colors.primary, letterSpacing: 1 }}>KAAMSETU</Text>
        <Muted>Speak the work. Structure the action.</Muted>
      </View>
      <Title>{t("signInTitle")}</Title>
      {notice ? <Text style={{ color: colors.warning, fontSize: 16, marginBottom: 12 }}>{t(notice)}</Text> : null}
      {technicianOnly ? (
        <Text style={{ color: colors.danger, fontSize: 16, marginBottom: 12 }} accessibilityRole="alert">
          {t("technicianOnly")}
        </Text>
      ) : error instanceof ApiError && error.status === 401 ? (
        <Text style={{ color: colors.danger, fontSize: 16, marginBottom: 12 }} accessibilityRole="alert">
          {error.message}
        </Text>
      ) : (
        <ErrorBanner error={error} />
      )}
      <Field
        label={t("email")}
        value={email}
        onChangeText={setEmail}
        autoCapitalize="none"
        autoComplete="email"
        keyboardType="email-address"
        testID="email"
      />
      <Field label={t("password")} value={password} onChangeText={setPassword} secureTextEntry autoComplete="password" testID="password" />
      <Button label={t("signIn")} onPress={() => void submit()} loading={busy} disabled={!email.trim() || !password} testID="sign-in" />
      <Muted style={{ marginTop: 24, fontSize: 13 }}>
        {t("server")}: {API_BASE_URL}
      </Muted>
    </Screen>
  );
}

export const LANGUAGES: Language[] = ["hinglish", "hi", "te", "en"];

export function LanguagePicker({ value, onChange }: { value: Language | null; onChange: (l: Language) => void }) {
  return (
    <Row>
      {LANGUAGES.map((l) => (
        <Chip key={l} label={LANGUAGE_NAME[l]} selected={value === l} onPress={() => onChange(l)} testID={`lang-${l}`} />
      ))}
    </Row>
  );
}

export function LanguageScreen() {
  const { user, setLanguage, t } = useSession();
  const [choice, setChoice] = useState<Language>(user?.preferred_language ?? "en");
  return (
    <Screen>
      <Title>{t("chooseLanguage")}</Title>
      <Muted style={{ marginBottom: 16 }}>{t("languageHint")}</Muted>
      <LanguagePicker value={choice} onChange={setChoice} />
      <Button label={t("continue")} onPress={() => void setLanguage(choice)} style={{ marginTop: 16 }} testID="language-continue" />
    </Screen>
  );
}

export function ProfileScreen() {
  const { user, language, setLanguage, logout, t } = useSession();
  return (
    <Screen>
      <Title>{t("profileTitle")}</Title>
      <Card>
        <Text style={{ fontSize: 20, fontWeight: "700", color: colors.ink }}>{user?.name}</Text>
        <Muted>{user?.email}</Muted>
        <Muted>{user?.site?.name}</Muted>
      </Card>
      <Card>
        <Text style={{ fontSize: 16, fontWeight: "700", color: colors.ink, marginBottom: 8 }}>{t("language")}</Text>
        <LanguagePicker value={language} onChange={(l) => void setLanguage(l)} />
      </Card>
      <Muted style={{ marginBottom: 16, fontSize: 13 }}>
        {t("server")}: {API_BASE_URL}
      </Muted>
      <Button label={t("signOut")} variant="danger" onPress={() => void logout()} testID="sign-out" />
    </Screen>
  );
}
