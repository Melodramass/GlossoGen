import { useQuery } from "@tanstack/react-query";
import { api } from "@/shared/lib/api-client";
import { apiError } from "@/shared/lib/api-error";

/** The query key every label list reads, and the one a label edit invalidates. */
export const GROUP_LABELS_QUERY_KEY = ["all-labels"];

/**
 * Every label any run in the group carries, from ``GET /labels``.
 *
 * The runs list, the label picker and the analysis cohort panel all read this one
 * query, so editing a run's labels refreshes each of them.
 */
export function useGroupLabels() {
  return useQuery({
    queryKey: GROUP_LABELS_QUERY_KEY,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/g/{group_slug}/labels");
      if (error) {
        throw apiError(error, "Failed to fetch labels");
      }
      return data.labels;
    },
  });
}
