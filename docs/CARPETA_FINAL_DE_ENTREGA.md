# Carpeta final de entrega

El MVP genera una carpeta final para conservar el mismo patrón operativo usado por Nómina.

## Estructura

```text
ENTREGA_NOMINA_<PERIODO>_V<n>/
├── Plantilla_BANCO-Pagos-Nomina_<PERIODO>.xlsx
├── 2026_CALCULO_DE_NOMINA_<PERIODO>.xlsx
├── FORMATO_NOMINA_FIRMA_<PERIODO>.xlsx
├── Comprobantes/
├── Liquidaciones/
└── Nomina Electronica/       # solo si fue preparada
```

## Seguridad

La carpeta completa se habilita únicamente cuando la revisión está en estado `APROBADO`. Esto evita entregar la plantilla bancaria antes de la aprobación humana.

## Implementación

- Servicio: `app/services/delivery_service.py`
- Ruta de descarga: `/descargar-entrega-completa`
- Salida local: `data/entregas/`
- La salida está excluida de Git mediante `.gitignore`.
