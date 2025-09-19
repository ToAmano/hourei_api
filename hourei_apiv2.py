"""
eGovのAPI v2を利用して，法令を取得するコード
取得した法令のxml構造を解析して，必要な情報を返す．
"""

# TODO :: パーサーは，textのパーサーとyamlのパーサー

from functools import lru_cache
from typing import Dict, Literal
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
    """save xml string to a file"""
    with open(filename, "w", encoding="utf-8") as f:
        f.write(xml_string)


def extract_sections_from_xml(xml_string: str) -> Dict[str, str | None | list[str]]:
    """TOC, MainProvision,SupplProvisionの3つを取得"""
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
