-- Preserve the two historical VIP1 contracts, offer a single 9,000 FCFA advance
-- once accrued, pay the remainder only at maturity, and make confirmed top-up spins
-- claimable through authenticated, idempotent database functions.
alter table public.vip_subscriptions
  add column if not exists early_payout_xof bigint not null default 0,
  add column if not exists early_payout_transaction_id uuid unique references public.wallet_transactions(id) on delete restrict;
do $$
begin
  if not exists (select 1 from pg_constraint where conname='vip_early_payout_within_total') then
    alter table public.vip_subscriptions add constraint vip_early_payout_within_total
      check (early_payout_xof >= 0 and early_payout_xof <= total_credit_xof);
  end if;
end $$;

create or replace function public.kpyx_claim_legacy_vip_advance(p_subscription_id uuid)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  uid uuid := (select auth.uid());
  sub public.vip_subscriptions%rowtype;
  accrued bigint;
  wallet_balance bigint;
  tx_id uuid;
begin
  if uid is null then raise exception 'authentication_required'; end if;
  select * into sub from public.vip_subscriptions
   where id=p_subscription_id and user_id=uid for update;
  if not found then raise exception 'subscription_not_found'; end if;
  if not (sub.plan_id='VIP1' and sub.price_xof=5000 and sub.daily_credit_xof=670
          and sub.total_credit_xof=60300 and sub.duration_days=90) then
    raise exception 'legacy_advance_not_available';
  end if;
  if sub.status<>'active' or sub.ends_at<=now() then raise exception 'subscription_not_active'; end if;
  if sub.early_payout_xof>0 or sub.early_payout_transaction_id is not null then
    raise exception 'legacy_advance_already_claimed';
  end if;
  accrued := least(sub.total_credit_xof,
    greatest(0,floor(extract(epoch from (least(now(),sub.ends_at)-sub.starts_at))/86400)::bigint)
      * sub.daily_credit_xof);
  if accrued<9000 then raise exception 'legacy_advance_threshold_not_reached'; end if;

  update public.wallets set balance_xof=balance_xof+9000,updated_at=now()
   where user_id=uid returning balance_xof into wallet_balance;
  if not found then raise exception 'wallet_not_found'; end if;
  insert into public.wallet_transactions(user_id,kind,direction,amount_xof,status,description)
  values(uid,'vip_payout','credit',9000,'confirmed','Avance de 9 000 FCFA sur ancien VIP1')
  returning id into tx_id;
  update public.vip_subscriptions set early_payout_xof=9000,early_payout_transaction_id=tx_id where id=sub.id;
  insert into public.notifications(user_id,title,body,kind)
  values(uid,'Avance VIP disponible','9 000 FCFA ont été ajoutés à votre solde. Le solde restant de ce forfait sera versé à son échéance.','account');
  return jsonb_build_object('ok',true,'paid_xof',9000,'remaining_at_maturity_xof',sub.total_credit_xof-9000,'wallet_balance_xof',wallet_balance);
end;
$$;
revoke all on function public.kpyx_claim_legacy_vip_advance(uuid) from public,anon;
grant execute on function public.kpyx_claim_legacy_vip_advance(uuid) to authenticated;

create or replace function public.kpyx_spin_lottery()
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  uid uuid := (select auth.uid());
  spin_id uuid;
  prize bigint;
  prizes bigint[] := array[100,200,500,1000,2000,5000,10000,20000]::bigint[];
  wallet_balance bigint;
  tx_id uuid;
begin
  if uid is null then raise exception 'authentication_required'; end if;
  select s.id into spin_id
    from public.lottery_spins s
    join public.payment_events pe on pe.id=s.qualifying_payment_event_id
   where s.user_id=uid and s.status='available'
     and pe.event_type='topup' and pe.status='confirmed' and pe.amount_xof>=3000
   order by s.created_at limit 1 for update of s skip locked;
  if spin_id is null then return jsonb_build_object('ok',false,'error','spin_unavailable'); end if;

  prize := prizes[1+floor(random()*array_length(prizes,1))::integer];
  update public.lottery_spins set status='used',prize_xof=prize,spun_at=now()
   where id=spin_id and status='available';
  if not found then return jsonb_build_object('ok',false,'error','spin_unavailable'); end if;
  update public.wallets set balance_xof=balance_xof+prize,updated_at=now()
   where user_id=uid returning balance_xof into wallet_balance;
  if not found then raise exception 'wallet_not_found'; end if;
  insert into public.wallet_transactions(user_id,kind,direction,amount_xof,status,description)
  values(uid,'lottery_prize','credit',prize,'confirmed','Gain de la roue de la chance') returning id into tx_id;
  insert into public.notifications(user_id,title,body,kind)
  values(uid,'Gain de la roue','Vous avez gagné '||prize::text||' FCFA. Le montant a été ajouté à votre solde.','account');
  return jsonb_build_object('ok',true,'spin_id',spin_id,'prize_xof',prize,'wallet_balance_xof',wallet_balance,'transaction_id',tx_id);
end;
$$;
revoke all on function public.kpyx_spin_lottery() from public,anon;
grant execute on function public.kpyx_spin_lottery() to authenticated;

create or replace function public.kpyx_settle_matured_vips(p_user_id uuid)
returns bigint language plpgsql security definer set search_path = '' as $$
declare
  sub record;
  tx_id uuid;
  balance bigint;
  due bigint;
  settled bigint := 0;
begin
  if p_user_id is null then raise exception 'authentication_required'; end if;
  for sub in
    update public.vip_subscriptions set status='completed',settled_at=now()
     where user_id=p_user_id and status='active' and ends_at<=now()
     returning id,user_id,plan_id,total_credit_xof,early_payout_xof
  loop
    due:=greatest(0,sub.total_credit_xof-sub.early_payout_xof);
    if due>0 then
      update public.wallets set balance_xof=balance_xof+due,updated_at=now()
       where user_id=sub.user_id returning balance_xof into balance;
      if not found then raise exception 'wallet_not_found'; end if;
      insert into public.wallet_transactions(user_id,kind,direction,amount_xof,status,description)
      values(sub.user_id,'vip_payout','credit',due,'confirmed',
        case when sub.early_payout_xof>0 then 'Solde du forfait VIP '||sub.plan_id||' à échéance'
             else 'Crédits à échéance du forfait '||sub.plan_id end)
      returning id into tx_id;
      update public.vip_subscriptions set payout_transaction_id=tx_id where id=sub.id;
      insert into public.notifications(user_id,title,body,kind)
      values(sub.user_id,'Crédits VIP disponibles',
        sub.plan_id||' arrivé à échéance : '||due::text||' FCFA ajoutés à votre solde.'
        ||case when sub.early_payout_xof>0 then ' Une avance de '||sub.early_payout_xof::text||' FCFA avait déjà été versée.' else '' end,
        'account');
    else
      insert into public.notifications(user_id,title,body,kind)
      values(sub.user_id,'Forfait VIP arrivé à échéance',
        sub.plan_id||' est arrivé à échéance. Tous les crédits prévus ont déjà été versés.','account');
    end if;
    settled:=settled+due;
  end loop;
  return settled;
end;
$$;
revoke all on function public.kpyx_settle_matured_vips(uuid) from public,anon,authenticated;
grant execute on function public.kpyx_settle_matured_vips(uuid) to service_role;

