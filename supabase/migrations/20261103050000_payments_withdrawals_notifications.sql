-- Payment confirmations, manual withdrawals, realtime notifications, and offer stock caps.
create table if not exists public.notifications (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  title text not null, body text not null,
  kind text not null check (kind in ('payment','withdrawal','stock','account')),
  read_at timestamptz, created_at timestamptz not null default now()
);
create index if not exists notifications_user_created_idx on public.notifications(user_id,created_at desc);
alter table public.notifications enable row level security;
create policy "notifications_read_own" on public.notifications for select to authenticated using ((select auth.uid())=user_id);
grant select on public.notifications to authenticated;
revoke insert,update,delete on public.notifications from anon,authenticated;
do $$ begin
  if not exists (select 1 from pg_publication_tables where pubname='supabase_realtime' and schemaname='public' and tablename='notifications') then
    alter publication supabase_realtime add table public.notifications;
  end if;
end $$;

create table if not exists public.withdrawal_requests (
  id uuid primary key default gen_random_uuid(), user_id uuid not null references auth.users(id) on delete restrict,
  amount_xof bigint not null check (amount_xof>=1200), fee_xof bigint not null check (fee_xof>=0), net_xof bigint not null check (net_xof>0),
  payment_method text not null check (payment_method in ('wave','orange','mtn','moov','djamo')),
  destination text not null, status text not null default 'pending' check (status in ('pending','processing','paid','rejected')),
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
  constraint withdrawal_amounts_valid check (amount_xof-fee_xof=net_xof)
);
create index if not exists withdrawal_requests_user_created_idx on public.withdrawal_requests(user_id,created_at desc);
alter table public.withdrawal_requests add column if not exists wallet_transaction_id uuid unique references public.wallet_transactions(id) on delete restrict;
alter table public.withdrawal_requests enable row level security;
create policy "withdrawals_read_own" on public.withdrawal_requests for select to authenticated using ((select auth.uid())=user_id);
grant select on public.withdrawal_requests to authenticated;
revoke insert,update,delete on public.withdrawal_requests from anon,authenticated;

create table if not exists public.digital_offer_capacity (
  product_id text primary key references public.digital_products(id) on delete cascade,
  max_customers integer not null default 25 check (max_customers=25),
  customers_served integer not null default 0 check (customers_served between 0 and max_customers),
  enabled boolean not null default true, updated_at timestamptz not null default now()
);
alter table public.digital_offer_capacity enable row level security;
create policy "offer_capacity_public_read" on public.digital_offer_capacity for select to anon,authenticated using (true);
grant select on public.digital_offer_capacity to anon,authenticated;
revoke insert,update,delete on public.digital_offer_capacity from anon,authenticated;
insert into public.digital_offer_capacity(product_id) select id from public.digital_products where category='pack' on conflict do nothing;

create or replace function public.kpyx_request_withdrawal(p_user_id uuid,p_amount_xof bigint,p_method text,p_destination text)
returns uuid language plpgsql security definer set search_path=''
as $$
declare uid uuid:=p_user_id; fee bigint; rid uuid:=gen_random_uuid(); balance bigint; txid uuid;
begin
 if uid is null then raise exception 'authentication_required'; end if;
 if p_amount_xof<1200 or mod(p_amount_xof,100)<>0 then raise exception 'invalid_amount'; end if;
 if p_method not in ('wave','orange','mtn','moov','djamo') or length(trim(p_destination))<6 or length(p_destination)>80 then raise exception 'invalid_destination'; end if;
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

create or replace function public.kpyx_apply_jeko_topup(p_reference text,p_transaction_id text,p_status text,p_amount_xof bigint)
returns boolean language plpgsql security definer set search_path=''
as $$
declare payment public.payment_events%rowtype;
begin
 if p_status not in ('confirmed','failed') then raise exception 'invalid_payment_status'; end if;
 select * into payment from public.payment_events where provider='jeko' and provider_event_id=p_reference for update;
 if not found then raise exception 'payment_reference_not_found'; end if;
 if payment.status<>'pending' then return false; end if;
 if payment.amount_xof<>p_amount_xof then raise exception 'payment_amount_mismatch'; end if;
 update public.payment_events set status=p_status,metadata=metadata||jsonb_build_object('jeko_transaction_id',p_transaction_id),confirmed_at=case when p_status='confirmed' then now() else null end where id=payment.id;
 if p_status='failed' then
   insert into public.notifications(user_id,title,body,kind) values(payment.user_id,'Recharge non aboutie','Le paiement n’a pas été confirmé. Aucun montant n’a été crédité.','payment'); return true;
 end if;
 update public.wallets set balance_xof=balance_xof+payment.amount_xof,updated_at=now() where user_id=payment.user_id;
 insert into public.wallet_transactions(user_id,payment_event_id,kind,direction,amount_xof,status,description) values(payment.user_id,payment.id,'topup','credit',payment.amount_xof,'confirmed','Recharge Jèko confirmée') on conflict(payment_event_id) do nothing;
 insert into public.notifications(user_id,title,body,kind) values(payment.user_id,'Recharge confirmée','Votre portefeuille a été crédité de '||payment.amount_xof::text||' FCFA.','payment');
 if payment.amount_xof>=3000 then
   insert into public.lottery_spins(user_id,qualifying_payment_event_id) values(payment.user_id,payment.id) on conflict(qualifying_payment_event_id) do nothing;
   insert into public.referral_credits(referrer_user_id,invited_user_id,qualifying_payment_event_id)
   select p.referred_by,payment.user_id,payment.id from public.profiles p where p.id=payment.user_id and p.referred_by is not null
   and (select count(*) from public.referral_credits r where r.referrer_user_id=p.referred_by)<3 on conflict(invited_user_id) do nothing;
 end if;
 return true;
end $$;
revoke all on function public.kpyx_apply_jeko_topup(text,text,text,bigint) from public,anon,authenticated;
grant execute on function public.kpyx_apply_jeko_topup(text,text,text,bigint) to service_role;

-- Grant the welcome bonus after account creation instead of waiting for phone confirmation.
create or replace function public.award_kpyx_welcome_bonus()
returns trigger language plpgsql security definer set search_path=''
as $$
begin
 update public.wallets set balance_xof=balance_xof+700,updated_at=now() where user_id=new.id;
 insert into public.wallet_transactions(user_id,kind,direction,amount_xof,status,description) values(new.id,'welcome_bonus','credit',700,'confirmed','Bonus de bienvenue KPYX') on conflict(user_id) where kind='welcome_bonus' do nothing;
 insert into public.notifications(user_id,title,body,kind) values(new.id,'Bienvenue chez KPYX','Votre bonus de bienvenue de 700 FCFA est disponible.','account');
 return new;
end $$;
revoke execute on function public.award_kpyx_welcome_bonus() from public,anon,authenticated;
drop trigger if exists on_kpyx_phone_confirmed_welcome_bonus on auth.users;
create trigger on_kpyx_user_created_welcome_bonus after insert on auth.users for each row execute function public.award_kpyx_welcome_bonus();
create or replace function public.kpyx_offer_stock()
returns table(product_id text, remaining integer)
language sql
stable
security definer
set search_path=''
as $$
  select p.id,
    greatest(0, least(coalesce(c.max_customers,25)-coalesce(c.customers_served,0),
      case when p.category='service' then
        (select count(*)::integer / greatest(p.access_count,1) from public.access_inventory ai where ai.product_id=p.id and ai.status='available')
      else coalesce((select min(
        (select count(*)::integer / greatest(pi.quantity,1)
         from public.access_inventory ai where ai.product_id=pi.product_id and ai.status='available')
      ) from public.pack_items pi where pi.pack_id=p.id),0) end
    ))::integer
  from public.digital_products p
  left join public.digital_offer_capacity c on c.product_id=p.id
  where p.active and coalesce(c.enabled,true);
$$;
revoke all on function public.kpyx_offer_stock() from public;
grant execute on function public.kpyx_offer_stock() to anon,authenticated;

insert into public.digital_offer_capacity(product_id)
select id from public.digital_products where active
on conflict(product_id) do nothing;
create or replace function public.kpyx_resolve_withdrawal(p_request_id uuid,p_status text)
returns boolean language plpgsql security definer set search_path=''
as $$
declare request public.withdrawal_requests%rowtype;
begin
 if p_status not in ('paid','rejected') then raise exception 'invalid_withdrawal_status'; end if;
 select * into request from public.withdrawal_requests where id=p_request_id for update;
 if not found or request.status<>'pending' then return false; end if;
 update public.withdrawal_requests set status=p_status,updated_at=now() where id=request.id;
 if p_status='rejected' then
   update public.wallets set balance_xof=balance_xof+request.amount_xof,updated_at=now() where user_id=request.user_id;
   update public.wallet_transactions set status='reversed' where id=request.wallet_transaction_id and status='pending';
   insert into public.wallet_transactions(user_id,kind,direction,amount_xof,status,description)
     values(request.user_id,'refund','credit',request.amount_xof,'confirmed','Remboursement du retrait refusé');
   insert into public.notifications(user_id,title,body,kind) values(request.user_id,'Retrait refusé','Le montant réservé a été recrédité sur votre portefeuille.','withdrawal');
 else
   insert into public.notifications(user_id,title,body,kind) values(request.user_id,'Retrait effectué','Votre retrait manuel de '||request.net_xof::text||' FCFA a été traité.','withdrawal');
 end if;
 return true;
end $$;
revoke all on function public.kpyx_resolve_withdrawal(uuid,text) from public,anon,authenticated;
grant execute on function public.kpyx_resolve_withdrawal(uuid,text) to service_role;
