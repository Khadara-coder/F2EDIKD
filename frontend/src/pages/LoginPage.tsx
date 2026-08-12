import { useState } from "react";
import { ArrowRight } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const logoSrc = `${import.meta.env.BASE_URL}genie-commande.png`;
  const logoFallback = `${import.meta.env.BASE_URL}file.png`;

  async function handleLogin() {
    setError("");
    if (!username.trim()) { setError("Identifiant requis"); return; }
    if (!password.trim()) { setError("Mot de passe requis"); return; }
    try {
      setLoading(true);
      await api.loginWithProfile({ actor: username.trim(), role: "admin", password });
      window.location.assign("/");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Identifiant ou mot de passe incorrect");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4">
      <Card className="w-full max-w-sm shadow-xl">
        <CardHeader className="flex flex-col items-center gap-2 pb-2">
          <img
            src={logoSrc}
            alt="Genie Commande"
            className="h-28 w-auto max-w-[220px] object-contain"
            onError={(e) => {
              const img = e.currentTarget;
              if (!img.src.endsWith("file.png")) img.src = logoFallback;
            }}
          />
          <p className="text-xs text-muted-foreground text-center">Connectez-vous avec votre identifiant</p>
        </CardHeader>

        <CardContent className="space-y-3 pt-2">
          <div className="space-y-1.5">
            <Label>Identifiant</Label>
            <Input
              value={username}
              placeholder="Votre identifiant"
              autoComplete="username"
              onChange={(e) => setUsername(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleLogin()}
            />
          </div>
          <div className="space-y-1.5">
            <Label>Mot de passe</Label>
            <Input
              type="password"
              value={password}
              placeholder="Mot de passe"
              autoComplete="current-password"
              onChange={(e) => setPassword(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleLogin()}
            />
          </div>
          {error && <p className="text-xs text-destructive">{error}</p>}
          <Button className="w-full gap-2" onClick={handleLogin} disabled={loading}>
            {loading ? "Connexion..." : "Se connecter"}
            <ArrowRight className="h-4 w-4" />
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}