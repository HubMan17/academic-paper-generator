import pytest
from services.pipeline.steps.outline import (
    filter_outline_sections,
    normalize_section_key,
    validate_outline_structure,
)
from services.pipeline.specs import (
    get_allowed_section_keys,
    get_allowed_chapter_keys,
)


class TestGetAllowedSectionKeys:
    def test_referat_keys_include_intro_conclusion(self):
        keys = get_allowed_section_keys('referat')
        assert 'intro' in keys
        assert 'conclusion' in keys

    def test_referat_keys_include_theory_sections(self):
        keys = get_allowed_section_keys('referat')
        assert 'theory_1' in keys
        assert 'theory_2' in keys
        assert 'theory_3' in keys

    def test_referat_keys_include_practice_sections(self):
        keys = get_allowed_section_keys('referat')
        assert 'practice_1' in keys
        assert 'practice_2' in keys
        assert 'practice_3' in keys

    def test_referat_keys_include_service_keys(self):
        keys = get_allowed_section_keys('referat')
        assert 'toc' in keys
        assert 'literature' in keys
        assert 'appendix' in keys

    def test_course_has_more_practice_sections(self):
        keys = get_allowed_section_keys('course')
        assert 'practice_4' in keys

    def test_diploma_has_more_sections(self):
        keys = get_allowed_section_keys('diploma')
        assert 'practice_4' in keys


class TestGetAllowedChapterKeys:
    def test_chapter_keys_complete(self):
        keys = get_allowed_chapter_keys()
        expected = {'toc', 'intro', 'theory', 'practice', 'conclusion', 'literature', 'appendix'}
        assert keys == expected


class TestNormalizeSectionKey:
    def test_already_normalized_theory(self):
        result = normalize_section_key('theory_1', 'theory', 0)
        assert result == 'theory_1'

    def test_normalize_unknown_theory_key(self):
        result = normalize_section_key('concepts', 'theory', 0)
        assert result == 'theory_1'

    def test_normalize_unknown_theory_key_second_index(self):
        result = normalize_section_key('technologies', 'theory', 1)
        assert result == 'theory_2'

    def test_already_normalized_practice(self):
        result = normalize_section_key('practice_1', 'practice', 0)
        assert result == 'practice_1'

    def test_normalize_unknown_practice_key(self):
        result = normalize_section_key('analysis', 'practice', 0)
        assert result == 'practice_1'

    def test_normalize_keeps_intro(self):
        result = normalize_section_key('intro', 'intro', 0)
        assert result == 'intro'


class TestFilterOutlineSections:
    def test_valid_outline_unchanged(self):
        outline = {
            'version': 'v2',
            'title': 'Test',
            'chapters': [
                {'key': 'intro', 'title': 'Introduction', 'points': []},
                {
                    'key': 'theory',
                    'title': 'Theory',
                    'sections': [
                        {'key': 'theory_1', 'title': '1.1 First', 'points': []},
                        {'key': 'theory_2', 'title': '1.2 Second', 'points': []},
                    ]
                },
                {
                    'key': 'practice',
                    'title': 'Practice',
                    'sections': [
                        {'key': 'practice_1', 'title': '2.1 First', 'points': []},
                        {'key': 'practice_2', 'title': '2.2 Second', 'points': []},
                    ]
                },
                {'key': 'conclusion', 'title': 'Conclusion', 'points': []},
            ]
        }
        result, warnings = filter_outline_sections(outline, 'referat')
        assert len(warnings) == 0
        assert result['chapters'][1]['sections'][0]['key'] == 'theory_1'

    def test_unknown_section_key_normalized(self):
        outline = {
            'version': 'v2',
            'title': 'Test',
            'chapters': [
                {
                    'key': 'theory',
                    'title': 'Theory',
                    'sections': [
                        {'key': 'concepts', 'title': '1.1 Concepts', 'points': []},
                        {'key': 'technologies', 'title': '1.2 Technologies', 'points': []},
                    ]
                },
            ]
        }
        result, warnings = filter_outline_sections(outline, 'referat')
        assert len(warnings) == 2
        assert any('Normalized' in w for w in warnings)
        assert result['chapters'][0]['sections'][0]['key'] == 'theory_1'
        assert result['chapters'][0]['sections'][0]['_original_key'] == 'concepts'
        assert result['chapters'][0]['sections'][1]['key'] == 'theory_2'

    def test_unknown_chapter_removed(self):
        outline = {
            'version': 'v2',
            'title': 'Test',
            'chapters': [
                {'key': 'intro', 'title': 'Introduction', 'points': []},
                {'key': 'unknown_chapter', 'title': 'Unknown', 'points': []},
                {'key': 'conclusion', 'title': 'Conclusion', 'points': []},
            ]
        }
        result, warnings = filter_outline_sections(outline, 'referat')
        assert len(warnings) == 1
        assert 'Removed unknown chapter' in warnings[0]
        chapter_keys = [c['key'] for c in result['chapters']]
        assert 'unknown_chapter' not in chapter_keys

    def test_non_v2_outline_unchanged(self):
        outline = {
            'title': 'Test',
            'sections': [
                {'key': 'anything', 'title': 'Test'},
            ]
        }
        result, warnings = filter_outline_sections(outline, 'referat')
        assert result == outline
        assert len(warnings) == 0

    def test_excess_practice_sections_beyond_allowed(self):
        outline = {
            'version': 'v2',
            'title': 'Test',
            'chapters': [
                {
                    'key': 'practice',
                    'title': 'Practice',
                    'sections': [
                        {'key': 'practice_1', 'title': '2.1', 'points': []},
                        {'key': 'practice_2', 'title': '2.2', 'points': []},
                        {'key': 'practice_3', 'title': '2.3', 'points': []},
                        {'key': 'practice_10', 'title': '2.10', 'points': []},
                    ]
                },
            ]
        }
        result, warnings = filter_outline_sections(outline, 'referat')
        section_keys = [s['key'] for s in result['chapters'][0]['sections']]
        assert 'practice_1' in section_keys
        assert 'practice_2' in section_keys
        assert 'practice_3' in section_keys

    def test_original_data_not_mutated(self):
        outline = {
            'version': 'v2',
            'title': 'Test',
            'chapters': [
                {
                    'key': 'theory',
                    'title': 'Theory',
                    'sections': [
                        {'key': 'concepts', 'title': '1.1', 'points': []},
                    ]
                },
            ]
        }
        original_key = outline['chapters'][0]['sections'][0]['key']
        filter_outline_sections(outline, 'referat')
        assert outline['chapters'][0]['sections'][0]['key'] == original_key


class TestValidateOutlineStructure:
    def test_valid_outline_passes(self):
        outline = {
            'chapters': [
                {
                    'key': 'theory',
                    'sections': [
                        {'key': 'theory_1'},
                        {'key': 'theory_2'},
                    ]
                },
                {
                    'key': 'practice',
                    'sections': [
                        {'key': 'practice_1'},
                        {'key': 'practice_2'},
                    ]
                },
            ]
        }
        valid, errors = validate_outline_structure(outline)
        assert valid is True
        assert len(errors) == 0

    def test_missing_theory_fails(self):
        outline = {
            'chapters': [
                {
                    'key': 'practice',
                    'sections': [
                        {'key': 'practice_1'},
                        {'key': 'practice_2'},
                    ]
                },
            ]
        }
        valid, errors = validate_outline_structure(outline)
        assert valid is False
        assert any("theory" in e.lower() for e in errors)

    def test_missing_practice_fails(self):
        outline = {
            'chapters': [
                {
                    'key': 'theory',
                    'sections': [
                        {'key': 'theory_1'},
                        {'key': 'theory_2'},
                    ]
                },
            ]
        }
        valid, errors = validate_outline_structure(outline)
        assert valid is False
        assert any("practice" in e.lower() for e in errors)

    def test_too_few_theory_sections_fails(self):
        outline = {
            'chapters': [
                {
                    'key': 'theory',
                    'sections': [
                        {'key': 'theory_1'},
                    ]
                },
                {
                    'key': 'practice',
                    'sections': [
                        {'key': 'practice_1'},
                        {'key': 'practice_2'},
                    ]
                },
            ]
        }
        valid, errors = validate_outline_structure(outline)
        assert valid is False
        assert any("at least 2" in e for e in errors)

    def test_too_many_theory_sections_fails(self):
        outline = {
            'chapters': [
                {
                    'key': 'theory',
                    'sections': [
                        {'key': f'theory_{i}'} for i in range(1, 8)
                    ]
                },
                {
                    'key': 'practice',
                    'sections': [
                        {'key': 'practice_1'},
                        {'key': 'practice_2'},
                    ]
                },
            ]
        }
        valid, errors = validate_outline_structure(outline)
        assert valid is False
        assert any("at most 5" in e for e in errors)
