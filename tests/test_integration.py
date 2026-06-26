import pytest
import requests
import yaml
from elaws_parser.api.hourei_apiv2 import (
    get_lawdata_from_law_id,
    get_lawid_from_lawtitle,
)
from elaws_parser.parser.text_converter import convert_xml_to_text
from elaws_parser.parser.yaml_converter import convert_xml_to_yaml


def test_api_to_parser_integration():
    """e-Gov法令APIから実際にデータを取得し、

    テキストおよびYAML形式へのパースが正常に完了することを確認する結合テスト。
    一時的なネットワークエラーやAPI側の制限等がある場合は、テスト失敗ではなくスキップする。
    """
    law_title = "大気汚染防止法"

    # 1. APIから法令IDを取得
    try:
        law_id = get_lawid_from_lawtitle(law_title, if_exact=True)
    except requests.exceptions.RequestException as e:
        pytest.skip(f"API connection failed during ID retrieval: {e}")

    assert isinstance(law_id, str)
    assert len(law_id) > 0

    # 2. 法令IDからXMLデータを取得
    try:
        raw_xml = get_lawdata_from_law_id(law_id, "xml")
    except requests.exceptions.RequestException as e:
        pytest.skip(f"API connection failed during XML retrieval: {e}")

    assert raw_xml is not None
    assert "<LawData>" in raw_xml or "<law_data_response>" in raw_xml

    # 3. テキストへのパースと検証
    actual_text = convert_xml_to_text(raw_xml)
    assert isinstance(actual_text, str)
    assert len(actual_text) > 100

    # 4. YAMLへのパースと検証
    actual_yaml_str = convert_xml_to_yaml(raw_xml)
    assert isinstance(actual_yaml_str, str)

    actual_yaml_data = yaml.safe_load(actual_yaml_str)
    assert isinstance(actual_yaml_data, dict)

    # メタデータの確認
    assert "law_info" in actual_yaml_data
    assert actual_yaml_data["law_info"].get("title") == "大気汚染防止法"

    # 本則部分（chapters または articles）が含まれることを確認
    assert "chapters" in actual_yaml_data or "articles" in actual_yaml_data
