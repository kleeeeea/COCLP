import os
import json
import random
from pathlib import Path
from openai import OpenAI
from .llm_utils import resolve_api_key, chat_extract_list

class AnonymizeSchoolNamesNode:
    """
    批量处理一个文件夹下的 .jsonl 文件，将文本中的真实学校名替换成随机生成的虚拟学校名。
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "input_folder": ("STRING", {
                    "multiline": False,
                    "default": "",
                    "lazy": True
                }),
                "output_folder": ("STRING", {
                    "multiline": False,
                    "default": "",
                    "lazy": True
                }),
                "api_key": ("STRING", {"multiline": False}),
                "api_url": ("STRING", {"multiline": False}),
            },
            "optional": {
                "model_name": ("STRING", {"default": "qwen", "multiline": False}),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("processed_folder",)
    FUNCTION = "process"
    OUTPUT_NODE = True
    CATEGORY = "MY_NODES/Anonymization"

    def __init__(self):
        pass

    def get_client(self, api_config_str):
        try:
            config = json.loads(api_config_str)
            api_key = resolve_api_key(config.get("api_key"))
            base_url = config.get("base_url")
            return OpenAI(api_key=api_key, base_url=base_url)
        except Exception as e:
            raise ValueError(f"Invalid API config JSON: {e}")

    def split_text(self, text, chunk_size=4000):
        return [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]

    def replace_names_in_text(self, text, name_mapping):
        for real_name, fake_name in name_mapping.items():
            text = text.replace(real_name, fake_name)
        return text

    def read_all_jsonl_files(self, input_dir):
        all_records = []
        input_path = Path(input_dir)
        for filename in os.listdir(input_path):
            if filename.endswith(".jsonl"):
                file_path = input_path / filename
                with open(file_path, "r", encoding="utf-8") as f:
                    for line in f:
                        try:
                            data = json.loads(line)
                            all_records.append((filename, data))
                        except Exception as e:
                            print(f"Error reading line in {filename}: {e}")
        return all_records

    def save_jsonl_files(self, records_by_file, output_dir):
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        for filename, records in records_by_file.items():
            out_file = output_path / filename
            with open(out_file, "w", encoding="utf-8") as f:
                for record in records:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def extract_school_names(self, client, text):
        system_prompt = (
            "你是一个信息抽取助手。"
            "你的任务是从用户给定的文本中，找出所有出现的中小学或学校名。"
            "如果没有学校名，就返回一个空列表。"
            "只返回严格的JSON数组，不要解释或输出其他内容。"
        )
        user_prompt = f"请从以下文本中提取所有学校名，返回JSON列表：\n{text}"
        return chat_extract_list(client, self.model_name, system_prompt, user_prompt)

    def generate_fake_school_names(self, n=100):
        regions = ["东城", "西城", "南山", "北湖", "中心", "华阳", "朝阳", "海滨", "绿洲", "阳光"]
        types = ["小学", "中学", "小学分校", "第一小学", "第二中学", "第三小学", "实验小学", "附属中学"]

        fake_names = set()
        while len(fake_names) < n:
            region = random.choice(regions)
            school_type = random.choice(types)
            fake_name = f"{region}{school_type}"
            fake_names.add(fake_name)
        return list(fake_names)

    def process(self, input_folder, output_folder, api_key, api_url, model_name="qwen"):
        self.model_name = model_name
        input_path = Path(input_folder)
        output_path = Path(output_folder)
        output_path.mkdir(parents=True, exist_ok=True)

        # Create OpenAI client with user-provided API config
        api=json.dumps(
                {"api_key": api_key, "base_url": api_url}
            )
        client = self.get_client(api)

        print(f"\n🔎 Reading input folder: {input_folder}")
        all_records = self.read_all_jsonl_files(input_path)
        print(f"✅ Loaded {len(all_records)} records")

        # Step 1: Extract school names
        print("\n📌 Step 1: Extracting school names")
        all_school_names = set()
        for _, data in all_records:
            text = data.get("text", "")
            chunks = self.split_text(text, 4000)
            for chunk in chunks:
                names = self.extract_school_names(client, chunk)
                all_school_names.update(names)
        print(f"✅ Found {len(all_school_names)} unique school names")

        # Step 2: Generate fake names
        fake_school_names = self.generate_fake_school_names(max(len(all_school_names), 50))
        school_mapping = dict(zip(all_school_names, fake_school_names))

        print("\n✅ Example mapping:")
        for i, (k, v) in enumerate(school_mapping.items()):
            if i < 10:
                print(f"  {k} -> {v}")

        # Step 3: Replace in text
        print("\n📌 Step 2: Replacing names in texts")
        new_records_by_file = {}
        for filename, data in all_records:
            text = data.get("text", "")
            text = self.replace_names_in_text(text, school_mapping)
            data["text"] = text

            if filename not in new_records_by_file:
                new_records_by_file[filename] = []
            new_records_by_file[filename].append(data)

        # Step 4: Save
        print("\n💾 Saving to output folder...")
        self.save_jsonl_files(new_records_by_file, output_path)
        print("\n✅ All done!")

        return (str(output_path),)

