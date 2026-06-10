import { useQuery } from "@tanstack/react-query";
import { getStats } from "../lib/api";

export function useStats() {
  return useQuery({
    queryKey: ["admin-stats"],
    queryFn: getStats,
    refetchInterval: 30000, // 30 seconds
  });
}
