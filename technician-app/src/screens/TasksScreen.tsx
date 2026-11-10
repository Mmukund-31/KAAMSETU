import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Pressable, RefreshControl, ScrollView, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useLanguage, useSession } from "../auth/SessionContext";
import { Badge, Chip, ErrorBanner, Loading, Muted, PriorityBadge, Row, StatusBadge, Title, colors } from "../components/ui";
import { workOrdersApi } from "../services";
import type { WorkOrderSummary } from "../types/api";

const DONE = new Set(["closed", "rejected"]);

export function TasksScreen({ onOpen }: { onOpen: (id: string) => void }) {
  const { t, user } = useSession();
  const language = useLanguage();
  const [tab, setTab] = useState<"assigned" | "reported">("assigned");
  // Pull-based: the list refreshes every 30 s and on pull-down (no push notifications in the MVP).
  const assigned = useQuery({ queryKey: ["work-orders", "assigned"], queryFn: workOrdersApi.assigned, refetchInterval: 30_000 });
  const reported = useQuery({
    queryKey: ["work-orders", "reported", user?.id],
    queryFn: () => workOrdersApi.reported(user!.id),
    enabled: tab === "reported" && !!user,
  });
  const query = tab === "assigned" ? assigned : reported;
  const items = (query.data?.items ?? []).filter((w) => tab === "reported" || !DONE.has(w.status));

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.background }} edges={["top", "left", "right"]}>
      <ScrollView
        contentContainerStyle={{ padding: 16, paddingBottom: 40 }}
        refreshControl={<RefreshControl refreshing={query.isRefetching} onRefresh={() => void query.refetch()} />}
      >
        <Title>{t("tabTasks")}</Title>
        <Row style={{ marginBottom: 8 }}>
          <Chip label={t("assignedToMe")} selected={tab === "assigned"} onPress={() => setTab("assigned")} testID="tab-assigned" />
          <Chip label={t("myReports")} selected={tab === "reported"} onPress={() => setTab("reported")} testID="tab-reported" />
        </Row>
        {query.isLoading ? <Loading /> : null}
        <ErrorBanner error={query.error} onRetry={() => void query.refetch()} />
        {query.isSuccess && items.length === 0 ? (
          <Muted style={{ textAlign: "center", marginTop: 32 }}>{tab === "assigned" ? t("noTasks") : t("noReports")}</Muted>
        ) : null}
        {items.map((wo) => (
          <TaskCard key={wo.id} wo={wo} onPress={() => onOpen(wo.id)} language={language} overdueText={t("overdue")} />
        ))}
      </ScrollView>
    </SafeAreaView>
  );
}

function TaskCard({
  wo,
  onPress,
  language,
  overdueText,
}: {
  wo: WorkOrderSummary;
  onPress: () => void;
  language: ReturnType<typeof useLanguage>;
  overdueText: string;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${wo.display_number} ${wo.equipment.code}`}
      onPress={onPress}
      testID={`task-${wo.display_number}`}
      style={({ pressed }) => ({
        backgroundColor: colors.surface,
        borderRadius: 12,
        borderWidth: 1,
        borderColor: wo.is_overdue ? colors.danger : colors.line,
        padding: 16,
        marginBottom: 12,
        opacity: pressed ? 0.85 : 1,
      })}
    >
      <View style={{ flexDirection: "row", justifyContent: "space-between", marginBottom: 6 }}>
        <Text style={{ fontSize: 18, fontWeight: "800", color: colors.ink }}>{wo.equipment.code}</Text>
        <Text style={{ fontSize: 15, color: colors.muted }}>{wo.display_number}</Text>
      </View>
      <Text style={{ fontSize: 15, color: colors.muted, marginBottom: 6 }}>{wo.equipment.name}</Text>
      <Text style={{ fontSize: 16, color: colors.ink, marginBottom: 10 }} numberOfLines={2}>
        {wo.issue_description}
      </Text>
      <Row>
        <PriorityBadge priority={wo.priority} language={language} />
        <StatusBadge status={wo.status} language={language} />
        {wo.is_overdue ? <Badge text={overdueText} tone="danger" /> : null}
      </Row>
    </Pressable>
  );
}
