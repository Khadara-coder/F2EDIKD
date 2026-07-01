import { Router } from "express";
import multer from "multer";
import { mockStore } from "../db/mockStore.js";

const upload = multer({ storage: multer.memoryStorage(), limits: { fileSize: 20 * 1024 * 1024 } });
const uploads = new Map<string, { fileName: string; fileSize: number }>();

const router = Router();

router.post("/", upload.single("pdf"), (req, res) => {
  if (!req.file) {
    res.status(400).json({ message: "PDF requis" });
    return;
  }
  const result = mockStore.saveUpload(req.file.originalname, req.file.size);
  uploads.set(result.uploadId, { fileName: req.file.originalname, fileSize: req.file.size });
  res.json(result);
});

router.post("/:uploadId/extract", (req, res) => {
  const meta = uploads.get(req.params.uploadId);
  if (!meta) {
    res.status(404).json({ message: "Upload introuvable" });
    return;
  }
  const preview = mockStore.launchExtraction(req.params.uploadId, meta.fileName, meta.fileSize);
  res.json(preview);
});

export default router;
