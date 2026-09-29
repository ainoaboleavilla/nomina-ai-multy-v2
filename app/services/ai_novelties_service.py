from __future__ import annotations
import re
from .employee_service import list_employees, normalize_document


def _number(text: str, patterns: list[str]):
    for p in patterns:
        m = re.search(p, text, re.I)
        if m:
            return float(m.group(1).replace(".", "").replace(",", "."))
    return None


def interpret_novelty_message(message: str) -> dict:
    text = str(message or "").strip()
    if not text:
        return {"ok": False, "message": "Escribe la novedad que quieres registrar."}
    employees = list_employees()
    low = text.lower()
    employee = None
    for item in employees:
        name = str(item.get("name") or "").lower()
        doc = normalize_document(item.get("document"))
        if (name and name in low) or (doc and doc in text):
            employee = item; break
    if employee is None:
        # intento por primer nombre
        for item in employees:
            first = str(item.get("name") or "").lower().split(" ")[0]
            if first and re.search(rf"\b{re.escape(first)}\b", low): employee=item; break
    extra = _number(text, [r"(\d+(?:[\.,]\d+)?)\s*horas?\s*extra", r"horas?\s*extra\s*(?:de|:)?\s*(\d+(?:[\.,]\d+)?)"])
    bonus = _number(text, [r"bonificaci[oó]n(?:\s+de)?\s*\$?\s*([\d\.,]+)", r"bono(?:\s+de)?\s*\$?\s*([\d\.,]+)"])
    discount = _number(text, [r"descuento(?:\s+de)?\s*\$?\s*([\d\.,]+)"])
    days = _number(text, [r"(\d+(?:[\.,]\d+)?)\s*d[ií]as?\s*(?:trabajados?|laborados?)"])
    if not employee:
        return {"ok": False, "message": "No pude identificar al empleado. Escribe su nombre completo o documento; si es nuevo, créalo primero desde Empleados."}
    proposal = {
        "documento": employee.get("document"), "empleado": employee.get("name"),
        "salario_base": employee.get("salary_base", ""), "dias_trabajados": days if days is not None else 30,
        "horas_extra": extra or 0, "bonificacion": bonus or 0, "descuento": discount or 0,
        "banco": employee.get("bank", ""), "cuenta": employee.get("bank_account", ""),
    }
    detected = []
    if extra is not None: detected.append(f"{extra:g} horas extra")
    if bonus is not None: detected.append(f"bonificación ${bonus:,.0f}")
    if discount is not None: detected.append(f"descuento ${discount:,.0f}")
    if days is not None: detected.append(f"{days:g} días trabajados")
    if not detected:
        return {"ok": False, "message": "Identifiqué al empleado, pero no reconocí una novedad (horas extra, bonificación, descuento o días trabajados)."}
    return {"ok": True, "proposal": proposal, "message": f"Encontré a {employee.get('name')}. Propongo registrar: " + ", ".join(detected) + ". Confirma antes de guardarlo."}
