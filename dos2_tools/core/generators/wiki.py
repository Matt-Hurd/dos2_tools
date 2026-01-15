from typing import List
from dos2_tools.core.generators.base import Generator
from dos2_tools.core.generators.item_page import ItemPageGenerator
from dos2_tools.core.models import WikiPage

class WikiGenerator(Generator):
    """
    Main orchestrator that uses sub-generators.
    """
    def generate(self) -> List[WikiPage]:
        pages = []

        # Add Item Pages
        item_gen = ItemPageGenerator(self.context)
        pages.extend(item_gen.generate())

        return pages
