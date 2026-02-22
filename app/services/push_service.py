from fastapi import HTTPException

from app.services import salesforce

SFDC_COMPOSITE_BATCH_SIZE = 200


def _chunk_records(records: list[dict], chunk_size: int) -> list[list[dict]]:
    return [records[index : index + chunk_size] for index in range(0, len(records), chunk_size)]


def _transform_record(record: dict, field_mapping: dict | None) -> dict:
    if not field_mapping:
        return dict(record)

    transformed: dict = {}
    for key, value in record.items():
        transformed_key = field_mapping.get(key, key)
        transformed[transformed_key] = value
    return transformed


def _build_batch_failure_result(error: HTTPException, batch_size: int) -> list[dict]:
    detail = error.detail
    if isinstance(detail, dict):
        status_code = str(detail.get("code", "salesforce_batch_failed"))
        message = str(detail.get("message", "Salesforce composite batch request failed"))
    else:
        status_code = "salesforce_batch_failed"
        message = str(detail) if detail is not None else "Salesforce composite batch request failed"

    return [
        {
            "id": None,
            "success": False,
            "created": False,
            "errors": [
                {
                    "statusCode": status_code,
                    "message": message,
                    "fields": [],
                }
            ],
        }
        for _ in range(batch_size)
    ]


async def push_records(
    nango_connection_id: str,
    object_type: str,
    external_id_field: str,
    records: list[dict],
    field_mapping: dict | None = None,
    provider_config_key: str | None = None,
) -> dict:
    transformed_records = []
    for record in records:
        transformed = _transform_record(record, field_mapping)
        transformed["attributes"] = {"type": object_type}
        transformed_records.append(transformed)

    all_results: list[dict] = []
    for batch in _chunk_records(transformed_records, SFDC_COMPOSITE_BATCH_SIZE):
        try:
            batch_results = await salesforce.composite_upsert(
                nango_connection_id=nango_connection_id,
                object_name=object_type,
                external_id_field=external_id_field,
                records=batch,
                provider_config_key=provider_config_key,
            )
        except HTTPException as error:
            batch_results = _build_batch_failure_result(error, len(batch))
        all_results.extend(batch_results)

    records_succeeded = sum(1 for result in all_results if isinstance(result, dict) and result.get("success") is True)
    records_failed = len(all_results) - records_succeeded

    if records_succeeded == len(all_results):
        status = "succeeded"
    elif records_failed == len(all_results):
        status = "failed"
    else:
        status = "partial"

    errors = [result for result in all_results if isinstance(result, dict) and result.get("success") is False]

    return {
        "status": status,
        "records_total": len(records),
        "records_succeeded": records_succeeded,
        "records_failed": records_failed,
        "results": all_results,
        "errors": errors,
    }
