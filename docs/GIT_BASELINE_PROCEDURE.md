# Git Baseline Procedure

The repository is initialized on `main` but has no commits, staged files, or remote publication by Codex. Because public sanitization currently says NO, do not create a public baseline commit yet.

1. Back up and hash the production DB outside Git.
2. Resolve the account-shaped default seed through a separately reviewed compatibility change; prove the live DB is unchanged and rerun all tests.
3. Review `git status --short`, ignored files, and every candidate source file.
4. Stage explicit paths—never `git add -f` and never broad staging before review.
5. Run source/staged secret and privacy scans, dependency audits, all tests/builds, and DB hash verification.
6. Confirm no DB, JSON local rules, uploads, exports, reports, environment files, archives, logs, or build dependencies are staged.
7. Create a private/local certified commit such as `phase0-certified-baseline` (or a Phase 1 foundation commit after approval).
8. Tag the exact reviewed commit, suggested `baseline-v1-certified-2026-08-07`.
9. Add a remote and push only when the sanitization report says YES and the user explicitly authorizes it.

For private-repository use, the same ignore and secret controls apply; privacy is not a reason to commit production data.
