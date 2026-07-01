import { Router } from "express";
import { mockStore } from "../db/mockStore.js";
import type { HistoryFilters } from "../types.js";

const router = Router();

router.get("/history", (req, res) => {
  const filters: HistoryFilters = {
    search: req.query.search as string | undefined,
    dateFrom: req.query.dateFrom as string | undefined,
    dateTo: req.query.dateTo as string | undefined,
    client: req.query.client as string | undefined,
    status: req.query.status as string | undefined,
    page: req.query.page ? Number(req.query.page) : 1,
    pageSize: req.query.pageSize ? Number(req.query.pageSize) : 10,
  };
  res.json(mockStore.getHistory(filters));
});

export default router;
