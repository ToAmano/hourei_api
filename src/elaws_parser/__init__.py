# flake8: noqa
__version__ = "0.1.0"

from elaws_parser.api import (
    extract_sections_from_xml,
    get_lawdata_from_law_id,
    get_lawdata_from_lawname,
    get_lawid_from_lawtitle,
    save_xml_string_to_file,
)
from elaws_parser.parser import (
    LawToYamlConverter,
    LawXmlParser,
    convert_xml_to_text,
    convert_xml_to_yaml,
)

# LLM/LangGraph機能はオプショナル依存関係のため、インストールされていない場合は無視する
try:
    from elaws_parser.extraction import (
        LegalExtractionConfig,
        YamlArticleExtractor,
        create_legal_extraction_system,
    )
except ImportError:
    pass
