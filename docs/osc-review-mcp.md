# OSC Review bot access (OSC 0028–0031)

Bot access is **off by default**. This patch series issues no production keys and performs no deployment. Apply the additive migrations before starting the updated API and workers. Existing users, projects, items, versions and notes survive unchanged.

An administrator opens **Settings → Admin → Bot access** to create, list or revoke a key. Select the permitted projects and actions; optionally set an expiry. The value appears once. Only its SHA-256 hash is stored. Every key has its own non-login actor (`🤖 name`), never the administrator's identity. A revoked or expired key is refused on the next request; permissions are read from the database each time.

Set `OSC_BOT_ACCESS_ENABLED=true` only after approval. With the environment unset, false or no issued keys, bot requests are refused. `OSC_BOT_REQUESTS_PER_MINUTE` defaults to 60 per key. Redis failures refuse bot access; HTTP 429 includes Retry-After. Audit records contain the key's database ID, operation, status and time, without headers, arguments, filenames or note text.

Scopes: `read`, `upload`, `organize`, `notes:read`, `archive`, `remove:request`. None grants share creation, client delivery, comment posting or replies. Upload clients need `read` + `upload` to poll processing. A project-limited key cannot create projects. Project creation requires an explicitly confirmed job stem.

## Connection and routing

MCP uses stateless Streamable HTTP at `/mcp`, JSON response mode, protocol 2025-06-18 (2025-03-26 compatible). Every request carries `Authorization: Bearer <your bot key>`; there is no human-session or JWT fallback. GET/DELETE return 405; notifications return 202. Origin checks reject browser origins other than the configured frontend. Bodies are limited to 64 KiB; media never passes through MCP messages. The [transport specification](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports) defines these response modes.

The ordinary user REST API still rejects bot tokens. The shared `/osc/actions/{name}` facade accepts a scoped bot token or a signed-in superadmin. The GUI and MCP call the same dispatcher and upload/export/organization services. Bot project membership is a request-local capability, never a persistent permission or a superadmin flag.

The existing OSC edge must route `/mcp` directly to the API **without stripping the path**. `deploy/osc/Caddyfile` is the candidate for that existing edge; `/api/*` retains its previous behavior. `docker-compose.prod.yml` provides the equivalent Traefik route. No DNS, account or new service is required. Deployment of the candidate edge still waits for the same approval as the app.

## Bot CLI

Inject `REVIEW_BASE_URL` (the HTTPS Review origin) and your own `REVIEW_BOT_TOKEN` from the harness's secret store. Never paste credentials into chat or commit them. Then:

```sh
python scripts/review_bot.py upload PROJECT_UUID '01_SPOT' /path/to/cut.mov
python scripts/review_bot.py upload PROJECT_UUID '02_NEW_SPOT' /path/to/cut.mov --new-item
python scripts/review_bot.py call list_projects
python scripts/review_bot.py call list_notes '{"version_id":"VERSION_UUID"}'
```

The client hashes incrementally, starts or adds a version, signs and PUTs multipart parts with a separate connection that has **no Review Authorization header**, completes the upload and polls until ready. It returns the internal item URL. The browser uses the same flow and hashes in bounded chunks. Processing status is not ready until the worker has checked the actual stored object against the expected SHA-256, then processed it. A mismatch fails before the encoder runs. Large masters therefore do not hold an HTTP completion request open while hashing.

Default upload adds a version; a missing item requires `new_item=true`. Item names cannot carry a version, round, date or alternate. Filename and content-hash duplicates are refused across the visible inventory; hash reservations and item creation are serialized in Postgres. `find_upload` exposes only permitted projects. For older human uploads the filename is searchable; no content hash is invented retrospectively. Preserve the version reference on interrupted transfers; the presign/complete tools can finish a multipart plan. The CLI's default ready wait is 30 minutes; processing can continue afterwards.

Enabled share links protect source items, destination folders and ancestor folders. Bot actions cannot move an internal item into a shared folder or silently replace a client's top version. Merge uses OSC 0016's common service with link overrides and repointing unavailable to bots.

Archive moves the item or folder to the project's `_archive` and creates an undo receipt. Enabled links cause refusal; disabled links stay off. `list_archives` recovers receipts after a lost response, and `restore_archive` restores the original location after checking intervening moves and links. Nothing is deleted. Archive receipts and upload fingerprints retain historical UUID references without blocking the existing retention collector.

`request_removal` stages only a request. In **Pending removals**, the superadmin reviews it, then confirms a 15-minute, single-use code bound to the request. Only a human session can obtain or consume that code; neither operation is an MCP tool. Confirmation uses one transaction and row lock, checks links, and moves the target to the existing Trash/retention flow. Hard purge remains outside bot access.

## GUI parity

The admin tab's Review actions form is generated from the same strict schemas as the tool catalog. Existing project, folder, player and upload views retain their normal actions. Additional archive/restore, merge, labels, upload search and removal requests are available in that tab. Transport steps are driven by the GUI uploader.

| Tool | Scope | GUI action |
|---|---|---|
| `list_projects` | `read` | Projects |
| `list_folders` | `read` | Project folders |
| `list_assets` | `read` | Project items and version stacks |
| `get_asset` | `read` | Item details |
| `get_version` | `read` | Item versions |
| `find_upload` | `read` | Review actions: find upload |
| `upload_version` | `upload` | Review actions: upload version |
| `presign_part` | `upload` | Upload transfer |
| `complete_upload` | `upload` | Upload transfer |
| `create_project` | `organize` | New project |
| `create_folder` | `organize` | New folder |
| `rename_asset` | `organize` | Rename item |
| `move_asset` | `organize` | Move item |
| `bulk_move` | `organize` | Move selected items |
| `set_version_label` | `organize` | Review actions: version label |
| `merge_into_stack` | `organize` | Review actions: merge stacks |
| `list_notes` | `notes:read` | Player notes |
| `export_notes` | `notes:read` | Player export notes |
| `mark_note_addressed` | `organize` | Resolve note |
| `archive_asset` | `archive` | Review actions: archive item |
| `archive_folder` | `archive` | Review actions: archive folder |
| `list_archives` | `archive` | Review actions: archived items |
| `restore_archive` | `archive` | Review actions: restore archive |
| `request_removal` | `remove:request` | Review actions: request removal |

## Verification

Run the backend suite with an isolated migrated Postgres. Set `OSC_REVIEW_TEST_DATABASE_URL` explicitly to a disposable database whose name contains `freeframe_test` to enable the new persisted integration checks. They never connect to a production URL by default.

```sh
python -m pytest apps/api/tests/ -q
pnpm --dir apps/web test
pnpm --dir apps/web exec tsc --noEmit
pnpm --dir apps/web lint
pnpm --dir apps/web build
```

On Node 26, use `NODE_OPTIONS=--no-experimental-webstorage` for Vitest so jsdom provides the test browser's localStorage. No production behavior changes. Tests cover every tool's scope check, cross-project refusal, token revocation over HTTP, multipart transfer and ready polling, byte-for-byte GUI exports, worker hash verification, archive undo and human-only expiring removal confirmation.

Legacy session-token scripts are not a fallback. They must be retired through the hash-pinned private O25 activation plan after approval; this public source contains no credentials, live project inventory or client data.
