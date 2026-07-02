import { ArrowRight, KeyRound, LockKeyhole, ShieldCheck, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
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
              <Button className="w-full" size="lg" onClick={startWorkspaceLogin}>
                Connexion Databricks
                <ArrowRight className="h-4 w-4" />
              </Button>

              <Separator />

              <p className="text-xs leading-relaxed text-muted-foreground">
                Si la connexion ne démarre pas automatiquement, clique sur le bouton ci-dessus ou
                recharge la page dans ton navigateur workspace.
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