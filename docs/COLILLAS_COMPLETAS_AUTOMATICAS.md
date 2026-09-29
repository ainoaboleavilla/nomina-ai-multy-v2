# Colillas completas automáticas

La colilla se construye sin volver a cargar un maestro en cada período.

Fuentes:
1. Maestro de trabajadores sincronizado/importado desde Siigo Nómina.
2. Datos persistentes enriquecidos una sola vez (seguridad social, cargo, contacto y banco).
3. Excel de NOVEDADES del período.
4. Motor Python de nómina.

La pantalla Trabajadores muestra `Perfil colilla: Completo` o los campos que faltan. Los datos faltantes no se inventan: la colilla los marca como `PENDIENTE EN MAESTRO` hasta que se completen una sola vez. Después quedan persistidos para las siguientes nóminas.

Campos automáticos de la colilla: nombre, identificación, contrato, correo, celular, cargo, tipo salario, EPS, AFP, ARL, fondo de cesantías, caja, salario, auxilio, banco, tipo/número de cuenta, valor pagado, período, fechas, incapacidad, días laborados, devengos, horas/dominicales, salud, pensión, totales y neto en letras.
