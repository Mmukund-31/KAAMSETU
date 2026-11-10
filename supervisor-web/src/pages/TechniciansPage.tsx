import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { UserPlus } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useCurrentUser } from "../auth/AuthContext";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  InlineError,
  LoadingState,
  Modal,
  PageHeader,
  SelectField,
  Table,
  Td,
  TextField,
  Th,
  cx,
} from "../components/ui";
import { LANGUAGE_LABEL } from "../lib/format";
import { queryKeys } from "../lib/queryKeys";
import { authApi, dashboardApi } from "../services";
import type { LanguageCode, UserRole } from "../types/api";

export function TechniciansPage() {
  const query = useQuery({ queryKey: queryKeys.workload, queryFn: dashboardApi.workload, refetchInterval: 30_000 });
  const [creating, setCreating] = useState(false);

  return (
    <>
      <PageHeader
        title="Technicians"
        description="Current workload per technician. Each one hears tasks in their own language."
        actions={
          <Button variant="primary" icon={<UserPlus className="h-4 w-4" />} onClick={() => setCreating(true)}>
            Add account
          </Button>
        }
      />
      <Card bodyClassName="p-0">
        {query.isLoading ? (
          <LoadingState />
        ) : query.isError ? (
          <ErrorState error={query.error} onRetry={() => void query.refetch()} />
        ) : !query.data?.length ? (
          <EmptyState title="No technicians at this site" action={<Button onClick={() => setCreating(true)}>Add a technician</Button>} />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Technician</Th>
                <Th>Language</Th>
                <Th className="text-right">Assigned</Th>
                <Th className="text-right">In progress</Th>
                <Th className="text-right">Blocked / parts</Th>
                <Th className="text-right">In review</Th>
                <Th className="text-right">Overdue</Th>
                <Th className="text-right">Open total</Th>
                <Th className="text-right">Closed, 30 d</Th>
              </tr>
            </thead>
            <tbody>
              {query.data.map((w) => (
                <tr key={w.technician.id} className="hover:bg-surface-subtle">
                  <Td>
                    <Link
                      to={`/work-orders?open=1&assigned_to=${w.technician.id}`}
                      className="font-medium text-primary-700 hover:underline"
                    >
                      {w.technician.name}
                    </Link>
                  </Td>
                  <Td className="text-sm text-ink-muted">{LANGUAGE_LABEL[w.preferred_language]}</Td>
                  <Num value={w.assigned} />
                  <Num value={w.in_progress} />
                  <Num value={w.blocked} warn />
                  <Num value={w.completion_review} />
                  <Num value={w.overdue} danger />
                  <Num value={w.open_total} strong />
                  <Num value={w.closed_30d} />
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
      {creating && <CreateUserDialog onClose={() => setCreating(false)} />}
    </>
  );
}

function Num({ value, warn, danger, strong }: { value: number; warn?: boolean; danger?: boolean; strong?: boolean }) {
  return (
    <Td
      className={cx(
        "text-right tabular-nums",
        strong && "font-semibold",
        value > 0 && danger && "font-semibold text-red-700",
        value > 0 && warn && "font-medium text-amber-800",
        value === 0 && "text-ink-faint",
      )}
    >
      {value}
    </Td>
  );
}

function CreateUserDialog({ onClose }: { onClose: () => void }) {
  const user = useCurrentUser();
  const client = useQueryClient();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [language, setLanguage] = useState<LanguageCode>("hinglish");
  const [role, setRole] = useState<UserRole>("technician");
  // Supervisors may only create technicians at their own site; managers may create any role.
  const roles: UserRole[] = user.role === "manager" ? ["technician", "supervisor", "manager"] : ["technician"];
  const passwordOk = password.length >= 8 && /[A-Za-z]/.test(password) && /\d/.test(password);

  const mutation = useMutation({
    mutationFn: () =>
      authApi.register({ name: name.trim(), email: email.trim(), password, role, preferred_language: language }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["dashboard"] });
      void client.invalidateQueries({ queryKey: ["users"] });
      onClose();
    },
  });

  return (
    <Modal
      open
      title="Add account"
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button
            variant="primary"
            loading={mutation.isPending}
            disabled={!name.trim() || !email.includes("@") || !passwordOk}
            onClick={() => mutation.mutate()}
          >
            Create account
          </Button>
        </>
      }
    >
      <p className="text-xs text-ink-muted">
        There is no self-registration. The account is created at {user.site?.name ?? "your site"}; share the password with
        the person directly.
      </p>
      <TextField label="Name" required value={name} onChange={(e) => setName(e.target.value)} maxLength={120} />
      <TextField label="Email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="off" />
      <TextField
        label="Initial password"
        type="password"
        required
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        autoComplete="new-password"
        hint="At least 8 characters with a letter and a digit."
        error={password && !passwordOk ? "At least 8 characters with a letter and a digit." : undefined}
      />
      <div className="grid gap-4 sm:grid-cols-2">
        <SelectField label="Role" value={role} onChange={(e) => setRole(e.target.value as UserRole)} disabled={roles.length === 1}>
          {roles.map((r) => (
            <option key={r} value={r} className="capitalize">
              {r.charAt(0).toUpperCase() + r.slice(1)}
            </option>
          ))}
        </SelectField>
        <SelectField
          label="Spoken language"
          value={language}
          onChange={(e) => setLanguage(e.target.value as LanguageCode)}
          hint="Used for speech recognition and spoken replies."
        >
          {(Object.keys(LANGUAGE_LABEL) as LanguageCode[]).map((l) => (
            <option key={l} value={l}>
              {LANGUAGE_LABEL[l]}
            </option>
          ))}
        </SelectField>
      </div>
      <InlineError error={mutation.error} />
    </Modal>
  );
}
