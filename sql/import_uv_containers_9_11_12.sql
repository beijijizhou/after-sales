-- UV 9柜、11柜、12柜货柜安排。
-- 到货日期为用户确认日期，发货日期按 45 天运输周期倒推。
-- 9柜预计 7月20日到货，但实际尚未到货，因此状态为延迟。

begin;

create temporary table uv_container_seed (
    container_key text,
    shipped_date date,
    expected_arrival_date date,
    actual_arrival_date date,
    container_no text,
    category text,
    material text,
    model text,
    quantity integer,
    status text,
    note text
) on commit drop;

insert into uv_container_seed values
    (
        '9柜', date '2026-06-05', date '2026-07-20', null,
        '9柜', '牌类', '铁牌', '2030', 40000, '延迟', '400箱，100件/箱'
    ),
    (
        '9柜', date '2026-06-05', date '2026-07-20', null,
        '9柜', '牌类', '铝牌', '2030', 20000, '延迟',
        '按数量20000件计；200件/箱折算100箱，原表箱数200不一致'
    ),
    (
        '9柜', date '2026-06-05', date '2026-07-20', null,
        '9柜', '牌类', '铝牌', 'YUAN', 20100, '延迟', '67箱，300件/箱'
    ),
    (
        '9柜', date '2026-06-05', date '2026-07-20', null,
        '9柜', '牌类', '铁牌', '3040', 25000, '延迟', '500箱，50件/箱'
    ),
    (
        '9柜', date '2026-06-05', date '2026-07-20', null,
        '9柜', '牌类', '铁牌', '1040', 20000, '延迟', '200箱，100件/箱'
    ),
    (
        '11柜', date '2026-06-16', date '2026-07-31', null,
        '11柜', '牌类', '铁牌', '2030', 85000, '未到货', '850箱，100件/箱'
    ),
    (
        '11柜', date '2026-06-16', date '2026-07-31', null,
        '11柜', '牌类', '铁牌', 'YUAN', 15000, '未到货', '100箱，150件/箱'
    ),
    (
        '12柜', date '2026-06-22', date '2026-08-06', null,
        '12柜', '木板画', '挂钟', '25', 20000, '未到货', null
    ),
    (
        '12柜', date '2026-06-22', date '2026-08-06', null,
        '12柜', '牌类', '铝牌', '2030', 30000, '未到货', '150箱，200件/箱'
    ),
    (
        '12柜', date '2026-06-22', date '2026-08-06', null,
        '12柜', '牌类', '铝牌', 'YUAN', 30000, '未到货', '100箱，300件/箱'
    ),
    (
        '12柜', date '2026-06-22', date '2026-08-06', null,
        '12柜', '牌类', '铁牌', '2030', 65000, '未到货', '650箱，100件/箱'
    );

update public.inventory_container_imports target
set
    shipped_date = source.shipped_date,
    expected_arrival_date = source.expected_arrival_date,
    actual_arrival_date = source.actual_arrival_date,
    container_no = source.container_no,
    department = 'UV',
    category = source.category,
    brand = '',
    material = source.material,
    color = '白',
    size = source.model,
    quantity = source.quantity,
    unit_cost = 0,
    status = source.status,
    note = source.note,
    品牌 = '',
    材质 = source.material,
    成本 = 0,
    updated_at = now()
from uv_container_seed source
where target.container_key = source.container_key
  and target.department = 'UV'
  and coalesce(target.category, '') = source.category
  and target.brand = ''
  and target.material = source.material
  and target.color = '白'
  and target.size = source.model;

insert into public.inventory_container_imports (
    container_key, shipped_date, expected_arrival_date, actual_arrival_date,
    container_no, department, category, brand, material, color, size,
    quantity, unit_cost, status, note, 品牌, 材质, 成本
)
select
    source.container_key, source.shipped_date, source.expected_arrival_date,
    source.actual_arrival_date, source.container_no, 'UV', source.category,
    '', source.material, '白', source.model, source.quantity, 0,
    source.status, source.note, '', source.material, 0
from uv_container_seed source
where not exists (
    select 1
    from public.inventory_container_imports target
    where target.container_key = source.container_key
      and target.department = 'UV'
      and coalesce(target.category, '') = source.category
      and target.brand = ''
      and target.material = source.material
      and target.color = '白'
      and target.size = source.model
);

with sku_source as (
    select distinct category, material, model
    from uv_container_seed
),
inserted as (
    insert into public.inventory_items (
        department, category, brand, material, color, size,
        unit_cost, quantity, 品牌, 材质, 成本
    )
    select
        'UV', category, '', material, '白', model,
        0, 0, '', material, 0
    from sku_source
    on conflict do nothing
    returning
        department, category, brand, material, color, size,
        unit_cost, quantity, 品牌, 材质, 成本
)
insert into public.inventory_sku_imports (
    department, category, brand, material, color, size,
    initial_quantity, unit_cost, import_date, 品牌, 材质, 成本
)
select
    department, category, brand, material, color, size,
    quantity, unit_cost, date '2026-07-22', 品牌, 材质, 成本
from inserted;

insert into public.inventory_container_events (
    container_key, container_no, event_type, effective_date,
    previous_status, new_status, operated_by, note
)
select
    source.container_key,
    source.container_no,
    '创建',
    source.shipped_date,
    null,
    '未到货',
    'Andy',
    'UV货柜资料导入'
from (
    select distinct
        container_key, container_no, shipped_date, status
    from uv_container_seed
) source
where not exists (
    select 1
    from public.inventory_container_events event
    where event.container_key = source.container_key
      and event.event_type = '创建'
);

insert into public.inventory_container_events (
    container_key, container_no, event_type, effective_date,
    previous_status, new_status, operated_by, note
)
select
    '9柜', '9柜', '状态变更', date '2026-07-22',
    '未到货', '延迟', 'Andy',
    '更正：2026-07-20为预计到货日期，货柜实际尚未到货'
where not exists (
    select 1
    from public.inventory_container_events
    where container_key = '9柜'
      and event_type = '状态变更'
      and effective_date = date '2026-07-22'
);

commit;

notify pgrst, 'reload schema';
