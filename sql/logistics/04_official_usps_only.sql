begin;

create temporary table logistics_shipments_to_remove
on commit drop
as
select shipment.id
from public.logistics_shipments as shipment
where
    not (
        shipment.tracking_number ~ '^9[0-9]{19,21}$'
        or shipment.tracking_number ~ '^[A-Z]{2}[0-9]{9}US$'
        or shipment.tracking_number ~ '^82[0-9]{8}$'
    )
    or lower(shipment.carrier) similar to
        '%(gofo|fedex|swiftx|swift x|uniuni|uni uni|ups)%'
    or lower(shipment.carrier) similar to '%(cbs|cbt|tiktok)%'
    or lower(shipment.source_payload::text) similar to
        '%(gofo|cbs|cbt|tiktok)%'
    or not exists (
        select 1
        from public.logistics_tracking_check_sources as source
        join public.logistics_tracking_checks as check_record
            on check_record.id = source.check_id
        where source.shipment_id = shipment.id
          and check_record.provider = 'USPS'
    );

delete from public.logistics_label_reviews
where shipment_id in (
    select id from logistics_shipments_to_remove
);

delete from public.logistics_tracking_check_sources
where shipment_id in (
    select id from logistics_shipments_to_remove
);

delete from public.logistics_shipments
where id in (
    select id from logistics_shipments_to_remove
);

commit;

notify pgrst, 'reload schema';
