import os
import re
import csv
import io

from dos2_tools.core.config import get_config
from dos2_tools.core.file_system import resolve_load_order, get_files_by_pattern
from dos2_tools.core.parsers import parse_stats_txt
from dos2_tools.core.stats_engine import resolve_all_stats

class TreasureParser:
    def __init__(self):
        self.tables = {}

    def parse_csv_line(self, line):
        f = io.StringIO(line)
        try: return next(csv.reader(f, delimiter=',', quotechar='"'))
        except StopIteration: return []

    def load_data(self, data_str):
        current_table = None
        current_s = None; current_e = None
        
        for line in data_str.split('\n'):
            line = line.strip()
            if not line or line.startswith('//'): continue
            
            if line.startswith('new treasuretable'):
                match = re.search(r'new treasuretable "([^"]+)"', line)
                if match:
                    current_table = match.group(1)
                    self.tables[current_table] = []
                    current_s = None; current_e = None
            elif line.startswith('new subtable') and current_table:
                match = re.search(r'new subtable "([^"]+)"', line)
                if match:
                    self.tables[current_table].append({'type': 'group', 'rule': match.group(1), 'items': []})
            elif line.startswith('StartLevel'):
                m = re.search(r'StartLevel "([^"]+)"', line)
                if m: current_s = int(m.group(1))
            elif line.startswith('EndLevel'):
                m = re.search(r'EndLevel "([^"]+)"', line)
                if m: current_e = int(m.group(1))
            elif line.startswith('object category') and current_table:
                parts = self.parse_csv_line(line.replace('object category ', ''))
                if parts and self.tables[current_table]:
                    self.tables[current_table][-1]['items'].append({
                        'name': parts[0],
                        'freq': int(parts[1]) if len(parts) > 1 else 1,
                        's': current_s, 'e': current_e
                    })

    def parse_qty_rule(self, drop_rule):
        if drop_rule.startswith('-'):
            val = abs(int(drop_rule))
            return val, val, 1.0
        pairs = drop_rule.split(';')
        min_q = 999; max_q = 0; total_w = 0; success_w = 0
        for p in pairs:
            if ',' not in p: continue
            try:
                c, w = map(int, p.split(','))
                total_w += w
                if c > 0:
                    success_w += w
                    min_q = min(min_q, c)
                    max_q = max(max_q, c)
            except: continue
        if total_w == 0: return 0,0,0
        if min_q == 999: min_q = 0
        return min_q, max_q, success_w/total_w

def clean_name(name):
    return name.replace("'", "\\'")

def main():
    conf = get_config()
    all_files = resolve_load_order(conf['base_path'], conf['cache_file'])
    
    print("Parsing treasure tables...")
    parser = TreasureParser()
    tt = [f for f in all_files if "TreasureTable.txt" in f]
    for f in tt:
        with open(f,'r',encoding='utf-8',errors='replace') as fo: parser.load_data(fo.read())
        
    lines = []
    lines.append("return {")
    
    for t_id, groups in parser.tables.items():
        if not groups: continue
        
        lines.append(f"['{clean_name(t_id)}'] = {{")
        
        for grp in groups:
            min_q, max_q, chance = parser.parse_qty_rule(grp['rule'])
            if chance <= 0: continue
            
            lines.append(f"  {{ Chance={chance:.4f}, Min={min_q}, Max={max_q}, Items={{")
            
            total_freq = sum(i['freq'] for i in grp['items'])
            if total_freq > 0:
                for item in grp['items']:
                    rel_chance = item['freq'] / total_freq
                    safe_item = clean_name(item['name'])
                    s_lvl = item['s'] if item['s'] else "nil"
                    e_lvl = item['e'] if item['e'] else "nil"
                    
                    lines.append(f"    {{ '{safe_item}', {rel_chance:.4f}, {s_lvl}, {e_lvl} }},")
            
            lines.append("  }},")
        
        lines.append("},")
        
    lines.append("}")
    
    with open("Module_LootData.lua", "w", encoding='utf-8') as f:
        f.write("\n".join(lines))
    
    print("Done! Generated Module_LootData.lua")

if __name__ == "__main__":
    main()