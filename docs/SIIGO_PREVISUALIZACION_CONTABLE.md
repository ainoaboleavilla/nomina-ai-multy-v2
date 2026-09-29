
# Previsualización contable antes del envío

La pantalla de integración muestra el número real de movimientos y un detalle agregado por grupo, cuenta, concepto, débito y crédito. El detalle se construye a partir de los mismos `items` del comprobante que se enviaría a Siigo; no recalcula la nómina.

La carga real continúa bloqueada por defecto con `SIIGO_LIVE_PAYROLL_JOURNAL_ENABLED=false`. Antes de cambiarla a `true`, Contabilidad debe validar las cuentas y la distribución mostradas en la previsualización.
