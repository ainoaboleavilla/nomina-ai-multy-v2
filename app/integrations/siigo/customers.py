from __future__ import annotations

from .client import SiigoError, get_siigo_client


def build_customer_payload(data: dict) -> dict:
    identification = str(data.get("identification") or "").strip()
    person_type = str(data.get("person_type") or "company").strip().lower()
    id_type = str(data.get("id_type") or ("31" if person_type == "company" else "13")).strip()
    name = str(data.get("name") or "").strip()
    address = str(data.get("address") or "").strip()
    first_name = str(data.get("contact_first_name") or name or "Contacto").strip()
    last_name = str(data.get("contact_last_name") or "").strip()
    email = str(data.get("email") or "").strip()
    if not identification or not name or not address:
        raise SiigoError("Identificación, nombre/razón social y dirección son obligatorios para sincronizar con Siigo.")

    names = [name] if person_type == "company" else [str(data.get("first_name") or name).strip(), str(data.get("last_name") or "").strip()]
    payload = {
        "type": "Customer",
        "person_type": person_type,
        "id_type": id_type,
        "identification": identification,
        "name": names,
        "commercial_name": str(data.get("commercial_name") or "").strip(),
        "branch_office": int(data.get("branch_office") or 0),
        "active": True,
        "vat_responsible": bool(data.get("vat_responsible")),
        "fiscal_responsibilities": [{"code": str(data.get("fiscal_responsibility") or "R-99-PN")}],
        "address": {
            "address": address,
            "city": {
                "country_code": str(data.get("country_code") or "CO").strip(),
                "state_code": str(data.get("state_code") or "05").strip(),
                "city_code": str(data.get("city_code") or "05001").strip(),
            },
        },
        "contacts": [{"first_name": first_name, "last_name": last_name, "email": email}],
        "comments": str(data.get("comments") or "").strip()[:4000],
    }
    phone = str(data.get("phone") or "").strip()
    if phone:
        payload["phones"] = [{"indicative": str(data.get("phone_indicative") or "57"), "number": phone}]
        payload["contacts"][0]["phone"] = {"indicative": str(data.get("phone_indicative") or "57"), "number": phone}
    check_digit = str(data.get("check_digit") or "").strip()
    if check_digit:
        payload["check_digit"] = check_digit
    postal = str(data.get("postal_code") or "").strip()
    if postal:
        payload["address"]["postal_code"] = postal
    return payload


def sync_customer(data: dict) -> tuple[dict, str]:
    client = get_siigo_client()
    payload = build_customer_payload(data)
    siigo_id = str(data.get("siigo_id") or "").strip()
    if siigo_id:
        return client.update_customer(siigo_id, payload), "ACTUALIZADO"

    found = client.customers(identification=payload["identification"], page=1, page_size=10)
    matches = found.get("results", []) if isinstance(found, dict) else []
    exact = next((c for c in matches if str(c.get("identification")) == payload["identification"] and int(c.get("branch_office") or 0) == int(payload.get("branch_office") or 0)), None)
    if exact and exact.get("id"):
        return client.update_customer(str(exact["id"]), payload), "VINCULADO_Y_ACTUALIZADO"
    return client.create_customer(payload), "CREADO"
