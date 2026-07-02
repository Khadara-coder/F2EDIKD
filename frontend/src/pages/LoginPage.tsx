import { useEffect, useState } from "react";
import { ArrowRight, KeyRound, LockKeyhole, ShieldCheck, Sparkles } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";

const loginHighlights = [
  {
    icon: ShieldCheck,
    title: "Accès sécurisé",
    description: "Authentification SSO Databricks avec contrôle des rôles applicatifs.",
  },
  {
    icon: LockKeyhole,
    title: "Traçabilité complète",
    description: "Chaque action est auditée avec acteur, timestamp et résultat métier.",
  },
  {
    icon: Sparkles,
    title: "Flux EDIFACT unifié",
    description: "Extraction, revue, génération et livraison depuis une seule interface.",
  },
];

function startWorkspaceLogin() {
  window.location.assign(`${window.location.origin}/`);
}

export function LoginPage() {
  const [actor, setActor] = useState("dik1dy@bosch.com");
  const [role, setRole] = useState<"admin" | "adv">("adv");
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
    return () => {
      active = false;
    };
  }, []);

  async function handleProfileLogin() {
    setError("");
    if (!actor.trim()) {
      setError("Identifiant requis");
      return;
    }
    try {
      setLoading(true);
      await api.loginWithProfile({ actor: actor.trim(), role });
      window.location.assign("/");
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Échec de connexion";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-[radial-gradient(1100px_circle_at_15%_-15%,hsl(var(--accent)),transparent_50%),radial-gradient(900px_circle_at_95%_0%,hsl(var(--secondary)),transparent_45%),linear-gradient(180deg,hsl(var(--background)),hsl(var(--background)))] p-4 md:p-8">
      <div className="mx-auto grid min-h-[calc(100vh-2rem)] w-full max-w-6xl overflow-hidden rounded-3xl border border-border/70 bg-card/60 shadow-2xl backdrop-blur md:grid-cols-[1.2fr_0.8fr] md:p-2">
        <section className="flex flex-col justify-between p-8 md:p-12">
          <div>
            <p className="mb-3 inline-flex items-center rounded-full border border-border bg-background/70 px-3 py-1 text-xs font-medium text-muted-foreground">
              FILE2EDI · Bosch Thermotechnologie France
            </p>
            <h1 className="max-w-xl text-3xl font-semibold leading-tight text-foreground md:text-4xl">
              Connexion requise pour accéder au cockpit EDIFACT
            </h1>
            <p className="mt-4 max-w-xl text-sm leading-relaxed text-muted-foreground md:text-base">
              Cette application est protégée. Connecte-toi avec ton compte Databricks Workspace
              pour accéder aux conversions, à la revue et à l&apos;historique.
            </p>
          </div>

          <div className="mt-8 grid gap-4 md:mt-0">
            {loginHighlights.map(({ icon: Icon, title, description }) => (
              <article key={title} className="rounded-xl border border-border/70 bg-background/60 p-4">
                <div className="flex items-start gap-3">
                  <span className="mt-0.5 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                    <Icon className="h-4 w-4" />
                  </span>
                  <div>
                    <h2 className="text-sm font-semibold text-foreground">{title}</h2>
                    <p className="mt-1 text-sm text-muted-foreground">{description}</p>
                  </div>
                </div>
              </article>
            ))}
          </div>
        </section>

        <section className="flex items-center justify-center border-t border-border/70 bg-background/85 p-6 md:border-l md:border-t-0 md:p-10">
          <Card className="w-full max-w-md border-border/80 shadow-xl">
            <CardHeader className="space-y-3">
              <div className="inline-flex h-11 w-11 items-center justify-center rounded-xl bg-primary text-primary-foreground">
                <KeyRound className="h-5 w-5" />
              </div>
              <CardTitle className="text-2xl">Se connecter</CardTitle>
              <CardDescription>
                Utilise l&apos;authentification Databricks pour ouvrir ta session File2EDI.
              </CardDescription>
            </CardHeader>

            <CardContent className="space-y-4">
              {profileLoginEnabled && (
                <div className="space-y-3 rounded-lg border border-border/70 bg-muted/30 p-3">
                  <div className="space-y-1.5">
                    <Label>Identifiant utilisateur</Label>
                    <Input
                      value={actor}
                      placeholder="prenom.nom@bosch.com"
                      onChange={(e) => setActor(e.target.value)}
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label>Profil souhaité</Label>
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
                  {error && <p className="text-xs text-destructive">{error}</p>}
                  <Button className="w-full" size="lg" onClick={handleProfileLogin} disabled={loading}>
                    {loading ? "Connexion..." : "Connexion par profil"}
                    <ArrowRight className="h-4 w-4" />
                  </Button>
                </div>
              )}

              <Button className="w-full" size="lg" variant="outline" onClick={startWorkspaceLogin}>
                Connexion Databricks Workspace
                <ArrowRight className="h-4 w-4" />
              </Button>

              <Separator />

              <p className="text-xs leading-relaxed text-muted-foreground">
                En local, tu peux choisir ton profil. En Databricks, utilise la connexion Workspace
                pour récupérer ton identité SSO.
              </p>
            </CardContent>

            <CardFooter>
              <p className="text-xs text-muted-foreground">Version sécurisée · accès role-based</p>
            </CardFooter>
          </Card>
        </section>
      </div>
    </div>
  );
}