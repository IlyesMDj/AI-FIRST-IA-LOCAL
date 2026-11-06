"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import { useI18n } from "./i18n";

/** Fetch a resource, optionally polling while `pollWhile(data)` is true. */
export function useResource<T>(path: string | null, opts?: { pollMs?: number; pollWhile?: (d: T) => boolean }) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  // Re-fetch when the UI language changes: the backend translates its messages.
  const { lang } = useI18n();
  const optsRef = useRef(opts);
  optsRef.current = opts;

  const load = useCallback(async () => {
    if (!path) return;
    try {
      const d = await api.get<T>(path);
      setData(d);
      setError(null);
      return d;
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, lang]);

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    let cancelled = false;
    const tick = async () => {
      const d = await load();
      const o = optsRef.current;
      if (cancelled || !o?.pollMs) return;
      if (!o.pollWhile || (d !== undefined && o.pollWhile(d))) timer = setTimeout(tick, o.pollMs);
    };
    setLoading(true);
    tick();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [load]);

  return { data, error, loading, reload: load, setData };
}
