import { useCallback, useState } from "react";
import { getChannels, reloadFeishu, saveFeishu, testFeishu } from "@/api/endpoints";
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

  const saveFeishuForm = useCallback(async (form: Record<string, unknown>) => {
    setSaving(true);
    setError("");
    try {
      const data = await saveFeishu(form);
      setDoc(data);
      return data;
    } catch (err: any) {
      setError(String(err));
      throw err;
    } finally {
      setSaving(false);
    }
  }, []);

  const testFeishuConn = useCallback(
    async ({ app_id, app_secret }: { app_id?: string; app_secret?: string } = {}) => {
      setTesting(true);
      setTestHint("正在请求飞书 tenant_access_token…");
      setError("");
      try {
        const data = await testFeishu({ app_id, app_secret });
        setTestHint(data?.message || "连通成功");
        return data;
      } catch (err: any) {
        setTestHint(String(err?.message || err));
        setError(String(err));
        throw err;
      } finally {
        setTesting(false);
      }
    },
    [],
  );

  const reloadFeishuChannel = useCallback(async () => {
    setSaving(true);
    try {
      const data = await reloadFeishu();
      setDoc(data);
      return data;
    } catch (err: any) {
      setError(String(err));
      throw err;
    } finally {
      setSaving(false);
    }
  }, []);

  const feishuChannel = useCallback((): ChannelEntry | null => {
    return (doc.channels || []).find((c) => c.id === "feishu") || null;
  }, [doc.channels]);

  return {
    doc,
    loading,
    saving,
    testing,
    error,
    testHint,
    load,
    saveFeishu: saveFeishuForm,
    testFeishu: testFeishuConn,
    reloadFeishu: reloadFeishuChannel,
    feishuChannel,
  };
}
