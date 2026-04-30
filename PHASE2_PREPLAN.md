# Phase 2 Pre-Plan: Autonomous Blog as a Web Service

Running notes captured while building the Copier template. Updated as findings emerge.

---

## What each blog produces that a service would need to index

- `content/posts/YYYY-MM-DD.md` — daily posts with YAML front matter: title, date, tags, description, relevance metadata
- `content/posts/YYYY-MM-DD-{slug}.md` — weekly roundup posts tagged `[roundup]`
- `static/search-index.json` — pre-computed embeddings (bge-small-en-v1.5) for semantic search
- `agents/seen.json` — URL deduplication state (60-day rolling window of published URLs)
- `roundup_topics.txt` — accumulated topic watchlist with surface counts and first-seen dates

A service would need to store all of these per-topic, not per-repo.

---

## What's topic-specific vs truly universal

**Topic-specific (changes per blog):**
- `config.py` fields: BLOG_NAME, BLOG_SLUG, BLOG_URL, BLOG_GITHUB, BOT_NAME, BOT_EMAIL, BLOG_DESCRIPTION
- `sources.py`: all fetcher functions and ALL_SOURCES dict
- Agent system prompts: `audience_description` and `topic_focus` strings
- `_HN_STORY_QUERIES`, `_HN_ASK_QUERIES`, `_STACKOVERFLOW_TAGS`, `_DEVTO_TAGS`, `_GITHUB_PAIN_REPOS` in `topic_agent.py`
- `CLIMATE_KEYWORDS` / `_TOPIC_KEYWORDS` regex in `sources.py`
- Hugo theme name (matches blog_slug)
- `hugo.toml`: baseURL, title, description

**Truly universal (no changes needed):**
- `model_selector.py` — pure OpenRouter model polling
- `validate_post.py` / `validate_roundup.py` — structural validators
- `rewrite_agent.py` — tone rewriter
- `build_index.py` — fastembed index builder
- `holidays.py` — holiday calendar
- `roundup_agent.py` — topic research logic (GitHub + HN search, deduped)
- All Hugo layouts and CSS (fully CSS-variable-based, no hardcoded colors)
- All GitHub Actions workflow logic (except bot name/email)
- The source fetcher infrastructure (`_get`, `_quality_score`, `_try_model`, retry/backoff patterns)

**Key insight:** The only truly topic-specific code is `sources.py` (what to fetch) and the system prompt strings embedded in agents. Everything else is generic pipeline infrastructure. This maps cleanly to a config schema.

---

## Config.py → DB schema mapping

Each `config.py` field maps directly to a `topics` table column:

```sql
CREATE TABLE topics (
  id           UUID PRIMARY KEY,
  user_id      UUID REFERENCES users(id),
  name         TEXT NOT NULL,          -- BLOG_NAME
  slug         TEXT NOT NULL UNIQUE,   -- BLOG_SLUG
  url          TEXT,                   -- BLOG_URL (set after GitHub Pages deploy)
  github_repo  TEXT,                   -- BLOG_GITHUB (owner/repo)
  description  TEXT,                   -- BLOG_DESCRIPTION
  -- Source config (replaces sources.py)
  arxiv_categories  JSONB DEFAULT '[]',
  hn_keywords       JSONB DEFAULT '[]',
  rss_feeds         JSONB DEFAULT '[]',  -- [{name, url}]
  github_topics     JSONB DEFAULT '[]',
  -- Agent prompt config
  audience_description TEXT,
  topic_focus          TEXT,
  -- State
  seen_urls    JSONB DEFAULT '{"urls": []}',  -- or separate table
  created_at   TIMESTAMPTZ DEFAULT now(),
  last_post_at TIMESTAMPTZ
);
```

The `seen.json` rolling window could stay as JSONB on the topic row for simplicity, or move to a separate `seen_urls` table if scale requires it.

---

## What makes sources composable

The Copier template revealed a clean 4-type source taxonomy:
1. **ArXiv** — category code → RSS → structured items
2. **HN search** — keyword → Algolia API → scored items
3. **RSS feeds** — {name, url} → feedparser → structured items
4. **GitHub topics** — topic slug → GH search API → quality-scored repos

Plus two derived sources that work for any topic with minimal config:
- **GitHub trending** — filter by keyword regex (derived from topic_focus)
- **HN Ask** — first word of each HN keyword (pain-point signal)

A service would represent this as a `sources` config object (JSONB on the topic row) and have a single generic `fetch_sources(topic_config)` function that loops over the typed source list. No code generation required — just data-driven dispatch.

---

## Topic "registration" UX for a web service

The Copier template prompts map directly to a multi-step web form:

**Step 1: Identity**
- Blog name, slug, description

**Step 2: Audience**
- Who is the audience? (textarea)
- What topics does this cover? (tags input)

**Step 3: Sources** (optional, collapsible)
- ArXiv categories (tag input with autocomplete for known codes)
- HN keywords (tag input)
- RSS feeds (add/remove rows with name+url)
- GitHub topics (tag input)

**Step 4: GitHub setup**
- GitHub repo (owner/name)
- Instructions to add OPENROUTER_API_KEY secret and enable Pages

On submit: generate the repo via GitHub API (template from this repo), push config, trigger first run.

---

## How the agent pipeline would run in a service context

**Current model (GitHub Actions):**
- Cron → GHA runner → Python scripts → commit to repo → gh-pages deploy

**Service model options:**

Option A: Keep GHA, replace config files with API calls
- Service manages `config.py` / `sources.py` as generated files per repo
- Still one GHA repo per topic — scales to ~100s of topics before management cost hurts
- Low ops cost, familiar to users

Option B: Central worker pool
- Service has a scheduler (cron) → job queue (e.g. pg_cron + LISTEN/NOTIFY)
- Worker pool runs the pipeline for each topic, writing to a central DB
- Hugo replaced with server-side rendering or a shared static builder
- Higher ops complexity, required for >1000 topics

Option C: Hybrid
- Service orchestrates GHA via workflow_dispatch API
- Central DB tracks state, GHA does the heavy lifting
- Good middle ground for MVP

**Recommendation for Phase 2 MVP:** Option C. Use GHA dispatch to run the pipeline, service manages state and the registration UX. When GHA limits become painful, migrate hot topics to Option B.

---

## What's worth keeping from the static Hugo approach

**Keep:**
- Hugo as the rendering engine — zero-cost, fast, no server
- `static/search-index.json` — client-side semantic search is great UX
- The CSS variable theme system — works as-is for any topic
- The `seen.json` rolling window pattern — simple, effective

**What needs to change:**
- One repo per topic doesn't scale beyond ~50 blogs managed by one person
- Hugo baseURL must be set correctly per-topic (currently manual post-generation step)
- The GitHub Actions bot commit pattern is fine for individual blogs but creates noise at scale
- `holidays.py` is US-centric; needs locale support for a multi-user service

---

## Minimal schema for users + topics + subscriptions

```sql
CREATE TABLE users (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email      TEXT UNIQUE NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- topics table: see above

CREATE TABLE subscriptions (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id    UUID REFERENCES users(id),
  topic_id   UUID REFERENCES topics(id),
  -- For future email digest delivery:
  frequency  TEXT DEFAULT 'daily',  -- 'daily' | 'weekly' | 'none'
  created_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE (user_id, topic_id)
);

-- For tracking what ran and when:
CREATE TABLE pipeline_runs (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  topic_id    UUID REFERENCES topics(id),
  run_type    TEXT NOT NULL,  -- 'daily' | 'roundup'
  status      TEXT NOT NULL,  -- 'running' | 'success' | 'failed'
  post_path   TEXT,
  started_at  TIMESTAMPTZ DEFAULT now(),
  finished_at TIMESTAMPTZ
);
```

---

## Decisions made during template build

**Delimiter strategy for Hugo vs Copier:** Used `{% raw %}...{% endraw %}` blocks around Hugo template expressions (`{{ }}`) inside `.jinja` files. This is the official Jinja2 approach and requires no Copier configuration changes. Files without `.jinja` suffix are copied verbatim, so pure Hugo templates (layouts) don't need any escaping.

**sources.py generation approach:** Chose data-driven Jinja2 conditionals over code generation. The template generates clean Python that reads naturally — no "this was generated" smell. ArXiv categories collapse into one function (not one per category), HN keywords collapse into two functions (stories + ask), RSS feeds get one function each with meaningful names derived from the feed name.

**Generic agents with no templating:** `model_selector.py`, `validate_post.py`, `validate_roundup.py`, `rewrite_agent.py`, `build_index.py`, `holidays.py`, `roundup_agent.py` are truly topic-agnostic. They import from `config.py` but don't have any topic strings embedded. This is the right abstraction boundary.

**Bot name/email is topic-specific:** Even "generic" workflows like `rebuild-index.yml` need the bot name. Every workflow that commits to the repo needs templating. Added `.jinja` suffix to all committing workflows.

**analytics stripped from head.html:** The Plausible snippet in Terra's `head.html` is a personal/paid analytics setup. Replaced with a comment for users to add their own. This was the only truly instance-specific thing in the theme files.

---

## Source Reliability Tiers

Not all RSS/Atom sources are equal. A service needs to handle them differently based on how intentional and stable they are.

**Tier 1 — Stable (intentional APIs):**
- ArXiv RSS (`arxiv.org/rss/{category}`)
- GitHub Atom releases (`github.com/{owner}/{repo}/releases.atom`)
- YouTube Atom feeds (`youtube.com/feeds/videos.xml?channel_id=...`)
- Google News RSS (`news.google.com/rss/search?q=...`)
- Any site's own RSS/Atom feed (explicitly offered)

These are deliberately exposed and rarely change structure. Treat failures as transient network issues, not structural breakage.

**Tier 2 — Fragile (works but not guaranteed):**
- Reddit RSS (`reddit.com/r/{sub}/hot.rss`) — has been throttled, restructured, and rate-limited before. Requires a descriptive User-Agent and silent failure handling.
- GitHub trending HTML scrape (`github.com/trending`) — HTML layout changes break CSS selectors without warning.

Tier 2 sources need: retry logic, silent failure (return `[]` rather than raising), and monitoring so breakage is detected quickly.

**Tier 3 — Off-limits without significant investment:**
- Twitter/X — API costs $100+/mo for basic read access. Not worth it.
- Most major social platform main feeds (Instagram, TikTok, LinkedIn) — actively block scrapers, no official RSS.
- Any site with aggressive anti-bot measures (Cloudflare challenges, fingerprinting).

Don't attempt Tier 3. The cost and maintenance burden exceed the value for a free-tier autonomous blog.

**Service implication:** The `sources` JSONB column on the `topics` table should include a `tier` field for each source entry. The pipeline runner uses this to apply appropriate resilience: Tier 1 gets standard retry, Tier 2 gets silent failure + monitoring alert on repeated misses, Tier 3 is rejected at config validation time with a clear error message explaining why.

---

## Source Health Monitoring

**Registration-time coverage check:** When a user registers a new topic via the web UI, run `check_sources.py` server-side against the proposed source config before committing to daily generation. If fewer than half the sources return items with at least 50% keyword relevance, surface a warning in the UI — "Your sources may not cover this topic well. Consider adding more RSS feeds or ArXiv categories." Don't hard-block registration; just warn and let the user proceed.

**Continuous health monitoring:** A background job runs each topic's source config daily and stores results in a `source_health` table:

```sql
CREATE TABLE source_health (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  topic_id         UUID REFERENCES topics(id),
  source_name      TEXT NOT NULL,
  checked_at       TIMESTAMPTZ DEFAULT now(),
  item_count       INTEGER NOT NULL,
  relevance_score  FLOAT,  -- fraction of items matching topic keywords (0.0–1.0)
  error            TEXT    -- NULL if successful
);
```

Trend data from this table lets you detect gradual degradation (e.g. Reddit throttling slowly reducing counts over weeks) before it meaningfully harms post quality. Alert when a 7-day rolling average drops below 50% of the 30-day baseline for that source.

**Tier-aware alerting thresholds:** The `tier` field on source configs informs alert sensitivity. Tier 1 sources (stable APIs) generate an alert after a single day of 0 items. Tier 2 sources (Reddit RSS, GitHub trending scrape) use a 3-day window before alerting and never page on-call — they go to a low-priority Slack channel. A Tier 2 source producing 0 items is expected occasionally and should not interrupt the human.

**Visual and audio content gap:** The pipeline is fundamentally text-based — it indexes titles, descriptions, and short excerpts. Topics where the primary artifact is an image, video, or audio file cannot be well-served by this architecture without a separate understanding layer:

- **Out of scope for v1:** fashion, TikTok trends, visual art, podcast-first communities, live sports scores.
- **Reason:** Even if RSS feeds exist for these topics, the signal is weak — a fashion RSS feed yields article titles, not the images that carry the content. The LLM writing agent cannot compensate for missing signal.
- **Path to v1 support:** An image captioning sidecar (CLIP/LLaVA) or podcast transcription sidecar (Whisper) could unblock these topics in v2. Flag them at registration time with a clear explanation, not a silent failure.
