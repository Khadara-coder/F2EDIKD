import { Router } from "express";
import { mockStore } from "../db/mockStore.js";

const router = Router();

router.get("/", (req, res) => {
  const type = (req.query.type as string) ?? "clients";
  const _search = req.query.search as string | undefined;
  void type;
  void _search;
  res.json(mockStore.getMasterData());
});

export default router;
