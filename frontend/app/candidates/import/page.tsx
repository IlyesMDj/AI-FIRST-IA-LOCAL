"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { CheckCircle2, Copy, Eye, FileText, Lock, Trash2, Upload, XCircle } from "lucide-react";
import { ErrorBanner, Notice, PageHeader } from "@/components/common";
import { Button, Card, CardContent, CardHeader, CardTitle } from "@/components/ui/primitives";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

const ACCEPT = ".pdf,.docx,.txt,.md,.jpg,.jpeg,.png";
const MAX_MB = 10;

interface Result { filename: string; status: "imported" | "duplicate" | "rejected"; error?: string; candidate_id?: string; existing_candidate_id?: string }

function Preview({ file }: { file: File }) {
  const { t } = useI18n();
  const [url, setUrl] = useState<string | null>(null);
  const [text, setText] = useState<string | null>(null);
  useEffect(() => {
    const ext = file.name.toLowerCase().split(".").pop();
    if (ext === "pdf" || ext === "jpg" || ext === "jpeg" || ext === "png") {
      const u = URL.createObjectURL(file);
      setUrl(u);
      return () => URL.revokeObjectURL(u);
    }
    if (ext === "txt" || ext === "md") {
      file.text().then((s) => setText(s.slice(0, 20000)));
    }
  }, [file]);
  if (url && /\.(jpe?g|png)$/i.test(file.name))
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={url} alt={t("Document preview")} className="mx-auto max-h-[70vh] rounded-md border" />;
  if (url) return <iframe src={url} title={t("Document preview")} className="h-[70vh] w-full rounded-md border" />;
  if (text !== null) return <pre className="max-h-[70vh] overflow-auto whitespace-pre-wrap rounded-md bg-muted p-4 text-sm">{text}</pre>;
  return <p className="text-sm text-muted-foreground">{t("Word documents cannot be previewed before import. After import, the extracted text is shown on the candidate page.")}</p>;
}

export default function ImportPage() {
  const { t, formatBytes } = useI18n();
  const [files, setFiles] = useState<File[]>([]);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [results, setResults] = useState<Result[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<File | null>(null);
  const input = useRef<HTMLInputElement>(null);

  const add = (list: FileList | null) => {
    if (!list) return;
    const arr = Array.from(list);
    setFiles((cur) => {
      const names = new Set(cur.map((f) => f.name + f.size));
      return [...cur, ...arr.filter((f) => !names.has(f.name + f.size))].slice(0, 50);
    });
    setResults(null);
  };

  const issues = (f: File) => {
    const ext = "." + f.name.toLowerCase().split(".").pop();
    if (!ACCEPT.split(",").includes(ext)) return t("Unsupported format");
    if (f.size > MAX_MB * 1048576) return t("Larger than {n} MB", { n: MAX_MB });
    if (f.size === 0) return t("Empty file");
    return null;
  };

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const form = new FormData();
      files.filter((f) => !issues(f)).forEach((f) => form.append("files", f));
      const r = await api.upload<{ results: Result[] }>("/api/candidates/upload", form);
      setResults(r.results);
      setFiles([]);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const valid = files.filter((f) => !issues(f));

  return (
    <>
      <PageHeader title={t("Import CVs")} description={t("PDF (including scanned), scanned images (JPG, PNG), Word (.docx) or text files — up to 50 files, 10 MB each.")} />
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <div
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => { e.preventDefault(); setDragging(false); add(e.dataTransfer.files); }}
            onClick={() => input.current?.click()}
            onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") input.current?.click(); }}
            role="button"
            tabIndex={0}
            className={`flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed px-6 py-12 text-center transition-colors ${dragging ? "border-primary bg-accent/50" : "hover:border-primary/50 hover:bg-muted/40"}`}
          >
            <Upload className="mb-3 size-6 text-muted-foreground" />
            <p className="font-medium">{t("Drop CVs here or click to browse")}</p>
            <p className="mt-1 text-sm text-muted-foreground">PDF, DOCX, TXT, JPG, PNG</p>
            <input ref={input} type="file" multiple accept={ACCEPT} className="hidden" onChange={(e) => { add(e.target.files); e.target.value = ""; }} />
          </div>

          {files.length > 0 && (
            <Card>
              <CardHeader className="flex-row items-center justify-between">
                <CardTitle>{t("{n} file(s) ready", { n: files.length })}</CardTitle>
                <Button onClick={submit} disabled={busy || valid.length === 0}>
                  <Upload /> {busy ? t("Importing…") : t("Import {n} file(s)", { n: valid.length })}
                </Button>
              </CardHeader>
              <CardContent>
                <ul className="divide-y">
                  {files.map((f, i) => {
                    const issue = issues(f);
                    return (
                      <li key={f.name + i} className="flex items-center gap-3 py-2 text-sm">
                        <FileText className="size-4 shrink-0 text-muted-foreground" />
                        <span className="min-w-0 flex-1 truncate">{f.name}</span>
                        <span className="text-xs text-muted-foreground">{formatBytes(f.size)}</span>
                        {issue ? <span className="text-xs text-destructive">{issue}</span> : (
                          <Button size="sm" variant="ghost" onClick={() => setPreview(f)}><Eye /> {t("Preview")}</Button>
                        )}
                        <Button size="icon" variant="ghost" aria-label={t("Remove {name}", { name: f.name })} onClick={() => setFiles((c) => c.filter((_, j) => j !== i))}>
                          <Trash2 />
                        </Button>
                      </li>
                    );
                  })}
                </ul>
              </CardContent>
            </Card>
          )}

          {error && <ErrorBanner message={error} />}

          {results && (
            <Card>
              <CardHeader><CardTitle>{t("Import results")}</CardTitle></CardHeader>
              <CardContent>
                <ul className="divide-y">
                  {results.map((r, i) => (
                    <li key={i} className="flex items-start gap-3 py-2.5 text-sm">
                      {r.status === "imported" ? <CheckCircle2 className="mt-0.5 size-4 text-success" /> : r.status === "duplicate" ? <Copy className="mt-0.5 size-4 text-warning" /> : <XCircle className="mt-0.5 size-4 text-destructive" />}
                      <div className="min-w-0 flex-1">
                        <div className="truncate font-medium">{r.filename}</div>
                        <div className="text-muted-foreground">
                          {r.status === "imported" ? t("Imported — the AI extraction runs in the background.") : r.error}
                        </div>
                      </div>
                      {r.candidate_id && <Link className="text-primary hover:underline" href={`/candidates/${r.candidate_id}`}>{t("Open")}</Link>}
                      {r.existing_candidate_id && <Link className="text-primary hover:underline" href={`/candidates/${r.existing_candidate_id}`}>{t("Existing")}</Link>}
                    </li>
                  ))}
                </ul>
                <div className="mt-4"><Button variant="outline" asChild><Link href="/candidates">{t("Go to candidates")}</Link></Button></div>
              </CardContent>
            </Card>
          )}
        </div>

        <div className="space-y-3">
          <Notice icon={Lock}>
            <strong>{t("Stays on this computer.")}</strong> {t("Documents are stored in the local data folder and analysed by the local AI model. Nothing is uploaded to the internet.")}
          </Notice>
          <Notice>
            {t("Before analysis, the text is cleaned of information not needed for recruitment (date of birth, age, family situation, nationality, address…).")}
          </Notice>
          <Notice>
            {t("Identical files are detected and not imported twice. Profiles that may belong to the same person are flagged for your review, never merged automatically.")}
          </Notice>
        </div>
      </div>

      <Dialog open={!!preview} onOpenChange={(o) => { if (!o) setPreview(null); }}>
        <DialogContent className="max-w-4xl">
          <DialogHeader><DialogTitle className="truncate pr-6">{preview?.name}</DialogTitle></DialogHeader>
          {preview && <Preview file={preview} />}
        </DialogContent>
      </Dialog>
    </>
  );
}
