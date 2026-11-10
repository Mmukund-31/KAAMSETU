import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { CategoryBadge, NeutralBadge } from "../components/badges";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  InlineError,
  LoadingState,
  Modal,
  PageHeader,
  Pagination,
  SelectField,
  Table,
  Td,
  TextField,
  Th,
  cx,
  plainInputClass,
} from "../components/ui";
import { CATEGORIES, CATEGORY_LABEL, OPERATIONAL_LABEL } from "../lib/format";
import { queryKeys } from "../lib/queryKeys";
import { equipmentApi } from "../services";
import type { EquipmentCategory, OperationalStatus } from "../types/api";

const PAGE_SIZE = 25;

const OP_STYLE: Record<OperationalStatus, string> = {
  running: "text-primary-700",
  degraded: "text-amber-800",
  stopped: "text-red-700",
  maintenance: "text-amber-800",
  decommissioned: "text-ink-faint",
};

export function EquipmentPage() {
  const [search, setSearch] = useState("");
  const [q, setQ] = useState("");
  const [category, setCategory] = useState<EquipmentCategory | "">("");
  const [page, setPage] = useState(1);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => {
      setQ(search.trim());
      setPage(1);
    }, 300);
    return () => clearTimeout(t);
  }, [search]);

  const params = { q: q || undefined, category: category || undefined, page, page_size: PAGE_SIZE };
  const query = useQuery({
    queryKey: queryKeys.equipmentList(params),
    queryFn: () => equipmentApi.list(params),
    placeholderData: keepPreviousData,
  });

  return (
    <>
      <PageHeader
        title="Equipment"
        description="The site register. Reports are only accepted for equipment listed here."
        actions={
          <Button variant="primary" icon={<Plus className="h-4 w-4" />} onClick={() => setCreating(true)}>
            Register equipment
          </Button>
        }
      />
      <Card className="mb-4">
        <div className="flex flex-wrap gap-2">
          <div className="relative min-w-[220px] flex-1">
            <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-ink-faint" aria-hidden />
            <input
              type="search"
              aria-label="Search equipment"
              placeholder="Search code or name"
              className={cx(plainInputClass, "pl-8")}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <select
            aria-label="Category"
            className={cx(plainInputClass, "w-auto")}
            value={category}
            onChange={(e) => {
              setCategory(e.target.value as EquipmentCategory | "");
              setPage(1);
            }}
          >
            <option value="">All categories</option>
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {CATEGORY_LABEL[c]}
              </option>
            ))}
          </select>
        </div>
      </Card>

      <Card bodyClassName="p-0">
        {query.isLoading ? (
          <LoadingState />
        ) : query.isError ? (
          <ErrorState error={query.error} onRetry={() => void query.refetch()} />
        ) : !query.data?.items.length ? (
          <EmptyState title="No equipment found" />
        ) : (
          <>
            <Table>
              <thead>
                <tr>
                  <Th>Code</Th>
                  <Th>Name</Th>
                  <Th>Category</Th>
                  <Th>Location</Th>
                  <Th>Status</Th>
                  <Th className="text-right">Open orders</Th>
                </tr>
              </thead>
              <tbody>
                {query.data.items.map((e) => (
                  <tr key={e.id} className="hover:bg-surface-subtle">
                    <Td>
                      <Link to={`/equipment/${e.id}`} className="font-mono text-sm font-semibold text-primary-700 hover:underline">
                        {e.code}
                      </Link>
                    </Td>
                    <Td>
                      {e.name}
                      {e.is_critical && (
                        <span className="ml-2">
                          <NeutralBadge>Critical</NeutralBadge>
                        </span>
                      )}
                    </Td>
                    <Td>
                      <CategoryBadge category={e.category} />
                    </Td>
                    <Td className="text-sm text-ink-muted">{e.location ?? "—"}</Td>
                    <Td className={cx("text-sm font-medium", OP_STYLE[e.operational_status])}>
                      {OPERATIONAL_LABEL[e.operational_status]}
                    </Td>
                    <Td className="text-right tabular-nums">{e.open_work_orders}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
            <Pagination page={query.data.page} pageSize={query.data.page_size} total={query.data.total} onPage={setPage} />
          </>
        )}
      </Card>
      {creating && <CreateEquipmentDialog onClose={() => setCreating(false)} />}
    </>
  );
}

function CreateEquipmentDialog({ onClose }: { onClose: () => void }) {
  const client = useQueryClient();
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [category, setCategory] = useState<EquipmentCategory>("mechanical");
  const [location, setLocation] = useState("");
  const [critical, setCritical] = useState(false);
  const codeValid = /^[A-Za-z]{1,3}[- ]?\d{2,4}$/.test(code.trim());

  const mutation = useMutation({
    mutationFn: () =>
      equipmentApi.create({
        equipment_code: code.trim(),
        name: name.trim(),
        category,
        location: location.trim() || null,
        is_critical: critical,
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["equipment"] });
      onClose();
    },
  });

  return (
    <Modal
      open
      title="Register equipment"
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" loading={mutation.isPending} disabled={!codeValid || name.trim().length < 2} onClick={() => mutation.mutate()}>
            Register
          </Button>
        </>
      }
    >
      <TextField
        label="Equipment code"
        required
        value={code}
        onChange={(e) => setCode(e.target.value)}
        placeholder="M-205"
        hint="1–3 letters and 2–4 digits, e.g. M-205. Technicians say this code in reports."
        error={code && !codeValid ? "Use a code like M-205 or CV12." : undefined}
      />
      <TextField label="Name" required value={name} onChange={(e) => setName(e.target.value)} maxLength={160} />
      <SelectField label="Category" value={category} onChange={(e) => setCategory(e.target.value as EquipmentCategory)}>
        {CATEGORIES.map((c) => (
          <option key={c} value={c}>
            {CATEGORY_LABEL[c]}
          </option>
        ))}
      </SelectField>
      <TextField label="Location" value={location} onChange={(e) => setLocation(e.target.value)} maxLength={160} />
      <label className="flex items-center gap-2 text-sm text-ink">
        <input type="checkbox" checked={critical} onChange={(e) => setCritical(e.target.checked)} className="h-4 w-4 rounded border-line-strong" />
        Critical equipment (a stopped critical machine is reported as critical priority)
      </label>
      <InlineError error={mutation.error} />
    </Modal>
  );
}
