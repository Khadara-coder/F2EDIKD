import { useEffect, useState } from "react";
import { ArrowRight, KeyRound } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

function startWorkspaceLogin() {
  window.location.assign(`${window.location.origin}/`);
}

export function LoginPage() {
  const [actor, setActor] = useState("dik1dy@bosch.com");
  const [role, setRole] = useState<"admin" | "adv">("adv");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [profileLoginEnabled, setProfileLoginEnabled] = useState(false);

  useEffect(() => {
    let active = true;
    api
      .getAuthModes()
      .then((modes) => {
        if (!active) return;
        setProfileLoginEnabled(Boolean(modes.profile_login_enabled));
      })
      .catch(() => {
        if (!active) return;
        setProfileLoginEnabled(false);
      });
    return () => { active = false; };
  }, []);

  async function handleProfileLogin() {
    setError("");
    if (!actor.trim()) { setError("Identifiant requis"); return; }
    if (!password.trim()) { setError("Mot de passe requis"); return; }
    try {
      setLoading(true);
      await api.loginWithProfile({ actor: actor.trim(), role, password });
      window.location.assign("/");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Échec de connexion");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4">
      <Card className="w-full max-w-sm shadow-xl">
        <CardHeader className="flex flex-col items-center gap-2 pb-2">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary text-primary-foreground">
            <KeyRound className="h-5 w-5" />
          </div>
          <CardTitle className="text-xl">File2EDI</CardTitle>
        </CardHeader>

        <CardContent className="space-y-3 pt-2">
          {profileLoginEnabled && (
            <>
              <div className="space-y-1.5">
                <Label>Identifiant</Label>
                <Input
                  value={actor}
                  placeholder="prenom.nom@bosch.com"
                  onChange={(e) => setActor(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleProfileLogin()}
                />
              </div>
              <div className="space-y-1.5">
                <Label>Profil</Label>
                <Select value={role} onValueChange={(v: "admin" | "adv") => setRole(v)}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="adv">ADV</SelectItem>
                    <SelectItem value="admin">Admin</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label>Mot de passe</Label>
                <Input
                  type="password"
                  value={password}
                  placeholder="Mot de passe"
                  onChange={(e) => setPassword(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleProfileLogin()}
                />
              </div>
              {error && <p className="text-xs text-destructive">{error}</p>}
              <Button className="w-full" onClick={handleProfileLogin} disabled={loading}>
                {loading ? "Connexion..." : "Se connecter"}
                <ArrowRight className="h-4 w-4" />
              </Button>
            </>
          )}

          {!profileLoginEnabled && (
            <Button className="w-full" onClick={startWorkspaceLogin}>
              Connexion Databricks
              <ArrowRight className="h-4 w-4" />
            </Button>
          )}
        </CardContent>
      </Card>
    </div>
  );
}