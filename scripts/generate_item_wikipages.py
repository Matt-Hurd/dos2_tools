import os
import argparse
from dos2_tools.core.context import AppContext
from dos2_tools.core.generators.wiki import WikiGenerator

def main():
    parser = argparse.ArgumentParser(description="Generate Divinity: Original Sin 2 Wiki Pages")
    parser.add_argument("--outdir", default="item_wikitext", help="Output directory for generated files")
    parser.add_argument("--mod", action="append", help="Additional mod/giftbag directories to load (can be used multiple times)")
    args = parser.parse_args()
    
    if not os.path.exists(args.outdir):
        os.makedirs(args.outdir)

    # Initialize Context (loads all data)
    print("Initializing Application Context...")
    context = AppContext(active_modules=args.mod)
    
    # Run Generator
    print("Generating Wiki Pages...")
    generator = WikiGenerator(context)
    pages = generator.generate()
    
    print(f"Writing {len(pages)} pages to {args.outdir}...")
    for page in pages:
        filename = f"{page.title}.txt"
        filepath = os.path.join(args.outdir, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(page.content)
            
    print("Done.")

if __name__ == "__main__":
    main()
