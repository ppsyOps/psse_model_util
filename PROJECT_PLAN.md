# Project Plan: psse_model_util

## Phase 1: Core Modernization & Refinement

### ✅ Phase 1.1: Build System Migration
- **Status:** Complete
- **Details:** Migrated the project from a legacy build system to PDM and Hatch for standardized dependency management and packaging.

### ✅ Phase 1.2: Code Cleanup
- **Status:** Complete
- **Details:** Performed an initial sweep to remove dead code and migrated the versioning system. (commit 740133b)

### ✅ Phase 1.3: Documentation
- **Status:** Complete
- **Details:** Created `README.md`, `ARCHITECTURE.md`, and `docs/RAW_TO_RAWX.md`. (commit 2c400b7)

### ✅ Phase 1.4: Testing Baseline
- **Status:** Complete
- **Details:** Integrated `pytest` and `pytest-cov` to establish an initial test coverage baseline.

### 🚧 Phase 1.5: Bug Fix (CSV Index)
- **Status:** To Do
- **Details:** Fix a known bug where CSV exports inadvertently drop index columns, leading to data integrity issues.

### ⏳ Phase 1.6: Code Quality & Linting
- **Status:** In Progress
- **Details:** Address code quality issues using `ruff` to improve maintainability and consistency.
  - [x] Establish linting baseline by running `ruff check .`
  - [-] **Manual Linting Fixes:** Manually fix all identified issues. The automated `--fix` command is not working reliably in this environment.
    - [ ] Fix whitespace, unused imports/variables, and incorrect type comparisons.
    - [ ] Refactor `dataformat/rawx_json_template.py` to remove star imports (`F403`/`F405` errors).
  - [ ] Final `ruff check` to ensure a clean codebase.

## Phase 2: Future Work

### 📋 Phase 2.1: CI/CD Integration
- **Status:** Not Started
- **Details:** Implement a GitHub Actions workflow to automatically run tests and linting on pull requests.

### 📋 Phase 2.2: API & Feature Enhancements
- **Status:** Not Started
- **Details:** (TBD based on user requirements)

| 4.4 | Switch remote URL to SSH | TBD | ⬜ Queued |

* Generate SSH key pair (if not exists)
* Add public key to GitHub account
* Update local repo remote URL to git@github.com:ppsyOps/psse_model_util.git
* Verify push/pull works

