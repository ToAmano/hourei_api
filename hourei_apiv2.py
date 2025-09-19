"""
eGovのAPI v2を利用して，法令を取得するコード
"""

# TODO :: APIのラッパーと，xmlのパーサーの二つでファイルを分割する
# TODO :: パーサーは，textのパーサーとyamlのパーサー

from abc import ABC, abstractmethod
from functools import lru_cache
from typing import Dict, List, Literal, Optional, Type
from xml.etree import ElementTree

import requests


@lru_cache
def get_lawid_from_lawtitle(
    law_title: str, *, if_exact: bool = True
) -> str | Dict[str, str]:
    """APIから法令タイトルでヒットする法令IDを取得(完全一致のみ)"""
    url = "https://laws.e-gov.go.jp/api/2/laws"
    r = requests.get(url, params={"response_format": "xml", "law_title": law_title})
    # XMLデータの解析
    root = ElementTree.fromstring(r.content.decode(encoding="utf-8"))

    laws_elem = root.find("laws")
    if laws_elem is None:
        print("Error: 'laws' element not found in response.")
        return {}

    counter = 0
    law_dict = {}  # 辞書{名称: 法令番号}の作成
    for law in laws_elem.findall("law"):  # loop over <law> elements
        counter += 1

        law_info = law.find("law_info")
        revision_info = law.find("revision_info")

        if law_info is None or revision_info is None:
            continue  # skip incomplete entries

        law_id: str = law_info.findtext("law_id", default="(no id)")
        law_num: str = law_info.findtext("law_num", default="(no number)")
        lawtitle: str = revision_info.findtext("law_title", default="(no title)")

        print(f"ID: {law_id}, Num: {law_num}, Title: {lawtitle}")
        law_dict[lawtitle] = law_id
    print(f"Number of laws: {counter}")
    if if_exact:
        return law_dict[law_title]  # allow exact match
    return law_dict  # return all matches


def get_lawdata_from_law_id(law_id: str, output_type: Literal["xml", "list"]):
    """法令IDから法令データを取得"""
    url = f"https://laws.e-gov.go.jp/api/2/law_data/{law_id}"
    r = requests.get(url, params={"response_format": "xml"})
    if r.status_code != 200:
        print(f"Error fetching law data for ID {law_id}: {r.status_code}")
        return None
    if output_type == "xml":
        return r.content.decode(encoding="utf-8")

    if output_type == "list":
        # XMLデータの解析
        root = ElementTree.fromstring(r.content.decode(encoding="utf-8"))
        contents = [e.text.strip() for e in root.iter() if e.text]
        return [t for t in contents if t]
    raise ValueError(f"Supported output type is xml or list. Got {output_type}")


def save_xml_string_to_file(xml_string: str, filename: str):
    """save xml string to txt"""
    with open(filename, "w", encoding="utf-8") as f:
        f.write(xml_string)


def extract_sections_from_xml(xml_string: str) -> Dict[str, str | None | list[str]]:
    """TOC, MainProvision,SupplProvisionの3つを取得"""
    # tree = ElementTree.parse(xml_file_path)
    # root = tree.getroot()
    root = ElementTree.fromstring(xml_string)

    # law_infoタグを取得
    law_full_text = root.find("law_full_text")
    if law_full_text is None:
        raise ValueError("law_full_textタグが見つかりません")

    # <Law> の中にある <LawBody> を探す
    law = law_full_text.find("Law")
    if law is None:
        raise ValueError("<Law> タグが <law_full_text> 内に見つかりません")

    law_body = law.find("LawBody")
    if law_body is None:
        raise ValueError("<LawBody> タグが <Law> 内に見つかりません")

    # 対象の3つのタグを取得
    toc = law_body.find("TOC")
    main_prov = law_body.find("MainProvision")
    suppl_provs = law_body.findall("SupplProvision")

    return {
        "TOC": (
            ElementTree.tostring(toc, encoding="unicode") if toc is not None else None
        ),
        "MainProvision": (
            ElementTree.tostring(main_prov, encoding="unicode")
            if main_prov is not None
            else None
        ),
        # "SupplProvision": (
        #     ElementTree.tostring(suppl_prov, encoding="unicode")
        #     if suppl_prov is not None
        #     else None
        # ),
        "SupplProvision": (
            [ElementTree.tostring(s, encoding="unicode") for s in suppl_provs]
            if suppl_provs
            else None
        ),
    }


def parse_toc_to_text(toc_xml: str | None) -> str:
    """XML文字列をパース"""
    if toc_xml is None:
        return ""

    toc_elem = ElementTree.fromstring(toc_xml)

    # 出力用リスト
    lines = []

    # TOCLabel を追加
    label = toc_elem.find("TOCLabel")
    if label is not None and label.text:
        lines.append(label.text.strip())

    # TOCChapter を順に処理
    for chapter in toc_elem.findall("TOCChapter"):
        title = chapter.find("ChapterTitle")
        article_range = chapter.find("ArticleRange")
        if title is not None and article_range is not None:
            line = f"{title.text.strip()}{article_range.text.strip()}"
            lines.append(line)

    # TOCSupplProvision のラベル（附則）を追加
    suppl = toc_elem.find("TOCSupplProvision")
    if suppl is not None:
        suppl_label = suppl.find("SupplProvisionLabel")
        if suppl_label is not None and suppl_label.text:
            lines.append(suppl_label.text.strip())

    return "\n".join(lines)


class BaseLawParser(ABC):
    """法令XMLパーサーの基底クラス"""

    def __init__(self, xml: str):
        self.root = ElementTree.fromstring(xml)
        self.lines: List[str] = []

    def parse(self) -> str:
        """XMLをテキストに変換する（Template Method）"""
        self._setup()
        self._process_top_level_elements()
        return self._finalize()

    def _setup(self) -> None:
        """初期化処理"""
        self.lines.clear()

    def _finalize(self) -> str:
        """最終処理"""
        return "\n".join(self.lines)

    @abstractmethod
    def _process_top_level_elements(self) -> None:
        """トップレベル要素を処理する（子クラスで実装）"""
        pass

    def _process_section(self, section) -> None:
        """節を処理する"""
        section_title = section.findtext("SectionTitle")
        if section_title:
            self._add_line(section_title)
            self._add_blank_line()

        # Chapter直下の全ての子要素を順番通りに処理
        for child in section:
            if child.tag == "Subsection":
                self._process_subsection(child)
            elif child.tag == "Article":
                self._process_article(child)

    def _process_subsection(self, subsection) -> None:
        """節を処理する"""
        subsection_title = subsection.findtext("SubsectionTitle")
        if subsection_title:
            self._add_line(subsection_title)
            self._add_blank_line()

        for article in subsection.findall("Article"):
            self._process_article(article)

    def _process_article(self, article) -> None:
        """条を処理する"""
        self._add_optional_text(article.findtext("ArticleCaption"))
        self._add_optional_text(article.findtext("ArticleTitle"))

        for paragraph in article.findall("Paragraph"):
            self._process_paragraph(paragraph)

    def _process_paragraph(self, paragraph) -> None:
        """項を処理する"""
        self._add_optional_text(paragraph.findtext("ParagraphNum"))

        # 段落の文を処理(ParagraphSentenceは常に一つのみで存在するためfindallではなくfindを使用)
        paragraph_sentence = paragraph.find("ParagraphSentence")
        if paragraph_sentence is not None:
            self._process_sentences(paragraph_sentence)

        # 項目を処理
        for item in paragraph.findall("Item"):
            self._process_item(item)

        # Tableがあれば処理
        table_struct = paragraph.find("TableStruct")
        if table_struct is not None:
            print("Processing TableStruct in Paragraph")
            self._parse_table_struct(table_struct)

    def _process_item(self, item) -> None:
        """項目を処理する（子クラスでオーバーライド可能）"""
        self._add_optional_text(item.findtext("ItemTitle"))

        item_sentence = item.find("ItemSentence")
        if item_sentence is not None:
            self._process_item_sentence(item_sentence)

        # Tableがあれば処理
        table_struct = item.find("TableStruct")
        if table_struct is not None:
            print("Processing TableStruct in Item")
            self._parse_table_struct(table_struct)

        # Subitem1要素を処理（再帰的にネストされたSubitemも処理）
        for subitem in item.findall("Subitem1"):
            self._process_subitem(subitem)

    def _process_item_sentence(self, item_sentence) -> None:
        """ItemSentenceを処理する（基本実装、子クラスでオーバーライド可能）"""
        self._process_sentences(item_sentence)

    def _process_subitem(self, subitem) -> None:
        """サブ項目を処理する（再帰的にネストされたSubitemを処理）"""
        # Subitemのレベルを動的に判定
        tag_name = subitem.tag
        level = self._extract_subitem_level(tag_name)

        # タイトルを処理
        title_tag = f"{tag_name}Title"
        self._add_optional_text(subitem.findtext(title_tag))
        # print(f"Processing {tag_name} at level {level} with {title_tag}")

        # 文章を処理
        sentence_tag = f"{tag_name}Sentence"
        subitem_sentence = subitem.find(sentence_tag)
        if subitem_sentence is not None:
            self._process_sentences(subitem_sentence)

        # Tableがあれば処理
        table_struct = subitem.find("TableStruct")
        if table_struct is not None:
            print("Processing TableStruct in SubItem")
            self._parse_table_struct(table_struct)

        # 次のレベルのSubitemを再帰的に処理
        next_level = level + 1
        next_subitem_tag = f"Subitem{next_level}"
        for next_subitem in subitem.findall(next_subitem_tag):
            self._process_subitem(next_subitem)

    def _extract_subitem_level(self, tag_name: str) -> int:
        """SubitemタグからレベルNumberを抽出する（例: "Subitem1" → 1）"""
        import re

        match = re.search(r"Subitem(\d+)", tag_name)
        return int(match.group(1)) if match else 1

    def _process_sentences(self, sentence_container) -> None:
        """文のコンテナを処理する"""
        for sentence in sentence_container.findall(".//Sentence"):
            sentence_text = self._extract_sentence_text(sentence)
            if sentence_text:
                self._add_line(sentence_text)

    def _extract_sentence_text(self, sentence) -> str:
        """文要素からテキストを抽出（ルビ対応）"""

        def process_element(elem):
            """要素を再帰的に処理してテキストを抽出"""
            text_parts = []

            # 要素のテキスト（開始タグ直後のテキスト）
            if elem.text:
                text_parts.append(elem.text)

            # 子要素を処理
            for child in elem:
                if child.tag == "Ruby":
                    # Ruby要素の場合は特別処理
                    text_parts.append(self._get_ruby_text(child))
                else:
                    # その他の子要素は再帰処理
                    text_parts.append(process_element(child))

                # 子要素の後のテキスト（tail）
                if child.tail:
                    text_parts.append(child.tail)

            return "".join(text_parts)

        return process_element(sentence).strip()

    def _get_ruby_text(self, element) -> str:
        """ルビ要素を処理する: <Ruby>漢字<Rt>読み</Rt></Ruby> → 漢字（読み）"""
        rt_element = element.find("Rt")
        if rt_element is not None and element.text:
            return f"{element.text}（{rt_element.text}）"

        # フォールバック: 全てのテキストを結合
        return "".join(element.itertext())

    def _parse_table_struct(self, table_struct):
        """<TableStruct>をパース
        テーブルは独立した構造を持つため，一旦パースして最後にadd_lineで追加する
        """
        table_struct = table_struct.find("Table")
        for row in table_struct.findall(".//TableRow"):  # 行の処理
            cols = []
            for col in row.findall("TableColumn"):
                sentences = [
                    self._extract_sentence_text(s) for s in col.findall("Sentence")
                ]
                cols.append(" ".join(sentences))
            if cols:
                # print("table =", "|" + " | ".join(cols) + "|")
                self._add_line(
                    "|" + " | ".join(cols) + "|"
                )  # |区切りでmarkdown風に結合

    def _add_optional_text(self, text: Optional[str]) -> None:
        """テキストがある場合のみ行に追加する"""
        if text:
            self._add_line(text)

    def _add_line(self, text: str) -> None:
        """行を追加する（空白をトリム）"""
        self.lines.append(text.strip())

    def _add_blank_line(self) -> None:
        """空行を追加する"""
        self.lines.append("")


class ChapterBasedParser(BaseLawParser):
    """Chapter構造の法令XMLパーサー"""

    def _process_top_level_elements(self) -> None:
        """Chapterから処理を開始する"""
        for chapter in self.root.findall("Chapter"):
            self._process_chapter(chapter)

    def _process_chapter(self, chapter) -> None:
        """章を処理する"""
        chapter_title = chapter.findtext("ChapterTitle")
        if chapter_title:
            self._add_line(chapter_title)
            self._add_blank_line()

        # Chapter直下の全ての子要素を順番通りに処理
        for child in chapter:
            if child.tag == "Section":
                self._process_section(child)
            elif child.tag == "Article":
                self._process_article(child)


class ArticleBasedParser(BaseLawParser):
    """Article構造の法令XMLパーサー"""

    def _process_top_level_elements(self) -> None:
        """Articleから処理を開始する"""
        for article in self.root.findall("Article"):
            self._process_article(article)

    def _process_item_sentence(self, item_sentence) -> None:
        """ItemSentenceを処理する（Column要素対応版）"""
        # Column要素がある場合はColumn経由で処理
        columns = item_sentence.findall("Column")
        if columns:
            for column in columns:
                self._process_sentences(column)
        else:
            # Column要素がない場合は直接処理
            self._process_sentences(item_sentence)


class LawXmlParser:
    """法令XMLパーサーのファクトリクラス"""

    @staticmethod
    def _detect_parser_type(xml: str) -> Type[BaseLawParser]:
        """XMLの構造を検出して適切なパーサータイプを返す"""
        try:
            root = ElementTree.fromstring(xml)

            # Chapter要素があるかチェック
            if root.find("Chapter") is not None:
                return ChapterBasedParser
            # Article要素があるかチェック
            elif root.find("Article") is not None:
                return ArticleBasedParser
            else:
                raise ValueError(
                    "Unknown XML structure: neither Chapter nor Article found at root level"
                )

        except ElementTree.ParseError as e:
            raise ValueError(f"Invalid XML format: {e}")

    @classmethod
    def parse(cls, xml: str) -> str:
        """XMLを自動検出してテキストに変換する"""
        parser_class = cls._detect_parser_type(xml)
        parser = parser_class(xml)
        return parser.parse()


def parse_mainprovision_to_text(xml: str) -> str:
    """MainProvisionを処理する（後方互換性のため）
    LawXmlParser.parseを呼び出すため，法令，施行規則の両方に対応
    """
    return LawXmlParser.parse(xml)


def parse_supplprovision_to_text(xml_string: str):
    """SupplProvisionのxmlを処理する(Paragraph->ParagraphCaption, ParagraphNum, Sentence)"""
    root = ElementTree.fromstring(xml_string)
    output = []

    for para in root.findall(".//Paragraph"):
        # 見出し（段落キャプション）があれば取得
        caption = para.findtext("ParagraphCaption")
        if caption:
            output.append(f"（{caption.strip('（）')}）")

        # 段落番号
        para_num = para.findtext("ParagraphNum")
        line = f"{para_num}　" if para_num else ""

        # センテンスをすべて連結
        sentences = para.findall(".//Sentence")
        sentence_texts = [s.text.strip() for s in sentences if s.text]
        line += (
            "。".join(s.strip("。") for s in sentence_texts) + "。"
            if sentence_texts
            else ""
        )

        # 出力に追加
        output.append(line)

    return "\n".join(output)


def convert_xml_to_text(xml_string: str) -> str:
    """
    通常の法令(Chapter始まり)と，施行規則(Article始まり)の二つに対応
    #TODO:: TOCのパターンの処理はもう少しスマートにできない？
    """
    law_text = extract_sections_from_xml(xml_string)
    if law_text["TOC"] is not None:
        toc_text = parse_toc_to_text(law_text["TOC"])
    main_text = LawXmlParser.parse(law_text["MainProvision"])
    suppl_text = parse_supplprovision_to_text(law_text["SupplProvision"][0])
    if law_text["TOC"] is not None:
        law_text = toc_text + main_text + suppl_text
        return law_text
    law_text = main_text + suppl_text
    return law_text
