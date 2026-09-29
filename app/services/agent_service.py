from __future__ import annotations

import re
import unicodedata

COLUMN_ALIASES = {
    'prestamo': ['prestamo','prestamos','loan'],
    'dias laborados': ['dias laborados','dias trabajados'],
    'dias novedad no justificada': ['novedad no justificada','dias no justificados','dnj'],
    'novedad justificada': ['novedad justificada','dj'],
    'salario basico': ['salario basico','salario','sueldo'],
    'auxilio de transporte': ['auxilio de transporte','transporte'],
    'no salarial': ['no salarial','no salario'],
    'comisiones vendedores': ['comision','comisiones'],
    'dispersion banco': ['dispersion','pago banco','banco'],
    'pago total nomina': ['pago total','neto','total nomina'],
}

IMPACT_HINTS = {
    'prestamos': ['Total deducciones', 'Pago Total nómina', 'Dispersión Banco', 'Formato de firma'],
    'aportes': ['Total deducciones', 'Pago Total nómina', 'Dispersión Banco', 'Formato de firma'],
    'dias salud': ['Aportes', 'Total deducciones', 'Pago Total nómina'],
    'dias novedad no justificada': ['Días Laborados', 'Salario quincenal', 'Auxilio de transporte', 'Pago Total nómina'],
    'novedad justificada': ['Días Novedad', 'Auxilio de transporte', 'Pago Total nómina'],
    'salario básico': ['Salario quincenal', 'Aportes', 'Dominical', 'Pago Total nómina', 'Dispersión Banco'],
    'auxilio de transporte': ['Subsidio de transporte', 'Dominical', 'Pago Total nómina'],
    'no salarial': ['No salarial quincenal', 'Pago Total nómina'],
    'comisiones vendedores': ['Total final / revisión de pago'],
    'número del producto o servicio': ['Archivo Banco'],
    'código del banco': ['Archivo Banco'],
}


def _norm(value):
    value = str(value or '').strip().lower()
    value = ''.join(c for c in unicodedata.normalize('NFD', value) if unicodedata.category(c) != 'Mn')
    value = re.sub(r'\s+', ' ', value)
    return value


def _find_record(catalog, message):
    msg = _norm(message)
    best = None
    best_score = 0
    for file_key, file_data in catalog.items():
        for row in file_data.get('rows', []):
            label = _norm(row.get('label'))
            parts = [p for p in re.split(r'[^a-z0-9]+', label) if len(p) >= 3]
            score = sum(1 for p in parts if p in msg)
            if label and label in msg:
                score += 5
            if score > best_score:
                best_score = score
                best = (file_key, row)
    return best if best_score else None


def _find_column(file_data, message):
    msg = _norm(message)
    headers = file_data.get('headers', [])
    best = None
    best_score = 0
    for h in headers:
        hn = _norm(h.get('name'))
        score = 5 if hn and hn in msg else 0
        for canonical, aliases in COLUMN_ALIASES.items():
            if canonical in hn:
                score += sum(3 for a in aliases if _norm(a) in msg)
        if score > best_score:
            best_score = score
            best = h
    return best if best_score else None


def _extract_new_value(message):
    patterns = [
        r'(?:deber[ií]a\s+decir|debe\s+decir|c[aá]mbial[oa]?\s+a|cambiar\s+a|pon\s+|poner\s+|nuevo\s+valor\s*[:=]?\s*)([^,.!?;]+)',
        r'(?:realmente\s+es|correcto\s+es|son)\s+([^,.!?;]+)',
    ]
    for p in patterns:
        m = re.search(p, message, flags=re.I)
        if m:
            return m.group(1).strip()
    return None


def _impacts(column_name):
    n = _norm(column_name)
    for key, items in IMPACT_HINTS.items():
        if _norm(key) in n or n in _norm(key):
            return items
    return ['La misma celda/campo seleccionado', 'Revisión de documentos derivados antes de aprobar']


def analyze_agent_message(message, catalog, current_context=None):
    current_context = current_context or {}
    file_key = current_context.get('file_key')
    row_number = current_context.get('row')
    column_number = current_context.get('column_number')

    found_record = _find_record(catalog, message)
    if found_record:
        file_key, row = found_record
        row_number = row.get('row')

    file_data = catalog.get(file_key) if file_key in catalog else None
    if not file_data:
        file_key = next(iter(catalog), None)
        file_data = catalog.get(file_key) if file_key else None

    row = None
    if file_data:
        row = next((r for r in file_data.get('rows', []) if str(r.get('row')) == str(row_number)), None)
        found_column = _find_column(file_data, message)
        if found_column:
            column_number = found_column.get('col')
        header = next((h for h in file_data.get('headers', []) if str(h.get('col')) == str(column_number)), None)
    else:
        header = None

    current_value = ''
    if row and header:
        current_value = row.get('values', {}).get(str(header.get('col')), '')

    new_value = _extract_new_value(message)
    proposal = None
    if file_data and row and header and new_value is not None:
        proposal = {
            'file_key': file_key,
            'file_label': file_data.get('label'),
            'row': row.get('row'),
            'record_label': row.get('label'),
            'column': header.get('name'),
            'column_number': header.get('col'),
            'current_value': current_value,
            'new_value': new_value,
            'reason': 'Corrección interpretada por el Agente de Nómina durante la revisión.',
            'impacts': _impacts(header.get('name')),
        }

    msgn = _norm(message)
    if proposal:
        text = (
            f'Encontré el cambio. {row.get("label")} tiene "{header.get("name")}" en '
            f'{current_value if current_value != "" else "(vacío)"} y entendí que debe quedar en {new_value}. '
            f'Antes de registrarlo, revisa la propuesta y confírmala.'
        )
    elif 'impact' in msgn or 'afecta' in msgn:
        if header:
            text = f'El campo "{header.get("name")}" puede impactar: ' + ', '.join(_impacts(header.get('name'))) + '.'
        else:
            text = 'Selecciona o menciona primero el campo para poder explicarte su impacto.'
    elif 'valor' in msgn or 'cuanto' in msgn or 'cuánto' in message.lower():
        if row and header:
            text = f'El valor actual de "{header.get("name")}" para {row.get("label")} es {current_value if current_value != "" else "(vacío)"}.'
        else:
            text = 'Necesito identificar el registro y la columna. Puedes seleccionarlos en el formulario o mencionarlos en el mensaje.'
    elif 'problema' in msgn or 'error' in msgn:
        if row:
            text = f'Ya ubiqué a {row.get("label")}. Indícame el campo o el valor correcto y preparo la propuesta de cambio.'
        else:
            text = 'Puedo buscar al empleado por nombre o cédula. Por ejemplo: “Laura tiene un problema con el préstamo”.'
    else:
        if row and header:
            text = f'Estoy revisando {file_data.get("label")}, {row.get("label")}, columna "{header.get("name")}". Valor actual: {current_value if current_value != "" else "(vacío)"}.'
        else:
            text = 'Puedo buscar empleados, identificar columnas, leer valores actuales, proponer correcciones y explicar qué otros campos/documentos se afectarían.'

    return {
        'message': text,
        'selection': {
            'file_key': file_key,
            'row': row.get('row') if row else row_number,
            'column_number': header.get('col') if header else column_number,
        },
        'proposal': proposal,
        'impacts': proposal.get('impacts') if proposal else (_impacts(header.get('name')) if header else []),
    }
