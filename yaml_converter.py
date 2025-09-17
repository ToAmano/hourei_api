"""
yaml形式でのxmlからの抽出

# TODO :: textパーサーと合わせて，重複部分を上位クラスに定義する
"""

import re
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree

import yaml


class LawToYamlConverter:
    """法令XMLをYAML形式に変換するコンバータークラス"""

    def __init__(self, xml_string: str):
        """
        Args:
            xml_string: 法令のXML文字列
        """
        self.root = ElementTree.fromstring(xml_string)
        self.yaml_data = {}

    def convert(self) -> Dict[str, Any]:
        """XML(self.root)をYAMLデータ構造に変換

        Returns:
            YAML形式のデータ構造（辞書）
        """
        self._extract_law_info()
        self._extract_toc()
        self._extract_main_provisions()
        self._extract_supplementary_provisions()
        return self.yaml_data

    def to_yaml_string(self) -> str:
        """YAML文字列として出力

        Returns:
            YAML形式の文字列
        """
        yaml_dict = self.convert()
        return yaml.dump(
            yaml_dict, allow_unicode=True, default_flow_style=False, sort_keys=False
        )

    def _extract_law_info(self) -> None:
        """法令の基本情報を抽出
        #TODO :: 再度全ての情報を過不足なく抽出できているか（スキップしているタグがないか）確認
        """
        law_info = {}

        # law_full_text/Law/LawBody/LawNum から法令番号を取得
        law_full_text = self.root.find("law_full_text")
        if law_full_text is not None:
            law = law_full_text.find("Law")
            if law is not None:
                law_body = law.find("LawBody")
                if law_body is not None:
                    law_num = law_body.findtext("LawNum")
                    if law_num:
                        law_info["law_num"] = law_num.strip()

        # その他の基本情報があれば追加
        law_title_elem = self.root.find(".//law_title")
        if law_title_elem is not None and law_title_elem.text:
            law_info["title"] = law_title_elem.text.strip()

        if law_info:
            self.yaml_data["law_info"] = law_info

    def _extract_toc(self) -> None:
        """目次情報を抽出"""
        law_full_text = self.root.find("law_full_text")
        if law_full_text is None:
            return

        law = law_full_text.find("Law")
        if law is None:
            return

        law_body = law.find("LawBody")
        if law_body is None:
            return

        toc = law_body.find("TOC")
        if toc is None:
            return

        toc_data = []

        # TOCLabelを取得
        toc_label = toc.findtext("TOCLabel")
        if toc_label:
            toc_data.append({"type": "label", "content": toc_label.strip()})

        # TOCChapterを処理
        for chapter in toc.findall("TOCChapter"):
            chapter_title = chapter.findtext("ChapterTitle")
            article_range = chapter.findtext("ArticleRange")

            if chapter_title and article_range:
                toc_data.append(
                    {
                        "type": "chapter",
                        "title": chapter_title.strip(),
                        "article_range": article_range.strip(),
                    }
                )

        # TOCSupplProvisionを処理
        toc_suppl = toc.find("TOCSupplProvision")
        if toc_suppl is not None:
            suppl_label = toc_suppl.findtext("SupplProvisionLabel")
            if suppl_label:
                toc_data.append(
                    {"type": "supplementary", "content": suppl_label.strip()}
                )

        if toc_data:
            self.yaml_data["table_of_contents"] = toc_data

    def _extract_main_provisions(self) -> None:
        """本則を抽出"""
        law_full_text = self.root.find("law_full_text")
        if law_full_text is None:
            return

        law = law_full_text.find("Law")
        if law is None:
            return

        law_body = law.find("LawBody")
        if law_body is None:
            return

        main_provision = law_body.find("MainProvision")
        if main_provision is None:
            return

        # Chapter構造かArticle構造かを判定
        if main_provision.find("Chapter") is not None:
            self._process_chapter_structure(main_provision)
        elif main_provision.find("Article") is not None:
            self._process_article_structure(main_provision)

    def _process_chapter_structure(self, main_provision) -> None:
        """Chapter構造の本則を処理"""
        chapters = []

        for chapter in main_provision.findall("Chapter"):
            chapter_data = self._process_chapter(chapter)
            if chapter_data:
                chapters.append(chapter_data)

        if chapters:
            self.yaml_data["chapters"] = chapters

    def _process_article_structure(self, main_provision) -> None:
        """Article構造の本則を処理（施行規則等）"""
        articles = []

        for article in main_provision.findall("Article"):
            article_data = self._process_article(article)
            if article_data:
                articles.append(article_data)

        if articles:
            self.yaml_data["articles"] = articles

    def _process_chapter(self, chapter) -> Dict[str, Any]:
        """章を処理"""
        chapter_data = {}

        chapter_title = chapter.findtext("ChapterTitle")
        if chapter_title:
            chapter_data["title"] = chapter_title.strip()
            # 章番号を抽出（第X章の形式）
            chapter_num = self._extract_number_from_title(chapter_title)
            if chapter_num:
                chapter_data["chapter_num"] = chapter_num

        # 章の下の節を処理
        sections = []
        for section in chapter.findall("Section"):
            section_data = self._process_section(section)
            if section_data:
                sections.append(section_data)

        if sections:
            chapter_data["sections"] = sections

        # 章の直下の条を処理（節がない場合）
        articles = []
        for article in chapter.findall("Article"):
            article_data = self._process_article(article)
            if article_data:
                articles.append(article_data)

        if articles:
            chapter_data["articles"] = articles

        return chapter_data

    def _process_section(self, section) -> Dict[str, Any]:
        """節を処理"""
        section_data = {}

        section_title = section.findtext("SectionTitle")
        if section_title:
            section_data["title"] = section_title.strip()
            section_num = self._extract_number_from_title(section_title)
            if section_num:
                section_data["section_num"] = section_num

        # 節の下の条を処理
        articles = []
        for article in section.findall("Article"):
            article_data = self._process_article(article)
            if article_data:
                articles.append(article_data)

        if articles:
            section_data["articles"] = articles

        return section_data

    def _process_article(self, article) -> Dict[str, Any]:
        """条を処理"""
        article_data = {}

        # 条のキャプション
        article_caption = article.findtext("ArticleCaption")
        if article_caption:
            article_data["caption"] = article_caption.strip()

        # 条のタイトル
        article_title = article.findtext("ArticleTitle")
        if article_title:
            article_data["title"] = article_title.strip()
            article_num = self._extract_number_from_title(article_title)
            if article_num:
                article_data["article_num"] = article_num

        # 項を処理
        paragraphs = []
        for paragraph in article.findall("Paragraph"):
            paragraph_data = self._process_paragraph(paragraph)
            if paragraph_data:
                paragraphs.append(paragraph_data)

        if paragraphs:
            article_data["paragraphs"] = paragraphs

        return article_data

    def _process_paragraph(self, paragraph) -> Dict[str, Any]:
        """項を処理"""
        paragraph_data = {}

        # 項番号
        paragraph_num = paragraph.findtext("ParagraphNum")
        if paragraph_num:
            paragraph_data["paragraph_num"] = paragraph_num.strip()
            num = self._extract_number_from_text(paragraph_num)
            if num:
                paragraph_data["num"] = num

        # 項の文章
        paragraph_sentence = paragraph.find("ParagraphSentence")
        if paragraph_sentence is not None:
            sentences = self._extract_sentences(paragraph_sentence)
            if sentences:
                paragraph_data["content"] = sentences

        # 号を処理
        items = []
        for item in paragraph.findall("Item"):
            item_data = self._process_item(item)
            if item_data:
                items.append(item_data)

        if items:
            paragraph_data["items"] = items

        # 表を処理
        table_struct = paragraph.find("TableStruct")
        if table_struct is not None:
            table_data = self._process_table(table_struct)
            if table_data:
                paragraph_data["table"] = table_data

        return paragraph_data

    def _process_item(self, item) -> Dict[str, Any]:
        """号を処理"""
        item_data = {}

        # 号のタイトル
        item_title = item.findtext("ItemTitle")
        if item_title:
            item_data["title"] = item_title.strip()
            item_num = self._extract_number_from_text(item_title)
            if item_num:
                item_data["item_num"] = item_num

        # 号の文章
        item_sentence = item.find("ItemSentence")
        if item_sentence is not None:
            sentences = self._extract_sentences(item_sentence)
            if sentences:
                item_data["content"] = sentences

        # サブ項目を処理
        subitems = []
        for subitem in item.findall("Subitem1"):
            subitem_data = self._process_subitem(subitem, 1)
            if subitem_data:
                subitems.append(subitem_data)

        if subitems:
            item_data["subitems"] = subitems

        # 表を処理
        table_struct = item.find("TableStruct")
        if table_struct is not None:
            table_data = self._process_table(table_struct)
            if table_data:
                item_data["table"] = table_data

        return item_data

    def _process_subitem(self, subitem, level: int) -> Dict[str, Any]:
        """サブ項目を再帰的に処理"""
        subitem_data = {}
        subitem_data["level"] = level

        # サブ項目のタイトル
        title_tag = f"Subitem{level}Title"
        title = subitem.findtext(title_tag)
        if title:
            subitem_data["title"] = title.strip()

        # サブ項目の文章
        sentence_tag = f"Subitem{level}Sentence"
        sentence = subitem.find(sentence_tag)
        if sentence is not None:
            sentences = self._extract_sentences(sentence)
            if sentences:
                subitem_data["content"] = sentences

        # 次のレベルのサブ項目を処理
        next_level = level + 1
        next_subitem_tag = f"Subitem{next_level}"
        next_subitems = []

        for next_subitem in subitem.findall(next_subitem_tag):
            next_subitem_data = self._process_subitem(next_subitem, next_level)
            if next_subitem_data:
                next_subitems.append(next_subitem_data)

        if next_subitems:
            subitem_data["subitems"] = next_subitems

        # 表を処理
        table_struct = subitem.find("TableStruct")
        if table_struct is not None:
            table_data = self._process_table(table_struct)
            if table_data:
                subitem_data["table"] = table_data

        return subitem_data

    def _process_table(self, table_struct) -> Dict[str, Any]:
        """表を処理
        # TODO :: 表をyamlに変換しているのであまりよくない．
        # TODO :: LLMに渡すときは，ここだけ表形式に直すか，あるいはyaml中でtextのmarkdownとして表を処理できないか検討
        """
        table = table_struct.find("Table")
        if table is None:
            return {}

        rows = []
        for row in table.findall(".//TableRow"):
            cols = []
            for col in row.findall("TableColumn"):
                sentences = self._extract_sentences(col)
                cols.append(sentences if sentences else "")
            if cols:
                rows.append(cols)

        return {"rows": rows} if rows else {}

    def _extract_sentences(self, container) -> str:
        """文章コンテナから文章を抽出"""
        sentences = []
        for sentence in container.findall(".//Sentence"):
            sentence_text = self._extract_sentence_text(sentence)
            if sentence_text:
                sentences.append(sentence_text)
        return " ".join(sentences) if sentences else ""

    def _extract_sentence_text(self, sentence) -> str:
        """文要素からテキストを抽出（ルビ対応）
        TODO:: text extractorと全く同じ実装なので被りを解除したい．
        """

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
        """ルビ要素を処理: <Ruby>漢字<Rt>読み</Rt></Ruby> → 漢字（読み）"""
        rt_element = element.find("Rt")
        if rt_element is not None and element.text:
            return f"{element.text}（{rt_element.text}）"

        # フォールバック: 全てのテキストを結合
        return "".join(element.itertext())

    def _extract_supplementary_provisions(self) -> None:
        """附則を抽出"""
        law_full_text = self.root.find("law_full_text")
        if law_full_text is None:
            return

        law = law_full_text.find("Law")
        if law is None:
            return

        law_body = law.find("LawBody")
        if law_body is None:
            return

        suppl_provisions = []
        for suppl in law_body.findall("SupplProvision"):
            suppl_data = self._process_supplementary_provision(suppl)
            if suppl_data:
                suppl_provisions.append(suppl_data)

        if suppl_provisions:
            self.yaml_data["supplementary_provisions"] = suppl_provisions

    def _process_supplementary_provision(self, suppl) -> Dict[str, Any]:
        """附則を処理"""
        suppl_data = {}

        # 附則のラベル
        suppl_label = suppl.findtext("SupplProvisionLabel")
        if suppl_label:
            suppl_data["label"] = suppl_label.strip()

        # 附則の段落を処理
        paragraphs = []
        for paragraph in suppl.findall("Paragraph"):
            para_data = {}

            # 段落キャプション
            caption = paragraph.findtext("ParagraphCaption")
            if caption:
                para_data["caption"] = caption.strip()

            # 段落番号
            para_num = paragraph.findtext("ParagraphNum")
            if para_num:
                para_data["paragraph_num"] = para_num.strip()

            # 段落の文章
            sentences = []
            for sentence in paragraph.findall(".//Sentence"):
                sentence_text = self._extract_sentence_text(sentence)
                if sentence_text:
                    sentences.append(sentence_text)

            if sentences:
                para_data["content"] = " ".join(sentences)

            if para_data:
                paragraphs.append(para_data)

        if paragraphs:
            suppl_data["paragraphs"] = paragraphs

        return suppl_data

    def _extract_number_from_title(self, title: str) -> Optional[int]:
        """タイトルから番号を抽出（第X章、第X節など）"""
        match = re.search(r"第([一二三四五六七八九十百千万壱弐参拾]+|[0-9]+)", title)
        if match:
            num_str = match.group(1)
            if num_str.isdigit():
                return int(num_str)
            else:
                # 漢数字を数字に変換（簡易版）
                return self._convert_kanji_to_number(num_str)
        return None

    def _extract_number_from_text(self, text: str) -> Optional[int]:
        """テキストから数字を抽出"""
        match = re.search(r"([0-9]+)", text)
        if match:
            return int(match.group(1))
        return None

    def _convert_kanji_to_number(self, kanji: str) -> Optional[int]:
        """漢数字を数字に変換
        # TODO :: これで足りてるか？
        """
        kanji_map = {
            "一": 1,
            "二": 2,
            "三": 3,
            "四": 4,
            "五": 5,
            "六": 6,
            "七": 7,
            "八": 8,
            "九": 9,
            "十": 10,
            "壱": 1,
            "弐": 2,
            "参": 3,
        }

        if kanji in kanji_map:
            return kanji_map[kanji]

        # 十の位の処理（簡易版）
        if "十" in kanji:
            if kanji == "十":
                return 10
            elif kanji.startswith("十"):
                return 10 + kanji_map.get(kanji[1], 0)
            elif kanji.endswith("十"):
                return kanji_map.get(kanji[0], 0) * 10
            else:
                parts = kanji.split("十")
                if len(parts) == 2:
                    left = kanji_map.get(parts[0], 0) if parts[0] else 1
                    right = kanji_map.get(parts[1], 0)
                    return left * 10 + right

        return None


def convert_xml_to_yaml(xml_string: str) -> str:
    """XMLを構造化YAMLに変換する便利関数

    Args:
        xml_string: 法令のXML文字列

    Returns:
        YAML形式の文字列
    """
    converter = LawToYamlConverter(xml_string)
    return converter.to_yaml_string()


# 使用例
if __name__ == "__main__":
    # 使用例（実際のXMLデータが必要）
    sample_xml = """
    <!-- ここに法令XMLデータを配置 -->
    """

    # converter = LawToYamlConverter(sample_xml)
    # yaml_output = converter.to_yaml_string()
    # print(yaml_output)

    # または
    # yaml_output = convert_xml_to_yaml(sample_xml)
    # print(yaml_output)
    pass
