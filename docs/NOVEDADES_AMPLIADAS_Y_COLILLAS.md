# Novedades ampliadas y colillas

Tipos soportados desde esta versión:
- INGRESO
- RETIRO
- INCAPACIDAD_JUSTIFICADA
- INCAPACIDAD_INJUSTIFICADA
- VACACIONES
- PERMISO_NO_REMUNERADO
- CAMBIO_BANCO

`dias_novedad` se usa con incapacidad, vacaciones y permiso no remunerado.
El permiso no remunerado y la incapacidad injustificada descuentan días completos del salario del período.
Vacaciones e incapacidad justificada quedan identificadas de forma separada para trazabilidad y usan la regla justificada existente del MVP; la parametrización legal/empresarial definitiva debe validarse antes de producción.

El Excel de novedades admite banco, tipo_cuenta y cuenta. En INGRESO/CAMBIO_BANCO esos datos se guardan en el maestro.

Se genera un cuarto archivo `04_COLILLAS_DE_PAGO.xlsx` con una hoja por empleado. Es un formato genérico y el diseño puede reemplazarse cuando Karen entregue la plantilla oficial sin modificar el motor de cálculo.

## Actualización con formatos reales de Multy
- `templates_excel/DESPRENDIBLE_DE_NOMINA.xlsx`: formato real recibido para colillas/desprendibles.
- `templates_excel/PLANTILLA_BANCO_PAGOS_NOMINA.xlsx`: plantilla bancaria real recibida.
- El Excel de novedades ahora admite: tipo de identificación, banco, código banco, tipo de producto/cuenta, número de cuenta, correo de pago, referencia y descripción.
- Los datos bancarios se persisten en el maestro solo con INGRESO o CAMBIO_BANCO; no deben repetirse cada quincena.
- Las colillas toman los resultados calculados por Python. Las fórmulas de ejemplo del formato recibido no sustituyen las reglas del motor.
