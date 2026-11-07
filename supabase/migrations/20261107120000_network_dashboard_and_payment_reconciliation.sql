-- Server-side, privacy-safe network aggregates and authenticated Jeko reconciliation.
create or replace function public.kpyx_apply_jeko_topup(p_reference text,p_transaction_id text,p_status text,p_amount_xof bigint)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
  payment public.payment_events%rowtype;
  inviter uuid;
begin
  if p_status not in ('confirmed', 'failed') then raise exception 'invalid_payment_status'; end if;
  select * into payment
    from public.payment_events
   where provider = 'jeko' and provider_event_id = p_reference
   for update;
  if not found then raise exception 'payment_reference_not_found'; end if;
  if payment.status <> 'pending' then return false; end if;
  if payment.amount_xof <> p_amount_xof then raise exception 'payment_amount_mismatch'; end if;

  update public.payment_events
     set status = p_status,
         metadata = metadata || jsonb_build_object('jeko_transaction_id', p_transaction_id),
         confirmed_at = case when p_status = 'confirmed' then now() else null end
   where id = payment.id;

  if p_status = 'failed' then
    insert into public.notifications(user_id, title, body, kind)
    values (payment.user_id, 'Recharge non aboutie', 'Le paiement n’a pas été confirmé. Aucun montant n’a été crédité.', 'payment');
    return true;
  end if;

  update public.wallets
     set balance_xof = balance_xof + payment.amount_xof, updated_at = now()
   where user_id = payment.user_id;
  if not found then raise exception 'wallet_not_found'; end if;
  insert into public.wallet_transactions(user_id, payment_event_id, kind, direction, amount_xof, status, description)
  values (payment.user_id, payment.id, 'topup', 'credit', payment.amount_xof, 'confirmed', 'Recharge Jèko confirmée')
  on conflict (payment_event_id) do nothing;
  insert into public.notifications(user_id, title, body, kind)
  values (payment.user_id, 'Recharge confirmée', 'Votre portefeuille a été crédité de ' || payment.amount_xof::text || ' FCFA.', 'payment');

  if payment.amount_xof >= 3000 then
    insert into public.lottery_spins(user_id, qualifying_payment_event_id)
    values (payment.user_id, payment.id) on conflict (qualifying_payment_event_id) do nothing;

    select p.referred_by into inviter from public.profiles p where p.id = payment.user_id;
    if inviter is not null then
      -- Serialize referrals for one inviter so simultaneous deposits cannot exceed the 3-credit cap.
      perform 1 from public.profiles where id = inviter for update;
      if (select count(*) from public.referral_credits where referrer_user_id = inviter) < 3 then
        insert into public.referral_credits(referrer_user_id, invited_user_id, qualifying_payment_event_id)
        values (inviter, payment.user_id, payment.id)
        on conflict (invited_user_id) do nothing;
      end if;
    end if;
  end if;
  return true;
end;
$$;
revoke all on function public.kpyx_apply_jeko_topup(text, text, text, bigint) from public, anon, authenticated;
grant execute on function public.kpyx_apply_jeko_topup(text, text, text, bigint) to service_role;

create or replace function public.kpyx_network_dashboard()
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
  with recursive network(user_id, depth, path) as (
    select p.id, 1, array[p.id]
      from public.profiles p
     where p.referred_by = (select auth.uid())
    union all
    select p.id, n.depth + 1, n.path || p.id
      from public.profiles p
      join network n on p.referred_by = n.user_id
     where n.depth < 3 and not (p.id = any(n.path))
  ),
  payment_activity as (
    select distinct pe.user_id
      from public.payment_events pe
      join network n on n.user_id = pe.user_id
     where pe.status = 'confirmed'
       and pe.confirmed_at >= now() - interval '30 days'
  ),
  network_orders as (
    select coalesce(sum(o.total_xof), 0)::bigint as total_xof
      from public.orders o
      join network n on n.user_id = o.user_id
     where o.status in ('paid', 'fulfilling', 'fulfilled')
  ),
  referral_benefits as (
    select coalesce(sum(r.amount_xof) filter (where r.status <> 'expired'), 0)::bigint as total_xof,
           coalesce(sum(r.amount_xof) filter (
             where r.status <> 'expired'
               and r.created_at >= date_trunc('week', now())
           ), 0)::bigint as week_xof
      from public.referral_credits r
     where r.referrer_user_id = (select auth.uid())
  )
  select jsonb_build_object(
    'total_members', (select count(*)::integer from network),
    'active_members', (select count(*)::integer from payment_activity),
    'direct_members', (select count(*)::integer from network where depth = 1),
    'level_1_members', (select count(*)::integer from network where depth = 1),
    'level_2_members', (select count(*)::integer from network where depth = 2),
    'level_3_members', (select count(*)::integer from network where depth = 3),
    'direct_active_members', (
      select count(*)::integer
        from network n join payment_activity a on a.user_id = n.user_id
       where n.depth = 1
    ),
    'network_subscriptions_xof', (select total_xof from network_orders),
    'referral_benefits_total_xof', (select total_xof from referral_benefits),
    'referral_benefits_week_xof', (select week_xof from referral_benefits)
  );
$$;

revoke all on function public.kpyx_network_dashboard() from public, anon;
grant execute on function public.kpyx_network_dashboard() to authenticated;

