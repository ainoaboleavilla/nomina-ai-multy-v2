# Empezar: solo cambia `.env`

1. Copia `.env.example` a `.env` si no existe.
2. Configura `SECRET_KEY`, `SIIGO_USERNAME` y `SIIGO_ACCESS_KEY`.
3. Mantén `SIIGO_PARTNER_ID=NominaAI`.
4. Conserva `SIIGO_PAYROLL_JOURNAL_DOCUMENT_CODE=992`. El programa consulta la API y obtiene automáticamente el ID interno del comprobante.
5. Mantén `SIIGO_PAYROLL_ACCOUNTING_MAPPING=app/config/payroll_accounting_multy.json`.
6. Deja `SIIGO_LIVE_PAYROLL_JOURNAL_ENABLED=false` mientras haces pruebas.
7. Ejecuta `python run.py`.
8. En **Siigo**, prueba autenticación y resolución de CC-992.
9. Completa el **Grupo de nómina** de cada empleado: Administración, Ventas o Producción.
10. Procesa y aprueba una nómina.
11. En **Integración Siigo**, previsualiza el comprobante, valida terceros y comprueba que débitos = créditos.
12. Solo cuando todo sea correcto cambia `SIIGO_LIVE_PAYROLL_JOURNAL_ENABLED=true` y realiza la carga con confirmación humana.

Las antiguas variables `SIIGO_ACCOUNT_*` ya no se usan. Las cuentas se leen del mapa contable real levantado de Siigo.

La facturación no forma parte de este MVP. El MCP oficial de Siigo se considera un complemento para herramientas publicadas por Siigo, no el canal de carga de nómina.
