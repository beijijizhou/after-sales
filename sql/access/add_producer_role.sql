alter table public.users
drop constraint if exists user_role_check;

update public.users
set role = 'producer'
where lower(trim(user_name)) = 'damo';

notify pgrst, 'reload schema';
