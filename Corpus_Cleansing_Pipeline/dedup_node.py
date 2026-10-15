"""3.3 去重与质量评分筛选: 基于 SimHash 的近似去重 + 优选 + 达标筛选 (接在 "质量评估" 节点后面).

    1. 每条语料按字符 3-gram 计算 64 位 SimHash
    2. 两两海明距离 <= 阈值的归为同一近似重复簇 (并查集)
    3. 簇内按质量评估总分保留最优一条, 其余 "剔除·近似重复"
    4. 质量档低于 "最低保留档" 的 "剔除·质量不达标"
输入是质量评估节点的输出目录 (scored.jsonl, 带 总分 / 质量档); 节点上显示簇与处理结论表 (web/pii_highlight.js 渲染).
示例: example/offline_prepared/dedup_quality/
"""
import hashlib
import html
import json
import re
from collections import Counter
from pathlib import Path

GRADES = ["A", "B", "C"]


def shingles(text, n=3):
    text = re.sub(r"\s+", "", text)
    return [text[i:i + n] for i in range(max(1, len(text) - n + 1))]


def simhash(text, bits=64):
    weights = [0] * bits
    for gram, count in Counter(shingles(text)).items():
        h = int.from_bytes(hashlib.md5(gram.encode("utf-8")).digest()[:8], "big")
        for i in range(bits):
            weights[i] += count if (h >> i) & 1 else -count
    return sum(1 << i for i, w in enumerate(weights) if w > 0)


def hamming(a, b):
    return bin(a ^ b).count("1")


def cluster(rows, threshold):
    """并查集: 海明距离 <= threshold 的连成一簇; 返回 [[行号...], ...] 和两两距离"""
    hashes = [simhash(r["text"]) for r in rows]
    parent = list(range(len(rows)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    dist = {}
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            dist[(i, j)] = dist[(j, i)] = hamming(hashes[i], hashes[j])
            if dist[(i, j)] <= threshold:
                parent[find(j)] = find(i)
    groups = {}
    for i in range(len(rows)):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values()), dist


def dedup_and_filter(rows, threshold, min_grade):
    groups, dist = cluster(rows, threshold)
    allowed = GRADES[:GRADES.index(min_grade) + 1]
    results = []
    for gid, members in enumerate(sorted(groups, key=min), start=1):
        best = max(members, key=lambda i: rows[i]["总分"])
        for i in members:
            r = rows[i]
            if i != best:
                verdict = f"剔除·近似重复 (与 {rows[best]['id']} 距离 {dist[(i, best)]})"
            elif r["质量档"] not in allowed:
                verdict = f"剔除·质量不达标 ({r['质量档']} 档)"
            else:
                verdict = "保留" + ("·簇内最优" if len(members) > 1 else "")
            results.append({**r, "簇": gid, "簇大小": len(members), "结论": verdict})
    return results


def dedup_html(results, threshold, min_grade):
    kept = [r for r in results if r["结论"].startswith("保留")]
    dup = sum(r["结论"].startswith("剔除·近似重复") for r in results)
    low = sum(r["结论"].startswith("剔除·质量不达标") for r in results)
    n_clusters = len({r["簇"] for r in results if r["簇大小"] > 1})
    head = (f'<div class="coclp-summary">输入 {len(results)} 条 → 保留 <b class="q-a">{len(kept)}</b> 条 · '
            f'剔除近似重复 <b class="q-b">{dup}</b> 条 (重复簇 {n_clusters} 个) · '
            f'剔除质量不达标 <b class="q-c">{low}</b> 条<br>'
            f'SimHash 64 位 · 字符 3-gram · 海明距离阈值 ≤ {threshold} · 最低保留档 {min_grade}</div>')
    rows = []
    for r in results:
        cls = "q-a" if r["结论"].startswith("保留") else "q-b" if "重复" in r["结论"] else "q-c"
        rows.append(f'<tr><td>簇{r["簇"]}</td><td>{html.escape(r["id"])}</td><td>{html.escape(r.get("title", ""))}</td>'
                    f'<td>{r["总分"]:.2f}</td><td class="q-{r["质量档"].lower()}">{r["质量档"]}</td>'
                    f'<td class="{cls}">{html.escape(r["结论"])}</td></tr>')
    return head + ('<table class="coclp-table"><tr><th>簇</th><th>ID</th><th>语料</th><th>总分</th><th>档</th>'
                   f'<th>处理结论</th></tr>{"".join(rows)}</table>')


class SimHashDedup:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "scored_dir": ("STRING", {"forceInput": True}),
            "output_dir": ("STRING", {"default": "../example/offline_prepared/dedup_quality/output/dedup"}),
            "海明距离阈值": ("INT", {"default": 12, "min": 0, "max": 64}),
            "最低保留档": (GRADES, {"default": "B"}),
        }}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("保留语料目录",)
    FUNCTION = "run"
    OUTPUT_NODE = True
    CATEGORY = "MY_NODES/清洗"

    def run(self, scored_dir, output_dir, 海明距离阈值, 最低保留档):
        rows = [json.loads(l) for l in (Path(scored_dir) / "scored.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
        results = dedup_and_filter(rows, 海明距离阈值, 最低保留档)
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "kept.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in results
                                                if r["结论"].startswith("保留")), encoding="utf-8")
        (out / "dedup_report.jsonl").write_text("".join(
            json.dumps({k: r[k] for k in ("id", "簇", "总分", "质量档", "结论")}, ensure_ascii=False) + "\n"
            for r in results), encoding="utf-8")
        return {"ui": {"html": [dedup_html(results, 海明距离阈值, 最低保留档)]}, "result": (output_dir,)}


if __name__ == "__main__":
    # 看两两海明距离, 用来定阈值: python Corpus_Cleansing_Pipeline/dedup_node.py <jsonl>
    import sys
    rows = [json.loads(l) for l in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines() if l.strip()]
    hashes = [simhash(r["text"]) for r in rows]
    for i in range(len(rows)):
        print(rows[i]["id"], " ".join(f"{hamming(hashes[i], hashes[j]):2d}" for j in range(len(rows))))
