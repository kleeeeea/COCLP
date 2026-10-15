import os
import json
import re

# api_key 控件填 "None"/空 时, 依次从这些环境变量取 key (run.sh start 会 source LLM_ENV_FILE)
API_KEY_ENV_NAMES = ("COCLP_API_KEY", "ECNU_API_KEY")


# 输出目录里有这个标记文件 = 结果已离线生成好, 大模型节点直接复用, 不再调 API (用于演示/截图)
OFFLINE_MARKER = ".offline_prepared"


def is_offline_prepared(output_folder):
    return bool(output_folder) and os.path.isfile(os.path.join(output_folder, OFFLINE_MARKER))


def resolve_api_key(api_key):
    """workflow json 里不存真实 key: 控件为空或 "None" 时从环境变量读"""
    if api_key and api_key.strip() not in ("", "None"):
        return api_key.strip()
    for env_name in API_KEY_ENV_NAMES:
        if os.environ.get(env_name):
            return os.environ[env_name]
    raise ValueError(f"api_key 为空, 且环境变量 {API_KEY_ENV_NAMES} 都没设置")


def parse_json_list(answer):
    """模型偶尔会包 ```json ... ``` 或带 <think>, 取出第一个 JSON 数组"""
    answer = re.sub(r"<think>.*?</think>", "", answer, flags=re.DOTALL)
    match = re.search(r"\[.*\]", answer, flags=re.DOTALL)
    if not match:
        return []
    items = json.loads(match.group(0))
    return [x for x in items if isinstance(x, str) and x.strip()]


def chat_extract_list(client, model_name, system_prompt, user_prompt):
    """调用 OpenAI 兼容接口, 返回字符串列表; 出错时打印原因并返回 [] (原代码是静默吞掉)"""
    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0,
        )
        return parse_json_list(response.choices[0].message.content or "")
    except Exception as e:
        print(f"[llm_utils] 抽取失败 ({model_name}): {type(e).__name__}: {e}")
        return []


if __name__ == "__main__":
    print(parse_json_list('```json\n["张三", "李四"]\n```'))
