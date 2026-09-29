# Parametrización real de nómina en Siigo · Grupo Multy

Fecha de levantamiento: 2026-09-12.

Esta versión reemplaza las variables genéricas `SIIGO_ACCOUNT_*` por un mapa contable versionado en:

`app/config/payroll_accounting_multy.json`

## Comprobantes configurados en Siigo

- CC-992: Comprobante de nómina / causación.
- CC-993: Comprobante de nómina provisión y seguridad social.
- CC-994: Comprobante liquidación de contrato.
- CC-996: Comprobante liquidación de cesantías.
- CC-997: Comprobante desembolso nómina.
- Cuenta de nómina por pagar: 25050501 - Salarios por pagar.

La API de Siigo necesita el **ID interno** del tipo de documento. El programa consulta `/v1/document-types?type=CC`, busca el código visible (por ejemplo 992) y obtiene su `id`. No se confunde el código `992` con el ID interno.

## Grupos de nómina

### Administración
- Sueldo: 51050601
- Auxilio de transporte: 51052701
- Horas extra y recargos: 51051501
- Incapacidades: 51052401
- Bonificaciones: 51054801
- Préstamos: 13651501

### Ventas
- Sueldo: 52050601
- Auxilio de transporte: 52052701
- Horas extra y recargos: 52051501
- Incapacidades: 52052401
- Bonificaciones: 52054801
- Comisiones: 52950501
- Préstamos: 13651501

### Producción
- Sueldo: 72050601
- Auxilio de transporte: 72052701
- Horas extra y recargos: 72051501
- Incapacidades: 72052401
- Bonificaciones: 72054801
- Préstamos: 13651501

No se inventó una cuenta de comisiones para Administración ni Producción porque no fue visible en la parametrización levantada. Si aparece una comisión para esos grupos, la carga a Siigo se bloquea hasta completar el mapa.

## Fondos observados

- Salud: gasto 51056901 / pasivo 23700501.
- Pensión: gasto 51057001 / pasivo 23803001.
- Caja de compensación: gasto 51057201 / pasivo 23701001.
- SENA: gasto 51057801 / pasivo 23701002.
- ICBF: gasto 51057501 / pasivo 23701003.
- ARL: gasto 51056801 / pasivo general 23700601.
- Excepción observada ARL Seguros de Vida Suramericana: pasivo 23701501.
- Fondo de cesantías: pasivo 2510100102.

## Provisiones observadas

- Cesantías: 51053001 / 2510100102.
- Vacaciones: 51053901 / 2510100302.
- Prima de servicios: 51053601 / 2510100402.
- Intereses de cesantías: 51053301 / 2510100202.

## Protección del flujo

Antes de crear CC-992 el sistema exige:

1. Empleado con documento.
2. Empleado con grupo de nómina: Administración, Ventas o Producción.
3. Cuenta existente para cada concepto con valor distinto de cero.
4. Tercero existente en Siigo.
5. Débitos y créditos balanceados.
6. Nómina aprobada por humano.
7. Confirmación explícita de carga real.

Si falta cualquier parametrización, la contabilización se detiene; no se crea un comprobante incompleto.

## Pendientes de validación con Contabilidad

- Confirmar si 13651501 - Educación debe seguir utilizándose para el concepto general Préstamos.
- Confirmar cuentas de comisiones para Administración y Producción si esos grupos utilizan comisiones.
- Verificar si las cuentas de fondos/provisiones cambian entre Administración, Ventas y Producción. No se extrapolaron cuentas no observadas.
- La generación completa de CC-993 y CC-997 debe activarse solo después de validar bases, porcentajes y reglas de seguridad social/provisiones con RRHH/Contabilidad.
