from functools import lru_cache
from typing import Dict, Literal, Optional
from xml.etree import ElementTree

import requests


@lru_cache
def get_lawid_from_lawtitle(law_title: str) -> str:
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
    return law_dict[law_title]  # allow exact match


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


def extract_sections_from_xml(xml_string: str) -> Dict["str", Optional["str"]]:
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


def parse_toc_to_text(toc_xml: str) -> str:
    """XML文字列をパース"""
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


def parse_mainprovision_to_text(xml: str):
    """MainProvisionを処理する"""

    def get_ruby_text(element):
        # <Ruby>漢字<Rt>読み</Rt></Ruby> → 漢字（読み）
        base = "".join(element.itertext())
        rt = element.find("Rt")
        if rt is not None:
            return f"{element.text}（{rt.text}）"
        return base

    root = ElementTree.fromstring(xml)

    lines = []

    for chapter in root.findall("Chapter"):
        chapter_title = chapter.findtext("ChapterTitle")
        if chapter_title:
            lines.append(chapter_title.strip())
            lines.append("")  # 改行

        for article in chapter.findall("Article"):
            caption = article.findtext("ArticleCaption")
            title = article.findtext("ArticleTitle")

            if caption:
                lines.append(caption.strip())
            if title:
                lines.append(title.strip())

            for para in article.findall("Paragraph"):
                para_num = para.findtext("ParagraphNum")
                if para_num:
                    lines.append(para_num.strip())

                # 本文の文を追加
                para_sentence = para.find("ParagraphSentence")
                if para_sentence is not None:
                    for sentence in para_sentence.findall(".//Sentence"):
                        sentence_text = ""
                        for elem in sentence.iter():
                            if elem.tag == "Ruby":
                                sentence_text += get_ruby_text(elem)
                            elif elem.text:
                                sentence_text += elem.text
                        lines.append(sentence_text.strip())

                # 項目（Item）も処理
                for item in para.findall("Item"):
                    item_title = item.findtext("ItemTitle")
                    if item_title:
                        lines.append(item_title.strip())

                    item_sentence = item.find("ItemSentence")
                    if item_sentence is not None:
                        for sentence in item_sentence.findall(".//Sentence"):
                            sentence_text = ""
                            for elem in sentence.iter():
                                if elem.tag == "Ruby":
                                    sentence_text += get_ruby_text(elem)
                                elif elem.text:
                                    sentence_text += elem.text
                            lines.append(sentence_text.strip())

    return "\n".join(lines)


def parse_supplprovision_to_text(xml_string: str):
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
