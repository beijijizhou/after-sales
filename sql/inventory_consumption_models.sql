create table if not exists public.inventory_consumption_models (
    id uuid primary key default gen_random_uuid(),
    model_name text not null,
    category text not null,
    client text not null default '',
    brand text not null default '',
    order_quantity integer not null check (order_quantity > 0),
    color text not null,
    size text not null,
    consumption_quantity integer not null check (consumption_quantity >= 0),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (model_name, category, client, brand, order_quantity, color, size)
);

grant select, insert, update on public.inventory_consumption_models to anon;
grant select, insert, update on public.inventory_consumption_models to authenticated;
grant select, insert, update on public.inventory_consumption_models to service_role;

insert into public.inventory_consumption_models (
    model_name,
    category,
    client,
    brand,
    order_quantity,
    color,
    size,
    consumption_quantity
)
values
    ('Haloo 15000订单消耗', '黑白短袖', 'Haloo', 'Haloo', 15000, '白', 'S', 308),
    ('Haloo 15000订单消耗', '黑白短袖', 'Haloo', 'Haloo', 15000, '黑', 'S', 758),
    ('Haloo 15000订单消耗', '黑白短袖', 'Haloo', 'Haloo', 15000, '白', 'M', 562),
    ('Haloo 15000订单消耗', '黑白短袖', 'Haloo', 'Haloo', 15000, '黑', 'M', 1431),
    ('Haloo 15000订单消耗', '黑白短袖', 'Haloo', 'Haloo', 15000, '白', 'L', 763),
    ('Haloo 15000订单消耗', '黑白短袖', 'Haloo', 'Haloo', 15000, '黑', 'L', 2225),
    ('Haloo 15000订单消耗', '黑白短袖', 'Haloo', 'Haloo', 15000, '白', 'XL', 815),
    ('Haloo 15000订单消耗', '黑白短袖', 'Haloo', 'Haloo', 15000, '黑', 'XL', 2741),
    ('Haloo 15000订单消耗', '黑白短袖', 'Haloo', 'Haloo', 15000, '白', '2XL', 617),
    ('Haloo 15000订单消耗', '黑白短袖', 'Haloo', 'Haloo', 15000, '黑', '2XL', 2160),
    ('Haloo 15000订单消耗', '黑白短袖', 'Haloo', 'Haloo', 15000, '白', '3XL', 531),
    ('Haloo 15000订单消耗', '黑白短袖', 'Haloo', 'Haloo', 15000, '黑', '3XL', 1501),
    ('Haloo 15000订单消耗', '黑白短袖', 'Haloo', 'Haloo', 15000, '白', '4XL', 119),
    ('Haloo 15000订单消耗', '黑白短袖', 'Haloo', 'Haloo', 15000, '黑', '4XL', 398),
    ('Haloo 15000订单消耗', '黑白短袖', 'Haloo', 'Haloo', 15000, '白', '5XL', 158),
    ('Haloo 15000订单消耗', '黑白短袖', 'Haloo', 'Haloo', 15000, '黑', '5XL', 581)
on conflict (model_name, category, client, brand, order_quantity, color, size)
do update set
    consumption_quantity = excluded.consumption_quantity,
    updated_at = now();
