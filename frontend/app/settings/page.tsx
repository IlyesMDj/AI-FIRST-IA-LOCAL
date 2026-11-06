"use client";

import { useEffect, useState } from "react";
import { Cpu, HardDrive, Power, PowerOff, RotateCcw, Save } from "lucide-react";
import { ErrorBanner, Meter, Notice, PageHeader } from "@/components/common";
import { Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Label, Select, Skeleton } from "@/components/ui/primitives";
import { api, type SystemStatus } from "@/lib/api";
import { useResource } from "@/lib/hooks";
import { useI18n } from "@/lib/i18n";

interface AISettings {
  active_model: string;
  embedding_model: string;
  vision_model: string;
  num_ctx: number;
  temperature: number;
  top_p: number;
  keep_alive: string;
  request_timeout_s: number;
  max_repair_attempts: number;
  auto_process_on_import: boolean;
  ocr_enabled: boolean;
  keep_original_files: boolean;
  duplicate_rules: { file_hash: boolean; email: boolean; name_and_phone: boolean };
}

function Toggle({ id, label, hint, checked, onChange }: { id: string; label: string; hint?: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label htmlFor={id} className="flex cursor-pointer items-start gap-3">
      <input id={id} type="checkbox" className="mt-0.5 size-4 accent-[hsl(var(--primary))]" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span>
        <span className="text-sm font-medium">{label}</span>
        {hint && <span className="block text-xs text-muted-foreground">{hint}</span>}
      </span>
    </label>
  );
}

export default function SettingsPage() {
  const { t, lang, gb, num } = useI18n();
  const sys = useResource<SystemStatus>("/api/system/status", { pollMs: 5000 });
  const [s, setS] = useState<AISettings | null>(null);
  const [roles, setRoles] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = () => {
    api.get<{ settings: AISettings; model_roles: Record<string, string> }>("/api/settings/ai")
      .then((r) => { setS(r.settings); setRoles(r.model_roles); })
      .catch((e) => setErr(e.message));
  };
  // Reload when the language changes: model descriptions come translated from the server.
  useEffect(() => {
    load();
  }, [lang]);

  const save = async () => {
    if (!s) return;
    setErr(null);
    setMsg(null);
    try {
      const r = await api.put<{ settings: AISettings }>("/api/settings/ai", s);
      setS(r.settings);
      setMsg(t("Settings saved."));
      sys.reload();
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  const modelAction = async (model: string, action: "load" | "unload") => {
    setErr(null);
    try {
      await api.post(`/api/system/models/${action}`, { model });
      sys.reload();
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  const set = <K extends keyof AISettings>(k: K, v: AISettings[K]) => setS((cur) => (cur ? { ...cur, [k]: v } : cur));
  const st = sys.data;
  const chatModels = st?.installed_models.filter((m) => !m.capabilities.includes("embedding")) || [];
  const embedModels = st?.installed_models.filter((m) => m.capabilities.includes("embedding")) || [];
  const keepAliveLabel = (k: string) => (k === "0" ? t("Unload after each request") : k === "-1" ? t("Always") : k);

  return (
    <>
      <PageHeader title={t("AI settings")} description={t("Advanced configuration of the local AI engine. Models are never downloaded automatically.")} />
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          {!s ? <Skeleton className="h-96" /> : (
            <>
              <Card>
                <CardHeader>
                  <CardTitle>{t("Models")}</CardTitle>
                  <CardDescription>{t("Only one analysis model is kept in memory at a time to fit 8 GB of GPU memory.")}</CardDescription>
                </CardHeader>
                <CardContent className="grid gap-4 sm:grid-cols-2">
                  <div className="space-y-1.5">
                    <Label htmlFor="am">{t("Analysis model")}</Label>
                    <Select id="am" value={s.active_model} onChange={(e) => set("active_model", e.target.value)}>
                      {!chatModels.some((m) => m.name === s.active_model) && <option value={s.active_model}>{s.active_model} ({t("not installed")})</option>}
                      {chatModels.map((m) => <option key={m.name} value={m.name}>{m.name} · {m.parameter_size}</option>)}
                    </Select>
                    {roles[s.active_model] && <p className="text-xs text-muted-foreground">{roles[s.active_model]}</p>}
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="em">{t("Search (embedding) model")}</Label>
                    <Select id="em" value={s.embedding_model} onChange={(e) => set("embedding_model", e.target.value)}>
                      {!embedModels.some((m) => m.name === s.embedding_model) && <option value={s.embedding_model}>{s.embedding_model} ({t("not installed")})</option>}
                      {embedModels.map((m) => <option key={m.name} value={m.name}>{m.name}</option>)}
                    </Select>
                    <p className="text-xs text-muted-foreground">{t("Changing it requires re-processing CVs for semantic search.")}</p>
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader><CardTitle>{t("Generation")}</CardTitle><CardDescription>{t("Lower context and temperature = faster, more deterministic.")}</CardDescription></CardHeader>
                <CardContent className="grid gap-4 sm:grid-cols-3">
                  <div className="space-y-1.5">
                    <Label htmlFor="ctx">{t("Context size (tokens)")}</Label>
                    <Select id="ctx" value={s.num_ctx} onChange={(e) => set("num_ctx", Number(e.target.value))}>
                      {[4096, 6144, 8192, 12288, 16384].map((n) => <option key={n} value={n}>{num(n)}{n === 8192 ? ` (${t("recommended")})` : ""}</option>)}
                    </Select>
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="temp">{t("Temperature")}</Label>
                    <Input id="temp" type="number" step={0.05} min={0} max={1.5} value={s.temperature} onChange={(e) => set("temperature", Number(e.target.value))} />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="topp">Top-p</Label>
                    <Input id="topp" type="number" step={0.05} min={0.05} max={1} value={s.top_p} onChange={(e) => set("top_p", Number(e.target.value))} />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="ka">{t("Keep model loaded")}</Label>
                    <Select id="ka" value={s.keep_alive} onChange={(e) => set("keep_alive", e.target.value)}>
                      {["0", "2m", "5m", "10m", "30m", "-1"].map((k) => <option key={k} value={k}>{keepAliveLabel(k)}</option>)}
                    </Select>
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="to">{t("Timeout (seconds)")}</Label>
                    <Input id="to" type="number" min={10} max={1800} value={s.request_timeout_s} onChange={(e) => set("request_timeout_s", Number(e.target.value))} />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="rep">{t("Repair attempts (invalid JSON)")}</Label>
                    <Input id="rep" type="number" min={0} max={4} value={s.max_repair_attempts} onChange={(e) => set("max_repair_attempts", Number(e.target.value))} />
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader><CardTitle>{t("Processing")}</CardTitle></CardHeader>
                <CardContent className="space-y-3">
                  <Toggle id="auto" label={t("Start AI extraction immediately after import")} hint={t("When off, you can preview documents and start processing manually.")} checked={s.auto_process_on_import} onChange={(v) => set("auto_process_on_import", v)} />
                  <Toggle id="ocr" label={t("Read scanned PDFs with local OCR")} checked={s.ocr_enabled} onChange={(v) => set("ocr_enabled", v)} />
                  <Toggle id="keep" label={t("Keep original documents after processing")} hint={t("When off, the original file is deleted once its text is extracted (data minimisation). It can then not be re-processed or previewed.")} checked={s.keep_original_files} onChange={(v) => set("keep_original_files", v)} />
                  <div className="pt-2 text-sm font-medium">{t("Possible duplicate detection (flags only, never merges)")}</div>
                  <Toggle id="d1" label={t("Same e-mail address")} checked={s.duplicate_rules.email} onChange={(v) => set("duplicate_rules", { ...s.duplicate_rules, email: v })} />
                  <Toggle id="d2" label={t("Same name and phone number")} checked={s.duplicate_rules.name_and_phone} onChange={(v) => set("duplicate_rules", { ...s.duplicate_rules, name_and_phone: v })} />
                  <p className="text-xs text-muted-foreground">{t("Identical files (same content hash) are always refused at import.")}</p>
                </CardContent>
              </Card>

              {err && <ErrorBanner message={err} />}
              {msg && <Notice>{msg}</Notice>}
              <div className="flex justify-end gap-2">
                <Button variant="outline" onClick={load}><RotateCcw /> {t("Reset")}</Button>
                <Button onClick={save}><Save /> {t("Save settings")}</Button>
              </div>
            </>
          )}
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader><CardTitle className="flex items-center gap-2"><Cpu className="size-4" /> {t("Engine & hardware")}</CardTitle></CardHeader>
            <CardContent className="space-y-3 text-sm">
              {!st ? <Skeleton className="h-32" /> : (
                <>
                  <div className="flex justify-between"><span className="text-muted-foreground">Ollama</span><span className={st.ollama.reachable ? "text-success" : "text-destructive"}>{st.ollama.reachable ? `v${st.ollama.version}` : t("offline")}</span></div>
                  <div className="flex justify-between"><span className="text-muted-foreground">{t("Endpoint")}</span><span>{st.ollama.url}</span></div>
                  <div className="flex justify-between"><span className="text-muted-foreground">CPU</span><span>{t("{n} threads · {pct}%", { n: st.hardware.cpu_count, pct: num(st.hardware.cpu_pct) })}</span></div>
                  <Meter label={t("RAM")} used={st.hardware.ram_total_mb - st.hardware.ram_available_mb} total={st.hardware.ram_total_mb} />
                  {st.hardware.gpus.map((g) => (
                    <div key={g.name} className="space-y-1">
                      <Meter label={g.name.replace("NVIDIA GeForce ", "")} used={g.vram_used_mb} total={g.vram_total_mb} />
                      <div className="text-xs text-muted-foreground">{t("GPU load {pct}% · {temp}°C", { pct: g.utilization_pct ?? "?", temp: g.temperature_c ?? "?" })}</div>
                    </div>
                  ))}
                  {st.issues.map((i) => <Notice key={i} tone="warning">{i}</Notice>)}
                </>
              )}
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle className="flex items-center gap-2"><HardDrive className="size-4" /> {t("Models in memory")}</CardTitle></CardHeader>
            <CardContent className="space-y-2 text-sm">
              {st?.running_models.length === 0 && <p className="text-muted-foreground">{t("No model loaded.")}</p>}
              {st?.running_models.map((m) => (
                <div key={m.name} className="flex items-center justify-between gap-2">
                  <div>
                    <div className="font-medium">{m.name}</div>
                    <div className="text-xs text-muted-foreground">
                      {gb(m.size_mb)} · {t("{pct}% on GPU", { pct: m.size_mb ? Math.round((m.vram_mb / m.size_mb) * 100) : 0 })}{m.context_length ? ` · ctx ${num(m.context_length)}` : ""}
                    </div>
                  </div>
                  <Button size="sm" variant="outline" onClick={() => modelAction(m.name, "unload")}><PowerOff /> {t("Unload")}</Button>
                </div>
              ))}
              {s && st && !st.running_models.some((m) => m.name === s.active_model) && st.active_model_available && (
                <Button size="sm" variant="outline" onClick={() => modelAction(s.active_model, "load")}><Power /> {t("Pre-load {model}", { model: s.active_model })}</Button>
              )}
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>{t("Installed models")}</CardTitle></CardHeader>
            <CardContent className="space-y-2 text-sm">
              {st?.installed_models.map((m) => (
                <div key={m.name} className="flex items-start justify-between gap-2">
                  <div>
                    <div className="font-medium">{m.name}</div>
                    <div className="text-xs text-muted-foreground">{m.parameter_size} · {m.quantization} · {gb(m.size_mb)}</div>
                  </div>
                  {m.capabilities.includes("embedding") ? <Badge>{t("search")}</Badge> : m.capabilities.includes("vision") ? <Badge>{t("vision")}</Badge> : <Badge variant="primary">{t("text")}</Badge>}
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      </div>
    </>
  );
}
