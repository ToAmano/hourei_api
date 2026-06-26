import glob
import os
import pytest
import yaml
from elaws_parser.parser.text_converter import convert_xml_to_text
from elaws_parser.parser.yaml_converter import convert_xml_to_yaml

# データディレクトリの特定
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")


def get_test_laws():
    """data/ ディレクトリ内の .xml ファイルを探し、

    対応する .txt や .yaml が揃っているものをテストケースとする。
    ただし、テスト実行時間短縮のため、巨大なファイルは除外する。
    """
    laws = []
    xml_files = glob.glob(os.path.join(DATA_DIR, "*.xml"))
    for xml_path in xml_files:
        base = os.path.splitext(xml_path)[0]
        # 除外するファイル（特殊なテンポラリなど）
        filename = os.path.basename(xml_path)
        if filename == "law.xml":
            continue
        # 巨大すぎるファイルをテストから除外する（租税特別措置法は14MBあり処理が遅いため）
        if "租税特別措置法" in filename:
            continue

        txt_path = base + ".txt"
        yaml_path = base + ".yaml"

        if os.path.exists(txt_path) and os.path.exists(yaml_path):
            laws.append((xml_path, txt_path, yaml_path))
    return laws


def normalize_val(val):
    """辞書やリストの中の数値をすべて文字列に正規化する。

    これにより、型（"77" と 77）の不一致による比較失敗を防ぐ。
    """
    if isinstance(val, dict):
        return {k: normalize_val(v) for k, v in val.items()}
    elif isinstance(val, list):
        return [normalize_val(x) for x in val]
    elif isinstance(val, (int, float)):
        return str(val)
    elif isinstance(val, str):
        return val.strip()
    return val


@pytest.mark.parametrize("xml_path, txt_path, yaml_path", get_test_laws())
def test_law_parsing_snapshot(xml_path, txt_path, yaml_path):
    # XMLを読み込み
    with open(xml_path, "r", encoding="utf-8") as f:
        xml_data = f.read()

    # 部分的XML（MainProvisionなど）の場合はダミー構造でラップする
    if not ("<law_full_text>" in xml_data or "<LawData>" in xml_data):
        xml_data = f"""<?xml version="1.0" encoding="UTF-8"?>
<LawData>
    <law_full_text>
        <Law>
            <LawBody>
                {xml_data}
            </LawBody>
        </Law>
    </law_full_text>
</LawData>
"""

    # 1. テキスト変換のテスト
    with open(txt_path, "r", encoding="utf-8") as f:
        expected_text = f.read().replace("\r\n", "\n").strip()

    actual_text = convert_xml_to_text(xml_data).replace("\r\n", "\n").strip()
    assert (
        actual_text == expected_text
    ), f"Text mismatch for {os.path.basename(xml_path)}"

    # 2. YAML変換のテスト
    with open(yaml_path, "r", encoding="utf-8") as f:
        expected_yaml_str = f.read()
        expected_yaml_data = yaml.safe_load(expected_yaml_str)

    actual_yaml_str = convert_xml_to_yaml(xml_data)
    actual_yaml_data = yaml.safe_load(actual_yaml_str)

    # 比較データを正規化して完全一致を確認
    norm_actual = normalize_val(actual_yaml_data)
    norm_expected = normalize_val(expected_yaml_data)

    assert (
        norm_actual == norm_expected
    ), f"YAML mismatch for {os.path.basename(xml_path)}"
