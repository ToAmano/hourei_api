import pytest
from unittest.mock import MagicMock, Mock
from pathlib import Path

from elaws_parser.extraction.law_extraction import (
    LegalDocument as LegalDocumentV1,
    ProcessingStage as ProcessingStageV1,
    GraphBuilder as GraphBuilderV1,
    ViewPointResult,
)
from elaws_parser.extraction.law_extraction_v2 import (
    YamlArticleExtractor,
    GraphBuilder as GraphBuilderV2,
    RelevantArticles,
    ExtractedArticleContent,
)


# ==========================================
# 1. YamlArticleExtractor の単体テスト
# ==========================================

def test_yaml_article_extractor_chapters():
    """chapter構造のYAMLから条文が正しく抽出されること"""
    sample_yaml = {
        "chapters": [
            {
                "chapter_num": "1",
                "title": "総則",
                "articles": [
                    {
                        "article_num": "1",
                        "title": "目的",
                        "paragraphs": [
                            {
                                "paragraph_num": "1",
                                "content": "この法律は目的について規定する。",
                            }
                        ],
                    }
                ],
            },
            {
                "chapter_num": "2",
                "title": "本則",
                "sections": [
                    {
                        "section_num": "1",
                        "title": "第一節",
                        "articles": [
                            {
                                "article_num": "2",
                                "title": "定義",
                                "paragraphs": [
                                    {
                                        "paragraph_num": "1",
                                        "content": "この法律における定義は以下の通り。",
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        ]
    }

    extractor = YamlArticleExtractor(sample_yaml)
    results = extractor.extract_articles_by_numbers(["1", "2", "3"])

    assert len(results) == 3
    
    # 第1条
    assert results[0].article_num == "1"
    assert results[0].title == "目的"
    assert results[0].found is True
    assert "目的" in results[0].full_content
    assert "この法律は目的について規定する。" in results[0].full_content

    # 第2条
    assert results[1].article_num == "2"
    assert results[1].title == "定義"
    assert results[1].found is True
    assert "定義" in results[1].full_content

    # 第3条 (存在しない)
    assert results[2].article_num == "3"
    assert results[2].found is False
    assert "取得できませんでした" in results[2].full_content


def test_yaml_article_extractor_articles():
    """articles（章節のないフラットな構造）のYAMLから条文が正しく抽出されること"""
    sample_yaml = {
        "articles": [
            {
                "article_num": "10",
                "title": "雑則",
                "paragraphs": [
                    {
                        "paragraph_num": "1",
                        "content": "雑則の内容。",
                        "items": [
                            {
                                "item_num": 1,
                                "title": "一",
                                "content": "第一号の細目",
                            }
                        ],
                    }
                ],
            }
        ]
    }

    extractor = YamlArticleExtractor(sample_yaml)
    results = extractor.extract_articles_by_numbers(["10"])

    assert len(results) == 1
    assert results[0].article_num == "10"
    assert results[0].found is True
    assert "雑則" in results[0].full_content
    assert "第一号の細目" in results[0].full_content


# ==========================================
# 2. GraphBuilder V2 (YAML対応版) のテスト
# ==========================================

def test_graph_builder_v2_success(tmp_path):
    """YAML対応版GraphBuilderの正常系テスト。
    LLMが適切な structured output を返し、全ノードを通って完了すること。
    """
    # モックLLMの設定
    mock_llm = MagicMock()
    
    # structured_llmのモックを作成
    mock_structured_llm_articles = MagicMock()
    # LawExtractorとRegulationExtractor用の関連条文モックレスポンス
    mock_structured_llm_articles.invoke.side_effect = [
        RelevantArticles(article_numbers=["1"], extraction_reasoning="Reason for Law"),
        RelevantArticles(article_numbers=["2"], extraction_reasoning="Reason for Reg"),
    ]
    
    mock_structured_llm_summary = MagicMock()
    # ViewpointGenerator用のサマリーモックレスポンス
    mock_structured_llm_summary.invoke.return_value = ViewPointResult(
        viewpoint="テストの最終判断軸",
        annotation="テストの注釈"
    )
    
    # schemaタイプに応じて異なるモックを返す
    def with_structured_output_mock(schema):
        if schema == RelevantArticles:
            return mock_structured_llm_articles
        elif schema == ViewPointResult:
            return mock_structured_llm_summary
        return MagicMock()
        
    mock_llm.with_structured_output.side_effect = with_structured_output_mock

    # ダミーのプロンプトファイルを準備
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    
    # プロンプトファイルを配置
    for prompt_name in ["extract_laws_v001", "extract_regulation_v001", "v003"]:
        prompt_file = prompts_dir / f"{prompt_name}.yaml"
        prompt_file.write_text("""
template: "This is a prompt template with {law_name}."
input_variables:
  - law_name
""", encoding="utf-8")

    # システムの初期化
    builder = GraphBuilderV2(llm=mock_llm, prompts_dir=prompts_dir)
    
    # テスト用ドキュメント（YAMLデータ含む）
    law_doc = LegalDocumentV1(
        name="テスト法",
        content="テスト法の全文内容",
        document_type="law",
        yaml_data={
            "articles": [
                {
                    "article_num": "1",
                    "title": "第1条",
                    "paragraphs": [{"paragraph_num": "1", "content": "第1条の内容"}],
                }
            ]
        }
    )
    
    reg_doc = LegalDocumentV1(
        name="テスト法施行規則",
        content="テスト法施行規則の全文内容",
        document_type="regulation",
        yaml_data={
            "articles": [
                {
                    "article_num": "2",
                    "title": "第2条",
                    "paragraphs": [{"paragraph_num": "1", "content": "第2条の内容"}],
                }
            ]
        }
    )

    # 実行
    result = builder.process(
        law_document=law_doc,
        regulation_document=reg_doc,
        target_articles=["1"]
    )

    # アサーション
    assert result["error_message"] is None
    assert result["current_stage"] == ProcessingStageV1.COMPLETED
    assert result["extracted_law_content"] is not None
    assert "第1条の内容" in result["extracted_law_content"]
    assert result["extracted_regulation_content"] is not None
    assert "第2条の内容" in result["extracted_regulation_content"]
    
    # 最終的な要点
    assert result["final_summary"] is not None
    assert result["final_summary"].viewpoint == "テストの最終判断軸"
    assert result["final_summary"].annotation == "テストの注釈"
    
    # LLMの呼び出し回数の確認
    assert mock_llm.with_structured_output.call_count == 3


def test_graph_builder_v2_error_handling(tmp_path):
    """YAML対応版GraphBuilderの異常系（エラーハンドリング）テスト。
    途中でLLMが例外を投げた場合に、エラーメッセージがキャッチされ正常終了すること。
    """
    mock_llm = MagicMock()
    # 最初のLLM呼び出しでエラーを発生させる
    mock_llm.with_structured_output.side_effect = Exception("LLM connection failed")

    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    
    for prompt_name in ["extract_laws_v001", "extract_regulation_v001", "v003"]:
        prompt_file = prompts_dir / f"{prompt_name}.yaml"
        prompt_file.write_text("template: \"foo\"\ninput_variables: []", encoding="utf-8")

    builder = GraphBuilderV2(llm=mock_llm, prompts_dir=prompts_dir)
    
    law_doc = LegalDocumentV1(
        name="テスト法",
        content="テスト法の内容",
        document_type="law",
        yaml_data={"articles": []}
    )
    reg_doc = LegalDocumentV1(
        name="テスト法施行規則",
        content="テスト法施行規則の内容",
        document_type="regulation",
        yaml_data={"articles": []}
    )

    # 実行
    result = builder.process(
        law_document=law_doc,
        regulation_document=reg_doc,
        target_articles=["1"]
    )

    # アサーション：エラーメッセージが記録され、COMPLETEDステージに到達していること
    assert result["error_message"] is not None
    assert "法令抽出エラー" in result["error_message"]
    assert result["current_stage"] == ProcessingStageV1.COMPLETED
    assert result["final_summary"] is None


# ==========================================
# 3. GraphBuilder V1 (非YAML/テキスト版) のテスト
# ==========================================

def test_graph_builder_v1_success(tmp_path):
    """非YAML版GraphBuilderの正常系テスト。"""
    mock_llm = MagicMock()
    
    # invoke() は V1の LawExtractor と RegulationExtractor で呼び出される
    mock_response_law = Mock()
    mock_response_law.content = "抽出された法律のテキスト本文"
    
    mock_response_reg = Mock()
    mock_response_reg.content = "抽出された規則のテキスト本文"
    
    mock_llm.invoke.side_effect = [mock_response_law, mock_response_reg]
    
    # with_structured_output() は V1の ViewpointGenerator で呼び出される
    mock_structured_llm = MagicMock()
    mock_structured_llm.invoke.return_value = ViewPointResult(
        viewpoint="非YAML版の最終判断軸",
        annotation="非YAML版の注釈"
    )
    mock_llm.with_structured_output.return_value = mock_structured_llm

    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    
    # V1用のプロンプトファイルを配置 (プレースホルダに注意)
    prompt_templates = {
        "extract_laws_v001": "template: \"{law_name} {law_article} {law_text}\"\ninput_variables:\n  - law_name\n  - law_article\n  - law_text",
        "extract_regulation_v001": "template: \"{law_name} {extracted_law_content} {regulation_text}\"\ninput_variables:\n  - law_name\n  - extracted_law_content\n  - regulation_text",
        "v003": "template: \"{law_name}\"\ninput_variables:\n  - law_name",
    }
    
    for prompt_name, content in prompt_templates.items():
        prompt_file = prompts_dir / f"{prompt_name}.yaml"
        prompt_file.write_text(content, encoding="utf-8")

    # システムの初期化
    builder = GraphBuilderV1(llm=mock_llm, prompts_dir=prompts_dir)
    
    law_doc = LegalDocumentV1(
        name="テスト法",
        content="テスト法の全文テキスト",
        document_type="law"
    )
    reg_doc = LegalDocumentV1(
        name="テスト法施行規則",
        content="テスト法施行規則の全文テキスト",
        document_type="regulation"
    )

    # 実行
    result = builder.process(
        law_document=law_doc,
        regulation_document=reg_doc,
        target_articles=["1"]
    )

    # アサーション
    assert result["error_message"] is None
    assert result["current_stage"] == ProcessingStageV1.COMPLETED
    assert result["extracted_law_content"] == "抽出された法律のテキスト本文"
    assert result["extracted_regulation_content"] == "抽出された規則のテキスト本文"
    
    assert result["final_summary"] is not None
    assert result["final_summary"].viewpoint == "非YAML版の最終判断軸"
    assert result["final_summary"].annotation == "非YAML版の注釈"
