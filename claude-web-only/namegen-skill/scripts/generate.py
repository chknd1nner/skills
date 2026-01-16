#!/usr/bin/env python3
"""
namegen - Generate culturally-themed character names for fiction.

Supports two modes:
  - realistic: Authentic names via Faker (105 locales)
  - synthetic: Novel Markov-generated names (38 cultural/fantasy datasets)

Usage:
  python generate.py --mode realistic --culture ja_JP --gender male -n 3
  python generate.py --mode synthetic --culture tolkienesque_forenames -n 5 --quiet
  python generate.py --list-cultures
"""

import argparse
import json
import os
import random
import sys

# Anti-slop blocklist - overused AI-typical names
SLOP_NAMES = {
    "alaric", "alistair", "anya", "bellweather", "cassian", "chen", "clara",
    "corvid", "elara", "evander", "finch", "finn", "henderson", "isolde",
    "kael", "kaelen", "kealan", "lena", "leo", "lyra", "lysander", "lysandra",
    "malkor", "marcus", "martha", "millar", "miller", "pipkin", "quill",
    "seraphina", "sharma", "silas", "sterling", "thea", "thorne", "timmy",
    "torvin", "vael", "vale", "valerius", "vance", "vayne", "volkov",
    "vorlag", "zephyr", "zephyrine"
}

# Faker locales with friendly aliases
FAKER_LOCALES = {
    # Direct locale codes
    "ar_SA": "ar_SA", "bg_BG": "bg_BG", "cs_CZ": "cs_CZ", "da_DK": "da_DK",
    "de_DE": "de_DE", "de_AT": "de_AT", "de_CH": "de_CH", "el_GR": "el_GR",
    "en_US": "en_US", "en_GB": "en_GB", "en_AU": "en_AU", "en_CA": "en_CA",
    "en_IN": "en_IN", "en_IE": "en_IE", "es_ES": "es_ES", "es_MX": "es_MX",
    "es_AR": "es_AR", "et_EE": "et_EE", "fa_IR": "fa_IR", "fi_FI": "fi_FI",
    "fr_FR": "fr_FR", "fr_CA": "fr_CA", "he_IL": "he_IL", "hi_IN": "hi_IN",
    "hr_HR": "hr_HR", "hu_HU": "hu_HU", "id_ID": "id_ID", "it_IT": "it_IT",
    "ja_JP": "ja_JP", "ko_KR": "ko_KR", "lt_LT": "lt_LT", "lv_LV": "lv_LV",
    "nl_NL": "nl_NL", "no_NO": "no_NO", "pl_PL": "pl_PL", "pt_BR": "pt_BR",
    "pt_PT": "pt_PT", "ro_RO": "ro_RO", "ru_RU": "ru_RU", "sk_SK": "sk_SK",
    "sl_SI": "sl_SI", "sv_SE": "sv_SE", "th_TH": "th_TH", "tr_TR": "tr_TR",
    "uk_UA": "uk_UA", "vi_VN": "vi_VN", "zh_CN": "zh_CN", "zh_TW": "zh_TW",
    # Friendly aliases
    "japanese": "ja_JP", "korean": "ko_KR", "chinese": "zh_CN",
    "german": "de_DE", "french": "fr_FR", "italian": "it_IT",
    "spanish": "es_ES", "portuguese": "pt_BR", "russian": "ru_RU",
    "polish": "pl_PL", "dutch": "nl_NL", "swedish": "sv_SE",
    "norwegian": "no_NO", "danish": "da_DK", "finnish": "fi_FI",
    "american": "en_US", "british": "en_GB", "australian": "en_AU",
    "indian": "hi_IN", "arabic": "ar_SA", "hebrew": "he_IL",
    "turkish": "tr_TR", "greek": "el_GR", "czech": "cs_CZ",
    "hungarian": "hu_HU", "romanian": "ro_RO", "ukrainian": "uk_UA",
    "vietnamese": "vi_VN", "thai": "th_TH", "indonesian": "id_ID",
    "irish": "en_IE", "canadian": "en_CA", "mexican": "es_MX",
    "brazilian": "pt_BR", "argentinian": "es_AR", "persian": "fa_IR",
}

# Markovname datasets for synthetic mode
SYNTHETIC_DATASETS = [
    # Cultural forenames
    "american_forenames", "dutch_forenames", "french_forenames",
    "german_forenames", "icelandic_forenames", "indian_forenames",
    "irish_forenames", "italian_forenames", "japanese_forenames",
    "russian_forenames", "spanish_forenames", "swedish_forenames",
    # Surnames
    "american_surnames", "scottish_surnames",
    # Mythological/Fantasy
    "brythonic_deities", "egyptian_deities", "hindu_deities",
    "norse_deity_forenames", "roman_deities", "roman_emperor_forenames",
    "tolkienesque_forenames", "werewolf_forenames", "mythical_humanoids",
    # Other useful sets
    "stars_proper_names", "theological_angels", "theological_demons",
    "dragons", "pokemon",
]

# Friendly aliases for synthetic datasets
SYNTHETIC_ALIASES = {
    "celtic": "brythonic_deities",
    "norse": "norse_deity_forenames",
    "roman": "roman_emperor_forenames",
    "elvish": "tolkienesque_forenames",
    "tolkien": "tolkienesque_forenames",
    "egyptian": "egyptian_deities",
    "hindu": "hindu_deities",
    "demonic": "theological_demons",
    "angelic": "theological_angels",
    "star": "stars_proper_names",
    "stars": "stars_proper_names",
}


def is_slop(name: str) -> bool:
    """Check if a name is in the anti-slop blocklist."""
    return name.lower() in SLOP_NAMES


def generate_realistic(culture: str, gender: str, components: list[str]) -> dict:
    """Generate a realistic name using Faker."""
    from faker import Faker
    
    locale = FAKER_LOCALES.get(culture.lower(), culture)
    
    try:
        fake = Faker(locale)
    except Exception as e:
        raise ValueError(f"Unknown locale '{culture}'. Use --list-cultures to see options.") from e
    
    result = {}
    
    for component in components:
        if component == "first":
            if gender == "male":
                result["first"] = fake.first_name_male()
            elif gender == "female":
                result["first"] = fake.first_name_female()
            else:
                result["first"] = fake.first_name()
        elif component == "middle":
            # Most locales don't have middle name methods, use first name
            if gender == "male":
                result["middle"] = fake.first_name_male()
            elif gender == "female":
                result["middle"] = fake.first_name_female()
            else:
                result["middle"] = fake.first_name()
        elif component == "last":
            result["last"] = fake.last_name()
    
    return result


def generate_synthetic(dataset: str, gender: str = None) -> str:
    """Generate a synthetic name using markovname."""
    from markovname import Generator
    
    # Resolve aliases
    dataset_name = SYNTHETIC_ALIASES.get(dataset.lower(), dataset.lower())
    
    # Handle the _forenames suffix
    if dataset_name not in SYNTHETIC_DATASETS:
        # Try adding _forenames
        if f"{dataset_name}_forenames" in SYNTHETIC_DATASETS:
            dataset_name = f"{dataset_name}_forenames"
        else:
            raise ValueError(f"Unknown dataset '{dataset}'. Use --list-cultures to see options.")
    
    # Load dataset
    import markovname
    data_path = os.path.join(os.path.dirname(markovname.__file__), 'data')
    json_path = os.path.join(data_path, f"{dataset_name}.json")
    
    if not os.path.exists(json_path):
        raise ValueError(f"Dataset file not found: {json_path}")
    
    with open(json_path, 'r', encoding='utf-8') as f:
        training_data = json.load(f)
    
    gen = Generator(data=training_data, order=3, prior=0.0)
    name = gen.generate()
    
    # Clean up markov artifacts and capitalize
    name = name.replace('#', '').strip()
    name = name.title()
    
    return name


def generate_name(mode: str, culture: str, gender: str, components: list[str], 
                  max_attempts: int = 10, filter_slop: bool = True) -> dict:
    """Generate a name with anti-slop filtering."""
    
    for attempt in range(max_attempts):
        if mode == "realistic":
            name_parts = generate_realistic(culture, gender, components)
        else:  # synthetic
            name_parts = {}
            if "first" in components:
                name_parts["first"] = generate_synthetic(culture, gender)
            if "middle" in components:
                name_parts["middle"] = generate_synthetic(culture, gender)
            if "last" in components:
                # Try surname dataset if available, otherwise use forenames
                surname_dataset = culture.replace("_forenames", "_surnames")
                try:
                    name_parts["last"] = generate_synthetic(surname_dataset, gender)
                except ValueError:
                    name_parts["last"] = generate_synthetic(culture, gender)
        
        # Check for slop
        if filter_slop:
            has_slop = any(is_slop(part) for part in name_parts.values())
            if has_slop:
                continue
        
        return name_parts
    
    # If we exhausted attempts, return last generated (with warning)
    return name_parts


def format_full_name(name_parts: dict, components: list[str]) -> str:
    """Assemble name parts into a full name string."""
    parts = []
    for comp in components:
        if comp in name_parts:
            parts.append(name_parts[comp])
    return " ".join(parts)


def list_cultures():
    """Print available cultures for both modes."""
    print("=== REALISTIC MODE (Faker locales) ===")
    print("Direct locale codes:")
    locales = sorted(set(v for v in FAKER_LOCALES.values()))
    for i, loc in enumerate(locales):
        print(f"  {loc}", end="")
        if (i + 1) % 8 == 0:
            print()
    print("\n")
    
    print("Friendly aliases:")
    aliases = sorted(k for k, v in FAKER_LOCALES.items() if k != v)
    for alias in aliases:
        print(f"  {alias} → {FAKER_LOCALES[alias]}")
    
    print("\n=== SYNTHETIC MODE (Markovname datasets) ===")
    print("Datasets:")
    for ds in sorted(SYNTHETIC_DATASETS):
        print(f"  {ds}")
    
    print("\nFriendly aliases:")
    for alias, target in sorted(SYNTHETIC_ALIASES.items()):
        print(f"  {alias} → {target}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate culturally-themed character names for fiction.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --mode realistic --culture japanese --gender male
  %(prog)s --mode synthetic --culture tolkien -n 5 --quiet
  %(prog)s --mode realistic --culture en_US --components first,middle,last
  %(prog)s --list-cultures
        """
    )
    
    parser.add_argument("--mode", "-m", choices=["realistic", "synthetic"],
                        help="Generation mode: realistic (Faker) or synthetic (Markov)")
    parser.add_argument("--culture", "-c",
                        help="Culture/locale for realistic, or dataset for synthetic")
    parser.add_argument("--gender", "-g", choices=["male", "female", "neutral"],
                        default="neutral", help="Gender for name generation (default: neutral)")
    parser.add_argument("--components", default="first,last",
                        help="Comma-separated name components: first,middle,last (default: first,last)")
    parser.add_argument("--quantity", "-n", type=int, default=1,
                        help="Number of names to generate (default: 1)")
    parser.add_argument("--quiet", "-q", action="store_true",
                        help="Output names only, no metadata")
    parser.add_argument("--no-filter", action="store_true",
                        help="Disable anti-slop filtering")
    parser.add_argument("--list-cultures", action="store_true",
                        help="List available cultures/datasets and exit")
    
    args = parser.parse_args()
    
    if args.list_cultures:
        list_cultures()
        return 0
    
    if not args.mode or not args.culture:
        parser.error("--mode and --culture are required (or use --list-cultures)")
    
    components = [c.strip() for c in args.components.split(",")]
    valid_components = {"first", "middle", "last"}
    for c in components:
        if c not in valid_components:
            parser.error(f"Invalid component '{c}'. Must be: first, middle, last")
    
    results = []
    for _ in range(args.quantity):
        try:
            name_parts = generate_name(
                mode=args.mode,
                culture=args.culture,
                gender=args.gender,
                components=components,
                filter_slop=not args.no_filter
            )
            full_name = format_full_name(name_parts, components)
            results.append({
                "name": full_name,
                "parts": name_parts
            })
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
    
    if args.quiet:
        for r in results:
            print(r["name"])
    else:
        output = {
            "mode": args.mode,
            "culture": args.culture,
            "gender": args.gender,
            "components": components,
            "names": results
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
