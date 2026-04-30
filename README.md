# Autonomous Blog Template

A [Copier](https://copier.readthedocs.io/) template for spinning up an autonomous daily AI-powered blog on any topic. Posts are researched, written, and published automatically via GitHub Actions using OpenRouter free-tier LLMs.

## Quick start

```bash
pip install copier
copier copy gh:mcfredrick/autonomous-blog-template my-new-blog
cd my-new-blog
```

Answer the prompts, then:

1. Create a GitHub repo and push
2. Add `OPENROUTER_API_KEY` to repo Settings → Secrets → Actions
3. Enable GitHub Pages: Settings → Pages → Source: Deploy from branch `gh-pages`, root `/`
4. Trigger the first run: Actions → Daily Digest → Run workflow

The blog will publish daily at 08:00 UTC and weekly roundups every Monday at 09:00 UTC.

## What you'll answer

| Question | Example |
|---|---|
| `blog_name` | `Terra` |
| `blog_slug` | `terra` |
| `blog_description` | `Daily climate tech digest for engineers` |
| `audience_description` | `engineers pivoting into climate tech` |
| `topic_focus` | `climate, clean energy, sustainability, agriculture` |
| `github_repo` | `mcfredrick/terra` |
| `arxiv_categories` | `[eess.SY, physics.ao-ph, cond-mat.mtrl-sci]` |
| `hn_keywords` | `[climate tech, clean energy, carbon capture]` |
| `rss_feeds` | `[{name: IEA, url: 'https://www.iea.org/feed/news'}]` |
| `github_topics` | `[solar-energy, carbon-footprint, climate-model]` |

## Architecture

```
agents/
  config.py          ← blog identity (generated from your answers)
  sources.py         ← data fetchers (generated from your sources config)
  research_agent.py  ← fetches + LLM-filters content
  writing_agent.py   ← writes daily post
  topic_agent.py     ← picks weekly roundup topic
  roundup_agent.py   ← researches roundup topic
  roundup_writer.py  ← writes weekly roundup
  validate_post.py   ← gates the commit
  model_selector.py  ← picks best available free LLM
  build_index.py     ← builds semantic search index
  holidays.py        ← holiday theming
  seen.json          ← URL deduplication (60-day rolling window)

.github/workflows/
  daily-post.yml     ← 08:00 UTC daily pipeline
  roundup.yml        ← 09:00 UTC Monday roundup
  publish.yml        ← Hugo build + gh-pages deploy
  rebuild-index.yml  ← semantic search index rebuild
  restyle-posts.yml  ← rewrite existing posts with updated tone
  tests.yml          ← pytest on push/PR

themes/{blog_slug}/  ← minimal Hugo theme (CSS variables, dark/light mode)
content/posts/       ← generated markdown posts
hugo.toml            ← Hugo config
```

## Customizing sources

After generation, edit `agents/sources.py` to:
- Add more RSS feeds
- Add domain-specific APIs
- Tune the GitHub topic list
- Add GitHub repos to monitor for issue signals in `topic_agent.py`

## Costs

Zero. Uses OpenRouter free-tier models only. The pipeline has built-in rate-limit handling and model rotation.

## Optional: semantic search

The blog ships with a semantic search page powered by `fastembed` + `transformers.js`. The index rebuilds automatically after each post. No external service required — index is stored as `static/search-index.json` in the repo.

## Testing your sources

Before relying on your blog to publish daily, verify your sources return relevant results:

```bash
# Check all sources return relevant results
python agents/check_sources.py --keywords "your topic keywords here"
```

This script calls every source fetcher, reports item counts and 3 sample titles per source, and scores relevance against your keywords. It exits with code 1 if more than half the sources return 0 items, so you can also run it in CI.

If no `--keywords` are given, the script extracts meaningful words from `BLOG_DESCRIPTION` in `config.py` as a fallback.

## Recovering a broken post

1. Delete the broken post via the GitHub API or web UI
2. Trigger `workflow_dispatch` on daily-post.yml with `skip_research: true` to reuse the cached research artifact
3. If the artifact is gone (>7 days old), omit `skip_research` to run the full pipeline
