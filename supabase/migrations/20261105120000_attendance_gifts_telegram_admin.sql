-- Daily attendance rewards, single-use/limited gift codes, and admin notifications.

alter table public.wallet_transactions drop constraint if exists wallet_transactions_kind_check;
alter table public.wallet_transactions add constraint wallet_transactions_kind_check
  check (kind in ('topup','purchase','refund','referral_credit','welcome_bonus','withdrawal','lottery_prize','attendance_bonus','gift_bonus'));

create table if not exists public.daily_attendance_claims (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  attendance_date date not null,
  amount_xof bigint not null default 100 check (amount_xof=100),
  created_at timestamptz not null default now(),
  unique(user_id,attendance_date)
);
create index if not exists daily_attendance_user_date_idx on public.daily_attendance_claims(user_id,attendance_date desc);
alter table public.daily_attendance_claims enable row level security;
create policy "attendance_read_own" on public.daily_attendance_claims for select to authenticated using ((select auth.uid())=user_id);
grant select on public.daily_attendance_claims to authenticated;
revoke insert,update,delete on public.daily_attendance_claims from anon,authenticated;

create table if not exists public.gift_codes (
  code text primary key check (code=upper(code) and length(code) between 4 and 40),
  amount_xof bigint not null check (amount_xof between 1 and 100000000),
  max_uses integer not null check (max_uses between 1 and 1000000),
  used_count integer not null default 0 check (used_count between 0 and max_uses),
  active boolean not null default true,
  expires_at timestamptz,
  created_at timestamptz not null default now()
);
create table if not exists public.gift_code_redemptions (
  id uuid primary key default gen_random_uuid(),
  code text not null references public.gift_codes(code) on delete restrict,
  user_id uuid not null references auth.users(id) on delete cascade,
  amount_xof bigint not null check (amount_xof>0),
  redeemed_at timestamptz not null default now(),
  unique(code,user_id)
);
create index if not exists gift_redemptions_user_created_idx on public.gift_code_redemptions(user_id,redeemed_at desc);
alter table public.gift_codes enable row level security;
alter table public.gift_code_redemptions enable row level security;
create policy "gift_redemptions_read_own" on public.gift_code_redemptions for select to authenticated using ((select auth.uid())=user_id);
grant select on public.gift_code_redemptions to authenticated;
revoke all on public.gift_codes from public,anon,authenticated;
revoke insert,update,delete on public.gift_code_redemptions from public,anon,authenticated;

create or replace function public.kpyx_claim_daily_attendance()
returns jsonb language plpgsql security definer set search_path=''
as $$
declare uid uuid:=auth.uid(); today date:=(now() at time zone 'Africa/Abidjan')::date; claimed_id uuid; current_balance bigint;
begin
 if uid is null then raise exception 'authentication_required'; end if;
 insert into public.daily_attendance_claims(user_id,attendance_date,amount_xof)
 values(uid,today,100) on conflict(user_id,attendance_date) do nothing returning id into claimed_id;
 if claimed_id is null then
   select balance_xof into current_balance from public.wallets where user_id=uid;
   return jsonb_build_object('claimed',false,'amount_xof',100,'balance_xof',coalesce(current_balance,0),'attendance_date',today);
 end if;
 update public.wallets set balance_xof=balance_xof+100,updated_at=now() where user_id=uid returning balance_xof into current_balance;
 if current_balance is null then raise exception 'wallet_not_found'; end if;
 insert into public.wallet_transactions(user_id,kind,direction,amount_xof,status,description)
 values(uid,'attendance_bonus','credit',100,'confirmed','Prime de présence quotidienne');
 insert into public.notifications(user_id,title,body,kind)
 values(uid,'Présence validée','Votre solde a été crédité de 100 FCFA.','account');
 return jsonb_build_object('claimed',true,'amount_xof',100,'balance_xof',current_balance,'attendance_date',today);
end $$;
revoke all on function public.kpyx_claim_daily_attendance() from public,anon;
grant execute on function public.kpyx_claim_daily_attendance() to authenticated;

create or replace function public.kpyx_redeem_gift_code(p_code text)
returns jsonb language plpgsql security definer set search_path=''
as $$
declare uid uuid:=auth.uid(); normalized text:=upper(trim(coalesce(p_code,''))); gift public.gift_codes%rowtype; new_balance bigint;
begin
 if uid is null then raise exception 'authentication_required'; end if;
 if length(normalized)<4 or length(normalized)>40 then return jsonb_build_object('redeemed',false,'reason','invalid'); end if;
 select * into gift from public.gift_codes where code=normalized for update;
 if not found or not gift.active or (gift.expires_at is not null and gift.expires_at<=now()) then return jsonb_build_object('redeemed',false,'reason','invalid'); end if;
 if exists(select 1 from public.gift_code_redemptions where code=normalized and user_id=uid) then return jsonb_build_object('redeemed',false,'reason','already_used'); end if;
 if gift.used_count>=gift.max_uses then return jsonb_build_object('redeemed',false,'reason','exhausted'); end if;
 insert into public.gift_code_redemptions(code,user_id,amount_xof) values(normalized,uid,gift.amount_xof);
 update public.gift_codes set used_count=used_count+1 where code=normalized;
 update public.wallets set balance_xof=balance_xof+gift.amount_xof,updated_at=now() where user_id=uid returning balance_xof into new_balance;
 if new_balance is null then raise exception 'wallet_not_found'; end if;
 insert into public.wallet_transactions(user_id,kind,direction,amount_xof,status,description)
 values(uid,'gift_bonus','credit',gift.amount_xof,'confirmed','Code cadeau '||normalized);
 insert into public.notifications(user_id,title,body,kind)
 values(uid,'Code cadeau utilisé','Votre solde a été crédité de '||gift.amount_xof::text||' FCFA.','account');
 return jsonb_build_object('redeemed',true,'amount_xof',gift.amount_xof,'balance_xof',new_balance);
end $$;
revoke all on function public.kpyx_redeem_gift_code(text) from public,anon;
grant execute on function public.kpyx_redeem_gift_code(text) to authenticated;

create or replace function public.kpyx_my_gift_redemptions()
returns table(code text,amount_xof bigint,redeemed_at timestamptz)
language sql stable security definer set search_path=''
as $$ select r.code,r.amount_xof,r.redeemed_at from public.gift_code_redemptions r where r.user_id=auth.uid() order by r.redeemed_at desc limit 50 $$;
revoke all on function public.kpyx_my_gift_redemptions() from public,anon;
grant execute on function public.kpyx_my_gift_redemptions() to authenticated;

create table if not exists public.telegram_admin_updates (
  update_id bigint primary key,
  processed_at timestamptz not null default now()
);
alter table public.telegram_admin_updates enable row level security;
revoke all on public.telegram_admin_updates from public,anon,authenticated;
