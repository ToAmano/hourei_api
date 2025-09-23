"""
YAMLパーサを利用する場合のlanggraphコード

# TODO :: law_extraction.pyとかぶっているGraphBuilderなどのリファクタリング
# TODO :: YAMLArticleExtractorとRegulationExtractorも共通部分が多いのでまとめられないか検討
# TODO :: YamlArticleExtractorはyaml_converterと密接に繋がっているので，場所を移動する．
"""

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

from law_extraction import (  # RegulationExtractor,
    BaseExtractor,
    ExtractionResult,
    GraphState,
    LegalDocument,
    ProcessingStage,
    PromptManager,
    ViewpointGenerator,
    flatten_state,
)

logger = logging.getLogger(__name__)


class RelevantArticles(BaseModel):
    """関連条文のstructured output用Pydanticモデル"""

    article_numbers: List[str] = Field(
        description="関連する条文番号のリスト（例: ['3', '4', '20_2', '62']）"
    )
    extraction_reasoning: str = Field(
        description="これらの条文を選択した理由の簡潔な説明"
    )


@dataclass
class ExtractedArticleContent:
    """抽出された条文内容"""

    article_num: str
    title: str
    full_content: str
    found: bool = True


class YamlArticleExtractor:
    """YAML構造から条文を抽出するクラス"""

    def __init__(self, yaml_data: Dict[str, Any]):
        """
        Args:
            yaml_data: 法令のYAMLデータ辞書
        """
        self.yaml_data = yaml_data

    def extract_articles_by_numbers(
        self, article_numbers: List[str]
    ) -> List[ExtractedArticleContent]:
        """指定された条文番号リストから条文内容を抽出

        Args:
            article_numbers: 抽出したい条文番号のリスト

        Returns:
            抽出された条文内容のリスト
        """
        extracted_articles = []

        for article_num in article_numbers:  # 条文でループ
            try:
                article_content = self._find_and_extract_article(article_num)
                extracted_articles.append(article_content)
            except Exception as e:
                logger.error(f"条文{article_num}の抽出でエラー: {e}")
                # 見つからない場合でもエラー情報を含めて追加
                extracted_articles.append(
                    ExtractedArticleContent(
                        article_num=article_num,
                        title="",
                        full_content=f"第{article_num}条の内容を取得できませんでした",
                        found=False,
                    )
                )

        return extracted_articles

    def _find_and_extract_article(self, article_num: str) -> ExtractedArticleContent:
        """指定された条文番号の条文を直接検索・抽出

        Args:
            article_num: 条文番号

        Returns:
            抽出された条文内容
        """
        # YAML構造を直接検索
        target_article = self._search_article_in_yaml(article_num)

        if not target_article:
            raise ValueError(f"第{article_num}条が見つかりません")

        # 条文の完全な内容を抽出
        title = target_article.get("title", "")
        full_content = self._extract_full_article_text(target_article)

        return ExtractedArticleContent(
            article_num=article_num, title=title, full_content=full_content, found=True
        )

    def _search_article_in_yaml(self, article_num: str) -> Optional[Dict[str, Any]]:
        """YAML構造から指定された条文番号を直接検索
        # TODO :: もう少し綺麗に実装する．三つあるのがやばい．
        """

        # part構造（一部の大規模法令）
        if "parts" in self.yaml_data:
            for part in self.yaml_data["parts"]:
                if "chapters" in part:
                    for chapter in part["chapters"]:
                        # 章直下の条文を検索
                        if "articles" in chapter:
                            for article in chapter["articles"]:
                                if article.get("article_num") == article_num:
                                    return article

                        # 節の下の条文を検索
                        if "sections" in chapter:
                            for section in chapter["sections"]:
                                # section直下がsubsectionの場合
                                if "subsections" in chapter:
                                    for subsection in section["subsections"]:
                                        # section直下がarticleの場合
                                        if "articles" in subsection:
                                            for article in subsection["articles"]:
                                                if (
                                                    article.get("article_num")
                                                    == article_num
                                                ):
                                                    return article

                                # section直下がarticleの場合
                                if "articles" in section:
                                    for article in section["articles"]:
                                        if article.get("article_num") == article_num:
                                            return article

        # chapters構造（一般的な法令）
        elif "chapters" in self.yaml_data:
            for chapter in self.yaml_data["chapters"]:
                # 章直下の条文を検索
                if "articles" in chapter:
                    for article in chapter["articles"]:
                        if article.get("article_num") == article_num:
                            return article

                # 節の下の条文を検索
                if "sections" in chapter:
                    for section in chapter["sections"]:
                        # section直下がsubsectionの場合
                        if "subsections" in chapter:
                            for subsection in section["subsections"]:
                                # section直下がarticleの場合
                                if "articles" in subsection:
                                    for article in subsection["articles"]:
                                        if article.get("article_num") == article_num:
                                            return article

                        # section直下がarticleの場合
                        if "articles" in section:
                            for article in section["articles"]:
                                if article.get("article_num") == article_num:
                                    return article

        # articles構造（施行規則等）
        elif "articles" in self.yaml_data:
            for article in self.yaml_data["articles"]:
                if article.get("article_num") == article_num:
                    return article

        return None

    def _extract_full_article_text(self, article: Dict[str, Any]) -> str:
        """条文の完全なテキストを抽出
        # TODO :: ここもどのようにテキスト化するか，論点になる．
        # TODO :: もっというと，xml->yaml->textとしてるので非常に効率が悪い．
        """
        content_parts = []

        # 条文タイトル
        title = article.get("title", "")
        caption = article.get("caption", "")
        article_num = article.get("article_num", "?")

        # 条文ヘッダー
        if caption:
            header = f"第{article_num}条（{caption}）"
        else:
            header = f"第{article_num}条"

        if title:
            header += f" {title}"

        content_parts.append(header)

        # 各項を処理
        paragraphs = article.get("paragraphs", [])
        for i, paragraph in enumerate(paragraphs):
            paragraph_content = self._extract_paragraph_text(paragraph, i + 1)
            if paragraph_content:
                content_parts.append(paragraph_content)

        return "\n".join(content_parts)

    def _extract_paragraph_text(
        self, paragraph: Dict[str, Any], paragraph_index: int
    ) -> str:
        """項のテキストを抽出"""
        parts = []

        # 項番号（明示的にない場合は項番号を付与）
        paragraph_num = paragraph.get("paragraph_num", str(paragraph_index))
        if (
            paragraph_num and paragraph_num != "1"
        ):  # 第1項の場合は番号を省略することが多い
            parts.append(f"（第{paragraph_num}項）")

        # 項の本文
        content = paragraph.get("content", "")
        if content:
            parts.append(content)

        # 号がある場合
        items = paragraph.get("items", [])
        for item in items:
            item_text = self._extract_item_text(item)
            if item_text:
                parts.append(f"  {item_text}")

        # 表がある場合
        if "table" in paragraph:
            table_text = self._extract_table_text(paragraph["table"])
            if table_text:
                parts.append(f"【表】\n{table_text}")

        return "\n".join(parts) if parts else ""

    def _extract_item_text(self, item: Dict[str, Any]) -> str:
        """号のテキストを抽出"""
        parts = []

        # 号番号とタイトル
        title = item.get("title", "")
        content = item.get("content", "")

        if title and content:
            parts.append(f"{title} {content}")
        elif content:
            parts.append(content)

        # サブ項目がある場合（イロハなど）
        subitems = item.get("subitems", [])
        for subitem in subitems:
            subitem_text = self._extract_subitem_text(subitem)
            if subitem_text:
                parts.append(f"    {subitem_text}")

        return "\n".join(parts) if parts else ""

    def _extract_subitem_text(self, subitem: Dict[str, Any]) -> str:
        """サブ項目のテキストを抽出（再帰的）"""
        parts = []

        # サブ項目のタイトルと内容
        title = subitem.get("title", "")
        content = subitem.get("content", "")

        if title and content:
            parts.append(f"{title} {content}")
        elif content:
            parts.append(content)

        # ネストしたサブ項目
        nested_subitems = subitem.get("subitems", [])
        for nested_subitem in nested_subitems:
            nested_text = self._extract_subitem_text(nested_subitem)
            if nested_text:
                parts.append(f"      {nested_text}")

        return "\n".join(parts) if parts else ""

    def _extract_table_text(self, table: Dict[str, Any]) -> str:
        """表のテキストを抽出"""
        rows = table.get("rows", [])
        if not rows:
            return ""

        table_lines = []
        for row in rows:
            if isinstance(row, list):
                # セル区切り文字として|を使用
                table_lines.append("| " + " | ".join(str(cell) for cell in row) + " |")

        return "\n".join(table_lines)


class LawExtractor(BaseExtractor):
    """法令本体からの関連条文抽出（yaml版）"""

    def extract(self, state: GraphState) -> ExtractionResult:
        """法令から関連条文を抽出（2段階方式）"""
        logger.info("法令からの関連条文抽出を開始")

        # ステップ1: LLMで関連条文番号を特定
        relevant_articles = self._identify_relevant_articles(state)
        # print("relevant_articles = :: ", relevant_articles)

        # ステップ2: YAML構造から該当条文を抽出
        extracted_content = self._extract_articles_from_yaml(
            state["law_document"], relevant_articles.article_numbers
        )
        # print("extracted_content = :: ", extracted_content)

        return ExtractionResult(
            content=extracted_content,
            metadata={
                "stage": "law_extraction",
                "source_document": state["law_document"].name,
                "target_articles": state["target_articles"],
                "identified_articles": relevant_articles.article_numbers,
                "extraction_reasoning": relevant_articles.extraction_reasoning,
            },
        )

    def _identify_relevant_articles(self, state: GraphState) -> RelevantArticles:
        """LLMを使用して関連条文番号を特定"""
        logger.info("LLMによる関連条文番号の特定を開始")

        # プロンプトテンプレートを読み込み
        base_context = flatten_state(state)
        special_context = {
            "law_name": state["law_document"].name,
            "law_article": ", ".join(state["target_articles"]),
            "law_text": state["law_document"].content,
        }

        formatted_prompt = self.prompt_manager.render_prompt(
            self.prompt_name,
            context={**base_context, **special_context},
        )

        # Structured outputでLLMを呼び出し
        messages = self._create_messages(formatted_prompt)

        # LLMをstructured outputモードに設定
        structured_llm = self.llm.with_structured_output(RelevantArticles)
        response = structured_llm.invoke(messages)

        logger.info(f"特定された関連条文: {response.article_numbers}")
        return response

    def _extract_articles_from_yaml(
        self, law_document: "LegalDocument", article_numbers: List[int]
    ) -> str:
        """YAML構造から指定された条文を抽出"""
        logger.info(f"YAML構造から{len(article_numbers)}件の条文を抽出中")

        # LegalDocumentからYAMLデータを取得
        # 注意: LegalDocumentクラスにyaml_dataフィールドが必要
        if not hasattr(law_document, "yaml_data") or law_document.yaml_data is None:
            logger.error("法令文書にYAMLデータが含まれていません")
            return "エラー: YAML構造データが利用できません"

        # YAML抽出器を初期化
        extractor = YamlArticleExtractor(law_document.yaml_data)

        # 指定された条文を抽出
        extracted_articles = extractor.extract_articles_by_numbers(article_numbers)

        # 抽出結果をテキストにフォーマット
        return self._format_extracted_articles(extracted_articles)

    def _format_extracted_articles(
        self, extracted_articles: List[ExtractedArticleContent]
    ) -> str:
        """抽出された条文をテキスト形式でフォーマット"""
        formatted_parts = [" 法令本文：抽出された関連条項"]

        for article in extracted_articles:
            if article.found:
                formatted_parts.append(f"\n{article.full_content}\n")
            else:
                formatted_parts.append(f"\n【注意】{article.full_content}\n")

        return "\n".join(formatted_parts)


# 使用例とテスト
def test_law_extractor():
    """LawExtractorのテスト用関数"""
    from unittest.mock import Mock

    # サンプルYAMLデータ
    sample_yaml_data = {
        "law_info": {"title": "土壌汚染対策法", "law_num": "平成14年法律第53号"},
        "articles": [
            {
                "article_num": 3,
                "title": "土壌汚染状況調査",
                "paragraphs": [
                    {
                        "paragraph_num": "1",
                        "content": "都道府県知事は、有害物質使用特定施設の使用が廃止されたときは、当該有害物質使用特定施設に係る工場又は事業場の敷地であった土地について、土壌汚染状況調査を行わせるものとする。",
                        "items": [
                            {
                                "item_num": 1,
                                "title": "一",
                                "content": "有害物質使用特定施設において製造、使用又は処理されていた物質",
                            }
                        ],
                    }
                ],
            },
            {
                "article_num": 4,
                "title": "調査命令",
                "paragraphs": [
                    {
                        "paragraph_num": "1",
                        "content": "都道府県知事は、土壌汚染により人の健康に係る被害が生ずるおそれがあるものとして環境省令で定める基準に該当する土地があると認めるときは、当該土地の所有者等に対し、土壌汚染状況調査を行うべきことを命ずることができる。",
                    }
                ],
            },
        ],
    }

    # LegalDocumentを作成
    law_document = LegalDocument(
        name="土壌汚染対策法",
        content="法令の本文テキスト...",
        document_type="law",
        yaml_data=sample_yaml_data,
    )

    # YamlArticleExtractorの動作テスト
    extractor = YamlArticleExtractor(sample_yaml_data)
    extracted = extractor.extract_articles_by_numbers([3, 4])

    print("=== 条文抽出テスト結果 ===")
    for article in extracted:
        print(f"\n【第{article.article_num}条】")
        print(f"タイトル: {article.title}")
        print(f"見つかった: {article.found}")
        print(f"内容:\n{article.full_content}")


class RegulationExtractor(BaseExtractor):
    """施行規則からの関連条文抽出（更新版）"""

    def extract(self, state: GraphState) -> ExtractionResult:
        """施行規則から関連条文を抽出（2段階方式）"""
        logger.info("施行規則からの関連条文抽出を開始")

        # ステップ1: LLMで関連条文番号を特定
        relevant_articles = self._identify_relevant_articles(state)

        # ステップ2: YAML構造から該当条文を抽出
        extracted_content = self._extract_articles_from_yaml(
            state["regulation_document"], relevant_articles.article_numbers
        )

        return ExtractionResult(
            content=extracted_content,
            metadata={
                "stage": "regulation_extraction",
                "source_document": state["regulation_document"].name,
                "law_reference": state["law_document"].name,
                "identified_articles": relevant_articles.article_numbers,
                "extraction_reasoning": relevant_articles.extraction_reasoning,
            },
        )

    def _identify_relevant_articles(self, state: GraphState) -> RelevantArticles:
        """LLMを使用して関連条文番号を特定"""
        logger.info("LLMによる施行規則の関連条文番号の特定を開始")

        # プロンプトテンプレートを読み込み
        base_context = flatten_state(state)
        special_context = {
            "law_name": state["law_document"].name,
            "extracted_law_content": state["extracted_law_content"],
            "regulation_text": state["regulation_document"].content,
        }
        formatted_prompt = self.prompt_manager.render_prompt(
            self.prompt_name,
            context={**base_context, **special_context},
        )

        # Structured outputでLLMを呼び出し
        messages = self._create_messages(formatted_prompt)

        # LLMをstructured outputモードに設定
        structured_llm = self.llm.with_structured_output(RelevantArticles)
        response = structured_llm.invoke(messages)

        logger.info(f"特定された関連条文: {response.article_numbers}")
        return response

    def _extract_articles_from_yaml(
        self, regulation_document: "LegalDocument", article_numbers: List[int]
    ) -> str:
        """YAML構造から指定された条文を抽出"""
        logger.info(f"施行規則のYAML構造から{len(article_numbers)}件の条文を抽出中")

        # LegalDocumentからYAMLデータを取得
        if (
            not hasattr(regulation_document, "yaml_data")
            or regulation_document.yaml_data is None
        ):
            logger.error("施行規則文書にYAMLデータが含まれていません")
            return "エラー: YAML構造データが利用できません"

        # YAML抽出器を初期化
        extractor = YamlArticleExtractor(regulation_document.yaml_data)

        # 指定された条文を抽出
        extracted_articles = extractor.extract_articles_by_numbers(article_numbers)

        # 抽出結果をテキストにフォーマット
        return self._format_extracted_articles(extracted_articles)

    def _format_extracted_articles(
        self, extracted_articles: List[ExtractedArticleContent]
    ) -> str:
        """抽出された条文をテキスト形式でフォーマット"""
        formatted_parts = [" 施行規則：抽出された関連条項"]

        for article in extracted_articles:
            if article.found:
                formatted_parts.append(f"\n{article.full_content}\n")
            else:
                formatted_parts.append(f"\n【注意】{article.full_content}\n")

        return "\n".join(formatted_parts)


class GraphBuilder:
    """法令要点抽出のグラフビルダー(yaml対応版)"""

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
            state["extracted_law_article_numbers"] = result.metadata[
                "identified_articles"
            ]
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
            state["extracted_regulation_article_numbers"] = result.metadata[
                "identified_articles"
            ]
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
            extracted_law_article_numbers=None,
            extracted_regulation_content=None,
            extracted_regulation_article_numbers=None,
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
