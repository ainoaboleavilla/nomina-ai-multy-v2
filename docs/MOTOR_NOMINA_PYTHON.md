# Motor de Nómina en Python

## Objetivo

La fuente de verdad de los cálculos de nómina es Python. Excel se usa como formato de entrada y salida, pero el backend no depende de que Excel evalúe ni guarde fórmulas.

## Separación de responsabilidades

- **Excel:** captura/entrada y entrega de archivos.
- **`payroll_engine.py`:** reglas determinísticas de negocio.
- **`payroll_service.py`:** lectura/escritura de Excel y orquestación del motor.
- **Agente:** interpreta, consulta, explica y propone cambios.
- **Humano:** confirma o rechaza cambios y aprueba la versión.

## Datos fuente

El motor toma directamente del Excel únicamente los datos considerados entrada de negocio:

- nombre, apellido, documento;
- salario básico;
- auxilio de transporte;
- días laborales;
- días de novedad no justificada;
- novedad justificada;
- días de salud;
- préstamos;
- valor no salarial;
- días dominicales;
- comisiones.

## Campos derivados

Python calcula:

1. días novedad;
2. días laborados;
3. subsidio de transporte quincenal;
4. salario quincenal;
5. total ingreso;
6. aportes;
7. no salarial quincenal;
8. total deducciones;
9. pago total nómina;
10. dispersión bancaria;
11. valor día dominical;
12. dominical;
13. total.

Las reglas están en `app/services/payroll_engine.py` mediante funciones puras y valores `Decimal` para evitar que una IA o el archivo Excel sean responsables del cálculo.

## Compatibilidad con el Excel histórico

Durante la migración se detectaron excepciones que estaban implícitas en el archivo original, por ejemplo:

- una fila histórica con aportes al 4% en lugar del 8%;
- filas donde `No salarial Quincenal` estaba deliberadamente vacío;
- valores manuales de `No salarial Quincenal`;
- valores manuales de `Valor día dominical`;
- variantes históricas de fórmula.

El backend convierte esas excepciones heredadas en **políticas explícitas de entrada** y luego Python ejecuta el cálculo. De esta forma se conserva el resultado histórico sin depender del motor de fórmulas de Excel.

> Pendiente de negocio: estas excepciones deben ser validadas con el responsable de nómina y, una vez formalizadas, deberían venir de una configuración/regla empresarial y no de la estructura del Excel legado.

## Salida procesada

El archivo `01_CALCULO_DE_NOMINA_PROCESADO.xlsx` ya no contiene fórmulas en las columnas derivadas controladas por el motor. Esas celdas contienen los valores calculados por Python.

Además se agrega la hoja `REGLAS_MOTOR_PYTHON`, que muestra las reglas aplicadas para facilitar revisión y auditoría.

## Pruebas

Ejecutar:

```powershell
python -m unittest discover -s tests -v
```

La prueba de paridad compara los resultados del nuevo motor con los valores almacenados en el Excel histórico. Esto sirve como prueba de regresión durante la migración.

## Siguiente evolución recomendada

1. Validar formalmente cada regla con Nómina/Contabilidad.
2. Pasar tasas y excepciones a configuración versionada por empresa/periodo.
3. Agregar pruebas para cada regla de negocio y cada caso límite.
4. Registrar la versión del motor de reglas utilizada en cada proceso.
5. Hacer que la generación V2 aplique cambios estructurados y recalcule automáticamente con este motor.
