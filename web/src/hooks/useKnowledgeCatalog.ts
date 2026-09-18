import { useCallback, useEffect, useState } from "react";

import {
  getWeknoraHealth,
  listWeknoraKbs,
  type WeknoraHealth,
  type WeknoraKb,
} from "@/api/endpoints";

export function useKnowledgeCatalog() {
  const [health, setHealth] = useState<WeknoraHealth | null>(null);
  const [kbs, setKbs] = useState<WeknoraKb[]>([]);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const h = await getWeknoraHealth();
      setHealth(h);
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
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return { health, kbs, loading, refresh };
}
