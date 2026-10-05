"use client";

import { FormEvent, useState } from "react";
import styles from "./CategoryUpload.module.css";

type ImportError = { row: number; code?: string | null; message: string };
type ImportResult = {
  filename: string;
  validate_only: boolean;
  total_rows: number;
  valid_rows: number;
  processed: number;
  updated: number;
  created_products: number;
  created: { areas: number; families: number; subfamilies: number; product_types: number; brands: number };
  errors: ImportError[];
  images_imported: number;
};

async function uploadCategoryFile(file: File, validateOnly: boolean): Promise<ImportResult> {
  const body = new FormData();
  body.append("file", file);
  body.append("validate_only", String(validateOnly));
  const response = await fetch("/api/v1/store/catalog-categories/import", {
    method: "POST",
    credentials: "include",
    body,
  });
  const text = await response.text();
  let payload: Record<string, unknown> = {};
  try { payload = text ? JSON.parse(text) : {}; }
  catch { throw new Error("El servicio no devolvió una respuesta válida"); }
  if (!response.ok) throw new Error(String(payload.detail || "No se pudo procesar el archivo"));
  return payload as ImportResult;
}

export default function CategoryUpload() {
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState<"validate" | "import" | null>(null);
  const [error, setError] = useState("");
  const [result, setResult] = useState<ImportResult | null>(null);

  async function run(validateOnly: boolean) {
    if (!file) { setError("Selecciona un archivo CSV o XLSX"); return; }
    if (!validateOnly && !window.confirm(`Se actualizará la clasificación de los materiales incluidos en ${file.name}. ¿Continuar?`)) return;
    setBusy(validateOnly ? "validate" : "import");
    setError("");
    setResult(null);
    try { setResult(await uploadCategoryFile(file, validateOnly)); }
    catch (exception) { setError((exception as Error).message); }
    finally { setBusy(null); }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    run(false);
  }

  return <div className={`page ${styles.page}`}>
    <header className={styles.heading}>
      <div>
        <span className="eyebrow">CATÁLOGO · POSTGRESQL</span>
        <h1>Carga de categorías</h1>
        <p>Actualiza la clasificación y el nombre homologado utilizando el código de material de EXIT.</p>
      </div>
      <div className={styles.headingActions}>
        <a className="secondary" href="/api/v1/store/catalog-categories/template">Descargar plantilla</a>
        <a className="ghost" href="/api/v1/store/catalog-categories/missing.csv">Artículos sin clasificar</a>
        <a className="ghost" href="/api/v1/store/catalog-images/missing.csv">Preparar fotografías</a>
      </div>
    </header>

    <section className={styles.notice}>
      <strong>Esta herramienta no carga imágenes.</strong>
      <span>Los enlaces descargan registros para revisión. No cargan categorías ni fotografías automáticamente.</span>
    </section>

    <form className={styles.uploadCard} onSubmit={submit}>
      <div className={styles.instructions}>
        <h2>Archivo de clasificación</h2>
        <p>Admite CSV y XLSX, con un máximo de 5.000 filas y 10 MB.</p>
        <ol>
          <li>Incluye código, área, familia, subfamilia y tipo de producto.</li>
          <li>Añade marca, nombre homologado y criterios cuando correspondan.</li>
          <li>Valida el archivo y revisa los errores antes de actualizar.</li>
        </ol>
      </div>
      <label className={styles.filePicker}>
        <span>{file ? file.name : "Seleccionar CSV o XLSX"}</span>
        <small>{file ? `${(file.size / 1024).toLocaleString("es-ES", { maximumFractionDigits: 1 })} KB` : "El archivo no se envía hasta que pulses un botón"}</small>
        <input
          type="file"
          accept=".csv,.xlsx,.xlsm,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          onChange={event => { setFile(event.target.files?.[0] || null); setResult(null); setError(""); }}
        />
      </label>
      <div className={styles.actions}>
        <button className="secondary" type="button" disabled={!file || busy !== null} onClick={() => run(true)}>
          {busy === "validate" ? "Validando…" : "Validar archivo"}
        </button>
        <button className="primary" disabled={!file || busy !== null}>
          {busy === "import" ? "Actualizando…" : "Actualizar categorías"}
        </button>
      </div>
    </form>

    {error && <div className={styles.error} role="alert">{error}</div>}
    {result && <section className={styles.result} aria-live="polite">
      <div className={styles.resultTitle}>
        <div>
          <span className="eyebrow">{result.validate_only ? "VALIDACIÓN TERMINADA" : "CARGA TERMINADA"}</span>
          <h2>{result.filename}</h2>
        </div>
        <span className={result.errors.length ? styles.resultWarning : styles.resultOk}>
          {result.errors.length ? `${result.errors.length} filas con error` : "Sin errores"}
        </span>
      </div>
      <div className={styles.summary}>
        <span><small>Filas leídas</small><strong>{result.total_rows}</strong></span>
        <span><small>{result.validate_only ? "Filas válidas" : "Procesadas"}</small><strong>{result.validate_only ? result.valid_rows : result.processed}</strong></span>
        <span><small>Actualizadas</small><strong>{result.updated}</strong></span>
        <span><small>Materiales creados</small><strong>{result.created_products}</strong></span>
      </div>
      {!result.validate_only && <p className={styles.created}>
        Nuevos niveles: {result.created.areas} áreas, {result.created.families} familias, {result.created.subfamilies} subfamilias, {result.created.product_types} tipos y {result.created.brands} marcas.
      </p>}
      {!!result.errors.length && <div className={styles.errorTable}>
        <div className={styles.errorHead}><span>Fila</span><span>Código</span><span>Motivo</span></div>
        {result.errors.map((item, index) => <div className={styles.errorRow} key={`${item.row}-${item.code}-${index}`}>
          <span>{item.row}</span><span>{item.code || "—"}</span><span>{item.message}</span>
        </div>)}
      </div>}
    </section>}
  </div>;
}
