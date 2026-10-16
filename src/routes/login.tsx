import { useState, type FormEvent } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { GROK_PROVIDERS, authClient, authEnabled, signIn } from "@/lib/auth/client";

export const Route = createFileRoute("/login")({
  component: Login,
});

function Login() {
  const navigate = useNavigate();
  const [mode, setMode] = useState<"in" | "up">("in");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    setError(null);
    const result =
      mode === "up"
        ? await authClient.signUp.email({ name: name || email, email, password })
        : await authClient.signIn.email({ email, password });
    setPending(false);
    if (result.error) {
      setError(result.error.message || "Sign-in failed.");
      return;
    }
    await navigate({ to: "/" });
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-4 py-10">
      <h1 className="font-serif text-4xl text-ink">Household chart</h1>
      <p className="mt-2 text-muted">A private record for the people in your household.</p>
      {!authEnabled ? (
        <p className="mt-6 text-sm text-muted">Sign-in is disabled.</p>
      ) : (
        <div className="mt-6 space-y-6 rounded-md border border-line bg-card p-5">
          <form className="space-y-4" onSubmit={onSubmit}>
            {mode === "up" ? (
              <label className="block text-sm font-medium text-ink">
                Name
                <input
                  className="mt-1 h-11 w-full rounded-md border border-line bg-paper px-3"
                  value={name}
                  autoComplete="name"
                  onChange={(event) => setName(event.target.value)}
                />
              </label>
            ) : null}
            <label className="block text-sm font-medium text-ink">
              Email
              <input
                required
                type="email"
                className="mt-1 h-11 w-full rounded-md border border-line bg-paper px-3"
                value={email}
                autoComplete="email"
                onChange={(event) => setEmail(event.target.value)}
              />
            </label>
            <label className="block text-sm font-medium text-ink">
              Password
              <input
                required
                type="password"
                minLength={8}
                className="mt-1 h-11 w-full rounded-md border border-line bg-paper px-3"
                value={password}
                autoComplete={mode === "up" ? "new-password" : "current-password"}
                onChange={(event) => setPassword(event.target.value)}
              />
            </label>
            {error ? <p className="text-sm text-alert">{error}</p> : null}
            <button
              type="submit"
              disabled={pending}
              className="h-11 w-full rounded-md bg-green font-medium text-green-ink disabled:opacity-60"
            >
              {pending ? "Please wait" : mode === "up" ? "Create account" : "Sign in"}
            </button>
            <button
              type="button"
              className="h-11 w-full rounded-md border border-line bg-paper font-medium text-ink"
              onClick={() => {
                setMode(mode === "up" ? "in" : "up");
                setError(null);
              }}
            >
              {mode === "up" ? "I already have an account" : "Create an account"}
            </button>
          </form>
          <div className="space-y-2">
            {GROK_PROVIDERS.map((provider) => (
              <button
                key={provider.providerId}
                type="button"
                className="h-11 w-full rounded-md border border-line bg-paper font-medium text-ink"
                onClick={() => signIn(provider.providerId, { callbackURL: "/" })}
              >
                Continue with {provider.label}
              </button>
            ))}
          </div>
        </div>
      )}
    </main>
  );
}
