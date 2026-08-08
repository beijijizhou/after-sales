begin;

create or replace function public.upsert_app_role(
    p_role_key text,
    p_role_name text,
    p_description text,
    p_permissions text[],
    p_changed_by text
)
returns table (role_key text, role_name text, description text)
language plpgsql
security definer
set search_path = public
as $$
declare
    normalized_key text := lower(trim(p_role_key));
    normalized_name text := trim(p_role_name);
    normalized_actor text := trim(p_changed_by);
    old_snapshot jsonb;
    new_snapshot jsonb;
    audit_action text;
begin
    if not public.app_actor_can_manage_access(normalized_actor) then
        raise exception 'Only an access administrator can configure roles';
    end if;
    if normalized_key !~ '^[a-z][a-z0-9_]{2,31}$' then
        raise exception 'Invalid role key';
    end if;
    if normalized_name = '' then
        raise exception 'Role name is required';
    end if;
    if exists (
        select 1 from unnest(coalesce(p_permissions, array[]::text[])) requested
        where not exists (
            select 1 from public.app_permissions p
            where p.permission_key = requested
        )
    ) then
        raise exception 'Unknown permission';
    end if;
    if normalized_key = 'admin'
       and not ('can_manage_access' = any(coalesce(p_permissions, array[]::text[]))) then
        raise exception 'Admin role must retain access management';
    end if;

    select jsonb_build_object(
        'role_name', r.role_name,
        'description', r.description,
        'permissions', coalesce((
            select jsonb_agg(rp.permission_key order by rp.permission_key)
            from public.app_role_permissions rp
            where rp.role_key = r.role_key
        ), '[]'::jsonb)
    ) into old_snapshot
    from public.app_roles r
    where r.role_key = normalized_key
    for update;

    audit_action := case when old_snapshot is null then 'create' else 'update' end;
    insert into public.app_roles (
        role_key, role_name, description, is_system,
        created_by, updated_by, updated_at
    ) values (
        normalized_key, normalized_name, coalesce(p_description, ''), false,
        normalized_actor, normalized_actor, now()
    )
    on conflict on constraint app_roles_pkey do update set
        role_name = excluded.role_name,
        description = excluded.description,
        updated_by = excluded.updated_by,
        updated_at = excluded.updated_at;

    delete from public.app_role_permissions rp
    where rp.role_key = normalized_key;
    insert into public.app_role_permissions (role_key, permission_key)
    select normalized_key, permission_key
    from unnest(coalesce(p_permissions, array[]::text[])) permission_key
    on conflict do nothing;

    new_snapshot := jsonb_build_object(
        'role_name', normalized_name,
        'description', coalesce(p_description, ''),
        'permissions', to_jsonb(coalesce(p_permissions, array[]::text[]))
    );
    insert into public.app_role_change_audit (
        role_key, action, old_snapshot, new_snapshot, changed_by
    ) values (
        normalized_key, audit_action, old_snapshot, new_snapshot,
        normalized_actor
    );
    return query select normalized_key, normalized_name, coalesce(p_description, '');
end;
$$;

revoke all on function public.upsert_app_role(text, text, text, text[], text)
    from public, anon, authenticated;
grant execute on function public.upsert_app_role(text, text, text, text[], text)
    to service_role;

commit;
