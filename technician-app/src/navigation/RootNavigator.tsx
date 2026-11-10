import { Ionicons } from "@expo/vector-icons";
import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import { createNativeStackNavigator, type NativeStackScreenProps } from "@react-navigation/native-stack";
import { useSession } from "../auth/SessionContext";
import { Loading, Screen, colors } from "../components/ui";
import { LanguageScreen, LoginScreen, ProfileScreen } from "../screens/AuthScreens";
import { HandoverScreen } from "../screens/HandoverScreen";
import { ReportScreen } from "../screens/ReportScreen";
import { TaskDetailScreen } from "../screens/TaskDetailScreen";
import { TasksScreen } from "../screens/TasksScreen";

export type TasksStackParams = { Tasks: undefined; TaskDetail: { id: string; title: string } };

const Tabs = createBottomTabNavigator();
const TasksStack = createNativeStackNavigator<TasksStackParams>();

function TasksList({ navigation }: NativeStackScreenProps<TasksStackParams, "Tasks">) {
  return <TasksScreen onOpen={(id) => navigation.navigate("TaskDetail", { id, title: "" })} />;
}

function TaskDetail({ route }: NativeStackScreenProps<TasksStackParams, "TaskDetail">) {
  return <TaskDetailScreen id={route.params.id} />;
}

function TasksNavigator() {
  const { t } = useSession();
  return (
    <TasksStack.Navigator>
      <TasksStack.Screen name="Tasks" component={TasksList} options={{ headerShown: false }} />
      <TasksStack.Screen name="TaskDetail" component={TaskDetail} options={{ title: t("tabTasks") }} />
    </TasksStack.Navigator>
  );
}

const icon = (name: keyof typeof Ionicons.glyphMap) =>
  function TabIcon({ color, size }: { color: string; size: number }) {
    return <Ionicons name={name} size={size} color={color} />;
  };

export function RootNavigator() {
  const { status, language, t } = useSession();
  if (status === "loading") {
    return (
      <Screen>
        <Loading />
      </Screen>
    );
  }
  if (status === "signed_out") return <LoginScreen />;
  // The language decides what Prisma listens for and what Timbre speaks, so it is chosen before anything else.
  if (!language) return <LanguageScreen />;

  return (
    <Tabs.Navigator
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.primary,
        tabBarInactiveTintColor: colors.muted,
        tabBarLabelStyle: { fontSize: 13, fontWeight: "600" },
        tabBarStyle: { minHeight: 60 },
      }}
    >
      <Tabs.Screen name="Report" component={ReportScreen} options={{ title: t("tabReport"), tabBarIcon: icon("mic") }} />
      <Tabs.Screen name="Work" component={TasksNavigator} options={{ title: t("tabTasks"), tabBarIcon: icon("construct") }} />
      <Tabs.Screen name="Handover" component={HandoverScreen} options={{ title: t("tabHandover"), tabBarIcon: icon("swap-horizontal") }} />
      <Tabs.Screen name="Profile" component={ProfileScreen} options={{ title: t("tabProfile"), tabBarIcon: icon("person") }} />
    </Tabs.Navigator>
  );
}
