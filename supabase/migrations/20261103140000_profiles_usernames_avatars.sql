-- Unique member usernames, editable profile fields and private upload ownership.
alter table public.profiles
  add column if not exists username text,
  add column if not exists first_name text not null default '',
  add column if not exists last_name text not null default '',
  add column if not exists date_of_birth date,
  add column if not exists avatar_path text,
  add column if not exists username_changed_at timestamptz;

create unique index if not exists profiles_username_lower_uidx
  on public.profiles (lower(username))
  where username is not null;

alter table public.profiles
  drop constraint if exists profiles_username_format_check;
alter table public.profiles
  add constraint profiles_username_format_check
  check (username is null or username ~ '^[A-Za-z0-9][A-Za-z0-9._-]{2,23}$');

create or replace function public.is_kpyx_username_available(p_username text)
returns boolean
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  candidate text := btrim(coalesce(p_username, ''));
begin
  if candidate !~ '^[A-Za-z0-9][A-Za-z0-9._-]{2,23}$' then
    return false;
  end if;
  return not exists (
    select 1 from public.profiles p
     where lower(p.username) = lower(candidate)
       and p.id is distinct from (select auth.uid())
  );
end;
$$;

revoke all on function public.is_kpyx_username_available(text) from public;
grant execute on function public.is_kpyx_username_available(text) to anon, authenticated;

create or replace function public.update_my_profile(
  p_username text,
  p_first_name text default '',
  p_last_name text default '',
  p_date_of_birth date default null,
  p_avatar_path text default null
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  uid uuid := (select auth.uid());
  candidate text := btrim(coalesce(p_username, ''));
  current_profile public.profiles%rowtype;
  next_avatar text;
begin
  if uid is null then
    raise exception using errcode = '28000', message = 'authentication_required';
  end if;
  if candidate !~ '^[A-Za-z0-9][A-Za-z0-9._-]{2,23}$' then
    raise exception using errcode = '22023', message = 'username_invalid';
  end if;
  if p_date_of_birth is not null and p_date_of_birth > current_date then
    raise exception using errcode = '22023', message = 'date_of_birth_invalid';
  end if;
  if p_avatar_path is not null and p_avatar_path <> ''
     and p_avatar_path <> (uid::text || '/avatar.webp') then
    raise exception using errcode = '22023', message = 'avatar_path_invalid';
  end if;

  select * into current_profile
    from public.profiles where id = uid for update;
  if not found then
    raise exception using errcode = 'P0002', message = 'profile_not_found';
  end if;

  if current_profile.username is not null
     and current_profile.username is distinct from candidate
     and current_profile.username_changed_at is not null
     and now() < current_profile.username_changed_at + interval '1 month' then
    raise exception using errcode = 'P0001', message = 'username_cooldown';
  end if;

  next_avatar := coalesce(nullif(p_avatar_path, ''), current_profile.avatar_path);
  update public.profiles
     set username = candidate,
         display_name = candidate,
         first_name = left(btrim(coalesce(p_first_name, '')), 80),
         last_name = left(btrim(coalesce(p_last_name, '')), 80),
         date_of_birth = p_date_of_birth,
         avatar_path = next_avatar,
         username_changed_at = case
           when current_profile.username is not null
            and current_profile.username is distinct from candidate then now()
           else current_profile.username_changed_at
         end,
         updated_at = now()
   where id = uid;

  return jsonb_build_object(
    'username', candidate,
    'first_name', left(btrim(coalesce(p_first_name, '')), 80),
    'last_name', left(btrim(coalesce(p_last_name, '')), 80),
    'date_of_birth', p_date_of_birth,
    'avatar_path', next_avatar,
    'username_changed_at', case
      when current_profile.username is not null
       and current_profile.username is distinct from candidate then now()
      else current_profile.username_changed_at
    end
  );
exception
  when unique_violation then
    raise exception using errcode = 'P0001', message = 'username_taken';
end;
$$;

revoke all on function public.update_my_profile(text, text, text, date, text) from public, anon;
grant execute on function public.update_my_profile(text, text, text, date, text) to authenticated;

-- The auth trigger inserts the chosen username in the same transaction as signup,
-- so simultaneous registrations cannot claim the same case-insensitive name.
create or replace function public.handle_new_kpyx_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  inviter uuid;
  candidate text := btrim(coalesce(new.raw_user_meta_data ->> 'username', ''));
begin
  if candidate !~ '^[A-Za-z0-9][A-Za-z0-9._-]{2,23}$' then
    raise exception using errcode = 'P0001', message = 'username_invalid';
  end if;

  if coalesce(new.raw_user_meta_data ->> 'referral_code', '') <> '' then
    select p.id into inviter
      from public.profiles p
     where upper(p.referral_code) = upper(new.raw_user_meta_data ->> 'referral_code')
     limit 1;
  end if;

  insert into public.profiles (
    id, phone_e164, display_name, username, referral_code, referred_by
  ) values (
    new.id,
    coalesce(new.phone, nullif(new.raw_user_meta_data ->> 'phone_e164', '')),
    candidate,
    candidate,
    'KPYX-' || upper(substr(replace(new.id::text, '-', ''), 1, 8)),
    case when inviter = new.id then null else inviter end
  ) on conflict (id) do nothing;

  insert into public.wallets (user_id) values (new.id) on conflict (user_id) do nothing;
  return new;
exception
  when unique_violation then
    raise exception using errcode = 'P0001', message = 'username_taken';
end;
$$;

revoke execute on function public.handle_new_kpyx_user() from public, anon, authenticated;

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('kpyx-avatars', 'kpyx-avatars', true, 8388608,
        array['image/jpeg', 'image/png', 'image/webp'])
on conflict (id) do update
  set public = excluded.public,
      file_size_limit = excluded.file_size_limit,
      allowed_mime_types = excluded.allowed_mime_types;

drop policy if exists "kpyx_avatars_insert_own" on storage.objects;
create policy "kpyx_avatars_insert_own" on storage.objects
  for insert to authenticated
  with check (
    bucket_id = 'kpyx-avatars'
    and (storage.foldername(name))[1] = (select auth.uid())::text
    and name = (select auth.uid())::text || '/avatar.webp'
  );

drop policy if exists "kpyx_avatars_update_own" on storage.objects;
create policy "kpyx_avatars_update_own" on storage.objects
  for update to authenticated
  using (
    bucket_id = 'kpyx-avatars'
    and (storage.foldername(name))[1] = (select auth.uid())::text
    and name = (select auth.uid())::text || '/avatar.webp'
  )
  with check (
    bucket_id = 'kpyx-avatars'
    and (storage.foldername(name))[1] = (select auth.uid())::text
    and name = (select auth.uid())::text || '/avatar.webp'
  );

drop policy if exists "kpyx_avatars_delete_own" on storage.objects;
create policy "kpyx_avatars_delete_own" on storage.objects
  for delete to authenticated
  using (
    bucket_id = 'kpyx-avatars'
    and (storage.foldername(name))[1] = (select auth.uid())::text
    and name = (select auth.uid())::text || '/avatar.webp'
  );
