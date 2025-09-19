# eGov法令API v2 ラッパー & 構造化コンバーター

このリポジトリは、[e-Gov法令検索](https://elaws.e-gov.go.jp/)の[法令API v2](https://developer.e-gov.go.jp/contents/law_api_v2_2)を利用して法令データを取得し、人間や機械が扱いやすいテキスト形式およびYAML形式に変換するためのPythonツール群です。


## 主な機能

- **法令データの取得**: 法令タイトルをキーに、eGov法令API v2から法令のXMLデータを取得します。(`hourei_apiv2.py`)
- **XMLからTextへの変換**: 取得した法令XMLを、読みやすいプレーンテキスト形式に変換します。(`text_converter.py`)
- **XMLからYAMLへの変換**: 法令XMLを、構造が分かりやすいYAML形式に変換します。これにより、プログラムでのデータ処理が容易になります。(`yaml_converter.py`)

## ディレクトリ構成

```
.
├── hourei_apiv2.py         # eGov法令API v2クライアント
├── text_converter.py       # XMLからTextへのコンバーター
├── yaml_converter.py       # XMLからYAMLへのコンバーター
├── requirements.txt        # 依存ライブラリ
```

## セットアップ

1. **リポジトリのクローン**
   ```bash
   git clone <repository_url>
   cd <repository_name>
   ```

2. **依存ライブラリのインストール**
   最小限の依存関係は`requirements.txt`に記載されています。
   ```bash
   pip install -r requirements.txt
   ```


## 使用方法

### 1. 法令データの取得と変換

法令名（例：「電気事業法」）を指定して、XMLデータを取得し、テキスト形式とYAML形式で保存する基本的な使用例です。

```python
from hourei_apiv2 import get_lawid_from_lawtitle, get_lawdata_from_law_id, save_xml_string_to_file, get_lawdata_from_lawname
from text_converter import convert_xml_to_text
from yaml_converter import convert_xml_to_yaml

# 法令名
law_title = "電気事業法"

# 法令名から法令IDを取得
law_id = get_lawid_from_lawtitle(law_title)

# 法令IDを使って法令のXMLデータを取得
xml_string = get_lawdata_from_law_id(law_id, output_type="xml")

# または，法令名から直接法令のXMLデータを取得
xml_string = get_lawdata_from_lawname(law_title)

# XMLをファイルに保存
xml_filename = f"{law_title}.xml"
save_xml_string_to_file(xml_string, xml_filename)
print(f"'{xml_filename}' を保存しました。")

# Text形式に変換して保存
text_content = convert_xml_to_text(xml_string)
text_filename = f"{law_title}.txt"
with open(text_filename, "w", encoding="utf-8") as f:
    f.write(text_content)
print(f"'{text_filename}' を保存しました。")

# YAML形式に変換して保存
yaml_content = convert_xml_to_yaml(xml_string)
yaml_filename = f"{law_title}.yaml"
with open(yaml_filename, "w", encoding="utf-8") as f:
    f.write(yaml_content)
print(f"'{yaml_filename}' を保存しました。")
```

## 参考文献

- https://laws.e-gov.go.jp/api/2/swagger-ui
