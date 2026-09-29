# Validación histórica y nómina electrónica

## 1. Validación histórica

El MVP incluye un módulo de regresión que compara nóminas anteriores contra `payroll_engine.py`.

### Flujo

1. Colocar archivos históricos `.xlsx`/`.xlsm` en `data/historical/`, o cargarlos desde `/validacion-historica`.
2. El sistema identifica la hoja con estructura de Cálculo de Nómina.
3. Lee los datos fuente y las políticas heredadas del libro con `data_only=False`.
4. Recalcula cada empleado con Python.
5. Abre el mismo libro con `data_only=True` para leer los resultados históricos cacheados.
6. Compara campo por campo con tolerancia de 0.01.
7. Reporta coincidencias, diferencias y celdas no comparables.

### CLI

```powershell
python scripts/validate_historical_payrolls.py data/historical
```

El reporte JSON se guarda en `data/historical_validation_report.json`.

> Los archivos históricos contienen información sensible y están excluidos de Git.

## 2. Nómina electrónica

Después de aprobación humana, la aplicación habilita `/nomina-electronica`.

El módulo crea un contrato interno normalizado:

`review aprobado -> paquete electrónico interno -> adaptador de proveedor -> proveedor tecnológico/DIAN`

El archivo generado usa el esquema `nomina-ai/electronic-payroll/v1` y queda con estado `PREPARED_NOT_TRANSMITTED`.

Esto es intencional: el paquete interno no se presenta como XML DIAN ni como un payload oficial de Siigo.

## 3. Siigo

Se agregó `app/services/siigo_service.py` con:

- autenticación oficial `/auth`;
- consulta de solo lectura de tipos de comprobante para probar conectividad;
- bloqueo explícito de `transmit_electronic_payroll()`.

La transmisión se mantiene bloqueada hasta recibir/documentar el contrato oficial que indique cómo transmitir **nómina electrónica** mediante Siigo. La API pública consultada actualmente documenta autenticación y múltiples recursos contables, pero no un endpoint público específico para transmisión de nómina electrónica.

Variables necesarias para una prueba read-only:

```env
SIIGO_USERNAME=
SIIGO_ACCESS_KEY=
SIIGO_PARTNER_ID=
```

Nunca guardar valores reales en Git.

## 4. Criterio de salida para activar transmisión real

Solo implementar envío real cuando existan:

1. endpoint/contrato oficial de nómina electrónica;
2. ambiente de pruebas;
3. mapeo de campos y catálogos validado;
4. manejo de respuestas, CUNE, estados y rechazos;
5. idempotencia y reintentos;
6. auditoría de request/response sin exponer secretos;
7. aprobación humana previa;
8. pruebas de integración exitosas.

## Ajuste CSV para Excel Colombia (2026-09-16)
El archivo de control de nómina electrónica se genera en UTF-8 con BOM, declaración `sep=;` y separador `;`, para que Excel con configuración regional colombiana abra cada campo en su propia columna. Los importes y días se escriben con dos decimales y coma decimal. El JSON conserva valores numéricos normalizados para integración.
