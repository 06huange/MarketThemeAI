import React, { useEffect, useMemo, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ArrowRight, Flame, Layers, Link2, Newspaper, Search, TrendingUp } from "lucide-react";
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
    <Card className="rounded-2xl shadow-sm">
      <CardContent className="p-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="text-sm text-slate-500">{title}</div>
            <div className="mt-2 text-3xl font-semibold tracking-tight">{value}</div>
            <div className="mt-1 text-sm text-slate-500">{subtitle}</div>
          </div>
          <div className="rounded-2xl bg-slate-100 p-3">
            <Icon className="h-5 w-5" />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function ThemeCard({ theme }: { theme: Theme }) {
  return (
    <motion.div layout initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
      <Card className="h-full rounded-2xl shadow-sm">
        <CardHeader className="pb-3">
          <div className="flex items-start justify-between gap-3">
            <div>
              <CardTitle className="text-lg leading-tight">{theme.label || "untitled theme"}</CardTitle>
              <div className="mt-2 flex flex-wrap gap-2">
                <Badge variant="secondary">{theme.week}</Badge>
                <Badge variant="secondary">{theme.size} articles</Badge>
                {theme.is_new_theme ? (
                  <Badge>New</Badge>
                ) : (
                  <Badge variant="outline">Growth {formatPct(theme.growth_rate)}</Badge>
                )}
                {theme.is_emerging ? <Badge variant="outline">Emerging</Badge> : null}
              </div>
            </div>
            <div className="text-right">
              <div className="text-xs uppercase tracking-wide text-slate-500">Score</div>
              <div className="text-2xl font-semibold">{formatScore(theme.emerging_score)}</div>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <div className="mb-2 text-sm font-medium">Top companies</div>
            <div className="flex flex-wrap gap-2">
              {theme.top_companies?.length ? (
                theme.top_companies.map((company) => (
                  <Badge key={company} variant="outline">{company}</Badge>
                ))
              ) : (
                <span className="text-sm text-slate-500">None extracted</span>
              )}
            </div>
          </div>

          <div>
            <div className="mb-2 text-sm font-medium">Top keywords</div>
            <div className="flex flex-wrap gap-2">
              {theme.top_keywords?.length ? (
                theme.top_keywords.map((keyword) => (
                  <Badge key={keyword} variant="secondary">{keyword}</Badge>
                ))
              ) : (
                <span className="text-sm text-slate-500">None extracted</span>
              )}
            </div>
          </div>

          <div>
            <div className="mb-2 text-sm font-medium">Representative headlines</div>
            <div className="space-y-2">
              {(theme.example_titles || []).slice(0, 3).map((title) => (
                <div key={title} className="rounded-xl border border-slate-200 p-3 text-sm text-slate-700">
                  {title}
                </div>
              ))}
              {!theme.example_titles?.length ? (
                <div className="rounded-xl border border-dashed border-slate-200 p-3 text-sm text-slate-500">
                  No example titles available
                </div>
              ) : null}
            </div>
          </div>

          <div className="flex items-center justify-between border-t pt-3 text-sm text-slate-500">
            <div>
              {theme.previous_week
                ? `From ${theme.previous_week} · similarity ${formatScore(theme.similarity_to_previous)}`
                : "No linked prior theme"}
            </div>
            <ArrowRight className="h-4 w-4" />
          </div>
        </CardContent>
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
    <Card className="rounded-2xl shadow-sm">
      <CardHeader>
        <CardTitle className="text-lg">{theme.label}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-center gap-2 text-sm">
          {trajectory.map((item, idx) => (
            <React.Fragment key={item.theme_id}>
              <Badge variant={idx === trajectory.length - 1 ? "default" : "secondary"}>
                {item.week}
              </Badge>
              {idx < trajectory.length - 1 ? <ArrowRight className="h-4 w-4 text-slate-400" /> : null}
            </React.Fragment>
          ))}
        </div>
        <div className="space-y-2">
          {trajectory.map((item) => (
            <div key={item.theme_id} className="rounded-xl border border-slate-200 p-3">
              <div className="flex items-center justify-between gap-3">
                <div className="font-medium">{item.week}</div>
                <div className="text-sm text-slate-500">{item.size} articles</div>
              </div>
              <div className="mt-1 text-sm text-slate-600">{item.label}</div>
            </div>
          ))}
        </div>
      </CardContent>
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
      <div className="min-h-screen bg-slate-50 p-8">
        <div className="mx-auto max-w-7xl">
          <Card className="rounded-2xl">
            <CardContent className="p-8 text-slate-600">Loading dashboard data...</CardContent>
          </Card>
        </div>
      </div>
    );
  }

  if (error || !dashboard) {
    return (
      <div className="min-h-screen bg-slate-50 p-8">
        <div className="mx-auto max-w-7xl">
          <Card className="rounded-2xl border-red-200">
            <CardContent className="p-8 text-red-600">
              {error || "Dashboard data not available."}
            </CardContent>
          </Card>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50 p-6 md:p-8">
      <div className="mx-auto max-w-7xl space-y-8">
        <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border bg-white px-3 py-1 text-sm text-slate-600 shadow-sm">
              <Flame className="h-4 w-4" />
              Semiconductor theme monitor
            </div>
            <h1 className="mt-3 text-4xl font-semibold tracking-tight">Weekly theme dashboard</h1>
            <p className="mt-2 max-w-3xl text-base text-slate-600">
              Browse clustered weekly themes, identify which ones are newly emerging, and inspect how topics evolve across time.
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
            value={dashboard.stats.hottest_theme?.label?.split("|")[0]?.trim() || "—"}
            subtitle={dashboard.stats.hottest_theme ? `${dashboard.stats.hottest_theme.week} · score ${formatScore(dashboard.stats.hottest_theme.emerging_score)}` : "No theme available"}
            icon={Flame}
          />
        </div>

        <Card className="rounded-2xl shadow-sm">
          <CardContent className="flex flex-col gap-4 p-5 md:flex-row md:items-center md:justify-between">
            <div className="relative w-full md:max-w-md">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search by theme, company, keyword, or headline"
                className="rounded-2xl pl-9"
              />
            </div>

            <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
              <Tabs value={selectedTab} onValueChange={setSelectedTab}>
                <TabsList className="grid w-full grid-cols-4 rounded-2xl">
                  <TabsTrigger value="emerging">Emerging</TabsTrigger>
                  <TabsTrigger value="new">New</TabsTrigger>
                  <TabsTrigger value="continuing">Continuing</TabsTrigger>
                  <TabsTrigger value="all">All</TabsTrigger>
                </TabsList>
              </Tabs>

              <Select value={selectedWeek} onValueChange={setSelectedWeek}>
                <SelectTrigger className="w-[190px] rounded-2xl bg-white">
                  <SelectValue placeholder="Select week" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All weeks</SelectItem>
                  {[...weeks].reverse().map((week) => (
                    <SelectItem key={week} value={week}>{week}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </CardContent>
        </Card>

        <div className="grid gap-5 lg:grid-cols-2 2xl:grid-cols-3">
          {filteredThemes.map((theme) => (
            <ThemeCard key={theme.theme_id} theme={theme} />
          ))}
        </div>

        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <Link2 className="h-5 w-5" />
            <h2 className="text-2xl font-semibold tracking-tight">Theme trajectories</h2>
          </div>
          <div className="grid gap-5 lg:grid-cols-2">
            {trajectories.map(({ theme, trajectory }) => (
              <TrajectoryCard key={theme.theme_id} theme={theme} trajectory={trajectory} />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
