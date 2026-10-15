# freeframe-deploy/ 🤖

Created 2026-10-02 by Majordomo, for the osc-review-server matter. The clone was made by that matter's worker.

**What it's for:** the working copy that FreeFrame is deployed to Railway from (review.oliverstreetcreative.com). `freeframe/` is a clean clone of upstream Techiebutler/freeframe, branch `stable` (MIT). It holds no OSC code.

**What the machine was thinking:** Railway's `railway up` uploads a directory. Upstream is cloned here, not into Dropbox, so node_modules and build context never sync. OSC's own pieces (the Caddy edge proxy, the runbook) live in the matter folder `Matters/osc-review-server/deploy/` and are copied in at deploy time.

**Rules:**
- Never commit OSC secrets here. Secrets go Keychain → stdin → Railway variables.
- To update, re-clone or `git pull` on `stable`. Don't hand-edit upstream files. If a patch is needed, record it in the matter's `deploy/RAILWAY-DEPLOY.md`.
- Live status: `Matters/osc-review-server/HANDOFF.md`.
