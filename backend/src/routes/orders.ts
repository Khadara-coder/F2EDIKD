import { Router } from "express";
import { mockStore } from "../db/mockStore.js";

const router = Router();

router.get("/:orderId/review", (req, res) => {
  const review = mockStore.getOrderReview(req.params.orderId);
  if (!review) {
    res.status(404).json({ message: "Commande introuvable" });
    return;
  }
  res.json(review);
});

router.patch("/:orderId", (req, res) => {
  const review = mockStore.updateOrderHeader(req.params.orderId, req.body);
  if (!review) {
    res.status(404).json({ message: "Commande introuvable" });
    return;
  }
  res.json(review);
});

router.patch("/partners/:partnerId", (req, res) => {
  const review = mockStore.updateOrderPartner(req.params.partnerId, req.body);
  if (!review) {
    res.status(404).json({ message: "Partenaire introuvable" });
    return;
  }
  res.json(review);
});

router.patch("/lines/:lineId", (req, res) => {
  const review = mockStore.updateOrderLine(req.params.lineId, req.body);
  if (!review) {
    res.status(404).json({ message: "Ligne introuvable" });
    return;
  }
  res.json(review);
});

router.post("/:orderId/lines", (req, res) => {
  const review = mockStore.addOrderLine(req.params.orderId, req.body);
  if (!review) {
    res.status(404).json({ message: "Commande introuvable" });
    return;
  }
  res.json(review);
});

router.delete("/lines/:lineId", (req, res) => {
  const review = mockStore.deleteOrderLine(req.params.lineId);
  if (!review) {
    res.status(404).json({ message: "Ligne introuvable" });
    return;
  }
  res.json(review);
});

router.patch("/anomalies/:anomalyId", (req, res) => {
  const { action } = req.body as { action: "corrected" | "ignored" | "blocking" };
  const review = mockStore.resolveAnomaly(req.params.anomalyId, action);
  if (!review) {
    res.status(404).json({ message: "Anomalie introuvable" });
    return;
  }
  res.json(review);
});

router.post("/:orderId/generate-edifact", (req, res) => {
  const result = mockStore.generateEdifact(req.params.orderId);
  if (!result.success) {
    res.status(422).json(result);
    return;
  }
  res.json(result);
});

export default router;
