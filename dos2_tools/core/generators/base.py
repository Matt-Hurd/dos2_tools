from abc import ABC, abstractmethod
from typing import List, Any
from dos2_tools.core.context import AppContext
from dos2_tools.core.models import WikiPage

class Generator(ABC):
    def __init__(self, context: AppContext):
        self.context = context

    @abstractmethod
    def generate(self) -> List[WikiPage]:
        """Returns a list of generated WikiPages."""
        pass
