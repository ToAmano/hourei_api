try:
    from .law_extraction_v2 import (
        LegalExtractionConfig,
        YamlArticleExtractor,
        create_legal_extraction_system,
    )
    __all__ = [
        "LegalExtractionConfig",
        "create_legal_extraction_system",
        "YamlArticleExtractor",
    ]
except ImportError:
    __all__ = []
