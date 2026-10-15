from pathlib import Path

P = Path("/Users/sam/code/freeframe-deploy/work/apps/web/components/review/progress-bar.tsx")
t = P.read_text()


def sub(a, b):
    global t
    assert t.count(a) == 1, a[:70]
    t = t.replace(a, b)


sub("      if (!storyboard) seekPreview(time)\n    },\n    [isDragging, getTimeFromEvent, onSeek, seekPreview, storyboard],",
    "      // hover-only preview: no decoder work while dragging or on touch\n"
    "      if (!storyboard && !isDragging && e.pointerType !== 'touch') seekPreview(time)\n"
    "    },\n    [isDragging, getTimeFromEvent, onSeek, seekPreview, storyboard, pointerKind],")
sub("      activePointerIdRef.current = e.pointerId\n",
    "      activePointerIdRef.current = e.pointerId\n"
    "      if (e.pointerType !== pointerKind) setPointerKind(e.pointerType)\n")
P.write_text(t)
print("ok")
