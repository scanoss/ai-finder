# Seed catalogue

Keeps `seed/sdks.json` and `seed/mcp_servers.json` current by checking every
entry against its package registry, ranking within each ecosystem, and showing a
human what changed.

```
python -m scripts.seed_catalog.refresh              # look up and report, write nothing
python -m scripts.seed_catalog.refresh --write      # also rewrite the seed JSONs
python -m scripts.seed_catalog.refresh --offline    # validate and check drift, no network
python -m scripts.seed_catalog.refresh --check      # CI: exit non-zero on anything material
```

After `--write`, run `python scripts/update_seed_checksums.py`. It bumps the
seed version and records the checksums; without it clients either reject the
download or never see one. The release pipeline fails if it is skipped.

## How it is put together

`candidates.json` is the curated pool and the only file a human edits. Each
entry names a package, its purl, the patterns the scanner matches, and whether
it is an `sdk` or an `mcp_server`. SDKs are never discovered automatically:
these rows decide what appears in a customer's AI bill of materials, and a
registry search for "ai" returns a great deal that is not an AI SDK.

MCP servers are the exception, because there is a source that makes exactly the
claim a row makes. `mcp_registry.py` reads the official MCP Registry, where
authors publish each server with the package that runs it, and proposes the
active, latest npm, PyPI and container-image servers as candidates:

```
python -m scripts.seed_catalog.mcp_registry            # report what would be added
python -m scripts.seed_catalog.mcp_registry --write    # add them to candidates.json
```

Proposals are candidates, not seed rows: `refresh.py` still verifies each one
and drops any package its registry does not have. The importer refuses a
partial listing rather than proposing from one.

`per_ecosystem_limit` ranks; it is set above the size of every group so it
never cuts a curated row. At 50 it dropped real packages (`mcp-agent`,
`guardrails-ai`) from detection to make room, and a package that verifies is a
package a customer may depend on.

`registries.py` asks each ecosystem the same four questions — does this still
exist, what is the latest version, what licence, how popular — and records which
of them that registry can actually answer. `catalog.py` turns the answers into
ranked seed rows. `drift.py` holds the other package lists in the tree to the
same catalogue. `refresh.py` is the command.

## The rules, and why each one is a decision

**A failed lookup is not a missing package.** A 404 means the registry does not
have it; a timeout means we could not ask. Only the first drops a row. Treating
the second as a deletion would quietly shrink what every customer scan detects
whenever a registry has a bad morning.

**A deprecated package is kept.** Deprecation says what people *should* depend
on. Detection is about what they *do* depend on, and deprecated packages are
exactly the ones still sitting in old manifests —
`@modelcontextprotocol/server-slack` is deprecated and still takes 374,000
downloads a month.

**Rank is per ecosystem and the signal is named.** npm and PyPI publish download
counts; Maven and Go publish nothing; Swift has no registry at all. Those
numbers are not comparable, so each ecosystem is ranked only against itself and
every report states what it ranked on. An entry with no signal sorts after every
entry that has one, rather than being treated as zero — a missing count is not a
count of zero.

**A non-SPDX answer never overwrites a committed SPDX id.** Registries really do
publish `SEE LICENSE IN LICENSE`, `Apache 2.0` and `non-standard` in the licence
field. Writing any of those over `Apache-2.0` makes the seed worse while looking
like an update.

**Container images are unverifiable, not missing.** Registries other than
Docker Hub need a token to read, so a `pkg:docker` row is kept and reported as
not checked, the same as Conan.

**Swift 404s are unverifiable, not missing.** Half the Swift rows are Apple
system frameworks — `apple/coreml`, `apple/vision` — which are real things to
detect and have no repository to find.

## The drift check

Before this tool there were four hand-maintained lists of AI packages, free to
disagree: the seed, `crawlers/npm.py`, `crawlers/pypi.py`, and the `AI_*`
frozensets in `manifests/`. Every run compares them, in the two directions they
actually mean:

* a **crawler** list may be shorter than the catalogue, but a name in it the
  catalogue has never heard of is drift;
* a **manifest** list may hold extra AI-adjacent names like `pillow`, but every
  catalogued SDK for that ecosystem must be in it, or the scanner is blind to a
  package the seed says we detect.

Lists are read with `ast`, never imported and never matched with a regex:
importing executes the package, and a regex over source stops matching the day
someone reformats the literal.

## Adding a package

Add an entry to `candidates.json` and run `--offline` to validate it, then a
full run to see how it ranks. The loader refuses a duplicate id, a duplicate
purl, an unknown category, a missing pattern, and an npm scope written `%40`
instead of `@` — each of those was a real defect found in the committed seed the
first time this ran.
