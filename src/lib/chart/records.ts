import { createServerFn } from "@tanstack/react-start";
import { z } from "zod";
import { authMiddleware } from "@/lib/auth/middleware";
import { getSql, type Sql } from "@/lib/db";
import { assertSameHousehold } from "./access";

const dateField = z
  .string()
  .regex(/^\d{4}-\d{2}-\d{2}$/)
  .nullable()
  .optional()
  .transform((value) => value || null);

const timeField = z
  .string()
  .regex(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/)
  .nullable()
  .optional()
  .transform((value) => value || null);

const textField = (max: number) =>
  z
    .string()
    .trim()
    .max(max)
    .nullable()
    .optional()
    .transform((value) => (value ? value : null));

const idField = z.string().min(1).nullable().optional().transform((value) => value || null);

const profileId = z.string().min(1);

const VOIDABLE = [
  "provider",
  "encounter",
  "problem",
  "allergy",
  "medication",
  "immunization",
  "procedure_event",
  "family_history",
  "social_history",
  "vital",
  "implant",
  "insurance",
  "pharmacy",
  "emergency_contact",
  "appointment",
] as const;

type Voidable = (typeof VOIDABLE)[number];

export type VoidKind = Voidable;

export type Link = { providerId: string; role: string; name: string };

export type Provider = {
  id: string;
  name: string;
  credentials: string | null;
  specialty: string | null;
  address: string | null;
  phone: string | null;
  fax: string | null;
  email: string | null;
  website: string | null;
  portalUrl: string | null;
  isPrimary: boolean;
  notes: string | null;
  status: string;
};

export type Encounter = {
  id: string;
  type: string;
  startsAt: string | null;
  endsAt: string | null;
  facility: string | null;
  reason: string | null;
  notes: string | null;
  status: string;
  links: Link[];
};

export type Problem = {
  id: string;
  displayName: string;
  icd10: string | null;
  onset: string | null;
  resolvedOn: string | null;
  notes: string | null;
  status: string;
};

export type Allergy = {
  id: string;
  substance: string;
  reaction: string | null;
  severity: string | null;
  onset: string | null;
  notes: string | null;
  status: string;
};

export type Medication = {
  id: string;
  name: string;
  dose: string | null;
  doseUnit: string | null;
  route: string | null;
  frequency: string | null;
  startOn: string | null;
  stopOn: string | null;
  prescriber: string | null;
  indication: string | null;
  notes: string | null;
  status: string;
};

export type Immunization = {
  id: string;
  vaccine: string;
  cvx: string | null;
  givenOn: string | null;
  lot: string | null;
  site: string | null;
  notes: string | null;
  status: string;
};

export type Procedure = {
  id: string;
  name: string;
  performedOn: string | null;
  laterality: string | null;
  providerName: string | null;
  facility: string | null;
  notes: string | null;
  encounterId: string | null;
  status: string;
};

export type FamilyHistory = {
  id: string;
  relationship: string;
  condition: string;
  ageAtOnset: string | null;
  deceased: boolean;
  notes: string | null;
  status: string;
};

export type SocialHistory = {
  id: string;
  asOf: string | null;
  smoking: string | null;
  alcohol: string | null;
  substances: string | null;
  occupation: string | null;
  livingSituation: string | null;
  notes: string | null;
  status: string;
};

export type Vital = {
  id: string;
  kind: string;
  systolic: string | null;
  value: string | null;
  unit: string | null;
  measuredAt: string | null;
  status: string;
};

export type Implant = {
  id: string;
  kind: string | null;
  name: string;
  model: string | null;
  laterality: string | null;
  implantedOn: string | null;
  facility: string | null;
  mriNote: string | null;
  udi: string | null;
  notes: string | null;
  status: string;
};

export type Insurance = {
  id: string;
  payer: string;
  planName: string | null;
  memberId: string | null;
  groupNumber: string | null;
  phone: string | null;
  status: string;
};

export type Pharmacy = {
  id: string;
  name: string;
  phone: string | null;
  fax: string | null;
  address: string | null;
  status: string;
};

export type EmergencyContact = {
  id: string;
  name: string;
  relationship: string | null;
  phone: string | null;
  status: string;
};

export type Appointment = {
  id: string;
  startsAt: string | null;
  providerName: string | null;
  place: string | null;
  reason: string | null;
  visitStatus: string;
  status: string;
};

export type ChartLists = {
  providers: Provider[];
  encounters: Encounter[];
  problems: Problem[];
  allergies: Allergy[];
  medications: Medication[];
  immunizations: Immunization[];
  procedures: Procedure[];
  family: FamilyHistory[];
  social: SocialHistory[];
  vitals: Vital[];
  implants: Implant[];
  insurance: Insurance[];
  pharmacies: Pharmacy[];
  contacts: EmergencyContact[];
  appointments: Appointment[];
};

function str(value: unknown): string | null {
  if (value == null) return null;
  const text = String(value);
  return text.length ? text : null;
}

function on(value: unknown): boolean {
  return value === true;
}

async function scope(userId: string, ownedProfileId: string): Promise<Sql> {
  const sql = await getSql();
  const members = await sql<{ household_id: string }>`
    select household_id from household_member where user_id = ${userId}
  `;
  const profiles = await sql<{ household_id: string }>`
    select household_id from profile where id = ${ownedProfileId}
  `;
  assertSameHousehold(profiles[0]?.household_id, members[0]?.household_id ?? "");
  return sql;
}

function visible(showVoided: boolean) {
  return showVoided;
}

async function loadLists(sql: Sql, ownedProfileId: string, showVoided: boolean): Promise<ChartLists> {
  const show = visible(showVoided);
  const providers = await sql<{
    id: string;
    name: string;
    credentials: string | null;
    specialty: string | null;
    address: string | null;
    phone: string | null;
    fax: string | null;
    email: string | null;
    website: string | null;
    portal_url: string | null;
    is_primary: boolean;
    notes: string | null;
    status: string;
  }>`
    select id, name, credentials, specialty, address, phone, fax, email, website, portal_url,
           is_primary, notes, status
    from provider
    where profile_id = ${ownedProfileId} and (${show} or status <> 'entered_in_error')
    order by is_primary desc, name
  `;
  const encounters = await sql<{
    id: string;
    type: string;
    starts_at: string | null;
    ends_at: string | null;
    facility: string | null;
    reason: string | null;
    notes: string | null;
    status: string;
  }>`
    select id, type,
           to_char(starts_at, 'YYYY-MM-DD"T"HH24:MI') as starts_at,
           to_char(ends_at, 'YYYY-MM-DD"T"HH24:MI') as ends_at,
           facility, reason, notes, status
    from encounter
    where profile_id = ${ownedProfileId} and (${show} or status <> 'entered_in_error')
    order by starts_at desc nulls last, created_at desc
  `;
  const links = await sql<{
    encounter_id: string;
    provider_id: string;
    role: string;
    name: string;
  }>`
    select ep.encounter_id, ep.provider_id, ep.role, p.name
    from encounter_provider ep
    join encounter e on e.id = ep.encounter_id
    join provider p on p.id = ep.provider_id
    where e.profile_id = ${ownedProfileId}
  `;
  const problems = await sql<Record<string, unknown>>`
    select id, display_name, icd10, onset, resolved_on, notes, status
    from problem
    where profile_id = ${ownedProfileId} and (${show} or status <> 'entered_in_error')
    order by status, display_name
  `;
  const allergies = await sql<Record<string, unknown>>`
    select id, substance, reaction, severity, onset, notes, status
    from allergy
    where profile_id = ${ownedProfileId} and (${show} or status <> 'entered_in_error')
    order by substance
  `;
  const medications = await sql<Record<string, unknown>>`
    select id, name, dose, dose_unit, route, frequency, start_on, stop_on, prescriber, indication, notes, status
    from medication
    where profile_id = ${ownedProfileId} and (${show} or status <> 'entered_in_error')
    order by status, name
  `;
  const immunizations = await sql<Record<string, unknown>>`
    select id, vaccine, cvx, given_on, lot, site, notes, status
    from immunization
    where profile_id = ${ownedProfileId} and (${show} or status <> 'entered_in_error')
    order by given_on desc nulls last, vaccine
  `;
  const procedures = await sql<Record<string, unknown>>`
    select id, name, performed_on, laterality, provider_name, facility, notes, encounter_id, status
    from procedure_event
    where profile_id = ${ownedProfileId} and (${show} or status <> 'entered_in_error')
    order by performed_on desc nulls last, name
  `;
  const family = await sql<Record<string, unknown>>`
    select id, relationship, condition, age_at_onset, deceased, notes, status
    from family_history
    where profile_id = ${ownedProfileId} and (${show} or status <> 'entered_in_error')
    order by relationship, condition
  `;
  const social = await sql<Record<string, unknown>>`
    select id, as_of, smoking, alcohol, substances, occupation, living_situation, notes, status
    from social_history
    where profile_id = ${ownedProfileId} and (${show} or status <> 'entered_in_error')
    order by as_of desc nulls last
  `;
  const vitals = await sql<Record<string, unknown>>`
    select id, kind, systolic::text as systolic, value::text as value, unit,
           to_char(measured_at, 'YYYY-MM-DD"T"HH24:MI') as measured_at, status
    from vital
    where profile_id = ${ownedProfileId} and (${show} or status <> 'entered_in_error')
    order by measured_at desc nulls last
  `;
  const implants = await sql<Record<string, unknown>>`
    select id, kind, name, model, laterality, implanted_on, facility, mri_note, udi, notes, status
    from implant
    where profile_id = ${ownedProfileId} and (${show} or status <> 'entered_in_error')
    order by implanted_on desc nulls last, name
  `;
  const insurance = await sql<Record<string, unknown>>`
    select id, payer, plan_name, member_id, group_number, phone, status
    from insurance
    where profile_id = ${ownedProfileId} and (${show} or status <> 'entered_in_error')
    order by payer
  `;
  const pharmacies = await sql<Record<string, unknown>>`
    select id, name, phone, fax, address, status
    from pharmacy
    where profile_id = ${ownedProfileId} and (${show} or status <> 'entered_in_error')
    order by name
  `;
  const contacts = await sql<Record<string, unknown>>`
    select id, name, relationship, phone, status
    from emergency_contact
    where profile_id = ${ownedProfileId} and (${show} or status <> 'entered_in_error')
    order by name
  `;
  const appointments = await sql<Record<string, unknown>>`
    select id, to_char(starts_at, 'YYYY-MM-DD"T"HH24:MI') as starts_at,
           provider_name, place, reason, visit_status, status
    from appointment
    where profile_id = ${ownedProfileId} and (${show} or status <> 'entered_in_error')
    order by starts_at desc nulls last
  `;

  const linksByEncounter = new Map<string, Link[]>();
  for (const link of links) {
    const list = linksByEncounter.get(link.encounter_id) ?? [];
    list.push({ providerId: link.provider_id, role: link.role, name: link.name });
    linksByEncounter.set(link.encounter_id, list);
  }

  return {
    providers: providers.map((row) => ({
      id: row.id,
      name: row.name,
      credentials: row.credentials,
      specialty: row.specialty,
      address: row.address,
      phone: row.phone,
      fax: row.fax,
      email: row.email,
      website: row.website,
      portalUrl: row.portal_url,
      isPrimary: row.is_primary,
      notes: row.notes,
      status: row.status,
    })),
    encounters: encounters.map((row) => ({
      id: row.id,
      type: row.type,
      startsAt: row.starts_at,
      endsAt: row.ends_at,
      facility: row.facility,
      reason: row.reason,
      notes: row.notes,
      status: row.status,
      links: linksByEncounter.get(row.id) ?? [],
    })),
    problems: problems.map((row) => ({
      id: String(row.id),
      displayName: String(row.display_name),
      icd10: str(row.icd10),
      onset: str(row.onset),
      resolvedOn: str(row.resolved_on),
      notes: str(row.notes),
      status: String(row.status),
    })),
    allergies: allergies.map((row) => ({
      id: String(row.id),
      substance: String(row.substance),
      reaction: str(row.reaction),
      severity: str(row.severity),
      onset: str(row.onset),
      notes: str(row.notes),
      status: String(row.status),
    })),
    medications: medications.map((row) => ({
      id: String(row.id),
      name: String(row.name),
      dose: str(row.dose),
      doseUnit: str(row.dose_unit),
      route: str(row.route),
      frequency: str(row.frequency),
      startOn: str(row.start_on),
      stopOn: str(row.stop_on),
      prescriber: str(row.prescriber),
      indication: str(row.indication),
      notes: str(row.notes),
      status: String(row.status),
    })),
    immunizations: immunizations.map((row) => ({
      id: String(row.id),
      vaccine: String(row.vaccine),
      cvx: str(row.cvx),
      givenOn: str(row.given_on),
      lot: str(row.lot),
      site: str(row.site),
      notes: str(row.notes),
      status: String(row.status),
    })),
    procedures: procedures.map((row) => ({
      id: String(row.id),
      name: String(row.name),
      performedOn: str(row.performed_on),
      laterality: str(row.laterality),
      providerName: str(row.provider_name),
      facility: str(row.facility),
      notes: str(row.notes),
      encounterId: str(row.encounter_id),
      status: String(row.status),
    })),
    family: family.map((row) => ({
      id: String(row.id),
      relationship: String(row.relationship),
      condition: String(row.condition),
      ageAtOnset: str(row.age_at_onset),
      deceased: on(row.deceased),
      notes: str(row.notes),
      status: String(row.status),
    })),
    social: social.map((row) => ({
      id: String(row.id),
      asOf: str(row.as_of),
      smoking: str(row.smoking),
      alcohol: str(row.alcohol),
      substances: str(row.substances),
      occupation: str(row.occupation),
      livingSituation: str(row.living_situation),
      notes: str(row.notes),
      status: String(row.status),
    })),
    vitals: vitals.map((row) => ({
      id: String(row.id),
      kind: String(row.kind),
      systolic: str(row.systolic),
      value: str(row.value),
      unit: str(row.unit),
      measuredAt: str(row.measured_at),
      status: String(row.status),
    })),
    implants: implants.map((row) => ({
      id: String(row.id),
      kind: str(row.kind),
      name: String(row.name),
      model: str(row.model),
      laterality: str(row.laterality),
      implantedOn: str(row.implanted_on),
      facility: str(row.facility),
      mriNote: str(row.mri_note),
      udi: str(row.udi),
      notes: str(row.notes),
      status: String(row.status),
    })),
    insurance: insurance.map((row) => ({
      id: String(row.id),
      payer: String(row.payer),
      planName: str(row.plan_name),
      memberId: str(row.member_id),
      groupNumber: str(row.group_number),
      phone: str(row.phone),
      status: String(row.status),
    })),
    pharmacies: pharmacies.map((row) => ({
      id: String(row.id),
      name: String(row.name),
      phone: str(row.phone),
      fax: str(row.fax),
      address: str(row.address),
      status: String(row.status),
    })),
    contacts: contacts.map((row) => ({
      id: String(row.id),
      name: String(row.name),
      relationship: str(row.relationship),
      phone: str(row.phone),
      status: String(row.status),
    })),
    appointments: appointments.map((row) => ({
      id: String(row.id),
      startsAt: str(row.starts_at),
      providerName: str(row.provider_name),
      place: str(row.place),
      reason: str(row.reason),
      visitStatus: String(row.visit_status),
      status: String(row.status),
    })),
  };
}

type Col = { column: string; value: unknown };

async function upsert(
  sql: Sql,
  table: Voidable,
  ownedProfileId: string,
  userId: string,
  id: string | null,
  cols: Col[],
): Promise<string> {
  if (id) {
    const sets = cols.map((col, index) => `${col.column} = $${index + 1}`).join(", ");
    const values = cols.map((col) => col.value);
    const rows = await sql.query<{ id: string }>(
      `update ${table} set ${sets}, updated_at = now() where id = $${cols.length + 1} and profile_id = $${cols.length + 2} returning id`,
      [...values, id, ownedProfileId],
    );
    if (!rows[0]) throw new Error("Not found");
    return id;
  }
  const newId = crypto.randomUUID();
  const columns = ["id", "profile_id", ...cols.map((col) => col.column), "created_by"];
  const placeholders = columns.map((_, index) => `$${index + 1}`).join(", ");
  await sql.query(
    `insert into ${table} (${columns.join(", ")}) values (${placeholders})`,
    [newId, ownedProfileId, ...cols.map((col) => col.value), userId],
  );
  return newId;
}

const base = { id: idField, profileId };

const saveShape = z.discriminatedUnion("kind", [
  z.object({
    kind: z.literal("provider"),
    ...base,
    name: z.string().trim().min(1).max(200),
    credentials: textField(80),
    specialty: textField(120),
    address: textField(300),
    phone: textField(40),
    fax: textField(40),
    email: textField(200),
    website: textField(300),
    portalUrl: textField(300),
    isPrimary: z.boolean().optional().default(false),
    notes: textField(2000),
  }),
  z.object({
    kind: z.literal("problem"),
    ...base,
    displayName: z.string().trim().min(1).max(200),
    icd10: textField(20),
    onset: dateField,
    resolvedOn: dateField,
    notes: textField(2000),
    status: z.enum(["active", "resolved"]).optional().default("active"),
  }),
  z.object({
    kind: z.literal("allergy"),
    ...base,
    substance: z.string().trim().min(1).max(200),
    reaction: textField(200),
    severity: z.enum(["mild", "moderate", "severe", "unknown"]).nullable().optional(),
    onset: dateField,
    notes: textField(2000),
  }),
  z.object({
    kind: z.literal("medication"),
    ...base,
    name: z.string().trim().min(1).max(200),
    dose: textField(40),
    doseUnit: textField(40),
    route: textField(40),
    frequency: textField(80),
    startOn: dateField,
    stopOn: dateField,
    prescriber: textField(200),
    indication: textField(200),
    notes: textField(2000),
    status: z.enum(["active", "stopped", "held"]).optional().default("active"),
  }),
  z.object({
    kind: z.literal("immunization"),
    ...base,
    vaccine: z.string().trim().min(1).max(200),
    cvx: textField(20),
    givenOn: dateField,
    lot: textField(40),
    site: textField(40),
    notes: textField(2000),
  }),
  z.object({
    kind: z.literal("procedure_event"),
    ...base,
    name: z.string().trim().min(1).max(200),
    performedOn: dateField,
    laterality: textField(40),
    providerName: textField(200),
    facility: textField(200),
    notes: textField(2000),
    encounterId: textField(80),
  }),
  z.object({
    kind: z.literal("family_history"),
    ...base,
    relationship: z.string().trim().min(1).max(80),
    condition: z.string().trim().min(1).max(200),
    ageAtOnset: textField(20),
    deceased: z.boolean().optional().default(false),
    notes: textField(2000),
  }),
  z.object({
    kind: z.literal("social_history"),
    ...base,
    asOf: dateField,
    smoking: textField(200),
    alcohol: textField(200),
    substances: textField(200),
    occupation: textField(200),
    livingSituation: textField(200),
    notes: textField(2000),
  }),
  z.object({
    kind: z.literal("vital"),
    ...base,
    vitalKind: z.enum(["bp", "heart_rate", "weight", "height", "temperature", "spo2"]),
    systolic: z.number().nullable().optional(),
    value: z.number().nullable().optional(),
    unit: textField(20),
    measuredAt: timeField,
  }),
  z.object({
    kind: z.literal("implant"),
    ...base,
    implantKind: textField(80),
    name: z.string().trim().min(1).max(200),
    model: textField(80),
    laterality: textField(40),
    implantedOn: dateField,
    facility: textField(200),
    mriNote: textField(200),
    udi: textField(80),
    notes: textField(2000),
  }),
  z.object({
    kind: z.literal("insurance"),
    ...base,
    payer: z.string().trim().min(1).max(200),
    planName: textField(200),
    memberId: textField(80),
    groupNumber: textField(80),
    phone: textField(40),
  }),
  z.object({
    kind: z.literal("pharmacy"),
    ...base,
    name: z.string().trim().min(1).max(200),
    phone: textField(40),
    fax: textField(40),
    address: textField(300),
  }),
  z.object({
    kind: z.literal("emergency_contact"),
    ...base,
    name: z.string().trim().min(1).max(200),
    relationship: textField(80),
    phone: textField(40),
  }),
  z.object({
    kind: z.literal("appointment"),
    ...base,
    startsAt: timeField,
    providerName: textField(200),
    place: textField(200),
    reason: textField(200),
    visitStatus: z.enum(["planned", "done", "cancelled"]).optional().default("planned"),
  }),
]);

export type SavePayload = z.input<typeof saveShape>;

export const listChart = createServerFn({ method: "POST" })
  .middleware([authMiddleware])
  .validator((input: unknown) =>
    z.object({ profileId, showVoided: z.boolean().optional().default(false) }).parse(input),
  )
  .handler(async ({ context, data }): Promise<ChartLists> => {
    const sql = await scope(context.userId, data.profileId);
    return loadLists(sql, data.profileId, data.showVoided);
  });

export const voidRecord = createServerFn({ method: "POST" })
  .middleware([authMiddleware])
  .validator((input: unknown) =>
    z
      .object({
        profileId,
        kind: z.enum(VOIDABLE),
        id: z.string().min(1),
        showVoided: z.boolean().optional().default(false),
      })
      .parse(input),
  )
  .handler(async ({ context, data }): Promise<ChartLists> => {
    const sql = await scope(context.userId, data.profileId);
    const rows = await sql.query<{ id: string }>(
      `update ${data.kind} set status = 'entered_in_error', updated_at = now() where id = $1 and profile_id = $2 returning id`,
      [data.id, data.profileId],
    );
    if (!rows[0]) throw new Error("Not found");
    return loadLists(sql, data.profileId, data.showVoided);
  });

export const saveRecord = createServerFn({ method: "POST" })
  .middleware([authMiddleware])
  .validator((input: unknown) => saveShape.parse(input))
  .handler(async ({ context, data }): Promise<ChartLists> => {
    const sql = await scope(context.userId, data.profileId);
    if (data.kind === "provider") {
      const id = await upsert(sql, "provider", data.profileId, context.userId, data.id, [
        { column: "name", value: data.name },
        { column: "credentials", value: data.credentials },
        { column: "specialty", value: data.specialty },
        { column: "address", value: data.address },
        { column: "phone", value: data.phone },
        { column: "fax", value: data.fax },
        { column: "email", value: data.email },
        { column: "website", value: data.website },
        { column: "portal_url", value: data.portalUrl },
        { column: "is_primary", value: data.isPrimary },
        { column: "notes", value: data.notes },
      ]);
      if (data.isPrimary) {
        await sql`
          update provider set is_primary = false, updated_at = now()
          where profile_id = ${data.profileId} and id <> ${id} and is_primary
        `;
      }
    } else if (data.kind === "problem") {
      await upsert(sql, "problem", data.profileId, context.userId, data.id, [
        { column: "display_name", value: data.displayName },
        { column: "icd10", value: data.icd10 },
        { column: "onset", value: data.onset },
        { column: "resolved_on", value: data.resolvedOn },
        { column: "notes", value: data.notes },
        { column: "status", value: data.status },
      ]);
    } else if (data.kind === "allergy") {
      await upsert(sql, "allergy", data.profileId, context.userId, data.id, [
        { column: "substance", value: data.substance },
        { column: "reaction", value: data.reaction },
        { column: "severity", value: data.severity ?? null },
        { column: "onset", value: data.onset },
        { column: "notes", value: data.notes },
      ]);
    } else if (data.kind === "medication") {
      await upsert(sql, "medication", data.profileId, context.userId, data.id, [
        { column: "name", value: data.name },
        { column: "dose", value: data.dose },
        { column: "dose_unit", value: data.doseUnit },
        { column: "route", value: data.route },
        { column: "frequency", value: data.frequency },
        { column: "start_on", value: data.startOn },
        { column: "stop_on", value: data.stopOn },
        { column: "prescriber", value: data.prescriber },
        { column: "indication", value: data.indication },
        { column: "notes", value: data.notes },
        { column: "status", value: data.status },
      ]);
    } else if (data.kind === "immunization") {
      await upsert(sql, "immunization", data.profileId, context.userId, data.id, [
        { column: "vaccine", value: data.vaccine },
        { column: "cvx", value: data.cvx },
        { column: "given_on", value: data.givenOn },
        { column: "lot", value: data.lot },
        { column: "site", value: data.site },
        { column: "notes", value: data.notes },
      ]);
    } else if (data.kind === "procedure_event") {
      if (data.encounterId) {
        const owned = await sql<{ id: string }>`
          select id from encounter where id = ${data.encounterId} and profile_id = ${data.profileId}
        `;
        if (!owned[0]) throw new Error("Not found");
      }
      await upsert(sql, "procedure_event", data.profileId, context.userId, data.id, [
        { column: "name", value: data.name },
        { column: "performed_on", value: data.performedOn },
        { column: "laterality", value: data.laterality },
        { column: "provider_name", value: data.providerName },
        { column: "facility", value: data.facility },
        { column: "notes", value: data.notes },
        { column: "encounter_id", value: data.encounterId },
      ]);
    } else if (data.kind === "family_history") {
      await upsert(sql, "family_history", data.profileId, context.userId, data.id, [
        { column: "relationship", value: data.relationship },
        { column: "condition", value: data.condition },
        { column: "age_at_onset", value: data.ageAtOnset },
        { column: "deceased", value: data.deceased },
        { column: "notes", value: data.notes },
      ]);
    } else if (data.kind === "social_history") {
      await upsert(sql, "social_history", data.profileId, context.userId, data.id, [
        { column: "as_of", value: data.asOf },
        { column: "smoking", value: data.smoking },
        { column: "alcohol", value: data.alcohol },
        { column: "substances", value: data.substances },
        { column: "occupation", value: data.occupation },
        { column: "living_situation", value: data.livingSituation },
        { column: "notes", value: data.notes },
      ]);
    } else if (data.kind === "vital") {
      if (data.vitalKind === "bp" && (data.systolic == null || data.value == null)) {
        throw new Error("Blood pressure needs both numbers");
      }
      if (data.vitalKind !== "bp" && data.value == null) {
        throw new Error("A value is required");
      }
      await upsert(sql, "vital", data.profileId, context.userId, data.id, [
        { column: "kind", value: data.vitalKind },
        { column: "systolic", value: data.vitalKind === "bp" ? data.systolic : null },
        { column: "value", value: data.value },
        { column: "unit", value: data.unit },
        { column: "measured_at", value: data.measuredAt },
      ]);
    } else if (data.kind === "implant") {
      await upsert(sql, "implant", data.profileId, context.userId, data.id, [
        { column: "kind", value: data.implantKind },
        { column: "name", value: data.name },
        { column: "model", value: data.model },
        { column: "laterality", value: data.laterality },
        { column: "implanted_on", value: data.implantedOn },
        { column: "facility", value: data.facility },
        { column: "mri_note", value: data.mriNote },
        { column: "udi", value: data.udi },
        { column: "notes", value: data.notes },
      ]);
    } else if (data.kind === "insurance") {
      await upsert(sql, "insurance", data.profileId, context.userId, data.id, [
        { column: "payer", value: data.payer },
        { column: "plan_name", value: data.planName },
        { column: "member_id", value: data.memberId },
        { column: "group_number", value: data.groupNumber },
        { column: "phone", value: data.phone },
      ]);
    } else if (data.kind === "pharmacy") {
      await upsert(sql, "pharmacy", data.profileId, context.userId, data.id, [
        { column: "name", value: data.name },
        { column: "phone", value: data.phone },
        { column: "fax", value: data.fax },
        { column: "address", value: data.address },
      ]);
    } else if (data.kind === "emergency_contact") {
      await upsert(sql, "emergency_contact", data.profileId, context.userId, data.id, [
        { column: "name", value: data.name },
        { column: "relationship", value: data.relationship },
        { column: "phone", value: data.phone },
      ]);
    } else {
      await upsert(sql, "appointment", data.profileId, context.userId, data.id, [
        { column: "starts_at", value: data.startsAt },
        { column: "provider_name", value: data.providerName },
        { column: "place", value: data.place },
        { column: "reason", value: data.reason },
        { column: "visit_status", value: data.visitStatus },
      ]);
    }
    return loadLists(sql, data.profileId, false);
  });

const encounterInput = z.object({
  id: idField,
  profileId,
  type: z.enum([
    "office_visit",
    "telehealth",
    "ed",
    "hospital_stay",
    "lab",
    "imaging",
    "procedure",
    "immunization_visit",
    "patient_entered",
    "other",
  ]),
  startsAt: timeField,
  endsAt: timeField,
  facility: textField(200),
  reason: textField(300),
  notes: textField(2000),
  links: z
    .array(
      z.object({
        providerId: z.string().min(1),
        role: z.enum(["attending", "ordering", "consulting", "primary"]),
      }),
    )
    .max(12),
});

export const saveEncounter = createServerFn({ method: "POST" })
  .middleware([authMiddleware])
  .validator((input: unknown) => encounterInput.parse(input))
  .handler(async ({ context, data }): Promise<ChartLists> => {
    const sql = await scope(context.userId, data.profileId);
    for (const link of data.links) {
      const rows = await sql<{ id: string }>`
        select id from provider where id = ${link.providerId} and profile_id = ${data.profileId}
      `;
      if (!rows[0]) throw new Error("Not found");
    }
    const id = await upsert(sql, "encounter", data.profileId, context.userId, data.id, [
      { column: "type", value: data.type },
      { column: "starts_at", value: data.startsAt },
      { column: "ends_at", value: data.endsAt },
      { column: "facility", value: data.facility },
      { column: "reason", value: data.reason },
      { column: "notes", value: data.notes },
    ]);
    await sql`delete from encounter_provider where encounter_id = ${id}`;
    for (const link of data.links) {
      await sql`
        insert into encounter_provider (encounter_id, provider_id, role)
        values (${id}, ${link.providerId}, ${link.role})
      `;
    }
    return loadLists(sql, data.profileId, false);
  });
