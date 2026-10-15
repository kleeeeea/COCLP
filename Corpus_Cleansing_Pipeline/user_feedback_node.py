"""2.4 用户贡献采集: 网站反馈接口日志 -> 结构化用户反馈数据 (规则解析, 不调模型).

日志格式 (每行一条):
    <日期> <时间> <级别> [feedback-api] <IP> <方法> /api/feedback/<类型> uid=<用户> resource=<资源> page="<页面>" body=<JSON>
输出 feedback.jsonl: 用户 ID 不可逆哈希、IP 脱敏, 反馈内容按类型拆成结构化字段.
示例: example/offline_prepared/user_flywheel/
"""
import hashlib
import json
import re
from pathlib import Path

LOG_RE = re.compile(
    r'^(?P<ts>\S+ \S+) \S+ \[feedback-api\] (?P<ip>\S+) (?P<method>[A-Z]+) /api/feedback/(?P<kind>\w+) '
    r'uid=(?P<uid>\S+) resource=(?P<resource>\S+) page="(?P<page>[^"]*)" body=(?P<body>\{.*\})$')
FEEDBACK_TYPES = {"rate": "评分", "comment": "评论", "correct": "纠错", "rewrite": "AI 回答改写", "upload": "资源上传"}
BODY_FIELDS = {"original": "原文", "corrected": "修改后", "note": "说明", "text": "评论", "value": "评分",
               "question": "问题", "ai_answer": "AI 回答", "user_answer": "用户改写"}


def hash_uid(uid, salt):
    """用户 ID 入库即不可逆哈希, 不保存明文账号"""
    return "U_" + hashlib.sha256((salt + uid).encode("utf-8")).hexdigest()[:10]


def mask_ip(ip):
    parts = ip.split(".")
    return ".".join(parts[:2] + ["*", "*"]) if len(parts) == 4 else "*"


def parse_feedback_line(line, salt):
    """一行日志 -> 一条结构化反馈; 解析不了返回 None"""
    m = LOG_RE.match(line.strip())
    if not m:
        return None
    body = json.loads(m["body"])
    record = {"时间": m["ts"], "用户": hash_uid(m["uid"], salt), "IP": mask_ip(m["ip"]),
              "资源": f'{m["resource"]} {m["page"]}', "反馈类型": FEEDBACK_TYPES.get(m["kind"], m["kind"])}
    record.update({BODY_FIELDS.get(k, k): v for k, v in body.items()})
    return record


class UserFeedbackLogParser:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "log_dir": ("STRING", {"default": "../example/offline_prepared/user_flywheel/data"}),
            "output_dir": ("STRING", {"default": "../example/offline_prepared/user_flywheel/output"}),
            "uid_salt": ("STRING", {"default": "edu-flywheel"}),
        }}

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("原始日志目录", "结构化反馈目录")
    FUNCTION = "run"
    CATEGORY = "MY_NODES/用户贡献"

    def run(self, log_dir, output_dir, uid_salt):
        records = []
        for log_file in sorted(Path(log_dir).glob("*.log")):
            for line in log_file.read_text(encoding="utf-8").splitlines():
                record = parse_feedback_line(line, uid_salt)
                if record:
                    records.append({"id": f"FB{len(records) + 1:04d}", **record})
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        with open(out / "feedback.jsonl", "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        return (log_dir, output_dir)


DEFAULT_SYSTEM_PROMPT = "你是一名严谨的中小学学科教学助手，回答要准确、规范，符合课程标准。"


def feedback_to_sft(fb, system_prompt):
    """一条结构化反馈 -> 一条 SFT 样本 (messages 对话格式); 不适合做 SFT 的反馈类型返回 None"""
    if fb["反馈类型"] == "纠错":
        user = f"下面这句话是否正确？如有错误请改正：\n{fb['原文']}"
        assistant = f"这句话有误。正确的说法是：{fb['修改后']}。"
    elif fb["反馈类型"] == "AI 回答改写":
        user, assistant = fb["问题"], fb["用户改写"]
    else:
        return None  # 评分、评论等只作为质量信号, 不直接生成训练样本
    return {"messages": [{"role": "system", "content": system_prompt},
                         {"role": "user", "content": user},
                         {"role": "assistant", "content": assistant}],
            "meta": {"来源": f"用户反馈 {fb['id']}", "资源": fb["资源"], "反馈类型": fb["反馈类型"]}}


class FeedbackToSFT:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "input_dir": ("STRING", {"forceInput": True}),
            "output_dir": ("STRING", {"default": "../example/offline_prepared/user_flywheel/output/sft"}),
            "system_prompt": ("STRING", {"default": DEFAULT_SYSTEM_PROMPT, "multiline": True}),
        }}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("SFT 样本目录",)
    FUNCTION = "run"
    CATEGORY = "MY_NODES/用户贡献"

    def run(self, input_dir, output_dir, system_prompt):
        samples = []
        with open(Path(input_dir) / "feedback.jsonl", encoding="utf-8") as f:
            for line in f:
                sample = feedback_to_sft(json.loads(line), system_prompt)
                if sample:
                    samples.append(sample)
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        with open(out / "sft.jsonl", "w", encoding="utf-8") as f:
            for s in samples:
                f.write(json.dumps(s, ensure_ascii=False) + "\n")
        return (output_dir,)


if __name__ == "__main__":
    import sys
    for i, line in enumerate(Path(sys.argv[1]).read_text(encoding="utf-8").splitlines(), start=1):
        fb = {"id": f"FB{i:04d}", **parse_feedback_line(line, "edu-flywheel")}
        print(json.dumps(fb, ensure_ascii=False, indent=1))
        print(json.dumps(feedback_to_sft(fb, DEFAULT_SYSTEM_PROMPT), ensure_ascii=False, indent=1))
