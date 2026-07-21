-- LEGACY INITIAL SETUP ONLY.
-- The current database uses the English columns from
-- inventory_department_english_columns.sql. Do not run this file on an
-- existing inventory database.

create table if not exists public.inventory_items (
    id uuid primary key default gen_random_uuid(),
    category text not null,
    品牌 text not null default '',
    材质 text not null default '180g',
    color text not null,
    size text not null,
    成本 numeric(10, 2) not null default 0,
    quantity integer not null default 0 check (quantity >= 0),
    updated_at timestamptz not null default now(),
    unique (category, 品牌, 材质, color, size)
);

create table if not exists public.inventory_movements (
    id uuid primary key default gen_random_uuid(),
    category text not null,
    品牌 text not null default '',
    材质 text not null default '180g',
    color text not null,
    size text not null,
    quantity_change integer not null,
    quantity_after integer not null,
    movement_date date not null default current_date,
    reason text,
    created_at timestamptz not null default now()
);

create table if not exists public.inventory_sku_imports (
    id uuid primary key default gen_random_uuid(),
    category text not null,
    品牌 text not null default '',
    材质 text not null default '180g',
    color text not null,
    size text not null,
    initial_quantity integer not null default 0 check (initial_quantity >= 0),
    成本 numeric(10, 2) not null default 0,
    import_date date not null default current_date,
    created_at timestamptz not null default now()
);

alter table public.inventory_movements
add column if not exists movement_date date not null default current_date;

alter table public.inventory_items
add column if not exists 材质 text not null default '180g';

alter table public.inventory_items
add column if not exists 品牌 text not null default '';

alter table public.inventory_items
add column if not exists 成本 numeric(10, 2) not null default 0;

alter table public.inventory_movements
add column if not exists 材质 text not null default '180g';

alter table public.inventory_movements
add column if not exists 品牌 text not null default '';

alter table public.inventory_sku_imports
add column if not exists 材质 text not null default '180g';

alter table public.inventory_sku_imports
add column if not exists 品牌 text not null default '';

alter table public.inventory_sku_imports
add column if not exists 成本 numeric(10, 2) not null default 0;

alter table public.inventory_items
drop constraint if exists inventory_items_category_color_size_key;

alter table public.inventory_items
drop constraint if exists "inventory_items_category_材质_color_size_key";

drop index if exists public.inventory_items_category_material_color_size_key;

create unique index if not exists inventory_items_category_brand_material_color_size_key
on public.inventory_items (category, 品牌, 材质, color, size);

create or replace function public.adjust_inventory_stock(
    p_category text,
    p_brand text,
    p_material text,
    p_color text,
    p_size text,
    p_quantity_change integer,
    p_reason text default null,
    p_movement_date date default current_date
)
returns public.inventory_items
language plpgsql
security definer
set search_path = public
as $$
declare
    current_item public.inventory_items;
begin
    insert into public.inventory_items (category, 品牌, 材质, color, size, quantity)
    values (p_category, coalesce(p_brand, ''), coalesce(nullif(p_material, ''), '180g'), p_color, p_size, 0)
    on conflict (category, 品牌, 材质, color, size) do nothing;

    select *
    into current_item
    from public.inventory_items
    where category = p_category
      and 品牌 = coalesce(p_brand, '')
      and 材质 = coalesce(nullif(p_material, ''), '180g')
      and color = p_color
      and size = p_size
    for update;

    if current_item.quantity + p_quantity_change < 0 then
        raise exception '库存不足：当前库存 %, 调整数量 %',
            current_item.quantity,
            p_quantity_change;
    end if;

    update public.inventory_items
    set quantity = quantity + p_quantity_change,
        updated_at = now()
    where id = current_item.id
    returning * into current_item;

    insert into public.inventory_movements (
        category,
        品牌,
        材质,
        color,
        size,
        quantity_change,
        quantity_after,
        movement_date,
        reason
    )
    values (
        p_category,
        current_item.品牌,
        current_item.材质,
        p_color,
        p_size,
        p_quantity_change,
        current_item.quantity,
        coalesce(p_movement_date, current_date),
        p_reason
    );

    return current_item;
end;
$$;

grant execute on function public.adjust_inventory_stock(text, text, text, text, text, integer, text, date) to anon;
grant execute on function public.adjust_inventory_stock(text, text, text, text, text, integer, text, date) to authenticated;
grant execute on function public.adjust_inventory_stock(text, text, text, text, text, integer, text, date) to service_role;

grant select, insert, update on public.inventory_items to anon;
grant select, insert, update on public.inventory_items to authenticated;
grant select, insert, update on public.inventory_items to service_role;
grant select, insert on public.inventory_movements to anon;
grant select, insert on public.inventory_movements to authenticated;
grant select, insert on public.inventory_movements to service_role;
grant select, insert on public.inventory_sku_imports to anon;
grant select, insert on public.inventory_sku_imports to authenticated;
grant select, insert on public.inventory_sku_imports to service_role;

insert into public.inventory_items (category, color, size, quantity)
values
    ('彩色 T-shirt', '橙色', 'S', 1350),
    ('彩色 T-shirt', '橙色', 'M', 1200),
    ('彩色 T-shirt', '橙色', 'L', 144),
    ('彩色 T-shirt', '橙色', 'XL', 216),
    ('彩色 T-shirt', '橙色', '2XL', 300),
    ('彩色 T-shirt', '橙色', '3XL', 300),
    ('彩色 T-shirt', '橙色', '4XL', 600),
    ('彩色 T-shirt', '橙色', '5XL', 500),
    ('彩色 T-shirt', '粉色', 'S', 300),
    ('彩色 T-shirt', '粉色', 'M', 0),
    ('彩色 T-shirt', '粉色', 'L', 144),
    ('彩色 T-shirt', '粉色', 'XL', 144),
    ('彩色 T-shirt', '粉色', '2XL', 0),
    ('彩色 T-shirt', '粉色', '3XL', 200),
    ('彩色 T-shirt', '粉色', '4XL', 0),
    ('彩色 T-shirt', '粉色', '5XL', 0),
    ('彩色 T-shirt', '灰色', 'S', 1350),
    ('彩色 T-shirt', '灰色', 'M', 1500),
    ('彩色 T-shirt', '灰色', 'L', 1200),
    ('彩色 T-shirt', '灰色', 'XL', 900),
    ('彩色 T-shirt', '灰色', '2XL', 500),
    ('彩色 T-shirt', '灰色', '3XL', 900),
    ('彩色 T-shirt', '灰色', '4XL', 800),
    ('彩色 T-shirt', '灰色', '5XL', 1200),
    ('彩色 T-shirt', '蓝色', 'S', 1000),
    ('彩色 T-shirt', '蓝色', 'M', 1044),
    ('彩色 T-shirt', '蓝色', 'L', 700),
    ('彩色 T-shirt', '蓝色', 'XL', 500),
    ('彩色 T-shirt', '蓝色', '2XL', 600),
    ('彩色 T-shirt', '蓝色', '3XL', 800),
    ('彩色 T-shirt', '蓝色', '4XL', 600),
    ('彩色 T-shirt', '蓝色', '5XL', 800),
    ('彩色 T-shirt', '绿色', 'S', 144),
    ('彩色 T-shirt', '绿色', 'M', 216),
    ('彩色 T-shirt', '绿色', 'L', 288),
    ('彩色 T-shirt', '绿色', 'XL', 0),
    ('彩色 T-shirt', '绿色', '2XL', 0),
    ('彩色 T-shirt', '绿色', '3XL', 0),
    ('彩色 T-shirt', '绿色', '4XL', 0),
    ('彩色 T-shirt', '绿色', '5XL', 0),
    ('彩色 T-shirt', '杏色', 'S', 1500),
    ('彩色 T-shirt', '杏色', 'M', 2200),
    ('彩色 T-shirt', '杏色', 'L', 1200),
    ('彩色 T-shirt', '杏色', 'XL', 1000),
    ('彩色 T-shirt', '杏色', '2XL', 250),
    ('彩色 T-shirt', '杏色', '3XL', 600),
    ('彩色 T-shirt', '杏色', '4XL', 700),
    ('彩色 T-shirt', '杏色', '5XL', 600),
    ('彩色 T-shirt', '紫色', 'S', 1200),
    ('彩色 T-shirt', '紫色', 'M', 1200),
    ('彩色 T-shirt', '紫色', 'L', 400),
    ('彩色 T-shirt', '紫色', 'XL', 700),
    ('彩色 T-shirt', '紫色', '2XL', 250),
    ('彩色 T-shirt', '紫色', '3XL', 800),
    ('彩色 T-shirt', '紫色', '4XL', 200),
    ('彩色 T-shirt', '紫色', '5XL', 400),
    ('彩色 T-shirt', '棕色', 'S', 0),
    ('彩色 T-shirt', '棕色', 'M', 200),
    ('彩色 T-shirt', '棕色', 'L', 576),
    ('彩色 T-shirt', '棕色', 'XL', 384),
    ('彩色 T-shirt', '棕色', '2XL', 288),
    ('彩色 T-shirt', '棕色', '3XL', 288),
    ('彩色 T-shirt', '棕色', '4XL', 288),
    ('彩色 T-shirt', '棕色', '5XL', 0)
on conflict (category, 品牌, 材质, color, size) do nothing;

update public.inventory_items
set category = '彩色短袖'
where category = '彩色 T-shirt';

notify pgrst, 'reload schema';
