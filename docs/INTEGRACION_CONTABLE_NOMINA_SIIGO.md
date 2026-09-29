# Integración contable de nómina con Siigo

## Objetivo

Una nómina aprobada se transforma en un **Comprobante Contable** y se carga a Siigo mediante `POST /v1/journals`. El proyecto no usa facturación electrónica.

## Parametrización real

Las cuentas ya no se definen como variables genéricas en `.env`. Se encuentran en:

`app/config/payroll_accounting_multy.json`

El mapa fue construido con la configuración observada en Siigo para:

- Administración.
- Ventas.
- Producción.
- Fondos de salud, pensión, caja, SENA, ICBF, ARL y cesantías.
- Provisiones.
- Comprobantes CC-992, CC-993, CC-994, CC-996 y CC-997.

## Flujo de causación CC-992

1. Procesar novedades con el motor Python.
2. Revisar y aprobar humanamente.
3. Verificar que cada empleado tenga **Grupo de nómina**.
4. Resolver el ID interno de CC-992 consultando los tipos de documento `CC` en la API.
5. Elegir las cuentas de gasto según grupo y concepto.
6. Separar las deducciones de salud y pensión del trabajador.
7. Usar 25050501 - Salarios por pagar para el neto.
8. Validar terceros en Siigo.
9. Validar que débitos = créditos.
10. Solicitar confirmación humana explícita.
11. Crear el comprobante en Siigo.
12. Guardar respuesta y auditoría.

## Protección contra parametrización incompleta

Si un empleado no tiene grupo, o si aparece un concepto con valor pero no existe una cuenta verificada para ese grupo, el sistema bloquea la carga. Ejemplo: comisiones de Administración o Producción no se inventan.

## CC-993 y CC-997

Los códigos quedaron registrados, pero la generación completa de **provisión/seguridad social (CC-993)** y **desembolso (CC-997)** debe activarse después de validar con RRHH/Contabilidad las bases, porcentajes y reglas de cada concepto. No se crean movimientos contables supuestos.

## Nómina Electrónica

Permanece como proceso separado. El módulo prepara la información mensual, pero no inventa un endpoint público de transmisión Siigo/DIAN que no esté documentado.
