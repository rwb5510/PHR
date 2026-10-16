create table if not exists provider (
  id text primary key,
  profile_id text not null references profile (id),
  name text not null,
  credentials text,
  specialty text,
  address text,
  phone text,
  fax text,
  email text,
  website text,
  portal_url text,
  is_primary boolean not null default false,
  notes text,
  status text not null default 'active',
  created_by text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint provider_status_chk check (status in ('active', 'entered_in_error'))
);

create table if not exists encounter (
  id text primary key,
  profile_id text not null references profile (id),
  type text not null,
  starts_at timestamp,
  ends_at timestamp,
  facility text,
  reason text,
  notes text,
  status text not null default 'active',
  created_by text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint encounter_type_chk check (
    type in (
      'office_visit', 'telehealth', 'ed', 'hospital_stay', 'lab', 'imaging',
      'procedure', 'immunization_visit', 'patient_entered', 'other'
    )
  ),
  constraint encounter_status_chk check (status in ('active', 'entered_in_error'))
);

create table if not exists encounter_provider (
  encounter_id text not null references encounter (id),
  provider_id text not null references provider (id),
  role text not null,
  primary key (encounter_id, provider_id, role),
  constraint encounter_provider_role_chk check (role in ('attending', 'ordering', 'consulting', 'primary'))
);

create table if not exists problem (
  id text primary key,
  profile_id text not null references profile (id),
  display_name text not null,
  icd10 text,
  onset date,
  resolved_on date,
  notes text,
  status text not null default 'active',
  created_by text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint problem_status_chk check (status in ('active', 'resolved', 'entered_in_error'))
);

create table if not exists allergy (
  id text primary key,
  profile_id text not null references profile (id),
  substance text not null,
  reaction text,
  severity text,
  onset date,
  notes text,
  status text not null default 'active',
  created_by text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint allergy_severity_chk check (severity is null or severity in ('mild', 'moderate', 'severe', 'unknown')),
  constraint allergy_status_chk check (status in ('active', 'entered_in_error'))
);

create table if not exists medication (
  id text primary key,
  profile_id text not null references profile (id),
  name text not null,
  dose text,
  dose_unit text,
  route text,
  frequency text,
  start_on date,
  stop_on date,
  prescriber text,
  indication text,
  notes text,
  status text not null default 'active',
  created_by text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint medication_status_chk check (status in ('active', 'stopped', 'held', 'entered_in_error'))
);

create table if not exists immunization (
  id text primary key,
  profile_id text not null references profile (id),
  vaccine text not null,
  cvx text,
  given_on date,
  lot text,
  site text,
  notes text,
  status text not null default 'active',
  created_by text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint immunization_status_chk check (status in ('active', 'entered_in_error'))
);

create table if not exists procedure_event (
  id text primary key,
  profile_id text not null references profile (id),
  name text not null,
  performed_on date,
  laterality text,
  provider_name text,
  facility text,
  notes text,
  encounter_id text,
  status text not null default 'active',
  created_by text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint procedure_status_chk check (status in ('active', 'entered_in_error'))
);

create table if not exists family_history (
  id text primary key,
  profile_id text not null references profile (id),
  relationship text not null,
  condition text not null,
  age_at_onset text,
  deceased boolean not null default false,
  notes text,
  status text not null default 'active',
  created_by text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint family_history_status_chk check (status in ('active', 'entered_in_error'))
);

create table if not exists social_history (
  id text primary key,
  profile_id text not null references profile (id),
  as_of date,
  smoking text,
  alcohol text,
  substances text,
  occupation text,
  living_situation text,
  notes text,
  status text not null default 'active',
  created_by text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint social_history_status_chk check (status in ('active', 'entered_in_error'))
);

create table if not exists vital (
  id text primary key,
  profile_id text not null references profile (id),
  kind text not null,
  systolic numeric,
  value numeric,
  unit text,
  measured_at timestamp,
  status text not null default 'active',
  created_by text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint vital_kind_chk check (kind in ('bp', 'heart_rate', 'weight', 'height', 'temperature', 'spo2')),
  constraint vital_status_chk check (status in ('active', 'entered_in_error'))
);

create table if not exists implant (
  id text primary key,
  profile_id text not null references profile (id),
  kind text,
  name text not null,
  model text,
  laterality text,
  implanted_on date,
  facility text,
  mri_note text,
  udi text,
  notes text,
  status text not null default 'active',
  created_by text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint implant_status_chk check (status in ('active', 'entered_in_error'))
);

create table if not exists insurance (
  id text primary key,
  profile_id text not null references profile (id),
  payer text not null,
  plan_name text,
  member_id text,
  group_number text,
  phone text,
  status text not null default 'active',
  created_by text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint insurance_status_chk check (status in ('active', 'entered_in_error'))
);

create table if not exists pharmacy (
  id text primary key,
  profile_id text not null references profile (id),
  name text not null,
  phone text,
  fax text,
  address text,
  status text not null default 'active',
  created_by text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint pharmacy_status_chk check (status in ('active', 'entered_in_error'))
);

create table if not exists emergency_contact (
  id text primary key,
  profile_id text not null references profile (id),
  name text not null,
  relationship text,
  phone text,
  status text not null default 'active',
  created_by text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint emergency_contact_status_chk check (status in ('active', 'entered_in_error'))
);

create table if not exists appointment (
  id text primary key,
  profile_id text not null references profile (id),
  starts_at timestamp,
  provider_name text,
  place text,
  reason text,
  visit_status text not null default 'planned',
  status text not null default 'active',
  created_by text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint appointment_visit_chk check (visit_status in ('planned', 'done', 'cancelled')),
  constraint appointment_status_chk check (status in ('active', 'entered_in_error'))
);

create index if not exists provider_profile_idx on provider (profile_id);
create index if not exists encounter_profile_idx on encounter (profile_id);
create index if not exists problem_profile_idx on problem (profile_id);
create index if not exists allergy_profile_idx on allergy (profile_id);
create index if not exists medication_profile_idx on medication (profile_id);
create index if not exists immunization_profile_idx on immunization (profile_id);
create index if not exists procedure_event_profile_idx on procedure_event (profile_id);
create index if not exists family_history_profile_idx on family_history (profile_id);
create index if not exists social_history_profile_idx on social_history (profile_id);
create index if not exists vital_profile_idx on vital (profile_id);
create index if not exists implant_profile_idx on implant (profile_id);
create index if not exists insurance_profile_idx on insurance (profile_id);
create index if not exists pharmacy_profile_idx on pharmacy (profile_id);
create index if not exists emergency_contact_profile_idx on emergency_contact (profile_id);
create index if not exists appointment_profile_idx on appointment (profile_id);
