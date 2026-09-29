# Entrega completa — Nómina AI MVP

Esta entrega consolida el estado actual del MVP.

## Incluye

- Motor determinístico de nómina en Python (`app/services/payroll_engine.py`).
- Lectura/generación de los tres archivos Excel (`payroll_service.py`).
- Flujo human-in-the-loop con revisión, cambios, versiones y aprobación.
- Agente contextual para consulta y propuesta de cambios.
- Auditoría local.
- Test histórico de nóminas (`historical_validation_service.py`).
- Script de validación masiva (`scripts/validate_historical_payrolls.py`).
- Preparación de paquete normalizado de nómina electrónica.
- Integración de autenticación/prueba read-only con Siigo.
- Bloqueo deliberado de transmisión de nómina electrónica hasta contar con contrato/endpoint oficial.
- Pruebas automatizadas.
- Documentación técnica y funcional.

## Estado de pruebas de esta entrega

Ejecutado con:

```bash
python -m unittest discover -s tests -v
```

Resultado: **4 pruebas ejecutadas, 4 exitosas**.

## Seguridad

Los Excel reales, históricos, auditoría, archivos generados, `.env` y credenciales están excluidos por `.gitignore`. Las plantillas Excel incluidas en este ZIP son para ejecución local y no deben subirse a un repositorio si contienen información real.

## Ejecutar

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

Abrir `http://127.0.0.1:5000`.

## Test histórico

Desde interfaz: `Test histórico`.

Desde consola:

```powershell
python scripts/validate_historical_payrolls.py data/historical
```

## Siigo

Copiar `.env.example` a `.env` y diligenciar credenciales de prueba. La transmisión productiva de nómina electrónica no está habilitada hasta confirmar el mecanismo oficial soportado por Siigo.
