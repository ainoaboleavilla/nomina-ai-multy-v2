"""Motor determinístico de cálculo de nómina.

Este módulo reemplaza las fórmulas de Excel como fuente de verdad del cálculo.
Excel queda como formato de entrada/salida; Python contiene las reglas.

Las reglas implementadas reproducen las fórmulas del archivo de cálculo recibido
para las columnas derivadas I:M, O, R:U, W:X y Z.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from decimal import Decimal, InvalidOperation
from typing import Any, Dict

RATE_APORTES = Decimal("0.08")
DAYS_BASE = Decimal("30")


def money(value: Any) -> Decimal:
    """Convierte números de Excel/strings a Decimal de manera segura.

    Los vacíos se interpretan como cero, igual que en las fórmulas originales.
    No se redondean cálculos intermedios porque el Excel original tampoco usa ROUND.
    """
    if value in (None, ""):
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError, AttributeError):
        raise ValueError(f"Valor numérico inválido: {value!r}")


@dataclass(frozen=True)
class PayrollInputs:
    nombre: Any
    apellido: Any
    cedula: Any
    salario_basico: Decimal
    aux_transporte: Decimal
    dias_laborales: Decimal
    dnj: Decimal
    dj: Decimal
    dias_salud: Decimal
    prestamos: Decimal
    no_salarial: Decimal
    dias_dominical: Decimal
    comisiones: Decimal
    aplicar_no_salarial_quincenal: bool = True
    no_salarial_quincenal_override: Decimal | None = None
    valor_dia_dominical_override: Decimal | None = None
    aportes_rate: Decimal = RATE_APORTES
    transport_dj_days_override: Decimal | None = None
    no_salarial_basis: str = "labor_days_minus_novelty"


@dataclass(frozen=True)
class PayrollCalculation:
    dias_novedad: Decimal
    dias_laborados: Decimal
    sub_trans_quincenal: Decimal
    salario_quincenal: Decimal
    total_ingreso: Decimal
    aportes: Decimal
    no_salarial_quincenal: Decimal
    total_deducciones: Decimal
    dispersion_banco: Decimal
    pago_total_nomina: Decimal
    valor_dia_dominical: Decimal
    dominical: Decimal
    total: Decimal


RULES = {
    "dias_novedad": "Días novedad = DNJ + DJ",
    "dias_laborados": "Días laborados = Días laborales - DNJ",
    "sub_trans_quincenal": (
        "Si DJ > 0: auxilio/30 × (días laborados - DJ); "
        "si no: auxilio/30 × días laborados"
    ),
    "salario_quincenal": "Salario quincenal = salario básico/30 × días laborados",
    "total_ingreso": "Total ingreso = salario quincenal + subsidio transporte quincenal",
    "aportes": "Aportes = salario básico × tasa de aportes / 30 × días salud (tasa explícita por política)",
    "no_salarial_quincenal": "No salarial quincenal = no salarial/30 × (días laborales - días novedad)",
    "total_deducciones": "Total deducciones = aportes + préstamos",
    "pago_total_nomina": (
        "Pago total nómina = subsidio transporte quincenal + salario quincenal + "
        "no salarial quincenal - aportes - préstamos"
    ),
    "dispersion_banco": "Dispersión banco = pago total nómina",
    "valor_dia_dominical": "Valor día dominical = salario básico/30 + auxilio transporte/30",
    "dominical": "Dominical = número de días dominical × valor día dominical",
    "total": "Total = pago total nómina + dominical + comisiones",
}


def calculate(inputs: PayrollInputs) -> PayrollCalculation:
    """Calcula una fila completa de nómina a partir de datos fuente."""
    dias_novedad = inputs.dnj + inputs.dj
    dias_laborados = inputs.dias_laborales - inputs.dnj

    if inputs.dj > 0:
        dias_dj_descuento = (
            inputs.transport_dj_days_override
            if inputs.transport_dj_days_override is not None
            else inputs.dj
        )
        sub_trans_quincenal = (inputs.aux_transporte / DAYS_BASE) * (dias_laborados - dias_dj_descuento)
    else:
        sub_trans_quincenal = (inputs.aux_transporte / DAYS_BASE) * dias_laborados

    salario_quincenal = (inputs.salario_basico / DAYS_BASE) * dias_laborados
    total_ingreso = salario_quincenal + sub_trans_quincenal
    aportes = (inputs.salario_basico * inputs.aportes_rate / DAYS_BASE) * inputs.dias_salud
    if inputs.no_salarial_quincenal_override is not None:
        no_salarial_quincenal = inputs.no_salarial_quincenal_override
    elif inputs.aplicar_no_salarial_quincenal:
        if inputs.no_salarial_basis == "worked_days":
            base_no_salarial = dias_laborados
        else:
            base_no_salarial = inputs.dias_laborales - dias_novedad
        no_salarial_quincenal = (inputs.no_salarial / DAYS_BASE) * base_no_salarial
    else:
        no_salarial_quincenal = Decimal("0")
    total_deducciones = aportes + inputs.prestamos
    pago_total_nomina = (
        sub_trans_quincenal
        + salario_quincenal
        + no_salarial_quincenal
        - aportes
        - inputs.prestamos
    )
    dispersion_banco = pago_total_nomina
    if inputs.valor_dia_dominical_override is not None:
        valor_dia_dominical = inputs.valor_dia_dominical_override
    else:
        valor_dia_dominical = (inputs.salario_basico / DAYS_BASE) + (inputs.aux_transporte / DAYS_BASE)
    dominical = inputs.dias_dominical * valor_dia_dominical
    total = pago_total_nomina + dominical + inputs.comisiones

    return PayrollCalculation(
        dias_novedad=dias_novedad,
        dias_laborados=dias_laborados,
        sub_trans_quincenal=sub_trans_quincenal,
        salario_quincenal=salario_quincenal,
        total_ingreso=total_ingreso,
        aportes=aportes,
        no_salarial_quincenal=no_salarial_quincenal,
        total_deducciones=total_deducciones,
        dispersion_banco=dispersion_banco,
        pago_total_nomina=pago_total_nomina,
        valor_dia_dominical=valor_dia_dominical,
        dominical=dominical,
        total=total,
    )


def build_inputs(raw: Dict[str, Any]) -> PayrollInputs:
    """Construye la entrada tipada desde una fila leída del Excel."""
    return PayrollInputs(
        nombre=raw.get("nombre"),
        apellido=raw.get("apellido"),
        cedula=raw.get("cedula"),
        salario_basico=money(raw.get("salario_basico")),
        aux_transporte=money(raw.get("aux_transporte")),
        dias_laborales=money(raw.get("dias_laborales")),
        dnj=money(raw.get("dnj")),
        dj=money(raw.get("dj")),
        dias_salud=money(raw.get("dias_salud")),
        prestamos=money(raw.get("prestamos")),
        no_salarial=money(raw.get("no_salarial")),
        dias_dominical=money(raw.get("dias_dominical")),
        comisiones=money(raw.get("comisiones")),
        aplicar_no_salarial_quincenal=bool(raw.get("aplicar_no_salarial_quincenal", True)),
        no_salarial_quincenal_override=(
            money(raw.get("no_salarial_quincenal_override"))
            if raw.get("no_salarial_quincenal_override") is not None else None
        ),
        valor_dia_dominical_override=(
            money(raw.get("valor_dia_dominical_override"))
            if raw.get("valor_dia_dominical_override") is not None else None
        ),
        aportes_rate=money(raw.get("aportes_rate", RATE_APORTES)),
        transport_dj_days_override=(
            money(raw.get("transport_dj_days_override"))
            if raw.get("transport_dj_days_override") is not None else None
        ),
        no_salarial_basis=str(raw.get("no_salarial_basis") or "labor_days_minus_novelty"),
    )


def as_float_dict(calc: PayrollCalculation) -> Dict[str, float]:
    """Convierte resultados Decimal a float para openpyxl/JSON/UI."""
    return {key: float(value) for key, value in asdict(calc).items()}
