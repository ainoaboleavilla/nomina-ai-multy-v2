# Maestro de empleados desde Siigo

## Regla obligatoria
El archivo de novedades **no define la planta de trabajadores**. Solo contiene cambios del período.

La planta se carga desde el listado oficial de Siigo:

1. Siigo → Nómina → Empleados.
2. `Exportar lista de empleados`.
3. En Nómina AI → Empleados → `Importar todos los empleados de Siigo`.
4. Verificar el contador de empleados activos.
5. Cargar novedades y calcular.

Si el maestro tiene 33 empleados activos, los archivos de cálculo, firma y banco deben contener exactamente 33 empleados. El sistema hace un control 1:1 y bloquea la salida si el cálculo no coincide.

## Por qué no se usa `/v1/customers` como fuente automática de la planta
La API pública de Siigo expone terceros/clientes. Un tercero persona no necesariamente es un empleado de nómina. Por eso `/v1/customers` queda como herramienta de vinculación/consulta, pero el listado exportado desde el módulo Nómina es la fuente exacta para construir la planta cuando no existe un endpoint público específico de empleados de nómina.

## Empleado nuevo
Si una novedad llega para un documento que no está en el maestro, se registra como `NUEVO_PENDIENTE_DATOS`, pero **no se incorpora silenciosamente a la nómina**. Debe confirmarse el alta/contrato antes de incluirlo.
