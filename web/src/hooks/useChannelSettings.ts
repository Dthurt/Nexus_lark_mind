import { useCallback, useState } from "react";
import {
  getChannels,
  reloadDingTalk,
  reloadFeishu,
  reloadWeCom,
  saveDingTalk,
  saveFeishu,
  saveWeCom,
  testDingTalk,
  testFeishu,
  testWeCom,
} from "@/api/endpoints";
import type { ChannelDoc, ChannelEntry } from "@/types/api";

export function useChannelSettings() {
  const [doc, setDoc] = useState<ChannelDoc>({
    product: "Nexus Lark Mind",
    channels: [],
  });
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState("");
  const [testHint, setTestHint] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await getChannels();
      setDoc(data || { product: "Nexus Lark Mind", channels: [] });
    } catch (err: any) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  const saveChannel = useCallback(
    async (kind: "feishu" | "dingtalk" | "wecom", form: Record<string, unknown>) => {
      setSaving(true);
      setError("");
      try {
        const fn = kind === "feishu" ? saveFeishu : kind === "dingtalk" ? saveDingTalk : saveWeCom;
        const data = await fn(form);
        setDoc(data);
        return data;
      } catch (err: any) {
        setError(String(err));
        throw err;
      } finally {
        setSaving(false);
      }
    },
    [],
  );

  const testChannel = useCallback(async (kind: "feishu" | "dingtalk" | "wecom", body: Record<string, unknown> = {}) => {
    setTesting(true);
    setTestHint(
      kind === "feishu"
        ? "正在请求飞书 tenant_access_token…"
        : kind === "dingtalk"
          ? "正在请求钉钉 accessToken…"
          : "正在请求企业微信 access_token…",
    );
    setError("");
    try {
      const fn = kind === "feishu" ? testFeishu : kind === "dingtalk" ? testDingTalk : testWeCom;
      const data = await fn(body as any);
      setTestHint(data?.message || "连通成功");
      return data;
    } catch (err: any) {
      setTestHint(String(err?.message || err));
      setError(String(err));
      throw err;
    } finally {
      setTesting(false);
    }
  }, []);

  const reloadChannel = useCallback(async (kind: "feishu" | "dingtalk" | "wecom") => {
    setSaving(true);
    try {
      const fn = kind === "feishu" ? reloadFeishu : kind === "dingtalk" ? reloadDingTalk : reloadWeCom;
      const data = await fn();
      setDoc(data);
      return data;
    } catch (err: any) {
      setError(String(err));
      throw err;
    } finally {
      setSaving(false);
    }
  }, []);

  const channelById = useCallback(
    (id: string): ChannelEntry | null => (doc.channels || []).find((c) => c.id === id) || null,
    [doc.channels],
  );

  return {
    doc,
    loading,
    saving,
    testing,
    error,
    testHint,
    load,
    saveFeishu: (form: Record<string, unknown>) => saveChannel("feishu", form),
    testFeishu: (body?: { app_id?: string; app_secret?: string }) => testChannel("feishu", body || {}),
    reloadFeishu: () => reloadChannel("feishu"),
    feishuChannel: () => channelById("feishu"),
    saveDingTalk: (form: Record<string, unknown>) => saveChannel("dingtalk", form),
    testDingTalk: (body?: { client_id?: string; client_secret?: string }) =>
      testChannel("dingtalk", body || {}),
    reloadDingTalk: () => reloadChannel("dingtalk"),
    dingtalkChannel: () => channelById("dingtalk"),
    saveWeCom: (form: Record<string, unknown>) => saveChannel("wecom", form),
    testWeCom: (body?: { corp_id?: string; secret?: string; agent_id?: string }) =>
      testChannel("wecom", body || {}),
    reloadWeCom: () => reloadChannel("wecom"),
    wecomChannel: () => channelById("wecom"),
  };
}
