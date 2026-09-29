# Flujo operativo: solo novedades

## Regla de producto
La operación periódica no debe exigir cargar empleados. El usuario carga únicamente `NOVEDADES.xlsx`.

1. La planta de Nómina se configura/valida una sola vez.
2. Antes de cada cálculo, Nómina AI refresca contra Siigo los trabajadores ya confirmados por identificación.
3. El archivo de novedades contiene solo las personas/campos que cambiaron.
4. Las novedades se cruzan por documento.
5. El motor Python calcula toda la planta activa.
6. Si el maestro tiene N empleados, cálculo/firma/banco deben contener N.
7. La revisión humana sigue siendo obligatoria antes de banco o contabilización en Siigo.

## Restricción de integración
No se convierten automáticamente todos los terceros persona de la API pública de Siigo en empleados, porque un tercero puede ser cliente, proveedor u otro contacto. La inicialización de la planta se mantiene separada y controlada hasta disponer de una fuente/API de Nómina que identifique empleados de forma inequívoca.
