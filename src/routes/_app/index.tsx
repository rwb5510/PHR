import { useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { displayName, useChart } from "@/components/chart-shell";
import {
  ProfileForm,
  draftFromProfile,
  emptyDraft,
  type ProfileDraft,
} from "@/components/profile-form";
import { createProfile, updateProfile } from "@/lib/chart/household";

export const Route = createFileRoute("/_app/")({
  component: Home,
});

function formatBirth(iso: string): string {
  const [year, month, day] = iso.split("-").map(Number);
  if (!year || !month || !day) return iso;
  return new Date(year, month - 1, day).toLocaleDateString(undefined, {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

function payload(draft: ProfileDraft) {
  return {
    legalName: draft.legalName,
    preferredName: draft.preferredName || null,
    birthDate: draft.birthDate || null,
    sex: (draft.sex || null) as "female" | "male" | "other" | "unknown" | null,
    bloodType: (draft.bloodType || null) as
      | "O+"
      | "O-"
      | "A+"
      | "A-"
      | "B+"
      | "B-"
      | "AB+"
      | "AB-"
      | null,
    relationshipLabel: draft.relationshipLabel || null,
    notes: draft.notes || null,
  };
}

function Home() {
  const { state, loading, error, replace } = useChart();
  const [mode, setMode] = useState<"closed" | "add" | "edit">("closed");
  const [pending, setPending] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const active = state?.profiles.find((profile) => profile.id === state.activeProfileId) ?? null;

  async function save(draft: ProfileDraft) {
    setPending(true);
    setFormError(null);
    try {
      const next =
        mode === "edit" && active
          ? await updateProfile({ data: { id: active.id, ...payload(draft) } })
          : await createProfile({ data: payload(draft) });
      replace(next);
      setMode("closed");
    } catch {
      setFormError("That person could not be saved. Check the name and try again.");
    } finally {
      setPending(false);
    }
  }

  if (loading) {
    return <div className="h-32 animate-pulse rounded-md bg-line" />;
  }

  return (
    <section className="space-y-6">
      {error ? <p className="text-alert">{error}</p> : null}
      {!active ? (
        <div className="rounded-md border border-line bg-card p-5">
          <h2 className="font-serif text-3xl text-ink">Add the first person</h2>
          <p className="mt-2 text-muted">
            Each person in the household has their own chart. You can switch between them later.
          </p>
          <div className="mt-5">
            <ProfileForm initial={emptyDraft} submitLabel="Add person" pending={pending} onSubmit={save} />
          </div>
        </div>
      ) : (
        <div className="rounded-md border border-line bg-card p-5">
          <p className="text-sm text-muted">{active.relationshipLabel || "Household member"}</p>
          <h2 className="font-serif text-4xl leading-tight text-ink">{displayName(active)}</h2>
          <dl className="mt-4 space-y-2 text-sm">
            <div className="flex justify-between gap-4">
              <dt className="text-muted">Legal name</dt>
              <dd>{active.legalName}</dd>
            </div>
            {active.birthDate ? (
              <div className="flex justify-between gap-4">
                <dt className="text-muted">Born</dt>
                <dd>{formatBirth(active.birthDate)}</dd>
              </div>
            ) : null}
            {active.sex ? (
              <div className="flex justify-between gap-4">
                <dt className="text-muted">Sex</dt>
                <dd className="capitalize">{active.sex}</dd>
              </div>
            ) : null}
            {active.bloodType ? (
              <div className="flex justify-between gap-4">
                <dt className="text-muted">Blood type</dt>
                <dd>{active.bloodType}</dd>
              </div>
            ) : null}
          </dl>
          {active.notes ? <p className="mt-4 text-sm text-muted">{active.notes}</p> : null}
          <p className="mt-4 text-sm text-muted">Use the sections above to add this person's history.</p>
          <div className="mt-5 flex flex-wrap gap-2">
            <button
              type="button"
              className="h-11 rounded-md border border-line bg-paper px-4 font-medium text-ink"
              onClick={() => setMode(mode === "edit" ? "closed" : "edit")}
            >
              Edit details
            </button>
            <button
              type="button"
              className="h-11 rounded-md bg-green px-4 font-medium text-green-ink"
              onClick={() => setMode(mode === "add" ? "closed" : "add")}
            >
              Add person
            </button>
          </div>
        </div>
      )}
      {formError ? <p className="text-alert">{formError}</p> : null}
      {active && mode === "edit" ? (
        <div className="rounded-md border border-line bg-card p-5">
          <h3 className="font-serif text-2xl text-ink">Edit {displayName(active)}</h3>
          <div className="mt-4">
            <ProfileForm
              key={active.id}
              initial={draftFromProfile(active)}
              submitLabel="Save"
              pending={pending}
              onSubmit={save}
            />
          </div>
        </div>
      ) : null}
      {active && mode === "add" ? (
        <div className="rounded-md border border-line bg-card p-5">
          <h3 className="font-serif text-2xl text-ink">Add a person</h3>
          <div className="mt-4">
            <ProfileForm
              key="add"
              initial={emptyDraft}
              submitLabel="Add person"
              pending={pending}
              onSubmit={save}
            />
          </div>
        </div>
      ) : null}
    </section>
  );
}
