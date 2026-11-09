---
name: fix-failed-app-patch
description: Fix a failed "Patch App" job on Easytouch Cloud (Press), for any app (etpos, erpnext, frappe, payments, hrms, and others). Use when an App Patch or its agent job fails at the "Git Apply" step with "patch does not apply" or "already exists in working directory", or when the user shares a dashboard link like https://easytouch.cloud/dashboard/groups/<group>/jobs/<job>. It builds a patch file that applies, named <app>-<from7>-<to7>.patch.
---

# Fix a failed Patch App job

A Patch App job runs `git apply` inside the bench container. It fails for one of two reasons:

| What the job output shows | Cause |
|---|---|
| Source files (`.py`, `.vue`, and others) fail, or `already exists in working directory` | The patch starts at the wrong commit. The bench already has some of these changes. |
| Only built files fail: `.html`, `.js` or `.css` under `public/` or `www/`, or names with a hash | The asset build after the last patch rewrote them with new hashed file names. No git patch matches them. |

Both causes need the same fix: a diff from the commit the bench is on now (FROM) to the wanted commit (TO), without the built files.

## What you need

These are environment variables in the session:

- `PRESS_URL`: `https://easytouch.cloud`
- `PRESS_API_KEY` and `PRESS_API_SECRET`: a System Manager user on Press
- Read access to every repository that a bench app comes from. Use one of these: the GitHub MCP connection, the session's own GitHub access, or a `GITHUB_TOKEN`.

Send `Authorization: token $PRESS_API_KEY:$PRESS_API_SECRET` with every Press call. A `press.api.*` method also needs `X-Press-Team: <team of the group>`.

## Steps

1. **Read the failed job.** The job name is the last part of the dashboard link.
   - `GET $PRESS_URL/api/resource/Agent Job/<job>`. Read `job_type` (it must be `Patch App`), `bench`, `reference_name` (the App Patch), and `output` (the git errors). Save `output` to `job.txt`.
   - `GET $PRESS_URL/api/resource/App Patch/<reference_name>`. Read `app`, `group`, `bench`, `url` and `filename`.
   - `GET $PRESS_URL/api/resource/Release Group/<group>`. Read `team`.

2. **Find the app's repository.** The repository name is not always the app name. For example, `erpnext` is in `easytouch_erp` and `frappe` is in `framework`.
   - `GET $PRESS_URL/api/resource/Bench/<bench>`. In its `apps` table, take the row for the app. Read `source` and `hash`.
   - `GET $PRESS_URL/api/resource/App Source/<source>`. Read `repository_url`.

3. **Find FROM, the commit the bench is on now, for this app only.** A bench carries patches for several apps, so always filter by `app`.
   - `GET $PRESS_URL/api/method/press.api.bench.last_patch_head?name=<group>&app=<app>&bench=<bench>`, with the `X-Press-Team` header.
   - If the result is empty, no patch has applied yet. Use the `hash` from step 2.

4. **Find TO.** Use the commit the user names. Otherwise take the commit after `...` in the failed patch's `url` or `filename`.

5. **Build the patch.** A clone is better, because the script can then test the patch.
   - **With a clone.** Use `git clone` with the session's GitHub access, or with `https://x-access-token:$GITHUB_TOKEN@github.com/<owner>/<repo>`.
     ```bash
     git clone --filter=blob:none https://github.com/<owner>/<repo> /tmp/<app>
     python3 .claude/skills/fix-failed-app-patch/make_patch.py --repo /tmp/<app> --app <app> \
       --from <FROM> --to <TO> --job-output job.txt
     ```
   - **Without a clone (GitHub MCP only).** Get the diff of `<owner>/<repo>` compare `<FROM>...<TO>` as a unified diff. With the MCP, use its compare or get-diff tool. With the API, use `GET /repos/<owner>/<repo>/compare/<FROM>...<TO>` and the header `Accept: application/vnd.github.diff`. Save the whole diff, unchanged, to `full.diff`. Then:
     ```bash
     python3 .claude/skills/fix-failed-app-patch/make_patch.py --diff-file full.diff --app <app> \
       --from <FROM> --to <TO> --job-output job.txt
     ```
     Without a clone, `git apply --check` cannot run. Give `--from` and `--to` as at least 7 characters.

   The script leaves out each file that the job output names and that looks built. It prints which files it left out.
   - The script can list files that failed but look like source. If the failed job's FROM was different from yours, the wrong FROM explains them. If it was the same FROM, the bench has local edits in those files. Stop and tell the user. Do not leave source files out of the patch.
   - To leave out another built file, add `--exclude '<glob>'`.
   - Keep the file name that the script prints. Press reads the commit at the end of the name as the bench head for the next patch.

6. **Ask the user before you apply.** Applying rebuilds the assets and restarts the bench, so every site on it reloads. Tell the user the app, the bench, the number of sites, FROM, TO, and the files left out. Wait for a yes.

7. **Apply.** `POST $PRESS_URL/api/method/press.api.bench.apply_patch`, with the `X-Press-Team` header and this JSON body:
   ```json
   {"release_group": "<group>", "app": "<app>",
    "patch_config": {"patch": "<file text>", "filename": "<app>-<from7>-<to7>.patch",
                     "build_assets": true, "patch_bench": "<bench>"}}
   ```
   `build_assets` must be `true`, so that the build regenerates the files that were left out.

8. **Watch the job.** Find the new job with `GET /api/resource/Agent Job?filters=[["reference_name","=","<new App Patch>"]]&fields=["name","status"]`. Poll every 30 seconds until it shows `Success` or `Failure`. Report the result and the dashboard link `$PRESS_URL/dashboard/groups/<group>/jobs/<job>`. If it fails again, save the new `output` to `job.txt` and go back to step 5.

## Do not

- Do not apply the GitHub compare URL again. It still contains the built files.
- Do not leave source files out to make a patch apply.
- Do not apply without the user's yes.
- If the bench carries more than about 5 stacked patches for the app, or an applied patch has no commit in its name, suggest a normal deploy of the group instead. A deploy builds a clean image at TO.

## Example

Patch 875 on `bench-0050-000028-app` (etpos, `e518ede...2471497`) failed only on `etpos/public/pos-app/index.html` and `etpos/www/pos-app.html`. `make_patch.py --from e518ede --to 2471497 --job-output job.txt` wrote `etpos-e518ede-2471497.patch`, with 21 of 23 files, and it applied.
