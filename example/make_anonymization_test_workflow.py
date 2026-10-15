"""从 anonymization_workflow.json 生成 anonymization_workflow_test.json:
- 输入用 pdf_workflow_test 清洗后的 jsonl (example/test_out/pdf/clean), 先跑 pdf 流程才有
- LLM 用 ECNU 的 ecnu-plus; api_key 填 None, 实际 key 由 run.sh start 从 .env 读进环境变量 ECNU_API_KEY
- 人名/学校名两步后面各接一个 "预览输出目录" 节点, 放在各自组里

用法: python example/make_anonymization_test_workflow.py
"""
import json
from pathlib import Path

from make_pdf_test_workflow import find_node, add_preview_node, PREVIEW_H

EXAMPLE_DIR = Path(__file__).resolve().parent
SRC = EXAMPLE_DIR / "anonymization_workflow.json"
DST = EXAMPLE_DIR / "anonymization_workflow_test.json"

INPUT_DIR = "../example/test_out/pdf/clean"
OUTPUT_ROOT = "../example/test_out/anonymize"
API_URL = "https://chat.ecnu.edu.cn/open/api/v1"
MODEL_NAME = "ecnu-plus"


def node_linked_to(workflow, target_node, input_name):
    """找连到 target_node 某个输入上的上游节点 (这里是提供 api_url 的 PromptTextEditor)"""
    link_id = next(i["link"] for i in target_node["inputs"] if i["name"] == input_name)
    from_id = next(l[1] for l in workflow["links"] if l[0] == link_id)
    return next(n for n in workflow["nodes"] if n["id"] == from_id)


def main():
    workflow = json.loads(SRC.read_text(encoding="utf-8"))

    name_node = find_node(workflow, "AnonymizeChineseNamesNode")
    school_node = find_node(workflow, "AnonymizeSchoolNamesNode")

    # widgets_values: [input_folder, output_folder, api_key, api_url, model_name]
    name_node["widgets_values"] = [INPUT_DIR, f"{OUTPUT_ROOT}/name", "None", "", MODEL_NAME]
    school_node["widgets_values"] = ["", f"{OUTPUT_ROOT}/school", "None", "", MODEL_NAME]
    for node in (name_node, school_node):
        node_linked_to(workflow, node, "api_url")["widgets_values"] = [API_URL]

    for node, group_title, title in [
        (name_node, "个人名字去隐私", "预览: 人名去隐私结果"),
        (school_node, "学校名字去隐私", "预览: 学校名去隐私结果"),
    ]:
        group = next(g for g in workflow["groups"] if g["title"] == group_title)
        gx, gy, gw, gh = group["bounding"]
        add_preview_node(workflow, node, (gx + 20, gy + gh + 20), title)
        group["bounding"][2] = max(gw, 460)
        group["bounding"][3] = gh + PREVIEW_H + 80  # 组往下扩, 把预览节点包进来

    DST.write_text(json.dumps(workflow, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"写入 {DST}")


if __name__ == "__main__":
    main()
