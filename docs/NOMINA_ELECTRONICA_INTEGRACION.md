# Nómina Electrónica — integración

Este módulo corresponde a **Nómina Electrónica**, no a facturación electrónica.

## Implementado

- disponible solo después de aprobación humana;
- construye paquete mensual normalizado desde la nómina calculada por Python;
- valida NIT/razón social, periodo, empleados, identificaciones y totales;
- genera JSON y CSV de control;
- registra auditoría;
- mantiene estado de transmisión separado del cálculo y de la contabilización.

## Transmisión externa

La documentación pública de Siigo consultada a septiembre de 2026 no publica un endpoint específico de Nómina Electrónica dentro de la API pública. Por eso el proyecto no usa `/invoices` ni inventa `/payroll`.

El último paso queda preparado mediante un adaptador de proveedor. Cuando Siigo/proveedor entregue el contrato oficial de Nómina Electrónica, se conecta allí sin modificar el motor de cálculo ni el flujo de revisión.
