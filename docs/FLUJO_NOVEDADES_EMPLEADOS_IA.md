# Flujo actualizado: Novedades → Nómina → Siigo

## Regla principal
El archivo de **Cálculo de Nómina ya no es una entrada**. La entrada operativa es la información de novedades.

El sistema ofrece tres canales:
1. archivo `NOVEDADES.xlsx`;
2. formulario web;
3. asistente de novedades en lenguaje natural con confirmación humana.

Todos terminan en la misma estructura de datos. El motor Python realiza los cálculos y genera los archivos de cálculo, firma y banco como salidas.

## Empleado nuevo
Cuando un documento aparece por primera vez en las novedades:
1. se crea un registro de empleado local con estado `NUEVO_PENDIENTE_DATOS`;
2. se conservan nombre, salario y datos bancarios disponibles;
3. el panel de Empleados muestra que faltan datos;
4. el usuario completa el perfil;
5. puede sincronizarlo con Siigo;
6. la integración busca primero el documento en Siigo para evitar duplicados y vincula/actualiza si ya existe.

En la interfaz siempre se habla de **Empleado**. El término Customer/Tercero solo existe dentro del adaptador técnico de Siigo.

## Paneles de consulta
- `/empleados`: maestro de empleados y estado Siigo.
- `/empleados/<documento>`: historial de nóminas por empleado.
- `/nominas`: historial por proceso de nómina.
- `/nominas/<review_id>`: detalle de una nómina empleado por empleado.

## Asistente IA
El asistente interpreta instrucciones como:
`A Laura Gómez agrégale 8 horas extra y bonificación de $250000`.

La propuesta nunca se guarda de forma automática. Primero se muestra al usuario y requiere confirmación. El asistente no calcula valores de nómina; el cálculo sigue siendo determinístico en Python.

## Siigo y MCP
La navegación del proyecto ya no gira alrededor de facturación. La integración prioritaria es:
- empleados/terceros para soportar la nómina;
- carga contable de la nómina aprobada mediante API;
- preparación de nómina electrónica en un flujo separado.

El MCP queda como complemento de consulta/orquestación y no como dependencia para cargar la nómina.

## Reglas parametrizadas
El MVP incluye parámetros en `.env` para el cálculo derivado del formato de novedades:
- `PAYROLL_OVERTIME_FACTOR`
- `PAYROLL_MONTH_HOURS`
- `PAYROLL_EMPLOYEE_CONTRIBUTION_RATE`

Deben validarse con RRHH/Contabilidad antes de usar el sistema en producción.
