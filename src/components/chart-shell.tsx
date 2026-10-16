import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { Link, useRouterState } from "@tanstack/react-router";
import { RedirectToSignIn, UserButton } from "@/lib/auth/gates";
import { useCurrentUserState } from "@/lib/auth/use-current-user";
import {
  getChartState,
  setActiveProfile,
  type ChartState,
} from "@/lib/chart/household";

const NAV = [
  { to: "/", label: "Dashboard" },
  { to: "/problems", label: "Problems" },
  { to: "/medications", label: "Medications" },
  { to: "/allergies", label: "Allergies" },
  { to: "/encounters", label: "Encounters" },
  { to: "/immunizations", label: "Immunizations" },
  { to: "/procedures", label: "Procedures" },
  { to: "/family", label: "Family" },
  { to: "/social", label: "Social" },
  { to: "/vitals", label: "Vitals" },
  { to: "/implants", label: "Implants" },
  { to: "/providers", label: "Providers" },
  { to: "/insurance", label: "Insurance" },
  { to: "/pharmacy", label: "Pharmacy" },
  { to: "/contacts", label: "Contacts" },
  { to: "/appointments", label: "Appointments" },
  { to: "/labs", label: "Labs" },
  { to: "/imaging", label: "Imaging" },
  { to: "/documents", label: "Documents" },
  { to: "/emergency", label: "Emergency" },
] as const;

type ChartContextValue = {
  state: ChartState | null;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  replace: (next: ChartState) => void;
};

const ChartContext = createContext<ChartContextValue | null>(null);

export function useChart(): ChartContextValue {
  const value = useContext(ChartContext);
  if (!value) throw new Error("Chart is only available inside the shell");
  return value;
}

export function displayName(profile: { preferredName: string | null; legalName: string }): string {
  return profile.preferredName || profile.legalName;
}

export function ChartShell({ children }: { children: ReactNode }) {
  const { user, isPending } = useCurrentUserState();
  const pathname = useRouterState({ select: (state) => state.location.pathname });
  const [state, setState] = useState<ChartState | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [switching, setSwitching] = useState(false);

  const refresh = useCallback(async () => {
    setError(null);
    const next = await getChartState();
    setState(next);
  }, []);

  useEffect(() => {
    if (!user) return;
    let cancelled = false;
    setLoading(true);
    getChartState()
      .then((next) => {
        if (!cancelled) setState(next);
      })
      .catch(() => {
        if (!cancelled) setError("The household could not be opened.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [user?.id]);

  if (isPending) {
    return (
      <div className="mx-auto min-h-screen max-w-3xl px-4 py-8">
        <p className="text-sm text-muted">Opening your chart</p>
        <div className="mt-4 h-8 w-40 animate-pulse rounded-md bg-line" />
        <div className="mt-6 h-24 animate-pulse rounded-md bg-line" />
      </div>
    );
  }
  if (!user) return <RedirectToSignIn />;

  const active = state?.profiles.find((profile) => profile.id === state.activeProfileId) ?? null;

  async function onSwitch(profileId: string) {
    setSwitching(true);
    setError(null);
    try {
      const next = await setActiveProfile({ data: { profileId } });
      setState(next);
    } catch {
      setError("That person is not in this household.");
    } finally {
      setSwitching(false);
    }
  }

  return (
    <ChartContext.Provider
      value={{
        state,
        loading,
        error,
        refresh,
        replace: setState,
      }}
    >
      <div className="flex min-h-screen flex-col">
        <header className="border-b border-line bg-card">
          <div className="mx-auto flex max-w-3xl flex-col gap-4 px-4 py-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-sm text-muted">{state?.householdName ?? "Household"}</p>
                <h1 className="font-serif text-3xl leading-tight text-ink">
                  {active ? displayName(active) : "Household chart"}
                </h1>
              </div>
              <UserButton />
            </div>
            <label className="block text-sm font-medium text-ink">
              Person
              <select
                className="mt-1 h-11 w-full rounded-md border border-line bg-paper px-3 text-ink"
                value={state?.activeProfileId ?? ""}
                disabled={switching || !state || state.profiles.length === 0}
                onChange={(event) => {
                  if (event.target.value) void onSwitch(event.target.value);
                }}
              >
                {state && state.profiles.length === 0 ? <option value="">No one yet</option> : null}
                {state?.profiles.map((profile) => (
                  <option key={profile.id} value={profile.id}>
                    {displayName(profile)}
                  </option>
                ))}
              </select>
            </label>
            <nav className="flex flex-wrap gap-2" aria-label="Chart">
              {NAV.map((item) => {
                const current = item.to === "/" ? pathname === "/" : pathname === item.to;
                return (
                  <Link
                    key={item.to}
                    to={item.to}
                    className={
                      "inline-flex h-11 items-center rounded-md px-3 text-sm font-medium " +
                      (current ? "bg-green text-green-ink" : "bg-paper text-ink")
                    }
                  >
                    {item.label}
                  </Link>
                );
              })}
            </nav>
          </div>
        </header>
        <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-6">{children}</main>
        <footer className="border-t border-line px-4 py-4 text-sm text-muted">
          <p className="mx-auto max-w-3xl">
            This is a personal household record. It is not a medical device, not an emergency
            service, and not a substitute for your clinicians or the original report. Ranges shown
            are the ranges that came with the result.
          </p>
        </footer>
      </div>
    </ChartContext.Provider>
  );
}
