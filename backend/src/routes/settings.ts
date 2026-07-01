import { Router } from "express";
import { mockStore } from "../db/mockStore.js";

const router = Router();

router.get("/", (_req, res) => {
  res.json(mockStore.getSettings());
});

router.put("/", (req, res) => {
  res.json(mockStore.updateSettings(req.body));
});

router.post("/test-connector/:connector", (req, res) => {
  res.json(mockStore.testConnector(req.params.connector));
});

export default router;
