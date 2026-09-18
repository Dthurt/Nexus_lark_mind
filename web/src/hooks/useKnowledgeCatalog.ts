import { useCallback, useEffect, useState } from "react";

import {
  getWeknoraHealth,
  listLocalKnowledgeBases,
  listWeknoraKbs,
  type LocalKnowledgeBase,
  type WeknoraHealth,
  type WeknoraKb,
} from "@/api/endpoints";

export function useKnowledgeCatalog(workspaceId = "") {
  const [health, setHealth] = useState<WeknoraHealth | null>(null);
  const [kbs, setKbs] = useState<WeknoraKb[]>([]);
  const [localKbs, setLocalKbs] = useState<LocalKnowledgeBase[]>([]);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [h, local] = await Promise.all([
        getWeknoraHealth().catch(() => null),
        listLocalKnowledgeBases(workspaceId).catch(() => ({ knowledge_bases: [] })),
      ]);
      setHealth(h);
      setLocalKbs(local?.knowledge_bases || []);
      if (h?.configured && !h?.skipped) {
        const data = await listWeknoraKbs(40);
        setKbs(data.knowledge_bases || []);
      } else {
        setKbs([]);
      }
    } catch {
      setHealth(null);
      setKbs([]);
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return { health, kbs, localKbs, loading, refresh };
}
