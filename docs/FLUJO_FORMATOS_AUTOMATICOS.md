# Flujo automático con formatos reales

## Operación normal

El operador carga únicamente el Excel de NOVEDADES.

Nómina AI toma la planta activa confirmada/sincronizada desde Siigo, cruza las novedades por identificación y ejecuta el motor Python. A partir de ese resultado genera automáticamente:

1. Cálculo de nómina con el mismo esquema A:Z del archivo histórico de Multy.
2. Formato de firma con el mismo esquema B:P, incluida Firma Conformidad.
3. Plantilla de pagos bancarios con el mismo esquema A:K del archivo real entregado por Multy.
4. Desprendibles de nómina.

El usuario no debe volver a cargar Cálculo, Firma o Banco para una corrida normal.

## Datos bancarios

Los datos históricos del archivo bancario entregado por Multy se conservan localmente por identificación. Los cambios futuros se capturan con INGRESO o CAMBIO_BANCO en NOVEDADES.

Si un trabajador activo de Siigo no tiene información bancaria completa, el sistema genera una advertencia en vez de inventar banco, tipo de producto o número de cuenta.
