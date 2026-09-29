# Nómina AI MVP — Novedades, Empleados, Siigo y Nómina Electrónica

Este proyecto está orientado exclusivamente al proceso de **nómina**. La entrada principal son las **novedades**; el cálculo no viene hecho en el Excel: lo realiza el motor Python del sistema.

## Flujo principal

1. Cargar novedades por Excel, formulario o asistente IA.
2. Detectar/crear empleados y completar datos faltantes.
3. Calcular nómina con el motor Python.
4. Generar archivos de cálculo, firma y banco.
5. Revisar y aprobar humanamente.
6. Consultar paneles por empleado y por nómina.
7. Sincronizar empleados como terceros en Siigo cuando sea necesario.
8. Crear el comprobante contable de nómina en Siigo, si la configuración contable está habilitada.
9. Preparar y validar el paquete mensual de **Nómina Electrónica**.
10. Auditar cada acción y versión.

## Importante

- **No existe módulo funcional de facturación electrónica en este proyecto.**
- La API pública documentada de Siigo se usa para autenticación, terceros y comprobantes contables.
- A septiembre de 2026, la documentación pública de Siigo consultada no publica un endpoint específico de Nómina Electrónica. Por seguridad, el sistema **no inventa** un endpoint para transmitir a Siigo/DIAN: prepara, valida y audita el paquete y deja listo el punto de integración para el contrato oficial del proveedor.
- La IA interpreta novedades; los cálculos monetarios los hace Python.
- La aprobación humana es obligatoria antes de banco, contabilización y preparación final.

## Ejecutar

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run.py
```

Configura `.env` con las credenciales API y la parametrización contable real de la empresa.

## Actualización 2026-09-12 · Parametrización real de Siigo

La integración contable ya no usa cuentas genéricas `SIIGO_ACCOUNT_*`. Se agregó `app/config/payroll_accounting_multy.json` con la parametrización levantada directamente de Siigo para los grupos Administración, Ventas y Producción, fondos y provisiones observados.

El comprobante de causación se identifica por el código visible **CC-992** y el sistema obtiene automáticamente su ID interno mediante la API antes de enviar. También quedaron registrados CC-993, CC-994, CC-996 y CC-997 para las siguientes fases.

Cada empleado debe tener un **Grupo de nómina**. Si falta el grupo o una cuenta requerida, la carga contable se bloquea. Consulta `docs/PARAMETRIZACION_REAL_SIIGO_MULTY.md`.

## Salidas de nómina

Al procesar NOVEDADES el sistema genera tres archivos:

1. `01_CALCULO_DE_NOMINA_PROCESADO.xlsx`: conserva la estructura histórica de cálculo de Multy (Nombre, Apellido, cédula, salario, días, aportes, deducciones, dispersión, dominicales/comisiones y total), pero los valores los calcula Python. Incluye hojas `DETALLE_MOTOR_PYTHON` y `REGLAS_MOTOR_PYTHON`.
2. `02_FORMATO_NOMINA_FIRMA.xlsx`: formato de revisión/firma.
3. `03_PLANTILLA_BANCO_PAGOS_NOMINA.xlsx`: archivo de dispersión bancaria.

Las plantillas incluidas en Git están sanitizadas: no contienen nombres, cédulas, cuentas bancarias ni datos reales de empleados.

## Salida de cálculo con formato histórico Multy

La salida `01_CALCULO_DE_NOMINA_PROCESADO.xlsx` conserva el formato de referencia de 26 columnas (`Nombre` a `Total`) y una sola hoja, incluyendo anchos, estilos, bordes y formatos del archivo histórico suministrado. El Excel es una salida: los valores se calculan en Python a partir de novedades. Los campos adicionales de novedades `auxilio_transporte`, `dias_novedad_no_justificada`, `novedad_justificada`, `dias_salud`, `no_salarial`, `dias_dominical` y `comisiones` son opcionales y permiten completar el formato histórico sin volver a depender de fórmulas del Excel.

## Planta completa de empleados

La nómina ya no se construye recorriendo únicamente las filas del archivo de novedades.
El flujo actual es:

1. **Empleados > Sincronizar desde Siigo** consulta los terceros persona activos de la API de Siigo.
2. La primera vez, una persona revisora marca cuáles corresponden realmente a trabajadores.
3. Esos trabajadores quedan en el **maestro de empleados** de Nómina AI.
4. Cada procesamiento toma **todos los empleados activos del maestro**.
5. Las novedades se cruzan por documento y solo modifican al trabajador afectado.
6. Quien no tenga novedad se calcula con sus datos base normales.
7. Los tres Excel (cálculo, firma y banco) se amplían dinámicamente y **no se truncan a 32 empleados**.

> Importante: la API pública de Siigo documenta `/v1/customers` para clientes/terceros, pero no publica un endpoint de Nómina Electrónica que permita distinguir automáticamente qué terceros son empleados. Por eso la primera clasificación tercero → empleado requiere confirmación humana. No se asume que todo tercero persona es trabajador.

### Datos base requeridos

Después de importar desde Siigo, completa en el maestro de empleados los datos laborales que la API pública de terceros no entrega, como mínimo:

- salario base;
- grupo de nómina (Administración, Ventas o Producción);
- banco y cuenta para dispersión, si aplica;
- fondos/entidades requeridos por el proceso.

La aprobación solo se bloquea por datos realmente críticos para el cálculo, como un salario base faltante o inválido. El grupo de nómina no bloquea el cálculo, pero para la contabilización debe ser uno de los grupos reales de Multy: Administración, Ventas o Producción. La planta vigente incluida en esta versión ya viene cargada con su grupo real; no se usa GENERAL.

## Corrección de integridad del maestro de empleados
- Las novedades ya no pueden crear accidentalmente una nómina de solo 4 personas.
- El maestro debe cargarse/confirmarse antes de calcular.
- Recomendado: exportar `Nómina > Empleados` desde Siigo e importarlo en `Empleados`.
- Control 1:1: `empleados calculados == empleados activos del maestro`.
- Si el maestro tiene 33 empleados, cálculo/firma/banco generan 33 filas de empleados.

## Fuente real de trabajadores de Grupo Multy (Siigo)

La versión `SIIGO_REAL_MULTY` reconoce directamente el archivo generado desde:
`Nómina electrónica > Empleados > Exportar lista de empleados`.

Columnas verificadas: Nombre, No Identificación, No contrato, Fecha inicio, Fecha fin, Sueldo y Tipo de contrato.
El sistema conserva el histórico, filtra contratos vigentes por fecha de corte y usa únicamente esa planta para el cálculo. Las novedades no crean empleados.

## Flujo operativo final: solo novedades

Esta entrega incluye el maestro persistente inicializado con el reporte oficial de empleados de Siigo suministrado para la prueba (fecha de referencia 2026-09-16). La pantalla Trabajadores es de consulta: no exige volver a exportar/subir la planta en cada período.

La operación normal es **Novedades → Procesar**. El archivo puede incluir `tipo_novedad` (o `accion`) con `INGRESO` o `RETIRO`. Los retiros no borran el histórico: desactivan al trabajador para conservar auditoría. Para un ingreso nuevo se requiere documento, empleado y salario_base. Las demás novedades modifican únicamente los campos indicados.

## Nómina electrónica — datos de empresa automáticos
La pantalla de Nómina electrónica ya no solicita NIT ni razón social en cada periodo. El usuario solo selecciona fecha inicial y fecha final. La razón social y el NIT se leen de la configuración segura de la integración (`SIIGO_COMPANY_NAME` y `SIIGO_COMPANY_NIT`).


## Grupos reales de la planta vigente (16/09/2026)

La planta vigente incluida en esta versión contiene 34 trabajadores con su grupo real de nómina cargado desde la información suministrada por Multy: Administración, Ventas o Producción. El valor GENERAL fue eliminado. Los ingresos futuros deben indicar el grupo mediante la novedad de INGRESO.

## Corrección de conexión Siigo — 16/09/2026
- Consultas GET a Siigo reintentan automáticamente fallos transitorios (máximo 2 reintentos).
- Autenticación puede reintentarse ante timeout de red.
- Escrituras contables NO se reintentan automáticamente después de un timeout.
- Si un POST a `/v1/journals` queda sin confirmación, el estado se guarda como `REQUIERE_VERIFICACION` para evitar duplicados.
- Cada intento de carga guarda `data/siigo/payroll_journals/*_SIIGO_ESTADO.json` con estado ENVIANDO, CONFIRMADA, ERROR o REQUIERE_VERIFICACION.
- Se mantiene `Idempotency-Key` determinística por revisión/versión/fecha.

## Control Excel de nómina electrónica
- Se genera un .xlsx recomendado para revisión humana con Unicode correcto, columnas, formatos monetarios y hoja Resumen.
- El CSV se conserva como respaldo técnico.
