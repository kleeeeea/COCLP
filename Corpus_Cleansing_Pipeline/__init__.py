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
from .preview_dir_node import PreviewOutputDir, PreviewPdfPage
from .compare_diff_node import CompareTextDiff
from .doc_preview_node import DocFirstPagePreview
from .five_dim_label_node import FiveDimLabelNode
from .stat_card_node import CorpusStatCard
from .audio_waveform_node import AudioWaveform
from .user_feedback_node import UserFeedbackLogParser, FeedbackToSFT
from .text_normalizer_node import TextNormalizer
from .privacy_detection_node import PIIRuleEngine, PIINerEngine, PIIMerge, PassThroughDir
from .desensitize_node import Desensitizer
from .human_audit_node import HumanSampleAudit
from .quality_control_node import QualityAssess, GoldenLabelCheck, ExpertSampleReview
from .version_trace_node import BatchVersionRegister, ModelCorpusTrace, ComplianceAudit
from .dedup_node import SimHashDedup

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
    "PreviewPdfPage": PreviewPdfPage,
    "CompareTextDiff": CompareTextDiff,
    "DocFirstPagePreview": DocFirstPagePreview,
    "FiveDimLabelNode": FiveDimLabelNode,
    "CorpusStatCard": CorpusStatCard,
    "AudioWaveform": AudioWaveform,
    "UserFeedbackLogParser": UserFeedbackLogParser,
    "FeedbackToSFT": FeedbackToSFT,
    "TextNormalizer": TextNormalizer,
    "PIIRuleEngine": PIIRuleEngine,
    "PIINerEngine": PIINerEngine,
    "PIIMerge": PIIMerge,
    "PassThroughDir": PassThroughDir,
    "Desensitizer": Desensitizer,
    "HumanSampleAudit": HumanSampleAudit,
    "QualityAssess": QualityAssess,
    "GoldenLabelCheck": GoldenLabelCheck,
    "ExpertSampleReview": ExpertSampleReview,
    "BatchVersionRegister": BatchVersionRegister,
    "ModelCorpusTrace": ModelCorpusTrace,
    "ComplianceAudit": ComplianceAudit,
    "SimHashDedup": SimHashDedup,

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
    "PreviewPdfPage": "PDF 页面预览",
    "CompareTextDiff": "清洗前后对比",
    "DocFirstPagePreview": "文档首页预览",
    "FiveDimLabelNode": "五维标注与分类",
    "CorpusStatCard": "语料规模看板",
    "AudioWaveform": "音频波形",
    "UserFeedbackLogParser": "用户反馈日志解析",
    "FeedbackToSFT": "反馈转 SFT 样本",
    "TextNormalizer": "格式归一化与语言规范化",
    "PIIRuleEngine": "隐私检测·规则引擎",
    "PIINerEngine": "隐私检测·NER 模型",
    "PIIMerge": "隐私检测结果合并",
    "PassThroughDir": "语料输入",
    "Desensitizer": "脱敏处理",
    "HumanSampleAudit": "人工抽样审计 (阻塞等待审核)",
    "QualityAssess": "质量评估 (规则 + 模型评审)",
    "GoldenLabelCheck": "黄金集质控 (五维标注)",
    "ExpertSampleReview": "专家抽样审核 (阻塞等待审核)",
    "BatchVersionRegister": "批次版本登记",
    "ModelCorpusTrace": "模型-语料双向追溯",
    "ComplianceAudit": "隐私合规审计 (月度报告)",
    "SimHashDedup": "近似去重与达标筛选 (SimHash)",
}


