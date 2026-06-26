import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, TypedDict

import yaml
from langchain_core.language_models import BaseLLM
from langchain_core.messages import BaseMessage, SystemMessage
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph  # CompiledGraph
from pydantic import BaseModel, Field

# ロギング設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ProcessingStage(Enum):
    """4つの処理段階の定義．エラー処理等で利用"""

    LAW_EXTRACTION = "law_extraction"
    REGULATION_EXTRACTION = "regulation_extraction"
    SUMMARY_GENERATION = "summary_generation"
    COMPLETED = "completed"


@dataclass
class ExtractionResult:
    """抽出結果のデータクラス"""

    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    token_count: Optional[int] = None
    processing_time: Optional[float] = None


@dataclass
class LegalDocument:
    """法令文書のデータクラス（YAML対応版）"""

    name: str
    content: str  # 法令全文
    document_type: Literal["law", "regulation"]  # 法令 or 施行規則
    yaml_data: Optional[Dict[str, Any]] = None  # YAML構造データを追加
    articles: Optional[List[str]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """文書の基本検証"""
        if not self.name or not self.content:
            raise ValueError("文書名と内容は必須です")

        # YAML構造データが提供されていない場合の警告
        if self.yaml_data is None:
            logger.warning(
                f"{self.name}: YAML構造データが提供されていません。新しい抽出機能は使用できません。"
            )


class GraphState(TypedDict):
    """グラフの状態管理用TypedDict"""

    law_document: LegalDocument  # 法令文書
    regulation_document: LegalDocument  # 施行規則文書
    target_articles: List[str]  # 抽出対象の条文リスト
    extracted_law_article_numbers: Optional[List[int]]  # 抽出された法令の条文
    extracted_law_content: Optional[str]  # 抽出された法令内容
    extracted_regulation_content: Optional[str]  # 抽出された施行規則内容
    extracted_regulation_article_numbers: Optional[
        List[int]
    ]  # 抽出された施行規則の条項一覧
    final_summary: Optional[str]  # 最終的な要点
    current_stage: ProcessingStage  # 現在の処理段階
    error_message: Optional[str]  # エラーメッセージ
    metadata: Dict[str, Any]  # 処理メタデータ
    application_item: Optional[str]  # 申請項目


def flatten_state(state: GraphState) -> dict[str, str]:
    """stateからプロンプト展開用のcontextを自動生成"""
    context = {}
    for key, value in state.items():
        if hasattr(value, "name") and hasattr(value, "content"):
            context[f"{key}_name"] = value.name
            context[f"{key}_text"] = value.content
        elif hasattr(value, "name"):
            context[f"{key}_name"] = value.name
        elif isinstance(value, (str, int, float)):
            context[key] = str(value)
        # 必要なら他の型にも対応
    return context


class PromptManager:
    """プロンプト管理クラス
    TODO :: prompts_dirをここで管理して良いかどうか．
    理想的には，load_promptでまとめてdir/fileを指定したい．
    そのためには，各部でload_promptを呼び出している部分のファイル名をハードコードから外から与える形にする必要がある．
    """

    def __init__(self, prompts_dir: Path = Path("prompts")):
        self.prompts_dir = prompts_dir
        self._prompts_cache: Dict[str, PromptTemplate] = {}

    def load_prompt(self, prompt_name: str) -> PromptTemplate:
        """プロンプトテンプレートの読み込み（キャッシュ機能付き）"""
        if prompt_name in self._prompts_cache:
            return self._prompts_cache[prompt_name]

        prompt_path = self.prompts_dir / f"{prompt_name}.yaml"
        if not prompt_path.exists():
            raise FileNotFoundError(
                f"プロンプトファイルが見つかりません: {prompt_path}"
            )

        with open(prompt_path, "r", encoding="utf-8") as f:
            prompt_data = yaml.safe_load(f)

        template = PromptTemplate(
            input_variables=prompt_data.get("input_variables", []),
            template=prompt_data["template"],
        )

        self._prompts_cache[prompt_name] = template
        return template

    def render_prompt(self, name: str, context: dict) -> str:
        """プロンプトテンプレートから必要な引数を自動で取得"""
        prompt_template = self.load_prompt(name)

        # 必要なキーだけ抽出して format に渡す
        subset = {
            k: context[k] for k in prompt_template.input_variables if k in context
        }
        print(f"debug subset = {subset}")
        return prompt_template.template.format(**subset)


class ViewPointResult(BaseModel):
    """判断軸のstructured output用Pydanticモデル"""

    viewpoint: str = Field(description="官庁への申請が必要な場合の観点")
    annotation: str = Field(description="注釈")


class BaseExtractor(ABC):
    """抽出処理の基底クラス"""

    def __init__(self, llm: BaseLLM, prompt_manager: PromptManager, prompt_name: str):
        self.llm = llm
        self.prompt_manager = prompt_manager
        self.prompt_name = prompt_name

    @abstractmethod
    def extract(self, state: GraphState) -> ExtractionResult:
        """抽出処理の実行．ここで_create_messagesと_invoke_llmを呼び出す"""
        pass

    def _create_messages(self, formatted_prompt: str) -> List[BaseMessage]:
        """メッセージリストの生成"""
        return [SystemMessage(content=formatted_prompt)]

    def _invoke_llm(self, messages: List[BaseMessage]) -> str:
        """LLMの呼び出しと例外処理"""
        try:
            response = self.llm.invoke(messages)
            return response.content if hasattr(response, "content") else str(response)
        except Exception as e:
            logger.error(f"LLM呼び出しエラー: {e}")
            raise


class LawExtractor(BaseExtractor):
    """法令本体からの関連条文抽出"""

    def extract(self, state: GraphState) -> ExtractionResult:
        """法令から関連条文を抽出"""
        logger.info("法令からの関連条文抽出を開始")

        # FIXME :: プロンプトのより良い読み込み方法を考える．
        prompt_template = self.prompt_manager.load_prompt(self.prompt_name)
        formatted_prompt = prompt_template.format(
            law_name=state["law_document"].name,
            law_article=", ".join(state["target_articles"]),
            law_text=state["law_document"].content,
        )

        messages = self._create_messages(formatted_prompt)
        extracted_content = self._invoke_llm(messages)

        return ExtractionResult(
            content=extracted_content,
            metadata={
                "stage": "law_extraction",
                "source_document": state["law_document"].name,
                "target_articles": state["target_articles"],
            },
        )


class RegulationExtractor(BaseExtractor):
    """施行規則からの関連条文抽出"""

    def extract(self, state: GraphState) -> ExtractionResult:
        """施行規則から関連条文を抽出"""
        logger.info("施行規則からの関連条文抽出を開始")

        # FIXME :: プロンプトのより良い読み込み方法を考える．
        prompt_template = self.prompt_manager.load_prompt(self.prompt_name)
        formatted_prompt = prompt_template.format(
            law_name=state["law_document"].name,
            extracted_law_content=state["extracted_law_content"],
            regulation_text=state["regulation_document"].content,
        )

        messages = self._create_messages(formatted_prompt)
        extracted_content = self._invoke_llm(messages)

        return ExtractionResult(
            content=extracted_content,
            metadata={
                "stage": "regulation_extraction",
                "source_document": state["regulation_document"].name,
                "law_reference": state["law_document"].name,
            },
        )


class ViewpointGenerator(BaseExtractor):
    """最終判断軸生成"""

    def extract(self, state: GraphState) -> ExtractionResult:
        """抽出した法令(state[extracted_law_content],state[extracted_regulation_content])を利用して，最終的な要点を生成"""
        logger.info("最終的な判断軸生成を開始")

        # プロンプトの読み込み
        base_context = flatten_state(state)
        special_context = {
            "law_name": state["law_document"].name,
            "law_article": ", ".join(state["target_articles"]),
            "law_text": state["extracted_law_content"],
            "enforcement_regulations": state["extracted_regulation_content"],
        }

        formatted_prompt = self.prompt_manager.render_prompt(
            self.prompt_name,
            context={**base_context, **special_context},
        )

        messages = self._create_messages(formatted_prompt)
        structured_llm = self.llm.with_structured_output(ViewPointResult)
        summary = structured_llm.invoke(messages)

        return ExtractionResult(
            content=summary,
            metadata={
                "stage": "summary_generation",
                "law_document": state["law_document"].name,
                "regulation_document": state["regulation_document"].name,
            },
        )


class GraphBuilder:
    """法令要点抽出のグラフビルダー"""

    # 各LLM呼び出しのプロンプト名
    DEFAULT_PROMPT_NAMES = {
        "extract_law": "extract_laws_v001",
        "extract_regulation": "extract_regulation_v001",
        "generate_summary": "v003",
    }

    def __init__(
        self,
        llm: BaseLLM,
        prompts_dir: Path = Path("prompts"),
        prompt_names: Optional[Dict[str, str]] = None,
    ):
        self.llm = llm
        self.prompt_manager = PromptManager(prompts_dir)

        # デフォルトとユーザ指定をマージ（ユーザ指定が優先）
        self.prompt_names = {**self.DEFAULT_PROMPT_NAMES, **(prompt_names or {})}

        # 各抽出器の初期化
        self.law_extractor = LawExtractor(
            llm, self.prompt_manager, self.prompt_names["extract_law"]
        )
        self.regulation_extractor = RegulationExtractor(
            llm, self.prompt_manager, self.prompt_names["extract_regulation"]
        )
        self.summary_generator = ViewpointGenerator(
            llm, self.prompt_manager, self.prompt_names["generate_summary"]
        )

        # グラフの構築
        self.graph = self._build_graph()

    def _build_graph(self):  # TODO:: CompiledGraph型の戻り値を指定
        """LangGraphの構築"""
        workflow = StateGraph(GraphState)

        # ノードの追加
        workflow.add_node("extract_law", self._extract_law_node)
        workflow.add_node("extract_regulation", self._extract_regulation_node)
        workflow.add_node("generate_summary", self._generate_summary_node)
        workflow.add_node("handle_error", self._handle_error_node)

        # エッジの設定
        workflow.set_entry_point("extract_law")

        workflow.add_conditional_edges(
            "extract_law",
            self._should_continue_to_regulation,
            {"continue": "extract_regulation", "error": "handle_error"},
        )

        workflow.add_conditional_edges(
            "extract_regulation",
            self._should_continue_to_summary,
            {"continue": "generate_summary", "error": "handle_error"},
        )

        workflow.add_edge("generate_summary", END)
        workflow.add_edge("handle_error", END)

        return workflow.compile()

    def _extract_law_node(self, state: GraphState) -> GraphState:
        """法令抽出ノード"""
        try:
            result = self.law_extractor.extract(state)
            state["extracted_law_content"] = result.content
            state["current_stage"] = ProcessingStage.LAW_EXTRACTION
            state["metadata"].update(result.metadata)
            logger.info("法令抽出が完了しました")
        except Exception as e:
            state["error_message"] = f"法令抽出エラー: {str(e)}"
            logger.error(state["error_message"])

        return state

    def _extract_regulation_node(self, state: GraphState) -> GraphState:
        """施行規則抽出ノード"""
        try:
            result = self.regulation_extractor.extract(state)
            state["extracted_regulation_content"] = result.content
            state["current_stage"] = ProcessingStage.REGULATION_EXTRACTION
            state["metadata"].update(result.metadata)
            logger.info("施行規則抽出が完了しました")
        except Exception as e:
            state["error_message"] = f"施行規則抽出エラー: {str(e)}"
            logger.error(state["error_message"])

        return state

    def _generate_summary_node(self, state: GraphState) -> GraphState:
        """要点生成ノード"""
        try:
            result = self.summary_generator.extract(state)
            state["final_summary"] = result.content
            state["current_stage"] = ProcessingStage.COMPLETED
            state["metadata"].update(result.metadata)
            logger.info("要点生成が完了しました")
        except Exception as e:
            state["error_message"] = f"要点生成エラー: {str(e)}"
            logger.error(state["error_message"])

        return state

    def _handle_error_node(self, state: GraphState) -> GraphState:
        """エラーハンドリングノード"""
        logger.error(
            f"処理中にエラーが発生しました: {state.get('error_message', '不明なエラー')}"
        )
        state["current_stage"] = ProcessingStage.COMPLETED
        return state

    def _should_continue_to_regulation(self, state: GraphState) -> str:
        """施行規則抽出への継続判定"""
        return "error" if state.get("error_message") else "continue"

    def _should_continue_to_summary(self, state: GraphState) -> str:
        """要点生成への継続判定"""
        return "error" if state.get("error_message") else "continue"

    def process(
        self,
        law_document: LegalDocument,
        regulation_document: LegalDocument,
        target_articles: List[str],
    ) -> GraphState:
        """処理の実行"""
        initial_state = GraphState(
            law_document=law_document,
            regulation_document=regulation_document,
            target_articles=target_articles,
            extracted_law_content=None,
            extracted_regulation_content=None,
            final_summary=None,
            current_stage=ProcessingStage.LAW_EXTRACTION,
            error_message=None,
            metadata={},
        )

        logger.info("法令判断軸抽出処理を開始します")
        result = self.graph.invoke(initial_state)
        logger.info(f"処理が完了しました。ステージ: {result['current_stage']}")

        return result


class LegalExtractionConfig:
    """設定管理クラス"""

    def __init__(
        self,
        llm,
        prompts_dir: str = "prompts",
        prompt_names: Optional[Dict[str, str]] = None,
    ):
        self.llm = llm
        self.prompts_dir = Path(prompts_dir)
        self.prompt_names = prompt_names


def create_legal_extraction_system(config: LegalExtractionConfig) -> GraphBuilder:
    """法令要点抽出システムのファクトリー関数"""
    return GraphBuilder(
        llm=config.llm, prompts_dir=config.prompts_dir, prompt_names=config.prompt_names
    )


# 使用例
def example_usage():
    """使用例の実装"""

    # 設定の初期化
    config = LegalExtractionConfig(
        model_name="gpt-4o-mini",
        temperature=0.1,
        prompts_dir="prompts",
    )

    # システムの初期化
    extraction_system = create_legal_extraction_system(config)

    # サンプルデータ
    law_document = LegalDocument(
        name="土壌汚染対策法", content="（ここに法令本文が入る）", document_type="law"
    )

    regulation_document = LegalDocument(
        name="土壌汚染対策法施行規則",
        content="（ここに施行規則本文が入る）",
        document_type="regulation",
    )

    target_articles = ["第3条", "第4条"]

    # 処理の実行
    try:
        result = extraction_system.process(
            law_document=law_document,
            regulation_document=regulation_document,
            target_articles=target_articles,
        )

        if result["error_message"]:
            print(f"エラーが発生しました: {result['error_message']}")
        else:
            print("=== 最終要点 ===")
            print(result["final_summary"])

            print("\n=== メタデータ ===")
            for key, value in result["metadata"].items():
                print(f"{key}: {value}")

    except Exception as e:
        logger.error(f"処理中に予期しないエラーが発生しました: {e}")
