create table if not exists household (
  id text primary key,
  name text not null,
  created_at timestamptz not null default now()
);

create table if not exists household_member (
  household_id text not null references household (id),
  user_id text not null,
  active_profile_id text,
  created_at timestamptz not null default now(),
  primary key (household_id, user_id)
);

create unique index if not exists household_member_user_id_idx
  on household_member (user_id);

create table if not exists profile (
  id text primary key,
  household_id text not null references household (id),
  legal_name text not null,
  preferred_name text,
  birth_date date,
  sex text,
  blood_type text,
  relationship_label text,
  notes text,
  created_by text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint profile_sex_chk check (
    sex is null or sex in ('female', 'male', 'other', 'unknown')
  ),
  constraint profile_blood_chk check (
    blood_type is null or blood_type in ('O+', 'O-', 'A+', 'A-', 'B+', 'B-', 'AB+', 'AB-')
  )
);

create index if not exists profile_household_id_idx on profile (household_id);
