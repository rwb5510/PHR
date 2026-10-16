import { useState, type FormEvent } from "react";
import type { Profile } from "@/lib/chart/household";

const SEX = [
  { value: "", label: "Not set" },
  { value: "female", label: "Female" },
  { value: "male", label: "Male" },
  { value: "other", label: "Other" },
  { value: "unknown", label: "Unknown" },
] as const;

const BLOOD = ["", "O+", "O-", "A+", "A-", "B+", "B-", "AB+", "AB-"] as const;

export type ProfileDraft = {
  legalName: string;
  preferredName: string;
  birthDate: string;
  sex: string;
  bloodType: string;
  relationshipLabel: string;
  notes: string;
};

export const emptyDraft: ProfileDraft = {
  legalName: "",
  preferredName: "",
  birthDate: "",
  sex: "",
  bloodType: "",
  relationshipLabel: "",
  notes: "",
};

export function draftFromProfile(profile: Profile): ProfileDraft {
  return {
    legalName: profile.legalName,
    preferredName: profile.preferredName ?? "",
    birthDate: profile.birthDate ?? "",
    sex: profile.sex ?? "",
    bloodType: profile.bloodType ?? "",
    relationshipLabel: profile.relationshipLabel ?? "",
    notes: profile.notes ?? "",
  };
}

const fieldClass = "mt-1 h-11 w-full rounded-md border border-line bg-card px-3 text-ink";
const labelClass = "block text-sm font-medium text-ink";

export function ProfileForm({
  initial,
  submitLabel,
  pending,
  onSubmit,
}: {
  initial: ProfileDraft;
  submitLabel: string;
  pending: boolean;
  onSubmit: (draft: ProfileDraft) => Promise<void>;
}) {
  const [draft, setDraft] = useState(initial);

  function set<K extends keyof ProfileDraft>(key: K, value: ProfileDraft[K]) {
    setDraft((current) => ({ ...current, [key]: value }));
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    await onSubmit(draft);
  }

  return (
    <form className="space-y-4" onSubmit={handleSubmit}>
      <label className={labelClass}>
        Legal name
        <input
          required
          className={fieldClass}
          value={draft.legalName}
          autoComplete="name"
          onChange={(event) => set("legalName", event.target.value)}
        />
      </label>
      <label className={labelClass}>
        Preferred name
        <input
          className={fieldClass}
          value={draft.preferredName}
          onChange={(event) => set("preferredName", event.target.value)}
        />
      </label>
      <label className={labelClass}>
        Date of birth
        <input
          type="date"
          className={fieldClass}
          value={draft.birthDate}
          onChange={(event) => set("birthDate", event.target.value)}
        />
      </label>
      <div className="grid gap-4 sm:grid-cols-2">
        <label className={labelClass}>
          Sex
          <select
            className={fieldClass}
            value={draft.sex}
            onChange={(event) => set("sex", event.target.value)}
          >
            {SEX.map((option) => (
              <option key={option.value || "unset"} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label className={labelClass}>
          Blood type
          <select
            className={fieldClass}
            value={draft.bloodType}
            onChange={(event) => set("bloodType", event.target.value)}
          >
            {BLOOD.map((option) => (
              <option key={option || "unset"} value={option}>
                {option || "Not set"}
              </option>
            ))}
          </select>
        </label>
      </div>
      <label className={labelClass}>
        Relationship
        <input
          className={fieldClass}
          placeholder="Self, spouse, child"
          value={draft.relationshipLabel}
          onChange={(event) => set("relationshipLabel", event.target.value)}
        />
      </label>
      <label className={labelClass}>
        Notes
        <textarea
          className="mt-1 min-h-24 w-full rounded-md border border-line bg-card px-3 py-2 text-ink"
          value={draft.notes}
          onChange={(event) => set("notes", event.target.value)}
        />
      </label>
      <button
        type="submit"
        disabled={pending}
        className="h-11 rounded-md bg-green px-4 font-medium text-green-ink disabled:opacity-60"
      >
        {pending ? "Saving" : submitLabel}
      </button>
    </form>
  );
}
