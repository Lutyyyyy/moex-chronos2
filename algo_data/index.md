# INDEX — algo_data

Full file map. Add an entry for every new file (role + update rule).

| File | Role | Update rule |
|---|---|---|
| `.claude/CLAUDE.md` | Goal, description, ALGOPACK clues, rules, compact index. | On goal/rule change or when a file is added/removed. |
| `index.md` | This file — full map of project files. | Whenever a file is created, removed or changes role. |
| `current_state.md` | Session scratchpad: what's done, open questions, next steps. | Refresh at end of every session. |
| `.env` | `ALGOPACK_API_KEY=...`. Secret. | User-edited only. Never read aloud, log, or commit. |
| `.gitignore` | Excludes secrets, data, caches. | When new generated/secret paths appear. |
| `needed.md` | Open gaps: blockers, user decisions, items to verify with a working key. | Tick off / remove items as they are settled; add new gaps. |
| `algopack_notes.md` | Verified ALGOPACK facts: auth, TLS, endpoints, fields, candles, universe, sources. | When a fact is (re)verified or an item moves over from `needed.md`. |
| `certs/russian_trusted_ca.pem` | Public Russian Trusted Root + Sub CA (needed to verify `apim.moex.com` TLS). Not secret. | Refresh before Sub CA expiry 2027-03-06 (source `https://gu-st.ru/content/Other/doc/`). |
| `how_to_use.md` | **Package instruction** for end users: quick start (Colab/local), full config.md reference, outputs/columns, futures roll, resume/runtime, troubleshooting, tests, status (verified/limits/open questions). | When config keys, outputs, behaviour, verified facts or open questions change (keep in sync with `docs/usage.md`). |
| `config.md` | Data manifest: first ```yaml block = pipeline config (plan, paths, period, datasets, intervals, tickers, futures roll, request). | When the panel/period/datasets change; keep keys in sync with `parse_config` + `docs/usage.md`. |
| `src/algopack_pipeline.py` | **Single source of the pipeline**, split into notebook cells by `# %%` (config, client, fetch/normalize, futures roll, storage/run, universe report). | Edit here only, then run `tools/build_notebook.py` + `pytest`. |
| `notebooks/algopack_pipeline.ipynb` | Colab notebook, generated from the module + Colab setup/run cells, CA PEM embedded. | Never edit by hand; rebuild. `tests/test_notebook.py` fails if stale. |
| `tools/build_notebook.py` | Builds the notebook from `src/` (+ injects `certs/` PEM). | When notebook setup/run cells change. |
| `tests/` | `pytest` offline suite (fake ISS: config, client, transforms, futures, universe ranking, end-to-end + resume, notebook) and `test_live.py` (`pytest -m live`, real API). | Add a test with every behaviour change / API quirk found. |
| `pytest.ini` | Test config; `live` marker excluded by default. | When markers/paths change. |
| `docs/usage.md` | How to use config.md + pipeline (Colab/local), output layout, column semantics, futures roll, equity universe selection, runtime, errors, maintenance. | When config keys, outputs or behaviour change. |
| `docs/universe.md` | What tickers/datasets are accessible, history depth, default panel rationale, caveats. | When coverage is re-verified or panel changes. |
| `docs/universe_snapshot.md` | Generated listing snapshot (`universe_report()`), dated. | Regenerate occasionally; don't hand-edit. |
| `data/universe/equity_universe.yaml` | Selected ~80-ticker equity universe + selection metadata (`rank_equity_universe()`), ready to paste into `config.md`. | Regenerate when the universe needs refreshing; gitignored (under `data/`). |
| `data/universe/equity_universe_candidates.csv` | Full audit trail: every TQBR candidate + status (selected / excluded + reason). | Regenerated alongside `equity_universe.yaml`; gitignored. |
| `tools/probe_algopack.py` | Re-runnable live access check (auth, datasets, depth, pagination, freshness, rate). Never prints the key. | When endpoints/checks change. |
| `.claude/skills/github-code-search/` | Skill: search GitHub for existing implementations. | Copied from `moex-hack`; edit only to improve the skill. |
| `.claude/skills/stackoverflow-search/` | Skill: search Stack Overflow for snippets. | Same as above. |
| `.claude/commands/search-github.md` | Slash command `/search-github`. | Same as above. |
