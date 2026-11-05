-- Require a verified top-up before gift redemption and let users mark their own notifications read.
create or replace function public.kpyx_redeem_gift_code(p_code text)
returns jsonb language plpgsql security definer set search_path=''
as $$
declare
 uid uuid:=auth.uid();
 normalized text:=upper(trim(coalesce(p_code,'')));
 gift public.gift_codes%rowtype;
 new_balance bigint;
begin
 if uid is null then raise exception 'authentication_required'; end if;
 if length(normalized)<4 or length(normalized)>40 then return jsonb_build_object('redeemed',false,'reason','invalid'); end if;
 select * into gift from public.gift_codes where code=normalized for update;
 if not found or not gift.active or (gift.expires_at is not null and gift.expires_at<=now()) then return jsonb_build_object('redeemed',false,'reason','invalid'); end if;
 if exists(select 1 from public.gift_code_redemptions where code=normalized and user_id=uid) then return jsonb_build_object('redeemed',false,'reason','already_used'); end if;
 if gift.used_count>=gift.max_uses then return jsonb_build_object('redeemed',false,'reason','exhausted'); end if;
 if not exists (
   select 1 from public.payment_events
   where user_id=uid and event_type='topup' and status='confirmed' and amount_xof>=3000
 ) then return jsonb_build_object('redeemed',false,'reason','topup_required'); end if;
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

create or replace function public.kpyx_mark_notification_read(p_notification_id uuid)
returns boolean language plpgsql security definer set search_path=''
as $$
declare uid uuid:=auth.uid(); changed integer;
begin
 if uid is null then raise exception 'authentication_required'; end if;
 update public.notifications set read_at=coalesce(read_at,now()) where id=p_notification_id and user_id=uid;
 get diagnostics changed=row_count;
 return changed>0;
end $$;
revoke all on function public.kpyx_mark_notification_read(uuid) from public,anon;
grant execute on function public.kpyx_mark_notification_read(uuid) to authenticated;

create or replace function public.kpyx_mark_all_notifications_read()
returns integer language plpgsql security definer set search_path=''
as $$
declare uid uuid:=auth.uid(); changed integer;
begin
 if uid is null then raise exception 'authentication_required'; end if;
 update public.notifications set read_at=now() where user_id=uid and read_at is null;
 get diagnostics changed=row_count;
 return changed;
end $$;
revoke all on function public.kpyx_mark_all_notifications_read() from public,anon;
grant execute on function public.kpyx_mark_all_notifications_read() to authenticated;
