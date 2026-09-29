from pathlib import Path
from shutil import copy2, rmtree
from zipfile import ZipFile, ZIP_DEFLATED
import re
from openpyxl import load_workbook


def _safe_period_label(input_path: Path) -> str:
    """Obtiene una etiqueta legible del periodo desde la hoja del Excel o el nombre del archivo."""
    try:
        wb = load_workbook(input_path, read_only=True, data_only=False)
        title = wb.active.title.strip()
        wb.close()
        if title:
            return re.sub(r"[^A-Za-z0-9ÁÉÍÓÚÜÑáéíóúüñ_-]+", "_", title).strip("_")
    except Exception:
        pass

    name = input_path.stem
    # Quita prefijos internos de review/version cuando existan.
    name = re.sub(r"^[A-Fa-f0-9-]+_V\d+_", "", name)
    name = re.sub(r"[^A-Za-z0-9ÁÉÍÓÚÜÑáéíóúüñ_-]+", "_", name)
    return name.strip("_") or "PERIODO"


def build_delivery_folder(
    *,
    base_dir: Path,
    input_path: Path,
    generated_files: dict,
    output_dir: Path,
    review_id: str,
    version: int,
    electronic_files: list[str] | None = None,
) -> dict:
    """Crea una carpeta de entrega de nómina con estructura orientada al usuario final.

    Estructura principal:
      ENTREGA_NOMINA_<periodo>_V<n>/
        Plantilla_BANCO-Pagos-Nomina_<periodo>.xlsx
        2026_CALCULO_DE_NOMINA_<periodo>.xlsx
        FORMATO_NOMINA_FIRMA_<periodo>.xlsx
        Comprobantes/
        Liquidaciones/

    Si ya existe nómina electrónica preparada, se añade en una subcarpeta independiente.
    """
    period = _safe_period_label(input_path)
    deliveries_dir = base_dir / "data" / "entregas"
    deliveries_dir.mkdir(parents=True, exist_ok=True)

    folder_name = f"ENTREGA_NOMINA_{period}_V{version}"
    folder = deliveries_dir / folder_name
    if folder.exists():
        rmtree(folder)
    folder.mkdir(parents=True, exist_ok=True)

    # Subcarpetas solicitadas por el flujo operativo.
    (folder / "Comprobantes").mkdir()
    (folder / "Liquidaciones").mkdir()

    mapping = {
        "calculation": f"2026_CALCULO_DE_NOMINA_{period}.xlsx",
        "signature": f"FORMATO_NOMINA_FIRMA_{period}.xlsx",
        "bank": f"Plantilla_BANCO-Pagos-Nomina_{period}.xlsx",
    }

    copied = []
    for key, target_name in mapping.items():
        source_name = generated_files.get(key)
        if not source_name:
            continue
        source = output_dir / source_name
        if source.exists():
            target = folder / target_name
            copy2(source, target)
            copied.append(target.name)

    electronic_copied = []
    if electronic_files:
        electronic_dir = folder / "Nomina Electronica"
        valid_sources = []
        for filename in electronic_files:
            if not filename:
                continue
            source = output_dir / filename
            if source.exists():
                valid_sources.append(source)
        if valid_sources:
            electronic_dir.mkdir()
            for source in valid_sources:
                target = electronic_dir / source.name
                copy2(source, target)
                electronic_copied.append(target.name)

    zip_path = deliveries_dir / f"{folder_name}.zip"
    if zip_path.exists():
        zip_path.unlink()

    # Zip conserva incluso las carpetas vacías Comprobantes y Liquidaciones.
    with ZipFile(zip_path, "w", ZIP_DEFLATED) as zf:
        zf.writestr(f"{folder_name}/Comprobantes/", "")
        zf.writestr(f"{folder_name}/Liquidaciones/", "")
        for path in folder.rglob("*"):
            if path.is_file():
                zf.write(path, arcname=f"{folder_name}/{path.relative_to(folder)}")

    return {
        "folder": folder,
        "zip": zip_path,
        "folder_name": folder_name,
        "period": period,
        "files": copied,
        "electronic_files": electronic_copied,
        "review_id": review_id,
        "version": version,
    }
