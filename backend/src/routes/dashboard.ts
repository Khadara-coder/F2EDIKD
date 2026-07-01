import { Router } from "express";
import { mockStore } from "../db/mockStore.js";

const router = Router();

router.get("/metrics", (_req, res) => {
  res.json(mockStore.getDashboardMetrics());
});

router.get("/review-queue", (_req, res) => {
  res.json(mockStore.getReviewQueue());
});

router.get("/recent-conversions", (_req, res) => {
  res.json(mockStore.getRecentConversions());
});

export default router;
