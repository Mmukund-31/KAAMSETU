import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { useCurrentUser } from "../auth/AuthContext";
import { CategoryBadge, NeutralBadge } from "../components/badges";
import {
  Button,
  Card,
  DefinitionList,
  EmptyState,
  ErrorState,
  InlineError,
  LoadingState,
  Modal,
  PageHeader,
  SelectField,
  TextField,
  cx,
  plainInputClass,
} from "../components/ui";
import { CATEGORIES, CATEGORY_LABEL, LANGUAGE_LABEL, formatDate } from "../lib/format";
import { queryKeys } from "../lib/queryKeys";
import { templatesApi } from "../services";
import type { ChecklistTemplate, EquipmentCategory } from "../types/api";

export function SettingsPage() {
  const user = useCurrentUser();
  const [showInactive, setShowInactive] = useState(false);
  const [editing, setEditing] = useState<ChecklistTemplate | "new" | null>(null);
  const templates = useQuery({
    queryKey: queryKeys.templates(!showInactive),
    queryFn: () => templatesApi.list({ active_only: !showInactive }),
  });

  return (
    <>
      <PageHeader title="Settings" />
      <div className="grid gap-6 xl:grid-cols-3">
        <Card title="Your account">
          <DefinitionList
            items={[
              ["Name", user.name],
              ["Email", user.email],
              ["Role", <span className="capitalize">{user.role}</span>],
              ["Site", user.site?.name ?? "All sites"],
              ["Language", LANGUAGE_LABEL[user.preferred_language]],
            ]}
          />
        </Card>

        <Card
          title="SOP checklist templates"
          className="xl:col-span-2"
          actions={
            <Button size="sm" variant="primary" icon={<Plus className="h-4 w-4" />} onClick={() => setEditing("new")}>
              New template
            </Button>
          }
        >
          <p className="mb-3 text-sm text-ink-muted">
            Enter company-approved procedure steps only; KAAMSETU never writes SOP content. Publishing a template with the
            same name and category creates a new version. Running checklists keep the version they started with.
          </p>
          <label className="mb-3 flex items-center gap-2 text-sm text-ink-muted">
            <input type="checkbox" className="h-4 w-4 rounded border-line-strong" checked={showInactive} onChange={(e) => setShowInactive(e.target.checked)} />
            Show older and deactivated versions
          </label>
          {templates.isLoading ? (
            <LoadingState />
          ) : templates.isError ? (
            <ErrorState error={templates.error} onRetry={() => void templates.refetch()} />
          ) : !templates.data?.length ? (
            <EmptyState title="No checklist templates" />
          ) : (
            <ul className="divide-y divide-line rounded-md border border-line">
              {templates.data.map((t) => (
                <TemplateRow key={t.id} template={t} onEdit={() => setEditing(t)} />
              ))}
            </ul>
          )}
        </Card>
      </div>
      {editing && <TemplateEditor base={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
    </>
  );
}

function TemplateRow({ template: t, onEdit }: { template: ChecklistTemplate; onEdit: () => void }) {
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const deactivate = useMutation({
    mutationFn: () => templatesApi.deactivate(t.id),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["templates"] }),
  });
  return (
    <li className="px-4 py-3">
      <div className="flex flex-wrap items-center gap-2">
        <button className="text-left text-sm font-medium text-ink hover:text-primary-700" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
          {t.name}
        </button>
        <CategoryBadge category={t.equipment_category} />
        <NeutralBadge>v{t.version}</NeutralBadge>
        <NeutralBadge>{t.items.length} steps</NeutralBadge>
        {!t.is_active && <NeutralBadge>Inactive</NeutralBadge>}
        <span className="ml-auto flex gap-1">
          {t.is_active && (
            <>
              <Button size="sm" variant="ghost" onClick={onEdit}>
                New version
              </Button>
              <Button size="sm" variant="ghost" loading={deactivate.isPending} onClick={() => deactivate.mutate()}>
                Deactivate
              </Button>
            </>
          )}
        </span>
      </div>
      <p className="mt-0.5 text-xs text-ink-muted">
        {t.work_order_type} · published {formatDate(t.created_at)}
      </p>
      <InlineError error={deactivate.error} />
      {open && (
        <ol className="mt-2 list-decimal space-y-1 pl-5 text-sm text-ink">
          {t.items.map((i) => (
            <li key={i.id}>
              {i.description}
              {i.is_mandatory && <span className="ml-1.5 text-xs font-medium text-red-700">Mandatory</span>}
            </li>
          ))}
        </ol>
      )}
    </li>
  );
}

interface DraftItem {
  key: number;
  description: string;
  is_mandatory: boolean;
}

let nextKey = 1;

function TemplateEditor({ base, onClose }: { base: ChecklistTemplate | null; onClose: () => void }) {
  const client = useQueryClient();
  const [name, setName] = useState(base?.name ?? "");
  const [category, setCategory] = useState<EquipmentCategory>(base?.equipment_category ?? "mechanical");
  const [items, setItems] = useState<DraftItem[]>(
    base?.items.map((i) => ({ key: nextKey++, description: i.description, is_mandatory: i.is_mandatory })) ?? [
      { key: nextKey++, description: "", is_mandatory: true },
    ],
  );
  const mutation = useMutation({
    mutationFn: () =>
      templatesApi.publish({
        name: name.trim(),
        equipment_category: category,
        work_order_type: base?.work_order_type ?? "corrective",
        items: items.map((i) => ({ description: i.description.trim(), is_mandatory: i.is_mandatory })),
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["templates"] });
      onClose();
    },
  });

  const valid = name.trim().length >= 3 && items.length > 0 && items.every((i) => i.description.trim().length >= 3);
  const update = (key: number, patch: Partial<DraftItem>) => setItems((list) => list.map((i) => (i.key === key ? { ...i, ...patch } : i)));
  const move = (index: number, delta: number) =>
    setItems((list) => {
      const next = [...list];
      const [item] = next.splice(index, 1);
      next.splice(index + delta, 0, item);
      return next;
    });

  return (
    <Modal
      open
      title={base ? `New version of ${base.name}` : "New checklist template"}
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" loading={mutation.isPending} disabled={!valid} onClick={() => mutation.mutate()}>
            Publish
          </Button>
        </>
      }
    >
      <TextField label="Name" required value={name} onChange={(e) => setName(e.target.value)} maxLength={160} disabled={!!base} />
      <SelectField label="Equipment category" value={category} onChange={(e) => setCategory(e.target.value as EquipmentCategory)} disabled={!!base}>
        {CATEGORIES.map((c) => (
          <option key={c} value={c}>
            {CATEGORY_LABEL[c]}
          </option>
        ))}
      </SelectField>
      <div>
        <p className="mb-1.5 text-sm font-medium text-ink">Steps</p>
        <ol className="space-y-2">
          {items.map((item, index) => (
            <li key={item.key} className="rounded-md border border-line p-2">
              <div className="flex gap-2">
                <span className="mt-2 w-5 text-right text-xs tabular-nums text-ink-muted">{index + 1}.</span>
                <textarea
                  className={cx(plainInputClass, "min-h-[40px]")}
                  rows={2}
                  aria-label={`Step ${index + 1}`}
                  value={item.description}
                  maxLength={500}
                  onChange={(e) => update(item.key, { description: e.target.value })}
                />
              </div>
              <div className="mt-1.5 flex items-center gap-1 pl-7">
                <label className="mr-auto flex items-center gap-1.5 text-xs text-ink-muted">
                  <input type="checkbox" className="h-3.5 w-3.5" checked={item.is_mandatory} onChange={(e) => update(item.key, { is_mandatory: e.target.checked })} />
                  Mandatory
                </label>
                <button className="rounded p-1 text-ink-muted hover:bg-surface-sunken disabled:opacity-30" disabled={index === 0} onClick={() => move(index, -1)} aria-label="Move up">
                  <ArrowUp className="h-3.5 w-3.5" />
                </button>
                <button className="rounded p-1 text-ink-muted hover:bg-surface-sunken disabled:opacity-30" disabled={index === items.length - 1} onClick={() => move(index, 1)} aria-label="Move down">
                  <ArrowDown className="h-3.5 w-3.5" />
                </button>
                <button className="rounded p-1 text-ink-muted hover:text-red-700 disabled:opacity-30" disabled={items.length === 1} onClick={() => setItems((l) => l.filter((i) => i.key !== item.key))} aria-label="Remove step">
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            </li>
          ))}
        </ol>
        <Button
          className="mt-2"
          size="sm"
          icon={<Plus className="h-4 w-4" />}
          disabled={items.length >= 50}
          onClick={() => setItems((l) => [...l, { key: nextKey++, description: "", is_mandatory: true }])}
        >
          Add step
        </Button>
      </div>
      <InlineError error={mutation.error} />
    </Modal>
  );
}
