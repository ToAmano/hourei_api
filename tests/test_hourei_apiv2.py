import os
from unittest.mock import Mock, patch
import pytest
from elaws_parser.api.hourei_apiv2 import (
    extract_sections_from_xml,
    get_lawdata_from_law_id,
    get_lawdata_from_lawname,
    get_lawid_from_lawtitle,
    save_xml_string_to_file,
)


def test_get_lawid_from_lawtitle_exact_match():
    # ダミーのXMLレスポンス
    mock_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <response>
        <laws>
            <law>
                <law_info>
                    <law_id>12345</law_id>
                    <law_num>平成五年法律第百号</law_num>
                </law_info>
                <revision_info>
                    <law_title>環境基本法</law_title>
                </revision_info>
            </law>
        </laws>
    </response>
    """

    with patch("requests.get") as mock_get:
        mock_response = Mock()
        mock_response.content = mock_xml.encode("utf-8")
        mock_get.return_value = mock_response

        # テスト実行
        result = get_lawid_from_lawtitle("環境基本法", if_exact=True)

        assert result == "12345"
        mock_get.assert_called_once_with(
            "https://laws.e-gov.go.jp/api/2/laws",
            params={"response_format": "xml", "law_title": "環境基本法"},
        )


def test_get_lawid_from_lawtitle_all_matches():
    mock_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <response>
        <laws>
            <law>
                <law_info>
                    <law_id>12345</law_id>
                    <law_num>平成五年法律第百号</law_num>
                </law_info>
                <revision_info>
                    <law_title>環境基本法</law_title>
                </revision_info>
            </law>
        </laws>
    </response>
    """

    with patch("requests.get") as mock_get:
        mock_response = Mock()
        mock_response.content = mock_xml.encode("utf-8")
        mock_get.return_value = mock_response

        # テスト実行（完全一致フラグをFalseに）
        result = get_lawid_from_lawtitle("環境基本法", if_exact=False)

        assert isinstance(result, dict)
        assert result == {"環境基本法": "12345"}


def test_get_lawdata_from_law_id_xml():
    mock_xml_content = "<LawData><LawNum>123</LawNum></LawData>"

    with patch("requests.get") as mock_get:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = mock_xml_content.encode("utf-8")
        mock_get.return_value = mock_response

        result = get_lawdata_from_law_id("12345", "xml")
        assert result == mock_xml_content


def test_get_lawdata_from_law_id_list():
    mock_xml_content = (
        "<LawData><LawNum>123</LawNum><LawTitle>環境基本法</LawTitle></LawData>"
    )

    with patch("requests.get") as mock_get:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = mock_xml_content.encode("utf-8")
        mock_get.return_value = mock_response

        result = get_lawdata_from_law_id("12345", "list")
        assert result == ["123", "環境基本法"]


def test_get_lawdata_from_law_id_failure():
    with patch("requests.get") as mock_get:
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        result = get_lawdata_from_law_id("invalid_id", "xml")
        assert result is None


def test_get_lawdata_from_law_id_invalid_type():
    with patch("requests.get") as mock_get:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"<dummy/>"
        mock_get.return_value = mock_response

        with pytest.raises(ValueError, match="Supported output type is xml or list"):
            get_lawdata_from_law_id("12345", "invalid_type")  # type: ignore



def test_get_lawdata_from_lawname():
    with patch(
        "elaws_parser.api.hourei_apiv2.get_lawid_from_lawtitle"
    ) as mock_get_id, patch(
        "elaws_parser.api.hourei_apiv2.get_lawdata_from_law_id"
    ) as mock_get_data:

        mock_get_id.return_value = "12345"
        mock_get_data.return_value = "<dummy_xml/>"

        result = get_lawdata_from_lawname("環境基本法")
        assert result == "<dummy_xml/>"
        mock_get_id.assert_called_once_with("環境基本法", if_exact=True)
        mock_get_data.assert_called_once_with("12345", "xml")


def test_save_xml_string_to_file(tmp_path):
    d = tmp_path / "sub"
    d.mkdir()
    file_path = d / "test.xml"

    xml_content = "<test>data</test>"
    save_xml_string_to_file(xml_content, str(file_path))

    assert file_path.read_text(encoding="utf-8") == xml_content


def test_extract_sections_from_xml_success():
    xml_data = """<?xml version="1.0" encoding="UTF-8"?>
    <LawData>
        <law_full_text>
            <Law Era="Reiwa" Year="1">
                <LawBody>
                    <TOC><ChapterTitle>第1章</ChapterTitle></TOC>
                    <MainProvision><Paragraph>本文</Paragraph></MainProvision>
                    <SupplProvision><Paragraph>附則</Paragraph></SupplProvision>
                    <SupplProvision><Paragraph>附則2</Paragraph></SupplProvision>
                </LawBody>
            </Law>
        </law_full_text>
    </LawData>
    """

    result = extract_sections_from_xml(xml_data)

    assert result["TOC"] is not None
    assert "<ChapterTitle>第1章</ChapterTitle>" in result["TOC"]

    assert result["MainProvision"] is not None
    assert "<Paragraph>本文</Paragraph>" in result["MainProvision"]

    assert isinstance(result["SupplProvision"], list)
    assert len(result["SupplProvision"]) == 2
    assert "<Paragraph>附則</Paragraph>" in result["SupplProvision"][0]
    assert "<Paragraph>附則2</Paragraph>" in result["SupplProvision"][1]


def test_extract_sections_from_xml_missing_elements():
    invalid_xml = "<invalid></invalid>"
    with pytest.raises(ValueError, match="law_full_textタグが見つかりません"):
        extract_sections_from_xml(invalid_xml)

    invalid_xml2 = "<LawData><law_full_text></law_full_text></LawData>"
    with pytest.raises(ValueError, match="<Law> タグが <law_full_text> 内に見つかりません"):
        extract_sections_from_xml(invalid_xml2)

    invalid_xml3 = "<LawData><law_full_text><Law></Law></law_full_text></LawData>"
    with pytest.raises(ValueError, match="<LawBody> タグが <Law> 内に見つかりません"):
        extract_sections_from_xml(invalid_xml3)
