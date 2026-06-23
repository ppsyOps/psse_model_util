# Publishing to PyPI

How `psse-model-util` is released to PyPI. The same pattern applies to sibling
packages (e.g. `key-facilities`). Publishing is automated with **Trusted
Publishing** (OIDC) — no API tokens are stored anywhere.

- **Stable** releases → [pypi.org](https://pypi.org/project/psse-model-util/)
- **Pre-releases** (`bN`/`rcN`) → also PyPI, but `pip` skips them unless `--pre`
- **Rehearsals** → [test.pypi.org](https://test.pypi.org/project/psse-model-util/)

Workflow file: [`.github/workflows/publish.yml`](../.github/workflows/publish.yml).

---

## One-time setup (already done for psse-model-util)

Per **maintainer** (PyPI account):

1. Register on **pypi.org** and **test.pypi.org** (separate accounts) and enable 2FA.

Per **project** (do once, for each of PyPI and TestPyPI):

2. **Add a pending publisher** (Trusted Publishing): Account → *Publishing* →
   *Add a new pending publisher*:
   - PyPI Project Name: `psse_model_util` (PyPI normalizes `_`↔`-`, so this == `psse-model-util`)
   - Owner: `ppsyOps` · Repository: `psse_model_util`
   - **Workflow name: `publish.yml`** (must match the file name exactly)
   - **Environment name: `pypi`** on pypi.org, **`testpypi`** on test.pypi.org
3. **Create the GitHub environments** (repo → Settings → Environments):
   - `pypi` — **add a required reviewer** (the human approval gate before a real publish).
   - `testpypi` — **no reviewer** (so rehearsals don't need a click).

> The pending-publisher's *Workflow name* and *Environment name* must match
> `publish.yml` exactly, or PyPI rejects the OIDC upload.

---

## Cutting a release

### 1. Bump the version

Edit `src/psse_model_util/__about__.py` — the single source of truth:

```python
__version__ = "2026.5.0b1"   # pre-release (beta)
# __version__ = "2026.5.0"   # stable
```

CalVer `YYYY.M.micro` + optional [PEP 440](https://peps.python.org/pep-0440/)
suffix: `bN` (beta), `rcN` (release candidate). Commit + merge to `main`.

### 2. Trigger the publish workflow — **manually**

> ⚠️ **Gotcha:** `cd.yml` auto-creates a GitHub Release on push to `main`, but a
> release created by the workflow's `GITHUB_TOKEN` **cannot** trigger
> `publish.yml` (GitHub blocks token-created events from starting other
> workflows). So the publish must be started by hand:

- **CLI:** `gh workflow run publish.yml --ref main`
- **UI:** Actions → *Publish to PyPI* → *Run workflow* → `main`

(A Release created manually by a human via the UI/`gh release create` *does*
trigger it — but `workflow_dispatch` is the reliable path.)

### 3. Let TestPyPI publish, then verify

The `build` → `publish-testpypi` jobs run automatically (the `publish-testpypi`
step uses `skip-existing: true`, so re-runs of an already-published version are
fine). Verify in a **clean** venv:

```bash
python -m venv /tmp/verify && /tmp/verify/Scripts/python -m pip install --pre \
  --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ psse-model-util
/tmp/verify/Scripts/python -c "import psse_model_util; print(psse_model_util.__version__)"
```

(`--extra-index-url` pulls real dependencies from PyPI; TestPyPI only has our package.)

### 4. Approve the PyPI gate (the real publish)

The `publish-pypi` job sits **`waiting`** on the `pypi` environment reviewer.
The reviewer for this repo is **`cadvena`** (the owner). Approve it:

- **UI:** Actions → the run → *Review deployments* → check `pypi` → *Approve and deploy*.
- **API (as the reviewer):**
  ```bash
  ENVID=$(gh api repos/ppsyOps/psse_model_util/actions/runs/<RUN_ID>/pending_deployments \
            --jq '.[] | select(.environment.name=="pypi") | .environment.id')
  gh api -X POST repos/ppsyOps/psse_model_util/actions/runs/<RUN_ID>/pending_deployments \
    -F "environment_ids[]=$ENVID" -f state=approved -f comment="release X.Y.Z"
  ```

For a **TestPyPI-only rehearsal**, just *don't* approve `pypi` (cancel the run, or let it expire).

### 5. Verify on real PyPI

```bash
pip install --pre psse-model-util         # beta
pip install psse-model-util               # once a stable (no-suffix) version is out
```

---

## Account / permissions notes (this org)

- Routine git/gh ops use **OrionAIDev** (`maintain` on `ppsyOps/psse_model_util`
  and `key_facilities`). It can push, PR, and `gh workflow run` (dispatch).
- **Owner-only** actions need **cadvena**: cancelling workflow runs, repo/env
  settings, and **approving the `pypi` deployment gate** (OrionAIDev
  `can_approve: false`). Briefly `gh auth switch --user cadvena`, act, switch back.

## Gotchas recap

| Symptom | Cause / fix |
| --- | --- |
| `publish.yml` never runs after a release | `cd.yml`'s `GITHUB_TOKEN` release can't trigger it → use `gh workflow run publish.yml` |
| `pip install <pkg>` says "no matching distribution" | only a pre-release is published → use `pip install --pre <pkg>` |
| TestPyPI step fails "file already exists" | a prior run published that version → `skip-existing: true` (already set) handles it |
| Trusted Publishing upload rejected | pending-publisher `Workflow name`/`Environment name` must match `publish.yml` / `pypi`,`testpypi` exactly |
| PyPI gate stuck `waiting` | `pypi` env needs reviewer approval (cadvena) — by design |

> Local install problems (broken venv, `_ctypes` DLL errors, missing registry
> values) are environment issues, **not** packaging — see the team memory note on
> Windows venvs / Python 3.14 if you hit them.
