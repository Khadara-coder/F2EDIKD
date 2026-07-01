import express from "express";
import cors from "cors";
import { isMockMode } from "./db/databricks.js";
import dashboardRoutes from "./routes/dashboard.js";
import uploadRoutes from "./routes/upload.js";
import ordersRoutes from "./routes/orders.js";
import conversionsRoutes from "./routes/conversions.js";
import masterDataRoutes from "./routes/master-data.js";
import settingsRoutes from "./routes/settings.js";
import { mockStore } from "./db/mockStore.js";

const app = express();
const PORT = Number(process.env.PORT ?? 3001);

app.use(cors());
app.use(express.json());

app.get("/api/health/system", (_req, res) => {
  res.json(mockStore.getSystemHealth());
});

app.use("/api/dashboard", dashboardRoutes);
app.use("/api/upload", uploadRoutes);
app.use("/api/orders", ordersRoutes);
app.use("/api/conversions", conversionsRoutes);
app.use("/api/master-data", masterDataRoutes);
app.use("/api/settings", settingsRoutes);

app.get("/health", (_req, res) => {
  res.json({
    status: "ok",
    mode: isMockMode() ? "mock" : "databricks",
    service: "file2edi-backend",
  });
});

app.listen(PORT, () => {
  console.log(`File2EDI API running on http://localhost:${PORT}`);
  console.log(`Mode: ${isMockMode() ? "MOCK (local dev)" : "Databricks SQL Warehouse"}`);
});

export default app;
