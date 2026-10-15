"""One-off edit: sharp storyboard tiers in the web client (scrub.tsx + progress-bar.tsx)."""
from pathlib import Path

W = Path("/Users/sam/code/freeframe-deploy/work/apps/web")
f = W / "components/osc/scrub.tsx"
t = f.read_text()
start = t.index("export interface StoryboardMeta {")
end = t.index("export function indexAtTime(")
new = (W.parent.parent.parent / "sharp_block.tsx").read_text()
t = t[:start] + new + t[end:]

a = """  const active = sb && frac !== null
  const idx = sb && frac !== null ? Math.floor(frac * sb.meta.count) : 0"""
b = """  const active = sb && frac !== null
  const idx = sb && frac !== null ? Math.floor(frac * sb.meta.count) : 0
  // tiles must be >= this card's CSS width x devicePixelRatio to look sharp (3x on iPhone)
  const [needPx, setNeedPx] = React.useState(0)
  React.useEffect(() => {
    const el = ref.current
    if (!el || !sb) return
    setNeedPx(Math.ceil(el.getBoundingClientRect().width * dpr()))
  }, [sb])
  const tier = useSharpTier(sb, needPx, idx)"""
assert t.count(a) == 1
t = t.replace(a, b)
a2 = "...tileStyle(sb!, idx) }} />"
assert t.count(a2) == 1
t = t.replace(a2, "...tileStyle(sb!, idx, tier) }} />")
a3 = "      data-osc-scrub-ready={sb ? 'yes' : 'no'}"
assert t.count(a3) == 1
t = t.replace(a3, a3 + "\n      data-osc-scrub-tier={tier ? tier.w : sb ? sb.meta.tile_w : undefined}")
f.write_text(t)

P = W / "components/review/progress-bar.tsx"
p = P.read_text()
a4 = "import { useStoryboard, tileStyle, indexAtTime } from '@/components/osc/scrub'"
assert p.count(a4) == 1
p = p.replace(a4, "import { useStoryboard, tileStyle, indexAtTime, useSharpTier, dpr } from '@/components/osc/scrub'")
a5 = "  const { sb: storyboard } = useStoryboard(storyboardAssetId, true)\n"
assert p.count(a5) == 1
p = p.replace(a5, a5 + "  // the preview box is 160 CSS px wide (w-40): sharp at 160 x devicePixelRatio\n"
                       "  const seekTier = useSharpTier(storyboard, Math.ceil(160 * dpr()))\n")
a6 = "...tileStyle(storyboard, indexAtTime(storyboard, hoverTime)) }} />"
assert p.count(a6) == 1
p = p.replace(a6, "...tileStyle(storyboard, indexAtTime(storyboard, hoverTime), seekTier) }} />")
P.write_text(p)
print("ok")
