import { useState, type FormEvent } from "react";
import { displayName } from "@/components/chart-shell";
import { RecordScreen, useLists, type Draft, type Listed } from "@/components/record-screen";
import { saveEncounter, voidRecord, type ChartLists } from "@/lib/chart/records";

function text(draft: Draft, name: string): string | null {
  const value = draft[name];
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function flag(draft: Draft, name: string): boolean {
  return draft[name] === true;
}

function num(draft: Draft, name: string): number | null {
  const value = draft[name];
  if (typeof value !== "string" || value.trim() === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function row(id: string, status: string, summary: string, draft: Draft): Listed {
  return { id, status, summary, draft };
}

const SEVERITY = [
  { value: "mild", label: "Mild" },
  { value: "moderate", label: "Moderate" },
  { value: "severe", label: "Severe" },
  { value: "unknown", label: "Unknown" },
];

const PROBLEM_STATUS = [
  { value: "active", label: "Active" },
  { value: "resolved", label: "Resolved" },
];

const MED_STATUS = [
  { value: "active", label: "Active" },
  { value: "stopped", label: "Stopped" },
  { value: "held", label: "Held" },
];

const VITAL_KIND = [
  { value: "bp", label: "Blood pressure" },
  { value: "heart_rate", label: "Heart rate" },
  { value: "weight", label: "Weight" },
  { value: "height", label: "Height" },
  { value: "temperature", label: "Temperature" },
  { value: "spo2", label: "Oxygen saturation" },
];

const VISIT = [
  { value: "planned", label: "Planned" },
  { value: "done", label: "Done" },
  { value: "cancelled", label: "Cancelled" },
];

export function ProblemsPage() {
  return (
    <RecordScreen
      title="Problems"
      kind="problem"
      empty="No problems yet."
      blank={{ displayName: "", icd10: "", onset: "", resolvedOn: "", notes: "", status: "active" }}
      fields={[
        { name: "displayName", label: "Problem", kind: "text", required: true },
        { name: "icd10", label: "ICD-10", kind: "text" },
        { name: "status", label: "Status", kind: "select", options: PROBLEM_STATUS },
        { name: "onset", label: "Onset", kind: "date" },
        { name: "resolvedOn", label: "Resolved", kind: "date" },
        { name: "notes", label: "Notes", kind: "textarea" },
      ]}
      select={(lists) =>
        lists.problems.map((item) =>
          row(item.id, item.status, item.displayName, {
            displayName: item.displayName,
            icd10: item.icd10 ?? "",
            onset: item.onset ?? "",
            resolvedOn: item.resolvedOn ?? "",
            notes: item.notes ?? "",
            status: item.status === "entered_in_error" ? "active" : item.status,
          }),
        )
      }
      payload={(draft, id, profileId) => ({
        kind: "problem",
        id,
        profileId,
        displayName: text(draft, "displayName") ?? "",
        icd10: text(draft, "icd10"),
        onset: text(draft, "onset"),
        resolvedOn: text(draft, "resolvedOn"),
        notes: text(draft, "notes"),
        status: text(draft, "status") === "resolved" ? "resolved" : "active",
      })}
    />
  );
}

export function AllergiesPage() {
  return (
    <RecordScreen
      title="Allergies"
      kind="allergy"
      empty="No allergies yet."
      blank={{ substance: "", reaction: "", severity: "", onset: "", notes: "" }}
      fields={[
        { name: "substance", label: "Substance", kind: "text", required: true },
        { name: "reaction", label: "Reaction", kind: "text" },
        { name: "severity", label: "Severity", kind: "select", options: SEVERITY },
        { name: "onset", label: "Onset", kind: "date" },
        { name: "notes", label: "Notes", kind: "textarea" },
      ]}
      select={(lists) =>
        lists.allergies.map((item) =>
          row(item.id, item.status, [item.substance, item.reaction, item.severity].filter(Boolean).join(" · "), {
            substance: item.substance,
            reaction: item.reaction ?? "",
            severity: item.severity ?? "",
            onset: item.onset ?? "",
            notes: item.notes ?? "",
          }),
        )
      }
      payload={(draft, id, profileId) => ({
        kind: "allergy",
        id,
        profileId,
        substance: text(draft, "substance") ?? "",
        reaction: text(draft, "reaction"),
        severity: (text(draft, "severity") as "mild" | "moderate" | "severe" | "unknown" | null) ?? null,
        onset: text(draft, "onset"),
        notes: text(draft, "notes"),
      })}
    />
  );
}

export function MedicationsPage() {
  return (
    <RecordScreen
      title="Medications"
      kind="medication"
      empty="No medications yet."
      blank={{ name: "", dose: "", doseUnit: "", route: "", frequency: "", startOn: "", stopOn: "", prescriber: "", indication: "", notes: "", status: "active" }}
      fields={[
        { name: "name", label: "Name", kind: "text", required: true },
        { name: "dose", label: "Dose", kind: "text" },
        { name: "doseUnit", label: "Dose unit", kind: "text" },
        { name: "route", label: "Route", kind: "text" },
        { name: "frequency", label: "Frequency", kind: "text" },
        { name: "status", label: "Status", kind: "select", options: MED_STATUS },
        { name: "startOn", label: "Started", kind: "date" },
        { name: "stopOn", label: "Stopped", kind: "date" },
        { name: "prescriber", label: "Prescriber", kind: "text" },
        { name: "indication", label: "Indication", kind: "text" },
        { name: "notes", label: "Notes", kind: "textarea" },
      ]}
      select={(lists) =>
        lists.medications.map((item) =>
          row(item.id, item.status, [item.name, item.dose, item.doseUnit, item.frequency].filter(Boolean).join(" "), {
            name: item.name,
            dose: item.dose ?? "",
            doseUnit: item.doseUnit ?? "",
            route: item.route ?? "",
            frequency: item.frequency ?? "",
            startOn: item.startOn ?? "",
            stopOn: item.stopOn ?? "",
            prescriber: item.prescriber ?? "",
            indication: item.indication ?? "",
            notes: item.notes ?? "",
            status: item.status === "entered_in_error" ? "active" : item.status,
          }),
        )
      }
      payload={(draft, id, profileId) => ({
        kind: "medication",
        id,
        profileId,
        name: text(draft, "name") ?? "",
        dose: text(draft, "dose"),
        doseUnit: text(draft, "doseUnit"),
        route: text(draft, "route"),
        frequency: text(draft, "frequency"),
        startOn: text(draft, "startOn"),
        stopOn: text(draft, "stopOn"),
        prescriber: text(draft, "prescriber"),
        indication: text(draft, "indication"),
        notes: text(draft, "notes"),
        status: (["stopped", "held"].includes(text(draft, "status") ?? "") ? text(draft, "status") : "active") as "active" | "stopped" | "held",
      })}
    />
  );
}

export function ProvidersPage() {
  return (
    <RecordScreen
      title="Providers"
      kind="provider"
      empty="No providers yet."
      blank={{ name: "", credentials: "", specialty: "", address: "", phone: "", fax: "", email: "", website: "", portalUrl: "", isPrimary: false, notes: "" }}
      fields={[
        { name: "name", label: "Name", kind: "text", required: true },
        { name: "credentials", label: "Credentials", kind: "text" },
        { name: "specialty", label: "Specialty", kind: "text" },
        { name: "phone", label: "Phone", kind: "text" },
        { name: "fax", label: "Fax", kind: "text" },
        { name: "email", label: "Email", kind: "text" },
        { name: "website", label: "Website", kind: "text" },
        { name: "portalUrl", label: "Patient portal", kind: "text" },
        { name: "address", label: "Address", kind: "textarea" },
        { name: "isPrimary", label: "Primary provider", kind: "check" },
        { name: "notes", label: "Notes", kind: "textarea" },
      ]}
      select={(lists) =>
        lists.providers.map((item) =>
          row(item.id, item.status, item.isPrimary ? `${item.name} · primary` : item.name, {
            name: item.name,
            credentials: item.credentials ?? "",
            specialty: item.specialty ?? "",
            address: item.address ?? "",
            phone: item.phone ?? "",
            fax: item.fax ?? "",
            email: item.email ?? "",
            website: item.website ?? "",
            portalUrl: item.portalUrl ?? "",
            isPrimary: item.isPrimary,
            notes: item.notes ?? "",
          }),
        )
      }
      payload={(draft, id, profileId) => ({
        kind: "provider",
        id,
        profileId,
        name: text(draft, "name") ?? "",
        credentials: text(draft, "credentials"),
        specialty: text(draft, "specialty"),
        address: text(draft, "address"),
        phone: text(draft, "phone"),
        fax: text(draft, "fax"),
        email: text(draft, "email"),
        website: text(draft, "website"),
        portalUrl: text(draft, "portalUrl"),
        isPrimary: flag(draft, "isPrimary"),
        notes: text(draft, "notes"),
      })}
    />
  );
}

export function ImmunizationsPage() {
  return (
    <RecordScreen
      title="Immunizations"
      kind="immunization"
      empty="No immunizations yet."
      blank={{ vaccine: "", cvx: "", givenOn: "", lot: "", site: "", notes: "" }}
      fields={[
        { name: "vaccine", label: "Vaccine", kind: "text", required: true },
        { name: "givenOn", label: "Date", kind: "date" },
        { name: "cvx", label: "CVX", kind: "text" },
        { name: "lot", label: "Lot", kind: "text" },
        { name: "site", label: "Site", kind: "text" },
        { name: "notes", label: "Notes", kind: "textarea" },
      ]}
      select={(lists) =>
        lists.immunizations.map((item) =>
          row(item.id, item.status, [item.vaccine, item.givenOn].filter(Boolean).join(" · "), {
            vaccine: item.vaccine,
            cvx: item.cvx ?? "",
            givenOn: item.givenOn ?? "",
            lot: item.lot ?? "",
            site: item.site ?? "",
            notes: item.notes ?? "",
          }),
        )
      }
      payload={(draft, id, profileId) => ({
        kind: "immunization",
        id,
        profileId,
        vaccine: text(draft, "vaccine") ?? "",
        cvx: text(draft, "cvx"),
        givenOn: text(draft, "givenOn"),
        lot: text(draft, "lot"),
        site: text(draft, "site"),
        notes: text(draft, "notes"),
      })}
    />
  );
}

export function ProceduresPage() {
  return (
    <RecordScreen
      title="Procedures"
      kind="procedure_event"
      empty="No procedures yet."
      blank={{ name: "", performedOn: "", laterality: "", providerName: "", facility: "", notes: "" }}
      fields={[
        { name: "name", label: "Procedure", kind: "text", required: true },
        { name: "performedOn", label: "Date", kind: "date" },
        { name: "laterality", label: "Laterality", kind: "text" },
        { name: "providerName", label: "Provider", kind: "text" },
        { name: "facility", label: "Facility", kind: "text" },
        { name: "notes", label: "Notes", kind: "textarea" },
      ]}
      select={(lists) =>
        lists.procedures.map((item) =>
          row(item.id, item.status, [item.name, item.performedOn].filter(Boolean).join(" · "), {
            name: item.name,
            performedOn: item.performedOn ?? "",
            laterality: item.laterality ?? "",
            providerName: item.providerName ?? "",
            facility: item.facility ?? "",
            notes: item.notes ?? "",
          }),
        )
      }
      payload={(draft, id, profileId) => ({
        kind: "procedure_event",
        id,
        profileId,
        name: text(draft, "name") ?? "",
        performedOn: text(draft, "performedOn"),
        laterality: text(draft, "laterality"),
        providerName: text(draft, "providerName"),
        facility: text(draft, "facility"),
        notes: text(draft, "notes"),
        encounterId: null,
      })}
    />
  );
}

export function FamilyPage() {
  return (
    <RecordScreen
      title="Family history"
      kind="family_history"
      empty="No family history yet."
      blank={{ relationship: "", condition: "", ageAtOnset: "", deceased: false, notes: "" }}
      fields={[
        { name: "relationship", label: "Relationship", kind: "text", required: true },
        { name: "condition", label: "Condition", kind: "text", required: true },
        { name: "ageAtOnset", label: "Age at onset", kind: "text" },
        { name: "deceased", label: "Deceased", kind: "check" },
        { name: "notes", label: "Notes", kind: "textarea" },
      ]}
      select={(lists) =>
        lists.family.map((item) =>
          row(item.id, item.status, `${item.relationship}: ${item.condition}`, {
            relationship: item.relationship,
            condition: item.condition,
            ageAtOnset: item.ageAtOnset ?? "",
            deceased: item.deceased,
            notes: item.notes ?? "",
          }),
        )
      }
      payload={(draft, id, profileId) => ({
        kind: "family_history",
        id,
        profileId,
        relationship: text(draft, "relationship") ?? "",
        condition: text(draft, "condition") ?? "",
        ageAtOnset: text(draft, "ageAtOnset"),
        deceased: flag(draft, "deceased"),
        notes: text(draft, "notes"),
      })}
    />
  );
}

export function SocialPage() {
  return (
    <RecordScreen
      title="Social history"
      kind="social_history"
      empty="No social history yet."
      blank={{ asOf: "", smoking: "", alcohol: "", substances: "", occupation: "", livingSituation: "", notes: "" }}
      fields={[
        { name: "asOf", label: "As of", kind: "date" },
        { name: "smoking", label: "Smoking", kind: "text" },
        { name: "alcohol", label: "Alcohol", kind: "text" },
        { name: "substances", label: "Other substances", kind: "text" },
        { name: "occupation", label: "Occupation", kind: "text" },
        { name: "livingSituation", label: "Living situation", kind: "text" },
        { name: "notes", label: "Notes", kind: "textarea" },
      ]}
      select={(lists) =>
        lists.social.map((item) =>
          row(item.id, item.status, item.asOf ? `As of ${item.asOf}` : "Social history", {
            asOf: item.asOf ?? "",
            smoking: item.smoking ?? "",
            alcohol: item.alcohol ?? "",
            substances: item.substances ?? "",
            occupation: item.occupation ?? "",
            livingSituation: item.livingSituation ?? "",
            notes: item.notes ?? "",
          }),
        )
      }
      payload={(draft, id, profileId) => ({
        kind: "social_history",
        id,
        profileId,
        asOf: text(draft, "asOf"),
        smoking: text(draft, "smoking"),
        alcohol: text(draft, "alcohol"),
        substances: text(draft, "substances"),
        occupation: text(draft, "occupation"),
        livingSituation: text(draft, "livingSituation"),
        notes: text(draft, "notes"),
      })}
    />
  );
}

export function VitalsPage() {
  return (
    <RecordScreen
      title="Vitals"
      kind="vital"
      empty="No vitals yet."
      blank={{ vitalKind: "bp", systolic: "", value: "", unit: "", measuredAt: "" }}
      fields={[
        { name: "vitalKind", label: "Kind", kind: "select", options: VITAL_KIND, required: true },
        { name: "systolic", label: "Systolic (blood pressure only)", kind: "number" },
        { name: "value", label: "Value or diastolic", kind: "number" },
        { name: "unit", label: "Unit", kind: "text" },
        { name: "measuredAt", label: "Measured", kind: "time" },
      ]}
      select={(lists) =>
        lists.vitals.map((item) =>
          row(
            item.id,
            item.status,
            item.kind === "bp" ? `Blood pressure ${item.systolic ?? ""}/${item.value ?? ""}` : `${labelKind(item.kind)} ${item.value ?? ""} ${item.unit ?? ""}`,
            {
              vitalKind: item.kind,
              systolic: item.systolic ?? "",
              value: item.value ?? "",
              unit: item.unit ?? "",
              measuredAt: item.measuredAt ?? "",
            },
          ),
        )
      }
      payload={(draft, id, profileId) => ({
        kind: "vital",
        id,
        profileId,
        vitalKind: (text(draft, "vitalKind") ?? "bp") as "bp" | "heart_rate" | "weight" | "height" | "temperature" | "spo2",
        systolic: num(draft, "systolic"),
        value: num(draft, "value"),
        unit: text(draft, "unit"),
        measuredAt: text(draft, "measuredAt"),
      })}
    />
  );
}

function labelKind(kind: string): string {
  return VITAL_KIND.find((item) => item.value === kind)?.label ?? kind;
}

export function ImplantsPage() {
  return (
    <RecordScreen
      title="Implants"
      kind="implant"
      empty="No implants or devices yet."
      blank={{ implantKind: "", name: "", model: "", laterality: "", implantedOn: "", facility: "", mriNote: "", udi: "", notes: "" }}
      fields={[
        { name: "name", label: "Name", kind: "text", required: true },
        { name: "implantKind", label: "Kind", kind: "text" },
        { name: "model", label: "Model", kind: "text" },
        { name: "laterality", label: "Laterality", kind: "text" },
        { name: "implantedOn", label: "Implanted", kind: "date" },
        { name: "facility", label: "Facility", kind: "text" },
        { name: "udi", label: "UDI", kind: "text" },
        { name: "mriNote", label: "MRI note", kind: "text" },
        { name: "notes", label: "Notes", kind: "textarea" },
      ]}
      select={(lists) =>
        lists.implants.map((item) =>
          row(item.id, item.status, item.name, {
            name: item.name,
            implantKind: item.kind ?? "",
            model: item.model ?? "",
            laterality: item.laterality ?? "",
            implantedOn: item.implantedOn ?? "",
            facility: item.facility ?? "",
            udi: item.udi ?? "",
            mriNote: item.mriNote ?? "",
            notes: item.notes ?? "",
          }),
        )
      }
      payload={(draft, id, profileId) => ({
        kind: "implant",
        id,
        profileId,
        name: text(draft, "name") ?? "",
        implantKind: text(draft, "implantKind"),
        model: text(draft, "model"),
        laterality: text(draft, "laterality"),
        implantedOn: text(draft, "implantedOn"),
        facility: text(draft, "facility"),
        udi: text(draft, "udi"),
        mriNote: text(draft, "mriNote"),
        notes: text(draft, "notes"),
      })}
    />
  );
}

export function InsurancePage() {
  return (
    <RecordScreen
      title="Insurance"
      kind="insurance"
      empty="No insurance yet."
      blank={{ payer: "", planName: "", memberId: "", groupNumber: "", phone: "" }}
      fields={[
        { name: "payer", label: "Payer", kind: "text", required: true },
        { name: "planName", label: "Plan", kind: "text" },
        { name: "memberId", label: "Member id", kind: "text" },
        { name: "groupNumber", label: "Group", kind: "text" },
        { name: "phone", label: "Phone", kind: "text" },
      ]}
      select={(lists) =>
        lists.insurance.map((item) =>
          row(item.id, item.status, item.payer, {
            payer: item.payer,
            planName: item.planName ?? "",
            memberId: item.memberId ?? "",
            groupNumber: item.groupNumber ?? "",
            phone: item.phone ?? "",
          }),
        )
      }
      payload={(draft, id, profileId) => ({
        kind: "insurance",
        id,
        profileId,
        payer: text(draft, "payer") ?? "",
        planName: text(draft, "planName"),
        memberId: text(draft, "memberId"),
        groupNumber: text(draft, "groupNumber"),
        phone: text(draft, "phone"),
      })}
    />
  );
}

export function PharmacyPage() {
  return (
    <RecordScreen
      title="Pharmacy"
      kind="pharmacy"
      empty="No pharmacy yet."
      blank={{ name: "", phone: "", fax: "", address: "" }}
      fields={[
        { name: "name", label: "Name", kind: "text", required: true },
        { name: "phone", label: "Phone", kind: "text" },
        { name: "fax", label: "Fax", kind: "text" },
        { name: "address", label: "Address", kind: "textarea" },
      ]}
      select={(lists) =>
        lists.pharmacies.map((item) =>
          row(item.id, item.status, item.name, {
            name: item.name,
            phone: item.phone ?? "",
            fax: item.fax ?? "",
            address: item.address ?? "",
          }),
        )
      }
      payload={(draft, id, profileId) => ({
        kind: "pharmacy",
        id,
        profileId,
        name: text(draft, "name") ?? "",
        phone: text(draft, "phone"),
        fax: text(draft, "fax"),
        address: text(draft, "address"),
      })}
    />
  );
}

export function ContactsPage() {
  return (
    <RecordScreen
      title="Emergency contacts"
      kind="emergency_contact"
      empty="No emergency contacts yet."
      blank={{ name: "", relationship: "", phone: "" }}
      fields={[
        { name: "name", label: "Name", kind: "text", required: true },
        { name: "relationship", label: "Relationship", kind: "text" },
        { name: "phone", label: "Phone", kind: "text" },
      ]}
      select={(lists) =>
        lists.contacts.map((item) =>
          row(item.id, item.status, [item.name, item.phone].filter(Boolean).join(" · "), {
            name: item.name,
            relationship: item.relationship ?? "",
            phone: item.phone ?? "",
          }),
        )
      }
      payload={(draft, id, profileId) => ({
        kind: "emergency_contact",
        id,
        profileId,
        name: text(draft, "name") ?? "",
        relationship: text(draft, "relationship"),
        phone: text(draft, "phone"),
      })}
    />
  );
}

export function AppointmentsPage() {
  return (
    <RecordScreen
      title="Appointments"
      kind="appointment"
      empty="No appointments yet."
      blank={{ startsAt: "", providerName: "", place: "", reason: "", visitStatus: "planned" }}
      fields={[
        { name: "startsAt", label: "When", kind: "time" },
        { name: "providerName", label: "Provider", kind: "text" },
        { name: "place", label: "Place", kind: "text" },
        { name: "reason", label: "Reason", kind: "text" },
        { name: "visitStatus", label: "Status", kind: "select", options: VISIT },
      ]}
      select={(lists) =>
        lists.appointments.map((item) =>
          row(item.id, item.status, [item.startsAt, item.reason, item.providerName].filter(Boolean).join(" · "), {
            startsAt: item.startsAt ?? "",
            providerName: item.providerName ?? "",
            place: item.place ?? "",
            reason: item.reason ?? "",
            visitStatus: item.visitStatus,
          }),
        )
      }
      payload={(draft, id, profileId) => ({
        kind: "appointment",
        id,
        profileId,
        startsAt: text(draft, "startsAt"),
        providerName: text(draft, "providerName"),
        place: text(draft, "place"),
        reason: text(draft, "reason"),
        visitStatus: (text(draft, "visitStatus") as "planned" | "done" | "cancelled" | null) ?? "planned",
      })}
    />
  );
}

const ENCOUNTER_TYPES = [
  ["office_visit", "Office visit"],
  ["telehealth", "Telehealth"],
  ["ed", "Emergency department"],
  ["hospital_stay", "Hospital stay"],
  ["lab", "Lab"],
  ["imaging", "Imaging"],
  ["procedure", "Procedure"],
  ["immunization_visit", "Immunization"],
  ["patient_entered", "Entered by you"],
  ["other", "Other"],
] as const;

const ROLES = [
  ["attending", "Attending"],
  ["ordering", "Ordering"],
  ["consulting", "Consulting"],
  ["primary", "Primary"],
] as const;

export function EncountersPage() {
  const screen = useLists();
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const [type, setType] = useState("office_visit");
  const [startsAt, setStartsAt] = useState("");
  const [endsAt, setEndsAt] = useState("");
  const [facility, setFacility] = useState("");
  const [reason, setReason] = useState("");
  const [notes, setNotes] = useState("");
  const [providerId, setProviderId] = useState("");
  const [role, setRole] = useState<(typeof ROLES)[number][0]>("attending");

  if (screen.loading) return <div className="h-24 animate-pulse rounded-md bg-line" />;
  if (!screen.profileId) return <p className="text-muted">Add a person on the dashboard before entering a chart.</p>;

  const encounters = screen.lists?.encounters ?? [];
  const providers = screen.lists?.providers.filter((item) => item.status !== "entered_in_error") ?? [];

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!screen.profileId) return;
    screen.setPending(true);
    screen.setError(null);
    try {
      await saveEncounter({
        data: {
          id: editing,
          profileId: screen.profileId,
          type: type as (typeof ENCOUNTER_TYPES)[number][0],
          startsAt: startsAt || null,
          endsAt: endsAt || null,
          facility: facility || null,
          reason: reason || null,
          notes: notes || null,
          links: providerId ? [{ providerId, role }] : [],
        },
      });
      setOpen(false);
      await screen.reload();
    } catch {
      screen.setError("That encounter could not be saved.");
    } finally {
      screen.setPending(false);
    }
  }

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-serif text-3xl text-ink">Encounters</h2>
        <button
          type="button"
          className="no-print h-11 rounded-md bg-green px-4 font-medium text-green-ink"
          onClick={() => {
            setEditing(null);
            setType("office_visit");
            setStartsAt("");
            setEndsAt("");
            setFacility("");
            setReason("");
            setNotes("");
            setProviderId("");
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
      {encounters.length === 0 ? <p className="text-muted">No encounters yet. A visit and a same-day lab stay separate.</p> : null}
      <ul className="space-y-3">
        {encounters.map((item) => (
          <li key={item.id} className="rounded-md border border-line bg-card p-4">
            <p className="text-ink">{ENCOUNTER_TYPES.find((entry) => entry[0] === item.type)?.[1] ?? item.type}</p>
            <p className="text-sm text-muted">{[item.startsAt, item.facility, item.reason].filter(Boolean).join(" · ")}</p>
            {item.links.length > 0 ? (
              <p className="mt-1 text-sm text-muted">{item.links.map((link) => `${link.name} (${link.role})`).join(", ")}</p>
            ) : null}
            <div className="no-print mt-3 flex gap-2">
              <button
                type="button"
                className="h-11 rounded-md border border-line px-3 text-sm"
                onClick={() => {
                  setEditing(item.id);
                  setType(item.type);
                  setStartsAt(item.startsAt ?? "");
                  setEndsAt(item.endsAt ?? "");
                  setFacility(item.facility ?? "");
                  setReason(item.reason ?? "");
                  setNotes(item.notes ?? "");
                  setProviderId(item.links[0]?.providerId ?? "");
                  setRole((item.links[0]?.role as (typeof ROLES)[number][0]) ?? "attending");
                  setOpen(true);
                }}
              >
                Edit
              </button>
              {item.status !== "entered_in_error" ? (
                <button
                  type="button"
                  className="h-11 rounded-md border border-line px-3 text-sm text-alert"
                  onClick={() => {
                    if (!screen.profileId) return;
                    voidRecord({
                      data: { profileId: screen.profileId, kind: "encounter", id: item.id, showVoided: screen.showVoided },
                    })
                      .then(() => screen.reload())
                      .catch(() => screen.setError("That encounter could not be voided."));
                  }}
                >
                  Void
                </button>
              ) : null}
            </div>
          </li>
        ))}
      </ul>
      {open ? (
        <form className="no-print space-y-4 rounded-md border border-line bg-card p-4" onSubmit={save}>
          <label className="block text-sm font-medium">
            Type
            <select className="mt-1 h-11 w-full rounded-md border border-line bg-card px-3" value={type} onChange={(event) => setType(event.target.value)}>
              {ENCOUNTER_TYPES.map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </label>
          <label className="block text-sm font-medium">
            Start
            <input className="mt-1 h-11 w-full rounded-md border border-line bg-card px-3" type="datetime-local" value={startsAt} onChange={(event) => setStartsAt(event.target.value)} />
          </label>
          <label className="block text-sm font-medium">
            End
            <input className="mt-1 h-11 w-full rounded-md border border-line bg-card px-3" type="datetime-local" value={endsAt} onChange={(event) => setEndsAt(event.target.value)} />
          </label>
          <label className="block text-sm font-medium">
            Facility
            <input className="mt-1 h-11 w-full rounded-md border border-line bg-card px-3" value={facility} onChange={(event) => setFacility(event.target.value)} />
          </label>
          <label className="block text-sm font-medium">
            Reason
            <input className="mt-1 h-11 w-full rounded-md border border-line bg-card px-3" value={reason} onChange={(event) => setReason(event.target.value)} />
          </label>
          <label className="block text-sm font-medium">
            Provider
            <select className="mt-1 h-11 w-full rounded-md border border-line bg-card px-3" value={providerId} onChange={(event) => setProviderId(event.target.value)}>
              <option value="">None</option>
              {providers.map((provider) => (
                <option key={provider.id} value={provider.id}>{provider.name}</option>
              ))}
            </select>
          </label>
          <label className="block text-sm font-medium">
            Role
            <select className="mt-1 h-11 w-full rounded-md border border-line bg-card px-3" value={role} onChange={(event) => setRole(event.target.value as (typeof ROLES)[number][0])}>
              {ROLES.map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </label>
          <label className="block text-sm font-medium">
            Notes
            <textarea className="mt-1 min-h-24 w-full rounded-md border border-line bg-card px-3 py-2" value={notes} onChange={(event) => setNotes(event.target.value)} />
          </label>
          <button type="submit" disabled={screen.pending} className="h-11 rounded-md bg-green px-4 font-medium text-green-ink disabled:opacity-60">
            Save
          </button>
        </form>
      ) : null}
    </section>
  );
}

function active<T extends { status: string }>(rows: T[]): T[] {
  return rows.filter((row) => row.status !== "entered_in_error");
}

export function EmergencyPage() {
  const screen = useLists();
  if (screen.loading) return <div className="h-24 animate-pulse rounded-md bg-line" />;
  if (!screen.profile || !screen.lists) {
    return <p className="text-muted">Add a person on the dashboard before printing an emergency snapshot.</p>;
  }
  const lists: ChartLists = screen.lists;
  const person = screen.profile;
  const primary = lists.providers.find((item) => item.isPrimary && item.status !== "entered_in_error");
  return (
    <article className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-serif text-4xl text-ink">{displayName(person)}</h2>
          <p className="text-muted">{person.legalName}</p>
        </div>
        <button type="button" className="no-print h-11 rounded-md bg-green px-4 font-medium text-green-ink" onClick={() => window.print()}>
          Print
        </button>
      </div>
      <dl className="grid grid-cols-2 gap-3 text-sm">
        <div><dt className="text-muted">Born</dt><dd>{person.birthDate ?? "Not set"}</dd></div>
        <div><dt className="text-muted">Sex</dt><dd className="capitalize">{person.sex ?? "Not set"}</dd></div>
        <div><dt className="text-muted">Blood type</dt><dd>{person.bloodType ?? "Not set"}</dd></div>
        <div><dt className="text-muted">Primary provider</dt><dd>{primary ? primary.name : "Not set"}</dd></div>
      </dl>
      <Snapshot title="Allergies" lines={active(lists.allergies).map((item) => [item.substance, item.reaction, item.severity].filter(Boolean).join(" · "))} empty="None recorded" />
      <Snapshot title="Problems" lines={active(lists.problems).filter((item) => item.status === "active").map((item) => item.displayName)} empty="None recorded" />
      <Snapshot title="Medications" lines={active(lists.medications).filter((item) => item.status === "active").map((item) => [item.name, item.dose, item.doseUnit, item.frequency].filter(Boolean).join(" "))} empty="None recorded" />
      <Snapshot title="Implants" lines={active(lists.implants).map((item) => item.name)} empty="None recorded" />
      <Snapshot title="Emergency contacts" lines={active(lists.contacts).map((item) => [item.name, item.relationship, item.phone].filter(Boolean).join(" · "))} empty="None recorded" />
      <Snapshot title="Pharmacy" lines={active(lists.pharmacies).map((item) => [item.name, item.phone].filter(Boolean).join(" · "))} empty="None recorded" />
      <Snapshot title="Insurance" lines={active(lists.insurance).map((item) => [item.payer, item.memberId].filter(Boolean).join(" · "))} empty="None recorded" />
    </article>
  );
}

function Snapshot({ title, lines, empty }: { title: string; lines: string[]; empty: string }) {
  return (
    <section>
      <h3 className="font-serif text-2xl text-ink">{title}</h3>
      {lines.length === 0 ? <p className="text-sm text-muted">{empty}</p> : (
        <ul className="mt-1 list-disc pl-5 text-sm">
          {lines.map((line, index) => (
            <li key={`${index}-${line}`}>{line}</li>
          ))}
        </ul>
      )}
    </section>
  );
}
