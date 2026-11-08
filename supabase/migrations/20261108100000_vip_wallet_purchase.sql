-- Atomic VIP subscription purchase: verify and debit the live wallet under one row lock.
create table if not exists public.vip_subscriptions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete restrict,
  plan_id text not null check (plan_id in ('VIP1','VIP2','VIP3','VIP4')),
  price_xof bigint not null check (price_xof > 0),
  daily_credit_xof bigint not null check (daily_credit_xof > 0),
  total_credit_xof bigint not null check (total_credit_xof > 0),
  duration_days integer not null default 90 check (duration_days > 0),
  status text not null default 'active' check (status in ('active','completed','cancelled')),
  starts_at timestamptz not null default now(),
  ends_at timestamptz not null,
  created_at timestamptz not null default now(),
  constraint vip_subscription_dates_valid check (ends_at > starts_at)
);

create index if not exists vip_subscriptions_user_created_idx
  on public.vip_subscriptions (user_id, created_at desc);

alter table public.vip_subscriptions enable row level security;
drop policy if exists vip_subscriptions_read_own on public.vip_subscriptions;
create policy vip_subscriptions_read_own on public.vip_subscriptions
  for select to authenticated using ((select auth.uid()) = user_id);
revoke all on public.vip_subscriptions from anon, authenticated;
grant select on public.vip_subscriptions to authenticated;
grant all on public.vip_subscriptions to service_role;

create or replace function public.kpyx_purchase_vip(p_user_id uuid, p_plan_id text)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  plan_price bigint;
  daily_credit bigint;
  total_credit bigint;
  current_balance bigint;
  subscription_id uuid;
begin
  select v.price, v.daily, v.total
    into plan_price, daily_credit, total_credit
    from (values
      ('VIP1'::text, 5000::bigint, 670::bigint, 60300::bigint),
      ('VIP2'::text, 8000::bigint, 1904::bigint, 171360::bigint),
      ('VIP3'::text, 15000::bigint, 3750::bigint, 337500::bigint),
      ('VIP4'::text, 30000::bigint, 7894::bigint, 710460::bigint)
    ) as v(id, price, daily, total)
   where v.id = upper(p_plan_id);
  if plan_price is null then return jsonb_build_object('ok', false, 'error', 'plan_unavailable'); end if;

  select w.balance_xof into current_balance
    from public.wallets w where w.user_id = p_user_id for update;
  if current_balance is null then raise exception 'wallet_not_found'; end if;
  if current_balance < plan_price then
    return jsonb_build_object('ok', false, 'error', 'insufficient_balance', 'balance_xof', current_balance, 'price_xof', plan_price);
  end if;

  update public.wallets
     set balance_xof = balance_xof - plan_price, updated_at = now()
   where user_id = p_user_id
   returning balance_xof into current_balance;

  insert into public.vip_subscriptions(user_id, plan_id, price_xof, daily_credit_xof, total_credit_xof, duration_days, ends_at)
  values (p_user_id, upper(p_plan_id), plan_price, daily_credit, total_credit, 90, now() + interval '90 days')
  returning id into subscription_id;

  insert into public.wallet_transactions(user_id, kind, direction, amount_xof, status, description)
  values (p_user_id, 'purchase', 'debit', plan_price, 'confirmed', 'Souscription au forfait ' || upper(p_plan_id));

  insert into public.notifications(user_id, title, body, kind)
  values (p_user_id, 'Forfait VIP activé', upper(p_plan_id) || ' a été activé. Montant débité : ' || plan_price::text || ' FCFA.', 'account');

  return jsonb_build_object('ok', true, 'plan_id', upper(p_plan_id), 'subscription_id', subscription_id, 'balance_xof', current_balance);
end;
$$;

revoke all on function public.kpyx_purchase_vip(uuid, text) from public, anon, authenticated;
grant execute on function public.kpyx_purchase_vip(uuid, text) to service_role;

