"""Deterministic interpretation shared by the catalogue and the operator's tester."""
import re
from .search import normalize_query


def material_groups(config):
    if config.get('material_groups') is not None:
        return config['material_groups']
    words = config['materials']
    result = []
    for word in words:
        if word == 'inox' and 'inoxidable' in words:
            continue
        result.append({'name': word, 'synonyms': ['inox'] if word == 'inoxidable' and 'inox' in words else []})
    return result


def occurrences(text, phrase):
    phrase = normalize_query(phrase)
    if not phrase:
        return []
    return [(match.start(), match.end()) for match in re.finditer(r'(?<!\w)' + re.escape(phrase) + r'(?!\w)', text)]


def non_overlapping(matches):
    """Prefer longer expressions; retain ambiguity when one expression names two types."""
    accepted = []
    for item in sorted(matches, key=lambda item: (-(item['end']-item['start']), item['start'])):
        overlaps = [old for old in accepted if item['start'] < old['end'] and item['end'] > old['start']]
        if not overlaps or all((item['start'],item['end']) == (old['start'],old['end']) for old in overlaps):
            accepted.append(item)
    return accepted


def resolve_search(query, config, groups):
    text = normalize_query(query)
    matches = []
    for group in groups:
        for phrase in dict.fromkeys([group['name'], *group['synonyms']]):
            for start,end in occurrences(text,phrase):
                matches.append({'start':start,'end':end,'group':group})
    matches = non_overlapping(matches)
    specific = [item for item in matches if not item['group']['is_general']]
    materials = []
    for group in material_groups(config):
        alternatives = list(dict.fromkeys(normalize_query(word) for word in [group['name'], *group['synonyms']]))
        for phrase in alternatives:
            for start,end in occurrences(text,phrase):
                if any(item['start'] <= start and end <= item['end'] for item in matches):
                    continue
                materials.append({'start':start,'end':end,'name':group['name'],'alternatives':alternatives})
    materials = non_overlapping(materials)
    simplify = bool(specific or materials)
    selected = specific or ([] if simplify else matches)
    selected_keys = set(item['group']['key'] for item in selected)
    selected_types = [{ 'key':group['key'], 'name':group['name'], 'is_general':group['is_general']}
                      for group in groups if group['key'] in selected_keys]
    ambiguous = len(selected_keys) > 1
    removed = list(selected)
    ignored = []
    if simplify:
        for item in matches:
            if item['group']['is_general']:
                removed.append(item); ignored.append(text[item['start']:item['end']])
        # A configured specific type/synonym is protected from the old general-word list.
        if config['enabled']:
            for phrase in config['accessory_terms']:
                for start,end in occurrences(text,phrase):
                    if not any(start < item['end'] and end > item['start'] for item in specific):
                        removed.append({'start':start,'end':end});ignored.append(text[start:end])
    spans = [(item['start'],item['end']) for item in removed]
    remaining = ''.join(' ' if any(start <= index < end for start,end in spans) else char for index,char in enumerate(text))
    remaining = ' '.join(remaining.split())
    # Material aliases are alternatives, while all other words and measures remain required.
    terms = []
    material_names = []
    candidates = []
    for group in material_groups(config):
        alternatives = list(dict.fromkeys(normalize_query(word) for word in [group['name'],*group['synonyms']]))
        for phrase in alternatives:
            for start,end in occurrences(remaining,phrase):
                candidates.append({'start':start,'end':end,'name':group['name'],'alternatives':alternatives})
    candidates = non_overlapping(candidates)
    cursor = 0
    for item in sorted(candidates,key=lambda item:item['start']):
        if item['start'] < cursor: continue
        terms.extend([[term] for term in remaining[cursor:item['start']].split()])
        terms.append(item['alternatives']);material_names.append(item['name']);cursor=item['end']
    terms.extend([[term] for term in remaining[cursor:].split()])
    return {'normalized':text,'query':remaining,'selected_types':selected_types,'ignored':list(dict.fromkeys(ignored)),
            'materials':list(dict.fromkeys(material_names)),'term_groups':terms,'ambiguous':ambiguous,
            'message':('La búsqueda identifica varios tipos: '+', '.join(item['name'] for item in selected_types)+'. Indica solo uno.' if ambiguous else '')}
