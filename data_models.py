from dataclasses import dataclass, field
from typing import Dict, Optional, Any

@dataclass
class Item:
    stats_id: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    root_template_uuid: Optional[str] = None
    stats: Dict[str, Any] = field(default_factory=dict)
    link_method: Optional[str] = None