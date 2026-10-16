import { useQuery } from "@tanstack/react-query";
import { api } from "@/shared/lib/api-client";

/**
 * The scenarios the server offers, with their metrics and the judge models, from
 * ``GET /scenarios``. One query shared by every surface that lists scenarios.
 */
export function useScenarioCatalog() {
  return useQuery({
    queryKey: ["scenarios"],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/g/{group_slug}/scenarios");
      if (error) {
        throw new Error("Failed to fetch scenarios");
      }
      return data;
    },
  });
}
