"""第 1 章 "多源多模态教育语料构建总体能力": 管道总览 + 规模看板 (1 张合图).

在本目录的 docx_workflow_test.json (文档处理流水线, 离线结果回放) 基础上:
- 右侧加 "语料规模看板" 分组, 三张大字号卡片: 入库文档数 / 语料规模 (Token) / 学段分布
- 卡片输入连到 "五维标注与分类" 的输出; 数字读 /data/corpus/production/edu_multimodal_corpus/*.json
  (本机经 config/path_aliases.json 映射到本目录的 edu_multimodal_corpus/; 示意数字, 正式使用前替换);
  把卡片的 stats_json 清空即改为对当前批次实时统计
- 新增看板分组的组执行器, 串在流水线组执行器之后: 点 "运行" 依次执行流水线和看板

用法:
    python example/offline_prepared/多源多模态教育语料构建总体能力/make_overview_workflow.py
    python example/offline_prepared/shoot_workflow.py --workflow 多源多模态教育语料构建总体能力/管道总览与规模看板.json \
        --out example/offline_prepared/多源多模态教育语料构建总体能力/管道总览与规模看板.png
"""
import copy
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from make_offline_docx_workflow import add_link, find_node  # noqa: E402

SRC = HERE / "docx_workflow_test.json"
DST = HERE / "管道总览与规模看板.json"
# 生产环境的统计目录; 本机没有 /data, 由 Corpus_Cleansing_Pipeline/config/path_aliases.json 映射到本目录的 edu_multimodal_corpus/
STATS_DIR = "/data/corpus/production/edu_multimodal_corpus"

PIPELINE_GROUP = "文档处理流水线"
DASHBOARD_GROUP = "语料规模看板"
CARD_W = 480
CARDS = [  # (metric, 统计文件, 卡片高度): 节点头 + 3 个参数行约占 110, 剩下给大字号内容
    ("文档数", "document_stats.json", 320),
    ("Token 数", "token_stats.json", 320),
    ("学段分布", "stage_distribution.json", 500),
]
CARD_GAP = 30


def new_node_id(workflow):
    workflow["last_node_id"] += 1
    return workflow["last_node_id"]


def add_dashboard_group(workflow, gap=60):
    pipeline = next(g for g in workflow["groups"] if g["title"] == PIPELINE_GROUP)
    px, py, pw, ph = pipeline["bounding"]
    gx = px + pw + gap
    cards_h = 60 + sum(h for _, _, h in CARDS) + CARD_GAP * len(CARDS)
    workflow["groups"].append({
        "id": max(g.get("id", 0) for g in workflow["groups"]) + 1, "title": DASHBOARD_GROUP,
        "bounding": [gx, py, CARD_W + 40, max(ph, cards_h)], "color": "#b06694", "font_size": 24, "flags": {},
    })

    labeler = find_node(workflow, "FiveDimLabelNode")
    y = py + 60
    for metric, stats_file, height in CARDS:
        card = {
            "id": new_node_id(workflow), "type": "CorpusStatCard", "title": f"规模看板: {metric}",
            "pos": [gx + 20, y], "size": [CARD_W, height], "flags": {}, "order": 99, "mode": 0,
            "inputs": [{"name": "corpus_dir", "type": "STRING", "widget": {"name": "corpus_dir"},
                        "link": None, "label": "语料目录"}],
            "outputs": [{"name": "指标", "type": "STRING", "links": None}],
            "properties": {"Node name for S&R": "CorpusStatCard"},
            "widgets_values": ["", metric, f"{STATS_DIR}/{stats_file}"],  # [corpus_dir(连线), metric, stats_json]
        }
        workflow["nodes"].append(card)
        add_link(workflow, labeler, 0, card, 0, "STRING")
        y += height + CARD_GAP


def chain_dashboard_executor(workflow):
    """复制流水线的组执行器给看板分组用: 流水线执行器 -> 看板执行器 -> 流水线执行器(Sender)"""
    pipeline_exec = next(n for n in workflow["nodes"]
                         if n["type"] == "GroupExecutorSingle" and n["widgets_values"][0] == PIPELINE_GROUP)
    sender = find_node(workflow, "GroupExecutorSender")
    old_link = next(l for l in workflow["links"] if l[1] == pipeline_exec["id"] and l[3] == sender["id"])

    dash_exec = copy.deepcopy(pipeline_exec)
    dash_exec.update({"id": new_node_id(workflow), "title": f"执行组: {DASHBOARD_GROUP}",
                      "pos": [pipeline_exec["pos"][0] + 340, pipeline_exec["pos"][1]]})
    dash_exec["widgets_values"][0] = DASHBOARD_GROUP
    dash_exec["inputs"][0]["link"] = None
    dash_exec["outputs"][0]["links"] = None
    workflow["nodes"].append(dash_exec)

    # 原来 流水线执行器 -> Sender 的连线改接到看板执行器, 再从看板执行器连到 Sender
    old_link[3], old_link[4] = dash_exec["id"], 0
    dash_exec["inputs"][0]["link"] = old_link[0]
    sender["inputs"][0]["link"] = None
    add_link(workflow, dash_exec, 0, sender, 0, "SIGNAL")
    sender["pos"][0] = max(sender["pos"][0], dash_exec["pos"][0] + 340)


def main():
    workflow = json.loads(SRC.read_text(encoding="utf-8"))
    workflow["id"] = "1a0c7e2e-5b3f-4d6a-9e81-0e5f3c2d1b01"  # 和 docx_workflow_test 区分, 可同时打开
    add_dashboard_group(workflow)
    chain_dashboard_executor(workflow)
    DST.write_text(json.dumps(workflow, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"写入 {DST}")


if __name__ == "__main__":
    main()
