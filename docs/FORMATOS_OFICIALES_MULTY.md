# Formatos oficiales Multy

Los tres archivos generados por la nómina conservan como base los formatos reales entregados por Multy:

- `2026_CALCULO_DE_NOMINA.xlsx`: estructura A:Z del cálculo histórico.
- `FORMATO_NOMINA_FIRMA.xlsx`: estructura B:P, incluida la columna `Firma Conformidad`.
- `PLANTILLA_BANCO_PAGOS_NOMINA.xlsx`: estructura A:K del archivo bancario real.

## Fuente de datos

El usuario no debe cargar estos tres archivos en cada periodo. El flujo operativo es:

1. Nómina AI conserva/sincroniza la planta confirmada desde Siigo.
2. El usuario carga únicamente el Excel de NOVEDADES.
3. Las novedades se cruzan por identificación con la planta activa.
4. El motor Python calcula la nómina completa.
5. Se generan automáticamente Cálculo, Firma, Banco y Desprendibles.

Los datos bancarios históricos existentes en la plantilla bancaria se usan como respaldo por identificación. Para ingresos nuevos o cambios de cuenta se usa `INGRESO` / `CAMBIO_BANCO` en NOVEDADES.

No se inventan datos faltantes. Si un dato obligatorio no existe, el sistema debe advertirlo antes del archivo bancario definitivo.
