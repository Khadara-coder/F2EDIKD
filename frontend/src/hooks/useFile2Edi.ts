import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

export function useDashboard() {
  const metrics = useQuery({
    queryKey: ["dashboard", "metrics"],
    queryFn: api.getDashboardMetrics,
  });
  const reviewQueue = useQuery({
    queryKey: ["dashboard", "review-queue"],
    queryFn: api.getReviewQueue,
  });
  const recentConversions = useQuery({
    queryKey: ["dashboard", "recent-conversions"],
    queryFn: api.getRecentConversions,
  });
  return { metrics, reviewQueue, recentConversions };
}

export function useOrdersList() {
  return useQuery({
    queryKey: ["orders"],
    queryFn: api.getOrdersList,
    refetchInterval: 30_000,
  });
}

export function useOrderReview(orderId: string) {
  return useQuery({
    queryKey: ["order", orderId, "review"],
    queryFn: () => api.getOrderReview(orderId),
    enabled: !!orderId,
  });
}

export function useHistory(filters: Parameters<typeof api.getHistory>[0]) {
  return useQuery({
    queryKey: ["history", filters],
    queryFn: () => api.getHistory(filters),
  });
}

export function useMasterData(type: string, search?: string) {
  return useQuery({
    queryKey: ["master-data", type, search],
    queryFn: () => api.getMasterData(type, search),
  });
}

export function useSettings() {
  return useQuery({
    queryKey: ["settings"],
    queryFn: api.getSettings,
  });
}
