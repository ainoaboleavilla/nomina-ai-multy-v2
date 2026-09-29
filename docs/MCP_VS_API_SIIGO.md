# MCP y API Siigo — alcance correcto del MVP

## MCP

El contexto funcional del agente es **nómina y nómina electrónica**: empleados, novedades, consultas, validaciones y explicaciones. El proyecto no presenta herramientas de facturación electrónica en su interfaz.

El MCP oficial de Siigo es complementario. Solo se utilizarán las herramientas que Siigo publique oficialmente y que sean útiles para este proceso. No se asume que el MCP transmita nómina electrónica.

## API REST

La API pública documentada de Siigo se utiliza para:

- autenticación;
- consulta/creación/actualización de terceros requeridos por el proceso de empleados;
- consulta de tipos de comprobante;
- creación del comprobante contable de nómina mediante `/v1/journals`.

## Nómina Electrónica

Nómina Electrónica es un proceso distinto del comprobante contable. El sistema construye un contrato interno normalizado, valida el periodo y los empleados, genera archivos de control y registra auditoría. La transmisión externa queda encapsulada para conectar únicamente un contrato oficial/documentado de Siigo o del proveedor tecnológico.
