# Sincronización automática de la planta con Siigo

## Uso normal
1. La planta de trabajadores se confirma una sola vez.
2. En cada procesamiento, Nómina AI consulta Siigo por identificación y refresca la identidad/vínculo de cada trabajador confirmado.
3. El usuario carga únicamente `NOVEDADES.xlsx` con `documento` y los campos que cambiaron.
4. El motor calcula a toda la planta activa, tenga o no novedades.

## Límite de la API pública
La API pública utilizada por este proyecto expone terceros (`/v1/customers`), pero no una bandera documentada que permita saber de forma segura cuáles terceros son empleados del módulo de Nómina. Por eso el sistema no convierte automáticamente todos los terceros persona en trabajadores.

La selección inicial de la planta se hace una sola vez. Después, el flujo periódico es automático y el usuario solo carga novedades.
