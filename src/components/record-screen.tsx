import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useChart } from "@/components/chart-shell";
import { listChart, saveRecord, voidRecord, type ChartLists, type SavePayload, type VoidKind } from "@/lib/chart/records";

export type Field = {
  name: string;
  label: string;
  kind: "text" | "date" | "time" | "textarea" | "number" | "select" | "check";
  required?: boolean;
  options?: { value: string; label: string }[];
};

export type Draft = Record<string, string | boolean>;

export type Listed = { id: string; status: string; summary: string; draft: Draft };

const inputClass = "mt-1 h-11 w-full rounded-md border border-line bg-card px-3 text-ink";
const labelClass = "block text-sm font-medium text-ink";

export function useLists() {
  const chart = useChart();
  const profileId = chart.state?.activeProfileId ?? null;
  const profile = chart.state?.profiles.find((item) => item.id === profileId) ?? null;
  const [showVoided, setShowVoided] = useState(false);
  const [lists, setLists] = useState<ChartLists | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const reload = useCallback(async () => {
    if (!profileId) return null;
    const next = await listChart({ data: { profileId, showVoided } });
    setLists(next);
    return next;
  }, [profileId, showVoided]);

  useEffect(() => {
    if (!profileId) return;
    let cancelled = false;
    setError(null);
    listChart({ data: { profileId, showVoided } })
      .then((next) => {
        if (!cancelled) setLists(next);
      })
      .catch(() => {
        if (!cancelled) setError("This section could not be loaded.");
      });
    return () => {
      cancelled = true;
    };
  }, [profileId, showVoided]);

  return {
    profileId,
    profile,
    lists,
    showVoided,
    setShowVoided,
    error,
    setError,
    pending,
    setPending,
    reload,
    loading: chart.loading,
  };
}

export function RecordScreen({
  title,
  kind,
  empty,
  fields,
  blank,
  select,
  payload,
}: {
  title: string;
  kind: VoidKind;
  empty: string;
  fields: Field[];
  blank: Draft;
  select: (lists: ChartLists) => Listed[];
  payload: (draft: Draft, id: string | null, profileId: string) => SavePayload;
}) {
  const screen = useLists();
  const [editing, setEditing] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<Draft>(blank);
  const rows = screen.lists ? select(screen.lists) : [];

  if (screen.loading) return <div className="h-24 animate-pulse rounded-md bg-line" />;
  if (!screen.profileId) {
    return <p className="text-muted">Add a person on the dashboard before entering a chart.</p>;
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!screen.profileId) return;
    screen.setPending(true);
    screen.setError(null);
    try {
      await saveRecord({ data: payload(draft, editing, screen.profileId) });
      setOpen(false);
      await screen.reload();
    } catch {
      screen.setError("That entry could not be saved.");
    } finally {
      screen.setPending(false);
    }
  }

  async function voidRow(id: string) {
    if (!screen.profileId) return;
    screen.setPending(true);
    screen.setError(null);
    try {
      await voidRecord({ data: { profileId: screen.profileId, kind, id, showVoided: screen.showVoided } });
      await screen.reload();
    } catch {
      screen.setError("That entry could not be voided.");
    } finally {
      screen.setPending(false);
    }
  }

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-serif text-3xl text-ink">{title}</h2>
        <button
          type="button"
          className="no-print h-11 rounded-md bg-green px-4 font-medium text-green-ink"
          onClick={() => {
            setEditing(null);
            setDraft(blank);
            setOpen(true);
          }}
        >
          Add
        </button>
      </div>
      <label className="no-print flex items-center gap-2 text-sm text-muted">
        <input
          type="checkbox"
          checked={screen.showVoided}
          onChange={(event) => screen.setShowVoided(event.target.checked)}
        />
        Show voided
      </label>
      {screen.error ? <p className="text-sm text-alert">{screen.error}</p> : null}
      {rows.length === 0 ? <p className="text-muted">{empty}</p> : null}
      <ul className="space-y-3">
        {rows.map((row) => (
          <li key={row.id} className="rounded-md border border-line bg-card p-4">
            <p className="text-ink">{row.summary}</p>
            {row.status !== "active" ? (
              <p className="mt-1 text-sm capitalize text-muted">{row.status.replaceAll("_", " ")}</p>
            ) : null}
            <div className="no-print mt-3 flex gap-2">
              <button
                type="button"
                className="h-11 rounded-md border border-line px-3 text-sm"
                onClick={() => {
                  setEditing(row.id);
                  setDraft(row.draft);
                  setOpen(true);
                }}
              >
                Edit
              </button>
              {row.status !== "entered_in_error" ? (
                <button type="button" className="h-11 rounded-md border border-line px-3 text-sm text-alert" onClick={() => voidRow(row.id)}>
                  Void
                </button>
              ) : null}
            </div>
          </li>
        ))}
      </ul>
      {open ? (
        <form className="no-print space-y-4 rounded-md border border-line bg-card p-4" onSubmit={save}>
          {fields.map((field) => (
            <FieldInput
              key={field.name}
              field={field}
              value={draft[field.name] ?? (field.kind === "check" ? false : "")}
              onChange={(value) => setDraft((current) => ({ ...current, [field.name]: value }))}
            />
          ))}
          <button
            type="submit"
            disabled={screen.pending}
            className="h-11 rounded-md bg-green px-4 font-medium text-green-ink disabled:opacity-60"
          >
            {screen.pending ? "Saving" : "Save"}
          </button>
        </form>
      ) : null}
    </section>
  );
}

function FieldInput({
  field,
  value,
  onChange,
}: {
  field: Field;
  value: string | boolean;
  onChange: (value: string | boolean) => void;
}) {
  if (field.kind === "check") {
    return (
      <label className="flex h-11 items-center gap-2 text-sm text-ink">
        <input type="checkbox" checked={value === true} onChange={(event) => onChange(event.target.checked)} />
        {field.label}
      </label>
    );
  }
  if (field.kind === "textarea") {
    return (
      <label className={labelClass}>
        {field.label}
        <textarea
          className="mt-1 min-h-24 w-full rounded-md border border-line bg-card px-3 py-2 text-ink"
          required={field.required}
          value={String(value)}
          onChange={(event) => onChange(event.target.value)}
        />
      </label>
    );
  }
  if (field.kind === "select") {
    return (
      <label className={labelClass}>
        {field.label}
        <select className={inputClass} required={field.required} value={String(value)} onChange={(event) => onChange(event.target.value)}>
          <option value="">Not set</option>
          {field.options?.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
    );
  }
  const type = field.kind === "date" ? "date" : field.kind === "time" ? "datetime-local" : field.kind === "number" ? "number" : "text";
  return (
    <label className={labelClass}>
      {field.label}
      <input
        className={inputClass}
        type={type}
        required={field.required}
        step={field.kind === "number" ? "any" : undefined}
        value={String(value)}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}
