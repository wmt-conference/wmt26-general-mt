# %%

def align_segments_by_merging_tgt(segments_src: list[str], segments_tgt: list[str]) -> list[str]:
    import statistics
    import itertools

    # assume the target is always over-segmented
    assert len(segments_src) <= len(segments_tgt)

    fertility = sum(len(x) for x in segments_tgt) / sum(len(x) for x in segments_src)
    def size_mismatch(segments_src: list[str], segments_tgt: list[str]) -> float:
        # compute MAE between segment sizes
        return statistics.mean([abs(len(a)*fertility - len(b)) for a, b in zip(segments_src, segments_tgt)])

    # find global optimum in allocation
    # we know that we need to merge k = len(segments_tgt) - len(segments_src) segments together
    # encode each merge as ordered k numbers from [0, len(segments_tgt)-1]
    best_candidate = None
    best_mae = float("inf")
    for merge_indices in itertools.combinations(range(len(segments_tgt)-1), len(segments_tgt) - len(segments_src)):
        # go backwards so we remain valid
        merge_indices = sorted(merge_indices, reverse=True)
        segments_tgt_candidate = list(segments_tgt)
        for merge_index in merge_indices:
            segments_tgt_candidate[merge_index] += "\n" + segments_tgt_candidate.pop(merge_index + 1)
        mae = size_mismatch(segments_src, segments_tgt_candidate)
        if mae < best_mae:
            best_mae = mae
            best_candidate = segments_tgt_candidate
    
    return best_candidate # type: ignore

# testing it on a toy example

example_src = """
This is first sentence. (1) This is a second sentence in the same paragraph. (2)

This is a third sentence but in another paragraph. (3)

And here is another paragraph, oh wow! (4)
Giraffe giraffe (5)

Trains are so much fun (6)
The rains in Spain fall mainly in the plain. (7)
It was the best of times, it was the worst of times... (8)
""".strip()

example_tgt = """
Das ist erster Satz. (1)

Das ist ein zweiter Satz im gleichen Absatz. (2)

Das ist ein dritter Satz in einem anderen Absatz. (3)

Und hier ist noch ein Absatz, oh wow! (4)
Giraffe giraffe (5)

Züge machen so viel Spaß. (6)
Die Regen in Spanien fallen hauptsächlich auf der Ebene. (7)

Es war die beste Zeit, es war die schlimmste Zeit... (8)
""".strip()


segments_src = example_src.split("\n\n")
segments_tgt = align_segments_by_merging_tgt(segments_src, example_tgt.split("\n\n")) # type: ignore

for src, tgt in zip(segments_src, segments_tgt):
    src = src.replace("\n", " ")
    tgt = tgt.replace("\n", " ")
    print(f"{src} ||| {tgt}\n----")