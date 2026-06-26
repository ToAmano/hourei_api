# e-Gov法令API v2 ラッパー & 構造化コンバーター (`hourei_api`)

このリポジトリは、[e-Gov法令検索](https://elaws.e-gov.go.jp/)の[法令API v2](https://developer.e-gov.go.jp/contents/law_api_v2_2)を利用して法令データを取得し、人間や機械が扱いやすいテキスト形式およびYAML形式に変換・抽出するためのPythonパッケージです。

---

## 主な機能

- **法令データの取得**: 法令タイトルをキーに、e-Gov法令API v2から法令のXMLデータを直接取得します。
- **XMLからテキストへの変換**: 取得した法令XMLを、読みやすいプレーンテキスト形式に構造を保ったまま変換します。
- **XMLからYAMLへの変換**: 法令XMLを、構造が分かりやすいYAML形式に変換します。プログラムでのパースや分析が容易になります。
- **LLM/LangGraphによる条文抽出**: LangGraphと大規模言語モデル（LLM）を活用して、特定の法令や施行規則から関連する条項を抽出し、要約・比較分析を行います。

---

## ディレクトリ構成

```
.
├── pyproject.toml          # パッケージのビルド・設定ファイル (setuptools)
├── requirements.txt        # 基本依存ライブラリ
├── src/
│   └── hourei_api/         # パッケージソース
│       ├── __init__.py     # パッケージエントリーポイント（公開API定義）
│       ├── hourei_apiv2.py # e-Gov法令API v2 クライアント
│       ├── text_converter.py # XMLからTextへの変換ロジック
│       ├── yaml_converter.py # XMLからYAMLへの変換ロジック
│       ├── law_extraction.py # LLMを用いた法令抽出（基本機能）
│       └── law_extraction_v2.py # LLMを用いた法令抽出（YAML構造・LangGraph版）
├── notebooks/
│   └── examples/           # パッケージの動作確認・検証用 Jupyter Notebook群
└── data/                   # 検証用に取得・生成された法令データ（xml, yaml, txt 等）
```

---

## セットアップ

### 1. リポジトリのクローン
```bash
git clone <repository_url>
cd <repository_name>
```

### 2. パッケージのインストール
本パッケージは、用途に合わせてインストールオプションを選択できます。

#### 基本機能（API取得・Text/YAML変換）のみを使用する場合:
```bash
pip install -e .
```

#### LLM/LangGraphを用いた抽出・要約機能も使用する場合:
```bash
pip install -e .[llm]
```

---

## 使用方法

### 1. 法令データの取得と変換（基本機能）
法令名（例：「電気事業法」）を指定して、XMLデータを取得し、テキスト形式とYAML形式で保存する基本的な例です。

```python
from hourei_api import (
    get_lawid_from_lawtitle,
    get_lawdata_from_law_id,
    get_lawdata_from_lawname,
    save_xml_string_to_file,
    convert_xml_to_text,
    convert_xml_to_yaml,
)

# 1. 法令名から直接法令のXMLデータを取得
law_title = "電気事業法"
xml_string = get_lawdata_from_lawname(law_title)

# 2. XMLをファイルに保存
save_xml_string_to_file(xml_string, f"data/{law_title}.xml")

# 3. Text形式に変換して保存
text_content = convert_xml_to_text(xml_string)
with open(f"data/{law_title}.txt", "w", encoding="utf-8") as f:
    f.write(text_content)

# 4. YAML形式に変換して保存
yaml_content = convert_xml_to_yaml(xml_string)
with open(f"data/{law_title}.yaml", "w", encoding="utf-8") as f:
    f.write(yaml_content)
```

### 2. LLMを用いた関連条文の抽出・要約
LLMおよびLangGraphを用いた高度な抽出機能のサンプルです（要 `pip install -e .[llm]`）。

```python
from langchain_openai import ChatOpenAI
from hourei_api import LegalExtractionConfig, create_legal_extraction_system

# LLMと設定の初期化
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.1)
config = LegalExtractionConfig(llm=llm, prompts_dir="prompts")
system = create_legal_extraction_system(config)

# ※具体的な実行方法は notebooks/examples/ のノートブックを参照してください。
```

### 3. Jupyter Notebookによる実例
より具体的な使用方法や動作テストの例については、`notebooks/examples/` ディレクトリ配下にある各種ノートブックを参照してください。

- **[examples01_hourei_xml_converter.ipynb](notebooks/examples/examples01_hourei_xml_converter.ipynb)**: 基本的な変換機能の実例
- **[test_houreiapiv2.ipynb](notebooks/examples/test_houreiapiv2.ipynb)**: APIラッパーのテスト
- **[test_law_extraction_v2.ipynb](notebooks/examples/test_law_extraction_v2.ipynb)**: LangGraphを用いた条文抽出機能の実例

---

## 参考文献

- [e-Gov法令検索 法令API v2 仕様書 (Swagger UI)](https://laws.e-gov.go.jp/api/2/swagger-ui)
