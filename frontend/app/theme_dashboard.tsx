"use client";

import React, { useEffect, useMemo, useState } from "react";
import {
  ArrowRight,
  Flame,
  Layers,
  Link2,
  Newspaper,
  Search,
  TrendingUp,
} from "lucide-react";
import { motion } from "framer-motion";

type Theme = {
  theme_id: string;
  week: string;
  cluster_id?: number;
  label: string;
  size: number;
  top_companies: string[];
  top_keywords: string[];
  example_titles: string[];
  article_ids?: string[];
  centroid?: number[];
  previous_theme_id?: string | null;
  previous_week?: string | null;
  previous_label?: string | null;
  previous_size?: number | null;
  similarity_to_previous?: number | null;
  growth_rate?: number | null;
  is_new_theme?: boolean;
  is_emerging?: boolean;
  next_theme_ids?: string[];
  out_degree?: number;
  emerging_score?: number;
};

type Link = {
  from_week: string;
  to_week: string;
  from_theme_id: string;
  to_theme_id: string;
  from_label: string;
  to_label: string;
  from_size: number;
  to_size: number;
  similarity: number;
};

type DashboardData = {
  weeks: string[];
  stats: {
    num_weeks: number;
    total_themes: number;
    emerging_themes: number;
    new_themes: number;
    average_theme_size: number;
    hottest_theme?: {
      theme_id: string;
      week: string;
      label: string;
      size: number;
      emerging_score: number;
    } | null;
  };
  themes: Theme[];
  emerging: Theme[];
  links: Link[];
};

function formatPct(value?: number | null) {
  if (value == null || Number.isNaN(value)) return "—";
  return `${Math.round(value * 100)}%`;
}

function formatScore(value?: number | null) {
  if (value == null || Number.isNaN(value)) return "—";
  return value.toFixed(2);
}

function normalizeText(s: string) {
  return s.toLowerCase().trim();
}

function uniqueNormalized(values: string[]) {
  const seen = new Set<string>();
  const out: string[] = [];

  for (const value of values) {
    const trimmed = value.trim();
    if (!trimmed) continue;

    const key = normalizeText(trimmed);
    if (seen.has(key)) continue;

    seen.add(key);
    out.push(trimmed);
  }

  return out;
}

function dedupeHeadlines(headlines: string[]) {
  const seen = new Set<string>();
  const out: string[] = [];

  for (const title of headlines) {
    const cleaned = title.replace(/\s+/g, " ").trim();
    if (!cleaned) continue;

    const key = normalizeText(cleaned)
      .replace(/[^\w\s]/g, "")
      .replace(/\s+/g, " ");

    if (seen.has(key)) continue;
    seen.add(key);
    out.push(cleaned);
  }

  return out;
}

function prettifyThemeLabel(label?: string | null) {
  if (!label) return "Untitled theme";

  const parts = label
    .split("|")
    .map((p) => p.trim())
    .filter(Boolean);

  const uniqueParts = uniqueNormalized(parts);

  if (uniqueParts.length === 0) return "Untitled theme";
  if (uniqueParts.length === 1) return uniqueParts[0];

  return uniqueParts.slice(0, 4).join(" · ");
}

function matchesSearch(theme: Theme, q: string) {
  if (!q) return true;
  const haystack = [
    theme.label,
    ...(theme.top_companies || []),
    ...(theme.top_keywords || []),
    ...(theme.example_titles || []),
  ]
    .join(" ")
    .toLowerCase();

  return haystack.includes(q);
}

function buildTrajectory(theme: Theme, themeMap: Map<string, Theme>) {
  const chain: Theme[] = [];
  let current: Theme | undefined = theme;
  let guard = 0;

  while (current && guard < 20) {
    chain.unshift(current);
    const prevId = current.previous_theme_id || undefined;
    current = prevId ? themeMap.get(prevId) : undefined;
    guard += 1;
  }

  return chain;
}

function Card({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`rounded-3xl border border-slate-200 bg-white shadow-[0_1px_2px_rgba(15,23,42,0.04),0_8px_24px_rgba(15,23,42,0.04)] ${className}`}
    >
      {children}
    </div>
  );
}

function Badge({
  children,
  variant = "default",
}: {
  children: React.ReactNode;
  variant?: "default" | "secondary" | "outline" | "subtle";
}) {
  const styles =
    variant === "secondary"
      ? "bg-slate-100 text-slate-800 border border-slate-200"
      : variant === "outline"
      ? "bg-white text-slate-800 border border-slate-300"
      : variant === "subtle"
      ? "bg-slate-50 text-slate-700 border border-slate-200"
      : "bg-slate-900 text-white border border-slate-900";

  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium ${styles}`}
    >
      {children}
    </span>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">
      {children}
    </div>
  );
}

function StatCard({
  title,
  value,
  subtitle,
  icon: Icon,
}: {
  title: string;
  value: string | number;
  subtitle: string;
  icon: React.ComponentType<{ className?: string }>;
}) {
  return (
    <Card>
      <div className="p-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="text-sm font-medium text-slate-600">{title}</div>
            <div className="mt-2 text-3xl font-semibold tracking-tight text-slate-950">
              {value}
            </div>
            <div className="mt-1 text-sm text-slate-600">{subtitle}</div>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-slate-50 p-3 text-slate-700">
            <Icon className="h-5 w-5" />
          </div>
        </div>
      </div>
    </Card>
  );
}

function ThemeCard({ theme }: { theme: Theme }) {
  const displayLabel = prettifyThemeLabel(theme.label);
  const displayCompanies = uniqueNormalized(theme.top_companies || []).slice(0, 6);
  const displayKeywords = uniqueNormalized(theme.top_keywords || []).slice(0, 8);
  const displayHeadlines = dedupeHeadlines(theme.example_titles || []).slice(0, 3);

  return (
    <motion.div layout initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
      <Card className="h-full">
        <div className="p-6">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <div className="text-xl font-semibold leading-tight text-slate-950">
                {displayLabel}
              </div>

              <div className="mt-3 flex flex-wrap gap-2">
                <Badge variant="subtle">{theme.week}</Badge>
                <Badge variant="subtle">{theme.size} articles</Badge>
                {theme.is_new_theme ? (
                  <Badge>New</Badge>
                ) : theme.growth_rate != null ? (
                  <Badge variant="outline">Growth {formatPct(theme.growth_rate)}</Badge>
                ) : null}
                {theme.is_emerging ? <Badge variant="outline">Emerging</Badge> : null}
              </div>
            </div>

            <div className="shrink-0 text-right">
              <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">
                Score
              </div>
              <div className="mt-1 text-2xl font-semibold text-slate-950">
                {formatScore(theme.emerging_score)}
              </div>
            </div>
          </div>

          <div className="mt-6 space-y-5">
            {displayCompanies.length > 0 ? (
              <div>
                <SectionLabel>Top companies</SectionLabel>
                <div className="flex flex-wrap gap-2">
                  {displayCompanies.map((company) => (
                    <Badge key={company} variant="outline">
                      {company}
                    </Badge>
                  ))}
                </div>
              </div>
            ) : null}

            {displayKeywords.length > 0 ? (
              <div>
                <SectionLabel>Top keywords</SectionLabel>
                <div className="flex flex-wrap gap-2">
                  {displayKeywords.map((keyword) => (
                    <Badge key={keyword} variant="secondary">
                      {keyword}
                    </Badge>
                  ))}
                </div>
              </div>
            ) : null}

            <div>
              <SectionLabel>Representative headlines</SectionLabel>
              <div className="space-y-2">
                {displayHeadlines.length > 0 ? (
                  displayHeadlines.map((title) => (
                    <div
                      key={title}
                      className="rounded-2xl border border-slate-200 bg-slate-50/70 p-3 text-sm leading-6 text-slate-800"
                    >
                      {title}
                    </div>
                  ))
                ) : (
                  <div className="rounded-2xl border border-dashed border-slate-200 p-3 text-sm text-slate-500">
                    No example headlines available
                  </div>
                )}
              </div>
            </div>

            <div className="flex items-center justify-between border-t border-slate-200 pt-4 text-sm text-slate-600">
              <div className="pr-4">
                {theme.previous_week
                  ? `Linked from ${theme.previous_week} · similarity ${formatScore(
                      theme.similarity_to_previous
                    )}`
                  : "No linked prior theme"}
              </div>
              <ArrowRight className="h-4 w-4 shrink-0 text-slate-500" />
            </div>
          </div>
        </div>
      </Card>
    </motion.div>
  );
}

function TrajectoryCard({
  theme,
  trajectory,
}: {
  theme: Theme;
  trajectory: Theme[];
}) {
  return (
    <Card>
      <div className="p-6">
        <div className="text-xl font-semibold text-slate-950">
          {prettifyThemeLabel(theme.label)}
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2 text-sm">
          {trajectory.map((item, idx) => (
            <React.Fragment key={item.theme_id}>
              <Badge variant={idx === trajectory.length - 1 ? "default" : "secondary"}>
                {item.week}
              </Badge>
              {idx < trajectory.length - 1 ? (
                <ArrowRight className="h-4 w-4 text-slate-400" />
              ) : null}
            </React.Fragment>
          ))}
        </div>

        <div className="mt-4 space-y-3">
          {trajectory.map((item) => (
            <div
              key={item.theme_id}
              className="rounded-2xl border border-slate-200 bg-slate-50/70 p-3"
            >
              <div className="flex items-center justify-between gap-3">
                <div className="font-medium text-slate-900">{item.week}</div>
                <div className="text-sm text-slate-600">{item.size} articles</div>
              </div>
              <div className="mt-1 text-sm leading-6 text-slate-700">
                {prettifyThemeLabel(item.label)}
              </div>
            </div>
          ))}
        </div>
      </div>
    </Card>
  );
}

export default function ThemeDashboard() {
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [selectedWeek, setSelectedWeek] = useState("all");
  const [selectedTab, setSelectedTab] = useState("emerging");

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        setLoading(true);
        setError(null);
        const res = await fetch("/data/dashboard.json", { cache: "no-store" });
        if (!res.ok) {
          throw new Error(`Failed to load dashboard.json (${res.status})`);
        }
        const data = (await res.json()) as DashboardData;
        if (!cancelled) {
          setDashboard(data);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Unknown error");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, []);

  const weeks = dashboard?.weeks ?? [];
  const themes = dashboard?.themes ?? [];
  const q = normalizeText(search);

  const themeMap = useMemo(() => {
    const map = new Map<string, Theme>();
    for (const theme of themes) map.set(theme.theme_id, theme);
    return map;
  }, [themes]);

  const filteredThemes = useMemo(() => {
    let items = themes.filter((theme) => matchesSearch(theme, q));

    if (selectedWeek !== "all") {
      items = items.filter((theme) => theme.week === selectedWeek);
    }

    if (selectedTab === "emerging") {
      items = items.filter((theme) => theme.is_emerging);
    } else if (selectedTab === "new") {
      items = items.filter((theme) => theme.is_new_theme);
    } else if (selectedTab === "continuing") {
      items = items.filter((theme) => !theme.is_new_theme);
    }

    items.sort((a, b) => {
      const scoreDiff = (b.emerging_score ?? 0) - (a.emerging_score ?? 0);
      if (scoreDiff !== 0) return scoreDiff;
      return b.size - a.size;
    });

    return items;
  }, [themes, q, selectedWeek, selectedTab]);

  const trajectories = useMemo(() => {
    const candidates = filteredThemes.slice(0, 12);
    return candidates.map((theme) => ({
      theme,
      trajectory: buildTrajectory(theme, themeMap),
    }));
  }, [filteredThemes, themeMap]);

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-100 p-6 md:p-8">
        <div className="mx-auto max-w-7xl">
          <Card>
            <div className="p-8 text-slate-700">Loading dashboard data...</div>
          </Card>
        </div>
      </div>
    );
  }

  if (error || !dashboard) {
    return (
      <div className="min-h-screen bg-slate-100 p-6 md:p-8">
        <div className="mx-auto max-w-7xl">
          <Card className="border-red-200">
            <div className="p-8 text-red-700">{error || "Dashboard data not available."}</div>
          </Card>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-100 p-6 md:p-8">
      <div className="mx-auto max-w-7xl space-y-8">
        <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-slate-300 bg-white px-3 py-1 text-sm font-medium text-slate-700 shadow-sm">
              <Flame className="h-4 w-4" />
              Semiconductor theme monitor
            </div>

            <h1 className="mt-3 text-4xl font-semibold tracking-tight text-slate-950">
              Weekly theme dashboard
            </h1>

            <p className="mt-2 max-w-3xl text-base leading-7 text-slate-700">
              Browse clustered weekly themes, identify which ones are newly emerging,
              and inspect how topics evolve over time.
            </p>
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <StatCard
            title="Weeks covered"
            value={dashboard.stats.num_weeks}
            subtitle="Available in the pipeline output"
            icon={Layers}
          />
          <StatCard
            title="Total themes"
            value={dashboard.stats.total_themes}
            subtitle="Across all weeks"
            icon={Newspaper}
          />
          <StatCard
            title="Emerging themes"
            value={dashboard.stats.emerging_themes}
            subtitle="New or fast-growing"
            icon={TrendingUp}
          />
          <StatCard
            title="Hottest theme"
            value={prettifyThemeLabel(dashboard.stats.hottest_theme?.label) || "—"}
            subtitle={
              dashboard.stats.hottest_theme
                ? `${dashboard.stats.hottest_theme.week} · score ${formatScore(
                    dashboard.stats.hottest_theme.emerging_score
                  )}`
                : "No theme available"
            }
            icon={Flame}
          />
        </div>

        <Card>
          <div className="flex flex-col gap-4 p-5 md:flex-row md:items-center md:justify-between">
            <div className="relative w-full md:max-w-md">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search by theme, company, keyword, or headline"
                className="w-full rounded-2xl border border-slate-300 bg-white py-2.5 pl-9 pr-3 text-slate-900 placeholder:text-slate-400 outline-none transition focus:border-slate-500 focus:ring-2 focus:ring-slate-200"
              />
            </div>

            <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
              <div className="flex rounded-2xl border border-slate-200 bg-slate-50 p-1">
                {[
                  { key: "emerging", label: "Emerging" },
                  { key: "new", label: "New" },
                  { key: "continuing", label: "Continuing" },
                  { key: "all", label: "All" },
                ].map((tab) => (
                  <button
                    key={tab.key}
                    onClick={() => setSelectedTab(tab.key)}
                    className={`rounded-xl px-3 py-2 text-sm font-medium transition ${
                      selectedTab === tab.key
                        ? "bg-slate-900 text-white shadow-sm"
                        : "text-slate-700 hover:bg-white"
                    }`}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>

              <select
                value={selectedWeek}
                onChange={(e) => setSelectedWeek(e.target.value)}
                className="w-[190px] rounded-2xl border border-slate-300 bg-white px-3 py-2.5 text-slate-900 outline-none transition focus:border-slate-500 focus:ring-2 focus:ring-slate-200"
              >
                <option value="all">All weeks</option>
                {[...weeks].reverse().map((week) => (
                  <option key={week} value={week}>
                    {week}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </Card>

        {filteredThemes.length === 0 ? (
          <Card>
            <div className="p-10 text-center">
              <div className="text-lg font-semibold text-slate-900">No themes found</div>
              <div className="mt-2 text-sm text-slate-600">
                Try a different search term, tab, or week filter.
              </div>
            </div>
          </Card>
        ) : (
          <div className="grid gap-5 lg:grid-cols-2 2xl:grid-cols-3">
            {filteredThemes.map((theme) => (
              <ThemeCard key={theme.theme_id} theme={theme} />
            ))}
          </div>
        )}

        {trajectories.length > 0 ? (
          <div className="space-y-4">
            <div className="flex items-center gap-2 text-slate-900">
              <Link2 className="h-5 w-5" />
              <h2 className="text-2xl font-semibold tracking-tight">Theme trajectories</h2>
            </div>

            <div className="grid gap-5 lg:grid-cols-2">
              {trajectories.map(({ theme, trajectory }) => (
                <TrajectoryCard key={theme.theme_id} theme={theme} trajectory={trajectory} />
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}