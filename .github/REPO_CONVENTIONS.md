# Repo conventions ([T.1.2.5](https://github.com/Anthony4044/WashSlot/issues/14))

## Labels

Tag every PR with **`backend`** and/or **`frontend`** (the PR template has a checklist for this).

## Protect `main` (admin only)

Someone with **admin** on the repo does this once:

1. Open **Settings → Branches → Add branch ruleset** (or classic **Branch protection rule**).
2. Target branch: `main`.
3. Turn on:
   - **Require a pull request before merging** (at least 1 approval)
   - **Require status checks to pass** — select:
     - `Backend (ruff + pytest)`
     - `Frontend (build)`  
     (these names come from `.github/workflows/ci.yml`; they appear after CI has run once on a PR)
   - **Do not allow bypassing the above settings** (or leave admins able to bypass only if the team agrees)
4. Block force pushes and deletions of `main`.

Until the ruleset is saved, people can still push straight to `main` — finish this step after the first green CI run so the check names show up in the dropdown.

## Pull requests

- One branch per story (`user_story/US1.2`, `US-4.1-hold-slot`, …).
- PR into `main`; another teammate reviews within 24 h.
- Title starts with the task tag when there is one: `[T.1.2.5] …`.
