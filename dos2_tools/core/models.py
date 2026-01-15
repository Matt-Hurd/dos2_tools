from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set, Any, Tuple

@dataclass
class StatEntry:
    """Represents a raw entry from a Stats .txt file."""
    name: str
    type: str = "Unknown"
    using: Optional[str] = None
    data: Dict[str, str] = field(default_factory=dict)
    source_module: Optional[str] = None # e.g. "DivinityOrigins", "Giftbag1", etc.

@dataclass
class RootTemplate:
    """Represents a Game Object Template from an .lsj file."""
    uuid: str
    name: str
    stats_id: Optional[str] = None
    type: Optional[str] = None
    display_name_handle: Optional[str] = None
    description_handle: Optional[str] = None
    icon: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    raw_data: Dict[str, Any] = field(default_factory=dict)

    # Actions
    book_id: Optional[str] = None
    taught_recipes: List[str] = field(default_factory=list)

    source_module: Optional[str] = None

@dataclass
class Recipe:
    """Represents a crafting recipe."""
    id: str
    title: Optional[str] = None
    ingredients: List[str] = field(default_factory=list)
    results: List[str] = field(default_factory=list)
    crafting_station: Optional[str] = None
    source_module: Optional[str] = None

@dataclass
class CraftingCombo:
    """Represents an entry from ItemCombos.txt"""
    combo_id: str
    result_id: str
    ingredients: Dict[str, str] = field(default_factory=dict) # Key: type/object identifier, Value: ID
    source_module: Optional[str] = None

@dataclass
class Location:
    """Represents where an item is found in the world."""
    region: str
    coordinates: Optional[str] = None
    container_name: Optional[str] = None
    npc_name: Optional[str] = None
    level_name: Optional[str] = None
    template_uuid: Optional[str] = None # The specific instance UUID if applicable

    def to_wiki_str(self):
        # Helper for sorting/deduping
        return f"{self.region}|{self.coordinates}|{self.container_name}|{self.npc_name}|{self.template_uuid}"

@dataclass
class Item:
    """
    A fully resolved item entity.
    Combines data from Stats, RootTemplates, and Localization.
    """
    name: str
    stats_id: Optional[str] = None
    template_uuid: Optional[str] = None
    description: Optional[str] = None
    root_template: Optional[RootTemplate] = None
    stats_entry: Optional[StatEntry] = None

    # Contextual data
    locations: List[Location] = field(default_factory=list)
    book_id: Optional[str] = None # The ID of the book text
    book_text: Optional[str] = None # The actual resolved text
    taught_recipes: List[str] = field(default_factory=list)
    properties: List[str] = field(default_factory=list) # E.g., from ItemComboProperties
    categories: List[str] = field(default_factory=list)

    source_module: Optional[str] = None # Derived from stats or template

@dataclass
class WikiPage:
    """Represents a generated Wiki Page."""
    title: str
    content: str
    categories: List[str] = field(default_factory=list)
    source_module: Optional[str] = None
