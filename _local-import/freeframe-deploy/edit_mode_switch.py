"""One-off edit (0011): make share-link decisions switchable (Fable review 10/3 04:30, item 1 [SAM]).
OSC_SHARE_DECISION_MODE = binding (today's 0010) | ok (non-binding "Looks good"; pill untouched) | off."""
from pathlib import Path

R = Path("/Users/sam/code/freeframe-deploy/work/apps/api/routers/osc_share_decision.py")
t = R.read_text()


def sub(a, b):
    global t
    assert t.count(a) == 1, a[:70]
    t = t.replace(a, b)


sub("router = APIRouter(tags=[\"osc_share_decision\"])\n",
    "router = APIRouter(tags=[\"osc_share_decision\"])\n\n"
    "# Fable review 10/3 04:30 #1 [SAM]: the portal may own the ONE approval of record. Until Sam rules,\n"
    "# one env var picks the behaviour without a code change:\n"
    "#   binding (default, 0010 as built): Approve / Request changes; approval turns the pill green\n"
    "#   ok:  non-binding 'Looks good' / 'Needs changes'; recorded + shown, the pill is NOT moved\n"
    "#   off: no buttons; the route answers 403\n"
    "import os as _os\n\n\n"
    "def mode() -> str:\n"
    "    m = _os.environ.get(\"OSC_SHARE_DECISION_MODE\", \"binding\").strip().lower()\n"
    "    return m if m in (\"binding\", \"ok\", \"off\") else \"binding\"\n")
sub("    if link.permission != SharePermission.approve:\n",
    "    if mode() == \"off\":\n"
    "        raise HTTPException(403, \"Approvals from links are turned off\")\n"
    "    if link.permission != SharePermission.approve:\n")
sub("    label = \"✅ Approved\" if decision == \"approved\" else \"🔁 Changes requested\"\n",
    "    if mode() == \"ok\":\n"
    "        label = \"👍 Looks good (not a sign-off)\" if decision == \"approved\" else \"✏️ Needs changes\"\n"
    "    else:\n"
    "        label = \"✅ Approved\" if decision == \"approved\" else \"🔁 Changes requested\"\n")
sub("    sync_status(db, asset, version.id)\n",
    "    if mode() == \"binding\":\n"
    "        sync_status(db, asset, version.id)\n")
sub("    return [{\"name\": r[0], \"decision\": r[1], \"at\": r[2].isoformat() if r[2] else None} for r in rows]",
    "    return {\"mode\": mode(),\n"
    "            \"decisions\": [{\"name\": r[0], \"decision\": r[1], \"at\": r[2].isoformat() if r[2] else None} for r in rows]}")
R.write_text(t)

W = Path("/Users/sam/code/freeframe-deploy/work/apps/web/components/osc/share-decision.tsx")
w = W.read_text()


def wsub(a, b):
    global w
    assert w.count(a) == 1, a[:70]
    w = w.replace(a, b)


wsub("  const [decisions, setDecisions] = React.useState<Decision[]>([])\n",
     "  const [decisions, setDecisions] = React.useState<Decision[]>([])\n"
     "  const [mode, setDecisionMode] = React.useState<'binding' | 'ok' | 'off' | null>(null)\n")
wsub("      if (r.ok) setDecisions(await r.json())\n",
     "      if (r.ok) { const d = await r.json(); setDecisions(d.decisions ?? []); setDecisionMode(d.mode ?? 'binding') }\n")
# the panel state was also called `mode`; rename it to `panel`
w = w.replace("const [mode, setMode] = React.useState<null | 'approved' | 'rejected'>(null)",
              "const [panel, setPanel] = React.useState<null | 'approved' | 'rejected'>(null)")
w = w.replace("setMode(", "setPanel(").replace("mode === 'approved'", "panel === 'approved'") \
     .replace("mode === 'rejected'", "panel === 'rejected'").replace("{mode && (", "{panel && (") \
     .replace("onClick={() => send(mode)}", "onClick={() => send(panel)}")
wsub("  if (permission !== 'approve') return null\n",
     "  if (permission !== 'approve' || mode === null || mode === 'off') return null\n"
     "  const ok = mode === 'ok'\n")
wsub("        <Check className=\"h-3.5 w-3.5\" /> Approve\n", "        <Check className=\"h-3.5 w-3.5\" /> {ok ? 'Looks good' : 'Approve'}\n")
wsub("<span className=\"hidden sm:inline\">Request changes</span>", "<span className=\"hidden sm:inline\">{ok ? 'Needs changes' : 'Request changes'}</span>")
wsub("{mine.decision === 'approved' ? 'Approved' : 'Changes requested'} by {mine.name}",
     "{mine.decision === 'approved' ? (ok ? 'Looks good to' : 'Approved by') : (ok ? 'Needs changes from' : 'Changes requested by')} {mine.name}")
W.write_text(w)
print("ok")
