alter table public.wallet_transactions
  drop constraint if exists wallet_transactions_kind_check;

alter table public.wallet_transactions
  add constraint wallet_transactions_kind_check
  check (kind in ('topup', 'purchase', 'refund', 'referral_credit', 'welcome_bonus', 'withdrawal', 'lottery_prize'));

create unique index if not exists wallet_transactions_one_welcome_bonus_per_user
  on public.wallet_transactions (user_id)
  where kind = 'welcome_bonus';

create or replace function public.award_kpyx_welcome_bonus()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  bonus_transaction_id uuid;
begin
  if new.phone_confirmed_at is not null
     and (tg_op = 'INSERT' or old.phone_confirmed_at is null) then
    insert into public.wallets (user_id, balance_xof)
    values (new.id, 0)
    on conflict (user_id) do nothing;

    insert into public.wallet_transactions (user_id, kind, direction, amount_xof, description)
    values (new.id, 'welcome_bonus', 'credit', 700, 'Bonus de bienvenue après vérification du numéro')
    on conflict (user_id) where kind = 'welcome_bonus' do nothing
    returning id into bonus_transaction_id;

    if bonus_transaction_id is not null then
      update public.wallets
         set balance_xof = balance_xof + 700,
             updated_at = now()
       where user_id = new.id;
    end if;
  end if;
  return new;
end;
$$;

revoke execute on function public.award_kpyx_welcome_bonus() from public, anon, authenticated;

drop trigger if exists on_kpyx_phone_confirmed_welcome_bonus on auth.users;
create trigger on_kpyx_phone_confirmed_welcome_bonus
  after insert or update of phone_confirmed_at on auth.users
  for each row execute function public.award_kpyx_welcome_bonus();
