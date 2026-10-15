from .Mineru_node import Mineru_ocr
from .move_md import MOVE_MD
from .auto_label import SampleDataNode, LabelDataNode
from .Copy_Files_by_ID import JsonlCopyFilesByIdNode
from .count_data import JsonlCountByConditionsNode
from .docx_to_markdown import DocxToMarkdown
from .Extract_IDs import JsonlExtractIdsByFieldNode
from .FileClassifier_Node import FileClassifier
from .md_to_jsonl import MarkdownInfoNode
from .multipruner_node_v2 import MultiPruner
from .pipeline_node import BatchProcessDocumentsNode
from .privacy_name import AnonymizeChineseNamesNode
from .privacy_school import AnonymizeSchoolNamesNode
from .QA_extract import BatchGenerateQANode
from .text_node import PromptTextEditor
from .train_label import TrainBertNode, InferenceBertNode
from .unzip_node import UNZIP
from .whisper_novad_node import WhisperNoVADTranscribeNode
from .preview_dir_node import PreviewOutputDir
from .compare_diff_node import CompareTextDiff
from .doc_preview_node import DocFirstPagePreview

# web/preview_dir.js 负责把 PreviewOutputDir 的 ui.text 显示在节点上
WEB_DIRECTORY = "./web"


NODE_CLASS_MAPPINGS = {
    "Mineru_ocr": Mineru_ocr,
    "MOVE_MD": MOVE_MD,
    "SampleDataNode": SampleDataNode,
    "LabelDataNode": LabelDataNode,
    "JsonlCopyFilesByIdNode": JsonlCopyFilesByIdNode,
    "JsonlCountByConditionsNode": JsonlCountByConditionsNode,
    "DocxToMarkdown": DocxToMarkdown,
    "JsonlExtractIdsByFieldNode": JsonlExtractIdsByFieldNode,
    "FileClassifier": FileClassifier,
    "MarkdownInfoNode": MarkdownInfoNode,
    "MultiPruner": MultiPruner,
    "BatchProcessDocuments_Zho": BatchProcessDocumentsNode,
    "AnonymizeChineseNamesNode": AnonymizeChineseNamesNode,
    "AnonymizeSchoolNamesNode": AnonymizeSchoolNamesNode,
    "BatchGenerateQANode": BatchGenerateQANode,
    "PromptTextEditor": PromptTextEditor,
    "TrainBertNode": TrainBertNode,
    "InferenceBertNode": InferenceBertNode,
    "UNZIP": UNZIP,
    "WhisperNoVADTranscribeNode": WhisperNoVADTranscribeNode,
    "PreviewOutputDir": PreviewOutputDir,
    "CompareTextDiff": CompareTextDiff,
    "DocFirstPagePreview": DocFirstPagePreview,

}


def _request_all_lazy_inputs(self, **kwargs):
    """节点里很多路径参数标了 "lazy": True 却没实现 check_lazy_status,
    ComfyUI 不会求值这种连线输入 -> 节点收到 None. 这里把仍为 None 的输入全部请求求值"""
    return [name for name, value in kwargs.items() if value is None]


for _node_class in NODE_CLASS_MAPPINGS.values():
    if not hasattr(_node_class, "check_lazy_status"):
        _node_class.check_lazy_status = _request_all_lazy_inputs

# A dictionary that contains the friendly/humanly readable titles for the nodes
NODE_DISPLAY_NAME_MAPPINGS = {
    "Mineru_ocr": "Mineru_ocr",
    "MOVE_MD": "MD文件移动工具",
    "SampleDataNode": "抽样数据 (蓄水池抽样)",
    "LabelDataNode": "标注数据 (LLM)",
    "JsonlCopyFilesByIdNode": "JSONL Copy Files By ID Node",
    "JsonlCountByConditionsNode": "JSONL Count By Conditions Node",
    "DocxToMarkdown": "DocxToMarkdown",
    "JsonlExtractIdsByFieldNode": "JSONL Extract IDs By Field Node",
    "FileClassifier": "文件分类器",
    "MarkdownInfoNode": "Markdown → JSONL",
    "MultiPruner": "多功能文本清洗器",
    "BatchProcessDocuments_Zho": "文档批量分类处理 (Batch Process)",
    "AnonymizeChineseNamesNode": "Anonymize Chinese Names Node",
    "AnonymizeSchoolNamesNode": "Anonymize School Names Node",
    "BatchGenerateQANode": "Batch Generate QA Node",
    "PromptTextEditor": "文本编辑器",
    "TrainBertNode": "训练BERT分类器",
    "InferenceBertNode": "使用BERT分类器推理",
    "UNZIP": "压缩包解压",
    "WhisperNoVADTranscribeNode": "Whisper 批量转写节点 (含VAD+简体)",
    "PreviewOutputDir": "预览输出目录",
    "CompareTextDiff": "清洗前后对比",
    "DocFirstPagePreview": "文档首页预览",
}


