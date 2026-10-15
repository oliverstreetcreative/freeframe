"""One-off edit (Sam 10/3 00:50): the timeline preview shows on HOVER only (mouse/pen, nothing
pressed). Hidden while dragging the playhead; never on touch. The main picture is the preview."""
from pathlib import Path

P = Path("/Users/sam/code/freeframe-deploy/work/apps/web/components/review/progress-bar.tsx")
t = P.read_text()


def sub(a, b):
    global t
    assert t.count(a) == 1, a[:70]
    t = t.replace(a, b)


sub("  const [isDragging, setIsDragging] = useState(false)\n",
    "  const [isDragging, setIsDragging] = useState(false)\n"
    "  // OSC (Sam 10/3 00:50): preview on HOVER only. Touch has no hover, so never there.\n"
    "  const [pointerKind, setPointerKind] = useState<string>('mouse')\n")
sub("      if (isDragging && e.pointerId !== activePointerIdRef.current) return\n",
    "      if (isDragging && e.pointerId !== activePointerIdRef.current) return\n"
    "      if (e.pointerType !== pointerKind) setPointerKind(e.pointerType)\n")
sub("      {hoverTime !== null && (",
    "      {hoverTime !== null && !isDragging && pointerKind !== 'touch' && (")
P.write_text(t)
print("ok")
