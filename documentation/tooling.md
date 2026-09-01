---
title: Tooling
status: active
updated: 2026-09-01
---

# Tooling

How the two context tools are configured here, and what each one puts under
version control. Back to [Documentation home](index.md).

Both tools exist to give an assistant machine-readable context, which is why
docstrings in this repository are written purely for humans — see
[Code conventions](code-conventions.md).

## Serena

Symbol-level semantic index and language-server integration.

Configured in `.serena/project.yml`. The languages are set explicitly to
`python`, `typescript`, and `bash` rather than left to autodetection, which
had picked up only `bash` from the single shell script present when the
project was created.

`ignore_all_files_in_gitignore` is left on, so Serena will not index anything
version control ignores.

### What Serena commits

Serena ships its own `.serena/.gitignore` containing `/cache` and
`/project.local.yml`. That is the upstream convention, so `.serena/` is
deliberately **not** blanket-ignored at the repository root — doing so would
override the tool's own boundary.

| Path | Tracked | Why |
| --- | --- | --- |
| `.serena/project.yml` | Yes | Language and tool config; should travel with the repo |
| `.serena/memories/` | Yes | Durable project knowledge, intended to be shared |
| `.serena/.gitignore` | Yes | The boundary itself |
| `.serena/cache/` | No | Pickled language-server symbols; regenerable, binary |
| `.serena/project.local.yml` | No | Per-machine overrides |

## Graphify

Relational knowledge graph across code and documents, queried with
`graphify query "<question>"`.

Graphify has **no configuration file** — it is driven entirely by CLI flags.
Build with `graphify .`, and refresh incrementally with `graphify . --update`.

The first build is deferred until there is application source worth indexing;
running it against documentation alone would spend tokens to describe files a
reader can simply open.

### What Graphify commits

Nothing. Everything under `graphify-out/` is ignored.

The upstream documentation, including `llms.txt`, gives no version-control
guidance, so this is a decision made here rather than a documented convention.
The reasoning:

- **Every artifact is regenerable** from source by re-running the build, so
  none of it is a source of truth.
- **`graph.json` and `graph.html` run to roughly 1.6 MB each**, with the
  cache reaching several megabytes. The assessment brief asks that
  dependency-style directories be excluded from the submission, and these are
  the same class of thing.
- **The outputs churn on every rebuild**, so tracking them would add a large,
  meaningless diff to any commit that follows one.

The root `.gitignore` entry is written in negatable form. To begin tracking
the human-readable report, uncomment the exception beneath
`/graphify-out/*`.

| Path | Tracked | Why |
| --- | --- | --- |
| `graphify-out/graph.json` | No | Canonical graph state, but regenerable and large |
| `graphify-out/graph.html` | No | Interactive visualisation, regenerable and large |
| `graphify-out/GRAPH_REPORT.md` | No | Human-readable report; regenerated on every build |
| `graphify-out/cache/`, `.graphify_*` | No | Intermediate build state |
