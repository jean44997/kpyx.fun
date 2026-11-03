-- Keep phone + password sign-in without SMS delivery by storing the normalized
-- phone as user metadata and using a deterministic, non-routable email identity.
-- The application never sends email to this internal address.
create or replace function public.handle_new_kpyx_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  inviter uuid;
begin
  if coalesce(new.raw_user_meta_data ->> 'referral_code', '') <> '' then
    select p.id into inviter
      from public.profiles p
     where upper(p.referral_code) = upper(new.raw_user_meta_data ->> 'referral_code')
     limit 1;
  end if;

  insert into public.profiles (id, phone_e164, display_name, referral_code, referred_by)
  values (
    new.id,
    coalesce(new.phone, nullif(new.raw_user_meta_data ->> 'phone_e164', '')),
    coalesce(new.raw_user_meta_data ->> 'display_name', ''),
    'KPYX-' || upper(substr(replace(new.id::text, '-', ''), 1, 8)),
    case when inviter = new.id then null else inviter end
  )
  on conflict (id) do nothing;

  insert into public.wallets (user_id) values (new.id) on conflict (user_id) do nothing;
  return new;
end;
$$;
