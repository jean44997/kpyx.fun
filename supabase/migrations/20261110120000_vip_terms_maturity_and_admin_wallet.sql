-- Update VIP terms, settle returns only at maturity, and provide audited
-- service-role-only wallet corrections for authorized administrators.

alter table public.vip_subscriptions
  drop constraint if exists vip_subscriptions_plan_id_check;
alter table public.vip_subscriptions
  add constraint vip_subscriptions_plan_id_check
  check (plan_id in ('VIP1','VIP2','VIP3','VIP4','VIP5','VIP6','VIP7','VIP8'));
alter table public.vip_subscriptions
  add column if not exists settled_at timestamptz,
  add column if not exists payout_transaction_id uuid unique references public.wallet_transactions(id) on delete restrict;

alter table public.wallet_transactions drop constraint if exists wallet_transactions_kind_check;
alter table public.wallet_transactions add constraint wallet_transactions_kind_check
  check (kind in ('topup','purchase','refund','referral_credit','welcome_bonus','withdrawal','lottery_prize','attendance_bonus','gift_bonus','vip_payout','admin_adjustment'));

create table if not exists public.wallet_admin_adjustments (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete restrict,
  transaction_id uuid not null unique references public.wallet_transactions(id) on delete restrict,
  previous_balance_xof bigint not null check (previous_balance_xof >= 0),
  new_balance_xof bigint not null check (new_balance_xof >= 0),
  delta_xof bigint not null check (delta_xof <> 0),
  reason text not null check (length(trim(reason)) between 10 and 240),
  actor text not null default current_user,
  created_at timestamptz not null default now()
);
alter table public.wallet_admin_adjustments enable row level security;
revoke all on public.wallet_admin_adjustments from public, anon, authenticated;
grant all on public.wallet_admin_adjustments to service_role;

create or replace function public.kpyx_admin_set_wallet_balance(
  p_user_id uuid,
  p_new_balance_xof bigint,
  p_reason text
) returns jsonb
language plpgsql security definer set search_path = ''
as $$
declare
  old_balance bigint;
  delta bigint;
  tx_id uuid;
begin
  if p_user_id is null or p_new_balance_xof is null or p_new_balance_xof < 0 then
    raise exception 'invalid_wallet_adjustment';
  end if;
  if length(trim(coalesce(p_reason,''))) not between 10 and 240 then
    raise exception 'adjustment_reason_required';
  end if;
  select balance_xof into old_balance from public.wallets where user_id = p_user_id for update;
  if old_balance is null then raise exception 'wallet_not_found'; end if;
  delta := p_new_balance_xof - old_balance;
  if delta = 0 then return jsonb_build_object('ok',true,'changed',false,'balance_xof',old_balance); end if;

  update public.wallets set balance_xof = p_new_balance_xof, updated_at = now()
   where user_id = p_user_id;
  insert into public.wallet_transactions(user_id,kind,direction,amount_xof,status,description)
  values(p_user_id,'admin_adjustment',case when delta > 0 then 'credit' else 'debit' end,abs(delta),'confirmed',left(trim(p_reason),240))
  returning id into tx_id;
  insert into public.wallet_admin_adjustments(user_id,transaction_id,previous_balance_xof,new_balance_xof,delta_xof,reason,actor)
  values(p_user_id,tx_id,old_balance,p_new_balance_xof,delta,left(trim(p_reason),240),
    coalesce(nullif(current_setting('request.jwt.claim.sub',true),''),session_user));
  return jsonb_build_object('ok',true,'changed',true,'balance_xof',p_new_balance_xof,'delta_xof',delta,'transaction_id',tx_id);
end;
$$;
revoke all on function public.kpyx_admin_set_wallet_balance(uuid,bigint,text) from public,anon,authenticated;
grant execute on function public.kpyx_admin_set_wallet_balance(uuid,bigint,text) to service_role;

create or replace function public.kpyx_purchase_vip(p_user_id uuid, p_plan_id text)
returns jsonb language plpgsql security definer set search_path = ''
as $$
declare
  plan_price bigint;
  daily_credit bigint;
  total_credit bigint;
  plan_days integer;
  current_balance bigint;
  subscription_id uuid;
  maturity timestamptz;
begin
  if p_user_id is null then raise exception 'authentication_required'; end if;
  select v.price, v.daily, v.daily * v.days, v.days
    into plan_price, daily_credit, total_credit, plan_days
    from (values
      ('VIP1'::text,5000::bigint,570::bigint,15),
      ('VIP2'::text,8000::bigint,820::bigint,18),
      ('VIP3'::text,15000::bigint,2027::bigint,21),
      ('VIP4'::text,30000::bigint,2840::bigint,25),
      ('VIP5'::text,60000::bigint,4900::bigint,31),
      ('VIP6'::text,150000::bigint,12400::bigint,35),
      ('VIP7'::text,300000::bigint,27000::bigint,40),
      ('VIP8'::text,600000::bigint,50000::bigint,50)
    ) as v(id,price,daily,days)
   where v.id = upper(p_plan_id);
  if plan_price is null then return jsonb_build_object('ok',false,'error','plan_unavailable'); end if;

  select w.balance_xof into current_balance
    from public.wallets w where w.user_id = p_user_id for update;
  if current_balance is null then raise exception 'wallet_not_found'; end if;
  if current_balance < plan_price then
    return jsonb_build_object('ok',false,'error','insufficient_balance','balance_xof',current_balance,'price_xof',plan_price);
  end if;
  update public.wallets set balance_xof = balance_xof - plan_price,updated_at = now()
   where user_id = p_user_id returning balance_xof into current_balance;

  maturity := now() + make_interval(days => plan_days);
  insert into public.vip_subscriptions(user_id,plan_id,price_xof,daily_credit_xof,total_credit_xof,duration_days,starts_at,ends_at)
  values(p_user_id,upper(p_plan_id),plan_price,daily_credit,total_credit,plan_days,now(),maturity)
  returning id into subscription_id;
  insert into public.wallet_transactions(user_id,kind,direction,amount_xof,status,description)
  values(p_user_id,'purchase','debit',plan_price,'confirmed','Souscription au forfait '||upper(p_plan_id));
  insert into public.notifications(user_id,title,body,kind)
  values(p_user_id,'Forfait VIP activé',upper(p_plan_id)||' activé pour '||plan_days::text||' jours. Les crédits cumulés seront ajoutés au solde à l’échéance.','account');
  return jsonb_build_object('ok',true,'plan_id',upper(p_plan_id),'subscription_id',subscription_id,
    'balance_xof',current_balance,'price_xof',plan_price,'daily_credit_xof',daily_credit,
    'total_credit_xof',total_credit,'duration_days',plan_days,'starts_at',now(),'ends_at',maturity);
end;
$$;
revoke all on function public.kpyx_purchase_vip(uuid,text) from public,anon,authenticated;
grant execute on function public.kpyx_purchase_vip(uuid,text) to service_role;

create or replace function public.kpyx_settle_matured_vips(p_user_id uuid)
returns bigint language plpgsql security definer set search_path = ''
as $$
declare
  sub record;
  tx_id uuid;
  balance bigint;
  settled bigint := 0;
begin
  if p_user_id is null then raise exception 'authentication_required'; end if;
  for sub in
    update public.vip_subscriptions
       set status='completed',settled_at=now()
     where user_id=p_user_id and status='active' and ends_at <= now()
     returning id,user_id,plan_id,total_credit_xof
  loop
    update public.wallets set balance_xof=balance_xof+sub.total_credit_xof,updated_at=now()
     where user_id=sub.user_id returning balance_xof into balance;
    if not found then raise exception 'wallet_not_found'; end if;
    insert into public.wallet_transactions(user_id,kind,direction,amount_xof,status,description)
    values(sub.user_id,'vip_payout','credit',sub.total_credit_xof,'confirmed','Crédits à échéance du forfait '||sub.plan_id)
    returning id into tx_id;
    update public.vip_subscriptions set payout_transaction_id=tx_id where id=sub.id;
    insert into public.notifications(user_id,title,body,kind)
    values(sub.user_id,'Crédits VIP disponibles',sub.plan_id||' arrivé à échéance : '||sub.total_credit_xof::text||' FCFA ajoutés à votre solde.','account');
    settled := settled + sub.total_credit_xof;
  end loop;
  return settled;
end;
$$;
revoke all on function public.kpyx_settle_matured_vips(uuid) from public,anon,authenticated;
grant execute on function public.kpyx_settle_matured_vips(uuid) to service_role;

-- Release mature VIP credits before checking withdrawable balance.
create or replace function public.kpyx_request_withdrawal(p_user_id uuid,p_amount_xof bigint,p_method text,p_destination text)
returns uuid language plpgsql security definer set search_path=''
as $$
declare uid uuid:=p_user_id; fee bigint; rid uuid:=gen_random_uuid(); balance bigint; txid uuid;
begin
 if uid is null then raise exception 'authentication_required'; end if;
 if p_amount_xof<1200 or mod(p_amount_xof,100)<>0 then raise exception 'invalid_amount'; end if;
 if p_method not in ('wave','orange','mtn','moov','djamo') or length(trim(p_destination))<6 or length(p_destination)>80 then raise exception 'invalid_destination'; end if;
 perform public.kpyx_settle_matured_vips(uid);
 if exists(select 1 from public.withdrawal_requests where user_id=uid and status in ('pending','processing')) then raise exception 'withdrawal_already_pending'; end if;
 fee:=round(p_amount_xof*0.07);
 select balance_xof into balance from public.wallets where user_id=uid for update;
 if balance is null or balance<p_amount_xof then raise exception 'insufficient_balance'; end if;
 update public.wallets set balance_xof=balance_xof-p_amount_xof,updated_at=now() where user_id=uid;
 insert into public.withdrawal_requests(id,user_id,amount_xof,fee_xof,net_xof,payment_method,destination) values(rid,uid,p_amount_xof,fee,p_amount_xof-fee,p_method,trim(p_destination));
 insert into public.wallet_transactions(user_id,kind,direction,amount_xof,status,description) values(uid,'withdrawal','debit',p_amount_xof,'pending','Demande de retrait en attente') returning id into txid;
 update public.withdrawal_requests set wallet_transaction_id=txid where id=rid;
 insert into public.notifications(user_id,title,body,kind) values(uid,'Retrait demandé','Votre demande est en attente de traitement. Frais : '||fee::text||' FCFA.','withdrawal');
 return rid;
end $$;
revoke all on function public.kpyx_request_withdrawal(uuid,bigint,text,text) from public,anon,authenticated;
grant execute on function public.kpyx_request_withdrawal(uuid,bigint,text,text) to service_role;

