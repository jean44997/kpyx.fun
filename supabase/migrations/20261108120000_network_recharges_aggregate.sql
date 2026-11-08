-- Show all confirmed deposits made by members of the authenticated user's 3-level network.
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
  network_recharges as (
    select coalesce(sum(pe.amount_xof), 0)::bigint as total_xof
      from public.payment_events pe
      join network n on n.user_id = pe.user_id
     where pe.event_type = 'topup'
       and pe.status = 'confirmed'
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
    'network_recharges_xof', (select total_xof from network_recharges),
    -- Kept temporarily so previously cached frontends show the new cumulative amount too.
    'network_subscriptions_xof', (select total_xof from network_recharges),
    'referral_benefits_total_xof', (select total_xof from referral_benefits),
    'referral_benefits_week_xof', (select week_xof from referral_benefits)
  );
$$;

revoke all on function public.kpyx_network_dashboard() from public, anon;
grant execute on function public.kpyx_network_dashboard() to authenticated;
