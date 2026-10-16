import { createServerFn } from "@tanstack/react-start";
import { z } from "zod";
import { authMiddleware } from "@/lib/auth/middleware";
import { getSql, type Sql } from "@/lib/db";
import { assertSameHousehold } from "./access";

const SEX = ["female", "male", "other", "unknown"] as const;
const BLOOD = ["O+", "O-", "A+", "A-", "B+", "B-", "AB+", "AB-"] as const;

const optionalText = (max: number) =>
  z
    .string()
    .trim()
    .max(max)
    .nullable()
    .optional()
    .transform((value) => (value ? value : null));

const profileFields = z.object({
  legalName: z.string().trim().min(1).max(200),
  preferredName: optionalText(200),
  birthDate: z
    .string()
    .regex(/^\d{4}-\d{2}-\d{2}$/)
    .nullable()
    .optional()
    .transform((value) => value || null),
  sex: z.enum(SEX).nullable().optional().transform((value) => value ?? null),
  bloodType: z.enum(BLOOD).nullable().optional().transform((value) => value ?? null),
  relationshipLabel: optionalText(80),
  notes: optionalText(2000),
});

export type Profile = {
  id: string;
  legalName: string;
  preferredName: string | null;
  birthDate: string | null;
  sex: string | null;
  bloodType: string | null;
  relationshipLabel: string | null;
  notes: string | null;
};

export type ChartState = {
  householdId: string;
  householdName: string;
  activeProfileId: string | null;
  profiles: Profile[];
};

type ProfileRow = {
  id: string;
  household_id: string;
  legal_name: string;
  preferred_name: string | null;
  birth_date: string | null;
  sex: string | null;
  blood_type: string | null;
  relationship_label: string | null;
  notes: string | null;
};

type MemberRow = {
  household_id: string;
  active_profile_id: string | null;
  name: string;
};

function toProfile(row: ProfileRow): Profile {
  return {
    id: row.id,
    legalName: row.legal_name,
    preferredName: row.preferred_name,
    birthDate: row.birth_date,
    sex: row.sex,
    bloodType: row.blood_type,
    relationshipLabel: row.relationship_label,
    notes: row.notes,
  };
}

async function memberFor(sql: Sql, userId: string): Promise<MemberRow | null> {
  const rows = await sql<MemberRow>`
    select m.household_id, m.active_profile_id, h.name
    from household_member m
    join household h on h.id = m.household_id
    where m.user_id = ${userId}
  `;
  return rows[0] ?? null;
}

async function requireMember(sql: Sql, userId: string): Promise<MemberRow> {
  const existing = await memberFor(sql, userId);
  if (existing) return existing;
  const householdId = crypto.randomUUID();
  try {
    await sql`insert into household (id, name) values (${householdId}, ${"My household"})`;
    await sql`
      insert into household_member (household_id, user_id)
      values (${householdId}, ${userId})
    `;
  } catch {
    const raced = await memberFor(sql, userId);
    if (raced) return raced;
    throw new Error("Could not open the household");
  }
  return { household_id: householdId, active_profile_id: null, name: "My household" };
}

async function profilesFor(sql: Sql, householdId: string): Promise<Profile[]> {
  const rows = await sql<ProfileRow>`
    select id, household_id, legal_name, preferred_name, birth_date, sex, blood_type,
           relationship_label, notes
    from profile
    where household_id = ${householdId}
    order by created_at, legal_name
  `;
  return rows.map(toProfile);
}

function stateFrom(member: MemberRow, profiles: Profile[]): ChartState {
  const active = profiles.some((profile) => profile.id === member.active_profile_id)
    ? member.active_profile_id
    : null;
  return {
    householdId: member.household_id,
    householdName: member.name,
    activeProfileId: active,
    profiles,
  };
}

async function loadState(userId: string): Promise<ChartState> {
  const sql = await getSql();
  const member = await requireMember(sql, userId);
  const profiles = await profilesFor(sql, member.household_id);
  return stateFrom(member, profiles);
}

export const getChartState = createServerFn({ method: "GET" })
  .middleware([authMiddleware])
  .handler(async ({ context }): Promise<ChartState> => loadState(context.userId));

export const createProfile = createServerFn({ method: "POST" })
  .middleware([authMiddleware])
  .validator((input: unknown) => profileFields.parse(input))
  .handler(async ({ context, data }): Promise<ChartState> => {
    const sql = await getSql();
    const member = await requireMember(sql, context.userId);
    const id = crypto.randomUUID();
    await sql`
      insert into profile (
        id, household_id, legal_name, preferred_name, birth_date, sex, blood_type,
        relationship_label, notes, created_by
      ) values (
        ${id}, ${member.household_id}, ${data.legalName}, ${data.preferredName},
        ${data.birthDate}, ${data.sex}, ${data.bloodType}, ${data.relationshipLabel},
        ${data.notes}, ${context.userId}
      )
    `;
    await sql`
      update household_member
      set active_profile_id = ${id}
      where user_id = ${context.userId} and household_id = ${member.household_id}
    `;
    return loadState(context.userId);
  });

export const updateProfile = createServerFn({ method: "POST" })
  .middleware([authMiddleware])
  .validator((input: unknown) => profileFields.extend({ id: z.string().min(1) }).parse(input))
  .handler(async ({ context, data }): Promise<ChartState> => {
    const sql = await getSql();
    const member = await requireMember(sql, context.userId);
    const rows = await sql<{ household_id: string }>`
      select household_id from profile where id = ${data.id}
    `;
    assertSameHousehold(rows[0]?.household_id, member.household_id);
    await sql`
      update profile set
        legal_name = ${data.legalName},
        preferred_name = ${data.preferredName},
        birth_date = ${data.birthDate},
        sex = ${data.sex},
        blood_type = ${data.bloodType},
        relationship_label = ${data.relationshipLabel},
        notes = ${data.notes},
        updated_at = now()
      where id = ${data.id} and household_id = ${member.household_id}
    `;
    return loadState(context.userId);
  });

export const setActiveProfile = createServerFn({ method: "POST" })
  .middleware([authMiddleware])
  .validator((input: unknown) => z.object({ profileId: z.string().min(1) }).parse(input))
  .handler(async ({ context, data }): Promise<ChartState> => {
    const sql = await getSql();
    const member = await requireMember(sql, context.userId);
    const rows = await sql<{ household_id: string }>`
      select household_id from profile where id = ${data.profileId}
    `;
    assertSameHousehold(rows[0]?.household_id, member.household_id);
    await sql`
      update household_member
      set active_profile_id = ${data.profileId}
      where user_id = ${context.userId} and household_id = ${member.household_id}
    `;
    return loadState(context.userId);
  });
