"""Real-photo evaluation. Put photos in eval_data/<object_name>/*.jpg (2+ photos per object:
different angles, lighting, backgrounds). Run: python evaluate_matching.py [folder]"""
import sys
from pathlib import Path

from app.services.matcher import ImageMatcher


def main(root: str = "eval_data") -> None:
    m, sigs = ImageMatcher(), {}
    for folder in sorted(p for p in Path(root).glob("*") if p.is_dir()):
        for f in sorted(folder.iterdir()):
            if f.suffix.lower() in {".jpg", ".jpeg", ".png"}:
                try:
                    sigs[(folder.name, f.name)] = m.signature(m.load_image(f))
                except ValueError:
                    print("skipped unreadable image:", f)
    keys = list(sigs)
    total = top1 = top3 = 0
    for q in keys:
        if sum(k[0] == q[0] for k in keys) < 2:
            continue
        ranked = sorted((k for k in keys if k != q), key=lambda k: -m.compare(sigs[q], sigs[k]).score)
        total += 1
        top1 += ranked[0][0] == q[0]
        top3 += any(k[0] == q[0] for k in ranked[:3])
    if not total:
        print(f"No usable photos found in '{root}/'. Add folders with 2+ photos of the same object.")
        return
    print(f"Query photos: {total}\nCorrect top-1: {top1} ({top1 / total:.0%})\nCorrect top-3: {top3} ({top3 / total:.0%})")


if __name__ == "__main__":
    main(*sys.argv[1:2])
