from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, session
from pathlib import Path
from werkzeug.utils import secure_filename
import json

from .services.payroll_service import process_payroll, generate_all_files
from .services.novelty_service import process_novelties_file, calculate_novelties, generate_all_novelty_files, save_payroll_snapshot, list_payrolls, get_payroll, employee_history
from .services.employee_service import list_employees, list_active_employees, get_employee, upsert_employee, ensure_employee_from_novelty, mark_siigo
from .services.ai_novelties_service import interpret_novelty_message
from .services.draft_novelties_service import list_draft, add as add_draft, clear as clear_draft
from .services.audit_service import new_review_id, record_review, read_reviews
from .services.agent_service import analyze_agent_message
from .services.historical_validation_service import validate_historical_folder
from .services.electronic_payroll_service import (
    build_electronic_payroll_package, save_electronic_payroll_package,
    save_electronic_payroll_summary_csv, save_electronic_payroll_summary_xlsx,
)
from .services.siigo_service import (
    integration_readiness as siigo_integration_readiness,
    test_connection_from_env as siigo_test_connection,
    SiigoError,
)
from .integrations.siigo.client import get_siigo_client
from .integrations.siigo.service import integration_status as siigo_integration_status
from .integrations.siigo.customers import sync_customer
from .services.delivery_service import build_delivery_folder
from .services.siigo_employee_roster_service import list_active_person_third_parties, import_selected_employees, refresh_confirmed_roster_from_siigo
from .services.siigo_employee_export_service import import_siigo_employee_export
from .services.siigo_payroll_accounting_service import (
    build_payroll_journal, validate_third_parties, save_preview, upload_payroll_journal,
)
from .services.change_service import (
    build_change_catalog,
    save_pending_changes,
    read_pending_changes,
)

main = Blueprint("main", __name__)

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = DATA_DIR / "output"
TEMPLATES_EXCEL_DIR = BASE_DIR / "templates_excel"
DATA_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
HISTORICAL_DIR = DATA_DIR / "historical"
HISTORICAL_DIR.mkdir(parents=True, exist_ok=True)


def _generated_from_session():
    return session.get("generated_files") or {}


def _current_result():
    if session.get("input_type") == "NOVEDADES" and session.get("review_id"):
        payroll = get_payroll(session.get("review_id"))
        if payroll:
            return {"rows": payroll.get("rows", []), "summary": payroll.get("summary", {})}
    input_path = session.get("last_input")
    if not input_path:
        return None
    path = Path(input_path)
    if not path.exists():
        return None
    return process_payroll(path)


def _render_review(result):
    generated = _generated_from_session()
    return render_template(
        "review.html",
        result=result,
        review_id=session.get("review_id"),
        version=session.get("version", 1),
        status=session.get("review_status", "EN_REVISION"),
        calculation_file=generated.get("calculation"),
        signature_file=generated.get("signature"),
        bank_file=generated.get("bank"),
        payslips_file=generated.get("payslips"),
        bank_warnings=session.get("bank_warnings", []),
    )


@main.get("/")
def index():
    return render_template("index.html", reviews=read_reviews(limit=8))


@main.route("/procesar", methods=["GET", "POST"])
def procesar():
    """Entrada principal: NOVEDADES. El cálculo lo hace Python."""
    if request.method == "GET":
        return render_template("upload.html", employees=list_employees(), draft=list_draft())

    file = request.files.get("archivo")
    if not file or not file.filename:
        flash("Debes seleccionar el archivo de NOVEDADES en Excel.")
        return redirect(url_for("main.procesar"))
    filename = secure_filename(file.filename)
    if not filename.lower().endswith(".xlsx"):
        flash("El archivo de novedades debe ser Excel (.xlsx).")
        return redirect(url_for("main.procesar"))

    # La planta es persistente. El flujo operativo no exige volver a cargar empleados.
    # Altas, retiros y modificaciones se reciben como novedades y conservan auditoría.
    if not list_active_employees():
        flash("No hay trabajadores activos en el maestro interno. Revisa el módulo Trabajadores.")
        return redirect(url_for("main.empleados"))

    review_id = new_review_id(); version = 1
    upload_path = DATA_DIR / f"{review_id}_V{version}_NOVEDADES_{filename}"
    file.save(upload_path)
    try:
        result = process_novelties_file(upload_path)
        generated = generate_all_novelty_files(result, review_id, version)
        save_payroll_snapshot(review_id, version, str(upload_path), result)
    except Exception as exc:
        flash(f"No fue posible procesar las novedades: {exc}")
        return redirect(url_for("main.procesar"))

    session["last_input"] = str(upload_path)
    session["input_type"] = "NOVEDADES"
    session["review_id"] = review_id; session["version"] = version
    session["review_status"] = "EN_REVISION"; session["bank_unlocked"] = False
    session["generated_files"] = {k: generated[k].name for k in ("calculation", "signature", "bank", "payslips") if k in generated}
    session["bank_warnings"] = generated["bank_warnings"]
    record_review(review_id=review_id, version=version, action="NOVEDADES_PROCESADAS", reviewer="Sistema", comments=f"Novedades procesadas por motor Python. Nuevos empleados detectados: {len(result.get('new_employees', []))}.", input_file=str(upload_path), generated_files=session["generated_files"], summary=result["summary"])
    record_review(review_id=review_id, version=version, action="EN_REVISION", reviewer="Sistema", comments="Cálculo generado desde novedades y entregado a revisión humana.", input_file=str(upload_path), generated_files=session["generated_files"], summary=result["summary"])
    return _render_review(result)


@main.post("/novedades/procesar-sin-novedades")
def procesar_sin_novedades():
    review_id = new_review_id(); version = 1
    try:
        result = calculate_novelties([])
        generated = generate_all_novelty_files(result, review_id, version)
        save_payroll_snapshot(review_id, version, "SIN_NOVEDADES", result)
    except Exception as exc:
        flash(f"No fue posible calcular la nómina completa: {exc}")
        return redirect(url_for("main.procesar"))
    session["last_input"] = "SIN_NOVEDADES"
    session["input_type"] = "NOVEDADES"
    session["review_id"] = review_id; session["version"] = version
    session["review_status"] = "EN_REVISION"; session["bank_unlocked"] = False
    session["generated_files"] = {k: generated[k].name for k in ("calculation", "signature", "bank", "payslips") if k in generated}
    session["bank_warnings"] = generated["bank_warnings"]
    record_review(review_id=review_id, version=version, action="NOMINA_COMPLETA_SIN_NOVEDADES", reviewer="Sistema", comments="Se calculó toda la planta activa sin novedades del período.", input_file="SIN_NOVEDADES", generated_files=session["generated_files"], summary=result["summary"])
    return _render_review(result)


@main.post("/novedades/agregar")
def agregar_novedad_manual():
    item = {
        "tipo_novedad": request.form.get("tipo_novedad", "").strip(),
        "documento": request.form.get("documento", "").strip(),
        "empleado": request.form.get("empleado", "").strip(),
        "salario_base": request.form.get("salario_base", "").strip(),
        "dias_trabajados": request.form.get("dias_trabajados", "30").strip(),
        "horas_extra": request.form.get("horas_extra", "0").strip(),
        "bonificacion": request.form.get("bonificacion", "0").strip(),
        "descuento": request.form.get("descuento", "0").strip(),
        "dias_novedad": request.form.get("dias_novedad", "0").strip(),
        "banco": request.form.get("banco", "").strip(),
        "tipo_cuenta": request.form.get("tipo_cuenta", "").strip(),
        "cuenta": request.form.get("cuenta", "").strip(),
        "tipo_identificacion": request.form.get("tipo_identificacion", "CC").strip(),
        "codigo_banco": request.form.get("codigo_banco", "").strip(),
        "correo_pago": request.form.get("correo_pago", "").strip(),
        "referencia_pago": request.form.get("referencia_pago", "NOMINA").strip(),
        "descripcion_pago": request.form.get("descripcion_pago", "").strip(),
    }
    if not item["documento"]:
        flash("El documento es obligatorio.")
    elif item["tipo_novedad"].upper() == "INGRESO" and (not item["empleado"] or not item["salario_base"]):
        flash("Para un ingreso debes indicar empleado y salario base.")
    else:
        add_draft(item); flash("Novedad agregada al borrador. Puedes agregar más empleados antes de procesar.")
    return redirect(url_for("main.procesar"))


@main.post("/novedades/procesar-borrador")
def procesar_borrador_novedades():
    rows = list_draft()
    if not rows:
        flash("No hay novedades en el borrador."); return redirect(url_for("main.procesar"))
    review_id = new_review_id(); version=1
    try:
        result=calculate_novelties(rows); generated=generate_all_novelty_files(result, review_id, version)
        save_payroll_snapshot(review_id, version, "FORMULARIO/IA", result)
    except Exception as exc:
        flash(f"No fue posible procesar el borrador: {exc}"); return redirect(url_for("main.procesar"))
    session["last_input"]="FORMULARIO/IA"; session["input_type"]="NOVEDADES"; session["review_id"]=review_id; session["version"]=1; session["review_status"]="EN_REVISION"; session["bank_unlocked"]=False
    session["generated_files"]={k:generated[k].name for k in ("calculation","signature","bank","payslips")}; session["bank_warnings"]=generated["bank_warnings"]
    clear_draft()
    record_review(review_id=review_id, version=1, action="NOVEDADES_PROCESADAS", reviewer="Sistema", comments="Novedades ingresadas por formulario/IA y calculadas por Python.", input_file="FORMULARIO/IA", generated_files=session["generated_files"], summary=result["summary"])
    return _render_review(result)


@main.post("/novedades/limpiar")
def limpiar_borrador_novedades():
    clear_draft(); flash("Borrador de novedades limpiado."); return redirect(url_for("main.procesar"))


@main.post("/api/novedades/ia")
def novedades_ia():
    payload=request.get_json(silent=True) or {}
    return interpret_novelty_message(payload.get("message", ""))


@main.post("/novedades/confirmar-ia")
def confirmar_novedad_ia():
    raw=request.form.get("proposal_json", "{}")
    try: item=json.loads(raw)
    except Exception: item={}
    if not item.get("documento"):
        flash("La propuesta de IA no es válida.")
    else:
        add_draft(item); flash("Novedad interpretada por IA confirmada y agregada al borrador.")
    return redirect(url_for("main.procesar"))


@main.get("/empleados")
def empleados():
    employees = list_employees()
    active = list_active_employees()
    pending_base = [e for e in active if not float(e.get("salary_base") or 0)]
    return render_template("employees.html", employees=employees, active_count=len(active), pending_base=pending_base)




@main.post("/empleados/importar-listado-siigo")
def empleados_importar_listado_siigo():
    file = request.files.get("archivo_empleados_siigo")
    if not file or not file.filename:
        flash("Selecciona el Excel exportado desde Siigo Nómina > Empleados.")
        return redirect(url_for("main.empleados"))
    if not file.filename.lower().endswith(".xlsx"):
        flash("El listado de empleados de Siigo debe ser un archivo .xlsx.")
        return redirect(url_for("main.empleados"))
    path = DATA_DIR / f"SIIGO_EMPLEADOS_{secure_filename(file.filename)}"
    file.save(path)
    try:
        from datetime import datetime
        fecha_corte = request.form.get("fecha_corte", "").strip()
        reference_date = datetime.strptime(fecha_corte, "%Y-%m-%d").date() if fecha_corte else None
        info = import_siigo_employee_export(path, reference_date=reference_date)
        flash(
            f"Siigo sincronizado: {info['active']} trabajadores vigentes para {info['reference_date']}. "
            f"Se analizaron {info['contracts']} contratos del reporte oficial."
        )
    except Exception as exc:
        flash(f"No fue posible importar el listado de empleados de Siigo: {exc}")
    finally:
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass
    return redirect(url_for("main.empleados"))

@main.route("/empleados/sincronizar-desde-siigo", methods=["GET", "POST"])
def empleados_sincronizar_desde_siigo():
    """Importa el maestro de trabajadores a partir de terceros persona de Siigo.

    La API pública no expone la etiqueta interna 'empleado de nómina', por eso la
    primera selección requiere confirmación humana para no confundir clientes persona
    con trabajadores. Una vez importados, todos se incluyen en cada nómina.
    """
    try:
        candidates = list_active_person_third_parties()
    except SiigoError as exc:
        flash(f"No fue posible consultar los terceros persona en Siigo: {exc}")
        return redirect(url_for("main.empleados"))

    if request.method == "POST":
        selected = request.form.getlist("employee_documents")
        if not selected:
            flash("Selecciona al menos un trabajador para importar desde Siigo.")
            return render_template("siigo_employee_roster.html", candidates=candidates)
        imported = import_selected_employees(candidates, selected)
        missing_salary = sum(1 for e in imported if not float(e.get("salary_base") or 0))
        flash(
            f"Se importaron/vincularon {len(imported)} trabajadores desde Siigo. "
            f"{missing_salary} requieren salario base antes de calcular una nómina."
        )
        return redirect(url_for("main.empleados"))

    return render_template("siigo_employee_roster.html", candidates=candidates)


@main.route("/empleados/nuevo", methods=["GET", "POST"])
def empleado_nuevo():
    if request.method == "POST":
        payload={k:request.form.get(k,"") for k in ["document","name","first_name","last_name","email","phone","address","city","position","payroll_group","health_provider","pension_provider","arl_provider","compensation_fund","severance_fund","bank","bank_account","bank_account_type","bank_code","id_type","payment_email","contract_number","contract_start","contract_end","contract_type","salary_type","salary_base","transport_allowance"]}
        try:
            emp=upsert_employee(payload); flash(f"Empleado {emp.get('name') or emp.get('document')} guardado.")
            return redirect(url_for("main.empleado_detalle", document=emp["document"]))
        except Exception as exc: flash(str(exc))
    return render_template("employee_form.html", employee=None)


@main.route("/empleados/<document>/editar", methods=["GET", "POST"])
def empleado_editar(document):
    emp=get_employee(document)
    if not emp: flash("Empleado no encontrado."); return redirect(url_for("main.empleados"))
    if request.method == "POST":
        payload={k:request.form.get(k,"") for k in ["name","first_name","last_name","email","phone","address","city","position","payroll_group","health_provider","pension_provider","arl_provider","compensation_fund","severance_fund","bank","bank_account","bank_account_type","bank_code","id_type","payment_email","contract_number","contract_start","contract_end","contract_type","salary_type","salary_base","transport_allowance"]}; payload["document"]=document
        emp=upsert_employee(payload); flash("Empleado actualizado."); return redirect(url_for("main.empleado_detalle", document=document))
    return render_template("employee_form.html", employee=emp)


@main.get("/empleados/<document>")
def empleado_detalle(document):
    emp=get_employee(document)
    if not emp: flash("Empleado no encontrado."); return redirect(url_for("main.empleados"))
    return render_template("employee_detail.html", employee=emp, history=employee_history(document))


@main.post("/empleados/<document>/sincronizar-siigo")
def empleado_sincronizar_siigo(document):
    emp=get_employee(document)
    if not emp:
        flash("Empleado no encontrado."); return redirect(url_for("main.empleados"))
    if not emp.get("address") or not emp.get("name"):
        flash("Completa al menos nombre y dirección antes de sincronizar el empleado con Siigo.")
        return redirect(url_for("main.empleado_editar", document=document))
    payload={
        "person_type":"person", "id_type":"13", "identification":emp.get("document"),
        "name":emp.get("name"), "first_name":emp.get("first_name") or emp.get("name"),
        "last_name":emp.get("last_name") or "", "address":emp.get("address"),
        "email":emp.get("email") or "", "phone":emp.get("phone") or "",
        "contact_first_name":emp.get("first_name") or emp.get("name"),
        "contact_last_name":emp.get("last_name") or "", "siigo_id":emp.get("siigo_id") or "",
        "comments":"Empleado sincronizado desde Nómina AI",
    }
    try:
        response, mode=sync_customer(payload)
        mark_siigo(document, siigo_id=str(response.get("id") or emp.get("siigo_id") or ""), status="SINCRONIZADO")
        flash(f"Empleado sincronizado con Siigo ({mode}).")
    except SiigoError as exc:
        mark_siigo(document, status="PENDIENTE")
        flash(f"No fue posible sincronizar el empleado con Siigo: {exc}")
    return redirect(url_for("main.empleado_detalle", document=document))


@main.get("/nominas")
def nominas():
    return render_template("payrolls.html", payrolls=list_payrolls())


@main.get("/nominas/<review_id>")
def nomina_detalle(review_id):
    payroll=get_payroll(review_id)
    if not payroll: flash("Nómina no encontrada."); return redirect(url_for("main.nominas"))
    return render_template("payroll_detail.html", payroll=payroll)


@main.get("/cambios")
def cambios():
    if session.get("review_status") != "EN_REVISION":
        flash("Sólo puedes solicitar cambios mientras la versión está en revisión.")
        return redirect(url_for("main.index"))

    generated = _generated_from_session()
    if not generated:
        flash("No hay documentos generados para revisar.")
        return redirect(url_for("main.index"))

    catalog = build_change_catalog(OUTPUT_DIR, generated)
    return render_template(
        "change_form.html",
        review_id=session.get("review_id"),
        version=session.get("version", 1),
        catalog=catalog,
        catalog_json=json.dumps(catalog, ensure_ascii=False),
    )


@main.post("/api/agente")
def agente_nomina():
    if session.get("review_status") != "EN_REVISION":
        return {"error": "La versión actual no está en revisión."}, 409

    generated = _generated_from_session()
    if not generated:
        return {"error": "No hay documentos generados para analizar."}, 404

    payload = request.get_json(silent=True) or {}
    message = str(payload.get("message") or "").strip()
    if not message:
        return {"error": "Escribe una consulta para el agente."}, 400

    catalog = build_change_catalog(OUTPUT_DIR, generated)
    response = analyze_agent_message(
        message=message,
        catalog=catalog,
        current_context=payload.get("context") or {},
    )
    return response


@main.post("/solicitar-cambios")
def solicitar_cambios():
    generated = _generated_from_session()
    result = _current_result()
    if not generated or result is None:
        flash("No hay una nómina en revisión.")
        return redirect(url_for("main.index"))

    reviewer = (request.form.get("reviewer") or "").strip()
    raw_changes = request.form.get("changes_json") or "[]"

    if not reviewer:
        flash("Debes indicar quién solicita los cambios.")
        return redirect(url_for("main.cambios"))

    try:
        changes = json.loads(raw_changes)
    except json.JSONDecodeError:
        changes = []

    if not isinstance(changes, list) or not changes:
        flash("Debes agregar por lo menos un cambio.")
        return redirect(url_for("main.cambios"))

    cleaned = []
    for idx, change in enumerate(changes, start=1):
        file_key = str(change.get("file_key", "")).strip()
        file_label = str(change.get("file_label", "")).strip()
        record_label = str(change.get("record_label", "")).strip()
        column = str(change.get("column", "")).strip()
        current_value = change.get("current_value", "")
        new_value = str(change.get("new_value", "")).strip()
        reason = str(change.get("reason", "")).strip()
        row = change.get("row", "")

        if not all([file_key, file_label, record_label, column, new_value, reason]):
            flash(f"El cambio #{idx} está incompleto. Revisa archivo, registro, columna, valor nuevo y motivo.")
            return redirect(url_for("main.cambios"))

        item = {
            "change_number": idx,
            "file_key": file_key,
            "file_label": file_label,
            "record_label": record_label,
            "row": row,
            "column": column,
            "current_value": current_value,
            "new_value": new_value,
            "reason": reason,
            "status": "PENDIENTE",
        }
        cleaned.append(item)

        # Cada cambio queda registrado individualmente en auditoría.
        record_review(
            review_id=session["review_id"],
            version=session.get("version", 1),
            action="CAMBIO_SOLICITADO",
            reviewer=reviewer,
            comments=(
                f"Cambio #{idx} | Archivo: {file_label} | Registro: {record_label} | "
                f"Columna: {column} | Actual: {current_value} | "
                f"Debe decir: {new_value} | Motivo: {reason}"
            ),
            input_file=session.get("last_input", ""),
            generated_files=generated,
            summary=result["summary"],
        )

    save_pending_changes(
        review_id=session["review_id"],
        version=session.get("version", 1),
        reviewer=reviewer,
        changes=cleaned,
    )

    record_review(
        review_id=session["review_id"],
        version=session.get("version", 1),
        action="CAMBIOS_SOLICITADOS",
        reviewer=reviewer,
        comments=f"Se solicitaron {len(cleaned)} cambio(s) estructurado(s).",
        input_file=session.get("last_input", ""),
        generated_files=generated,
        summary=result["summary"],
    )

    session["review_status"] = "CAMBIOS_SOLICITADOS"
    session["bank_unlocked"] = False

    return render_template(
        "changes_requested.html",
        review_id=session["review_id"],
        version=session.get("version", 1),
        reviewer=reviewer,
        changes=cleaned,
    )


@main.route("/nueva-version", methods=["GET", "POST"])
def nueva_version():
    if session.get("review_status") != "CAMBIOS_SOLICITADOS":
        flash("No hay cambios pendientes para generar una nueva versión.")
        return redirect(url_for("main.index"))

    pending = read_pending_changes(session.get("review_id", ""))

    if request.method == "GET":
        return render_template(
            "new_version.html",
            review_id=session.get("review_id"),
            next_version=session.get("version", 1) + 1,
            pending=pending,
        )

    file = request.files.get("archivo")
    if not file or not file.filename:
        flash("Debes cargar el archivo de NOVEDADES corregido.")
        return redirect(url_for("main.nueva_version"))

    filename = secure_filename(file.filename)
    if not filename.lower().endswith(".xlsx"):
        flash("El archivo debe ser Excel (.xlsx).")
        return redirect(url_for("main.nueva_version"))

    version = session.get("version", 1) + 1
    review_id = session["review_id"]
    upload_path = DATA_DIR / f"{review_id}_V{version}_{filename}"
    file.save(upload_path)

    try:
        result = process_novelties_file(upload_path)
        generated = generate_all_novelty_files(result, review_id, version)
        save_payroll_snapshot(review_id, version, str(upload_path), result)
    except Exception as exc:
        flash(f"No fue posible generar la nueva versión: {exc}")
        return redirect(url_for("main.nueva_version"))

    session["last_input"] = str(upload_path)
    session["version"] = version
    session["review_status"] = "EN_REVISION"
    session["bank_unlocked"] = False
    session["generated_files"] = {k: generated[k].name for k in ("calculation", "signature", "bank", "payslips") if k in generated}
    session["bank_warnings"] = generated["bank_warnings"]

    change_count = len((pending or {}).get("changes", []))
    record_review(
        review_id=review_id, version=version, action="NUEVA_VERSION_GENERADA",
        reviewer="Sistema",
        comments=f"Se generó V{version} después de recibir {change_count} cambio(s) de la versión anterior.",
        input_file=str(upload_path), generated_files=session["generated_files"],
        summary=result["summary"],
    )
    record_review(
        review_id=review_id, version=version, action="EN_REVISION",
        reviewer="Sistema",
        comments=f"V{version} entregada para revisión. El proceso vuelve a quedar en stand by.",
        input_file=str(upload_path), generated_files=session["generated_files"],
        summary=result["summary"],
    )
    return _render_review(result)


@main.post("/aprobar")
def aprobar():
    generated = _generated_from_session()
    result = _current_result()
    if not generated or result is None:
        flash("No hay una nómina procesada para aprobar.")
        return redirect(url_for("main.index"))

    reviewer = (request.form.get("reviewer") or "").strip()
    comments = (request.form.get("comments") or "").strip()
    confirmed = request.form.get("confirmed") == "yes"

    if int((result.get("summary") or {}).get("criticos_incompletos") or 0) > 0:
        flash("No se puede aprobar: hay trabajadores sin salario base válido. Revisa la novedad o la información disponible del trabajador y vuelve a procesar.")
        return redirect(url_for("main.revisar_actual"))
    if not reviewer:
        flash("Debes indicar el nombre de la persona que realiza la revisión.")
        return redirect(url_for("main.revisar_actual"))
    if not confirmed:
        flash("Debes confirmar que revisaste los documentos antes de aprobar.")
        return redirect(url_for("main.revisar_actual"))

    event = record_review(
        review_id=session["review_id"], version=session.get("version", 1),
        action="APROBADO", reviewer=reviewer, comments=comments or "Sin observaciones.",
        input_file=session.get("last_input", ""), generated_files=generated,
        summary=result["summary"],
    )
    session["review_status"] = "APROBADO"
    session["bank_unlocked"] = True

    return render_template(
        "approved.html", result=result, event=event,
        calculation_file=generated["calculation"],
        signature_file=generated["signature"],
        bank_file=generated["bank"],
        payslips_file=generated.get("payslips"),
    )


@main.get("/revision")
def revisar_actual():
    if session.get("review_status") != "EN_REVISION":
        flash("La ejecución actual no está esperando revisión.")
        return redirect(url_for("main.index"))

    result = _current_result()
    if result is None or not _generated_from_session():
        flash("No hay una nómina pendiente de revisión.")
        return redirect(url_for("main.index"))
    return _render_review(result)


@main.route("/validacion-historica", methods=["GET", "POST"])
def validacion_historica():
    report = None
    if request.method == "POST":
        files = request.files.getlist("archivos")
        saved = 0
        for file in files:
            if not file or not file.filename:
                continue
            filename = secure_filename(file.filename)
            if not filename.lower().endswith((".xlsx", ".xlsm")):
                continue
            file.save(HISTORICAL_DIR / filename)
            saved += 1
        if not saved:
            flash("Selecciona por lo menos un Excel histórico (.xlsx o .xlsm).")
            return redirect(url_for("main.validacion_historica"))
        report = validate_historical_folder(HISTORICAL_DIR)
    return render_template("historical_validation.html", report=report)


@main.route("/siigo", methods=["GET", "POST"])
def siigo_conexion():
    """Estado de Siigo. Las credenciales se leen exclusivamente desde .env."""
    result = None
    error = None
    if request.method == "POST":
        try:
            result = siigo_test_connection()
            count = int(result.get("journal_document_types_found", 0)) if isinstance(result, dict) else 0
            flash(f"Conexión Siigo correcta. Tipos de comprobante contable encontrados: {count}.")
        except SiigoError as exc:
            error = str(exc)
            flash(error)
    return render_template(
        "siigo_connection.html",
        siigo_status=siigo_integration_status(),
        test_result=result,
        error=error,
    )


@main.route("/integracion-siigo-nomina", methods=["GET", "POST"])
def integracion_siigo_nomina():
    if session.get("review_status") != "APROBADO":
        flash("Primero debes aprobar la nómina antes de prepararla o cargarla a Siigo.")
        return redirect(url_for("main.index"))

    result = _current_result()
    if result is None:
        flash("No hay una nómina aprobada disponible.")
        return redirect(url_for("main.index"))

    status = siigo_integration_status()
    preview = None
    third_parties = None
    error = None
    response = None
    action = request.form.get("action") if request.method == "POST" else ""
    journal_date = (request.form.get("journal_date") or "").strip() or None

    try:
        if action in {"preview", "validate", "upload"}:
            preview = build_payroll_journal(result, journal_date=journal_date)
            save_preview(session.get("review_id") or "NOMINA", session.get("version", 1), preview)

        if action in {"validate", "upload"}:
            third_parties = validate_third_parties(result)

        if action == "upload":
            reviewer = (request.form.get("reviewer") or "").strip()
            confirmed = request.form.get("confirmed") == "yes"
            if not reviewer:
                raise SiigoError("Debes indicar quién autoriza la carga contable a Siigo.")
            if not confirmed:
                raise SiigoError("Debes confirmar la revisión antes de cargar la nómina a Siigo.")
            if third_parties and third_parties.get("missing"):
                raise SiigoError("Hay empleados que no existen como terceros en Siigo. Créelos/sincronízalos antes de cargar.")
            response, response_file = upload_payroll_journal(
                session.get("review_id") or "NOMINA", session.get("version", 1), preview
            )
            record_review(
                review_id=session.get("review_id") or "NOMINA",
                version=session.get("version", 1),
                action="NOMINA_CARGADA_SIIGO_COMPROBANTE_CONTABLE",
                reviewer=reviewer,
                comments=f"Comprobante contable de nómina creado en Siigo: {response.get('name') or response.get('id') or 'sin nombre'}.",
                input_file=session.get("last_input", ""),
                generated_files={"siigo_response": response_file},
                summary=preview.get("_summary", {}),
            )
            flash("Nómina cargada a Siigo como comprobante contable.")
    except SiigoError as exc:
        error = str(exc)
        flash(error)

    return render_template(
        "siigo_payroll_integration.html",
        siigo_status=status,
        preview=preview,
        third_parties=third_parties,
        error=error,
        response=response,
    )


@main.route("/nomina-electronica", methods=["GET", "POST"])
def nomina_electronica():
    if session.get("review_status") != "APROBADO":
        flash("La nómina electrónica solo se prepara después de la aprobación humana final.")
        return redirect(url_for("main.index"))

    result = _current_result()
    if result is None:
        flash("No hay una nómina aprobada disponible.")
        return redirect(url_for("main.index"))

    generated_file = session.get("electronic_payroll_file")
    generated_summary_file = session.get("electronic_payroll_summary_file")
    generated_control_xlsx = session.get("electronic_payroll_control_xlsx")
    package_validation = session.get("electronic_payroll_validation")
    siigo_status = None
    siigo_readiness = siigo_integration_readiness()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "prepare":
            period_start = (request.form.get("period_start") or "").strip()
            period_end = (request.form.get("period_end") or "").strip()
            # Los datos de empresa no se solicitan al usuario en cada periodo.
            # Se toman de la configuración segura asociada a la integración Siigo.
            siigo_cfg = get_siigo_client().config
            nit = siigo_cfg.company_nit
            company_name = siigo_cfg.company_name
            if not period_start or not period_end:
                flash("Indica el periodo de la nómina electrónica.")
                return redirect(url_for("main.nomina_electronica"))
            package = build_electronic_payroll_package(
                result=result,
                review_id=session["review_id"],
                version=session.get("version", 1),
                period_start=period_start,
                period_end=period_end,
                employer={"nit": nit, "name": company_name},
            )
            path = save_electronic_payroll_package(OUTPUT_DIR, package)
            summary_path = save_electronic_payroll_summary_csv(OUTPUT_DIR, package)
            control_xlsx_path = save_electronic_payroll_summary_xlsx(OUTPUT_DIR, package)
            session["electronic_payroll_file"] = path.name
            session["electronic_payroll_summary_file"] = summary_path.name
            session["electronic_payroll_control_xlsx"] = control_xlsx_path.name
            session["electronic_payroll_validation"] = package.get("validation", {})
            generated_file = path.name
            generated_summary_file = summary_path.name
            generated_control_xlsx = control_xlsx_path.name
            package_validation = package.get("validation", {})
            record_review(
                review_id=session["review_id"], version=session.get("version", 1),
                action="NOMINA_ELECTRONICA_PREPARADA", reviewer="Sistema",
                comments="Paquete interno preparado. No transmitido a Siigo/DIAN.",
                input_file=session.get("last_input", ""), generated_files=_generated_from_session(),
                summary=result["summary"],
            )
        elif action == "test_siigo":
            try:
                result = siigo_test_connection()
                count = int(result.get("journal_document_types_found", 0)) if isinstance(result, dict) else 0
                siigo_status = f"Conexión Siigo OK. Tipos de comprobante contable encontrados: {count}."
            except SiigoError as exc:
                siigo_status = str(exc)

    return render_template(
        "electronic_payroll.html",
        generated_file=generated_file,
        generated_summary_file=generated_summary_file,
        generated_control_xlsx=generated_control_xlsx,
        package_validation=package_validation,
        siigo_status=siigo_status,
        siigo_readiness=siigo_readiness,
        review_id=session.get("review_id"),
        version=session.get("version", 1),
        company_name=get_siigo_client().config.company_name,
        company_nit=get_siigo_client().config.company_nit,
    )


@main.get("/descargar-nomina-electronica/<filename>")
def descargar_nomina_electronica(filename):
    filename = secure_filename(filename)
    allowed = {session.get("electronic_payroll_file"), session.get("electronic_payroll_summary_file"), session.get("electronic_payroll_control_xlsx")}
    if session.get("review_status") != "APROBADO" or filename not in allowed:
        flash("El archivo de nómina electrónica solicitado no está autorizado para esta revisión.")
        return redirect(url_for("main.index"))
    path = OUTPUT_DIR / filename
    if not path.exists():
        flash("No se encontró el paquete de nómina electrónica.")
        return redirect(url_for("main.nomina_electronica"))
    return send_file(path.resolve(), as_attachment=True, download_name=filename)


@main.get("/descargar-entrega-completa")
def descargar_entrega_completa():
    if session.get("review_status") != "APROBADO":
        flash("La carpeta completa se habilita únicamente después de la aprobación humana final.")
        return redirect(url_for("main.index"))

    generated = _generated_from_session()
    input_path = session.get("last_input")
    if not generated:
        flash("No hay una nómina aprobada disponible para construir la carpeta de entrega.")
        return redirect(url_for("main.index"))
    if not input_path or not Path(input_path).exists():
        calc_name = generated.get("calculation")
        fallback = OUTPUT_DIR / calc_name if calc_name else None
        if not fallback or not fallback.exists():
            flash("No hay una fuente disponible para construir la carpeta de entrega.")
            return redirect(url_for("main.index"))
        input_path = str(fallback)

    electronic_files = [
        session.get("electronic_payroll_file"),
        session.get("electronic_payroll_summary_file"),
        session.get("electronic_payroll_control_xlsx"),
    ]
    package = build_delivery_folder(
        base_dir=BASE_DIR,
        input_path=Path(input_path),
        generated_files=generated,
        output_dir=OUTPUT_DIR,
        review_id=session.get("review_id", ""),
        version=session.get("version", 1),
        electronic_files=electronic_files,
    )
    record_review(
        review_id=session.get("review_id", ""),
        version=session.get("version", 1),
        action="CARPETA_ENTREGA_GENERADA",
        reviewer="Sistema",
        comments=f"Carpeta final preparada: {package['folder_name']}",
        input_file=input_path,
        generated_files=generated,
        summary=(_current_result() or {}).get("summary", {}),
    )
    return send_file(
        package["zip"].resolve(),
        as_attachment=True,
        download_name=package["zip"].name,
    )


@main.get("/auditoria")
def auditoria():
    return render_template("audit.html", reviews=read_reviews(limit=300))


@main.get("/descargar/<filename>")
def descargar(filename):
    filename = secure_filename(filename)
    generated = _generated_from_session()

    if generated.get("bank") == filename and not session.get("bank_unlocked", False):
        flash("El archivo bancario permanece bloqueado hasta la aprobación final.")
        if session.get("review_status") == "EN_REVISION":
            return redirect(url_for("main.revisar_actual"))
        return redirect(url_for("main.index"))

    if filename not in generated.values():
        flash("El archivo solicitado no pertenece a la versión actual.")
        return redirect(url_for("main.index"))

    path = OUTPUT_DIR / filename
    if not path.exists():
        flash(f"No se encontró el archivo: {filename}")
        return redirect(url_for("main.index"))

    return send_file(path.resolve(), as_attachment=True, download_name=filename)


@main.get("/formato/<format_name>")
def descargar_formato(format_name):
    formats = {
        "calculo": TEMPLATES_EXCEL_DIR / "2026_CALCULO_DE_NOMINA.xlsx",
        "firma": TEMPLATES_EXCEL_DIR / "FORMATO_NOMINA_FIRMA.xlsx",
        "banco": TEMPLATES_EXCEL_DIR / "PLANTILLA_BANCO_PAGOS_NOMINA.xlsx",
    }
    path = formats.get(format_name)
    if not path or not path.exists():
        flash("Formato no encontrado.")
        return redirect(url_for("main.index"))
    return send_file(path.resolve(), as_attachment=True, download_name=path.name)
