import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

def _load_comparison_module():
    path = ROOT / "Check Manga" / "Manga_Folder_Comparison_Duplicates.py"
    spec = importlib.util.spec_from_file_location("manga_folder_comparison_duplicates", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


comparison = _load_comparison_module()

from mangarunner.engine.queue_manager import normalize_detection_mode


def test_name_and_hash_keeps_same_chapter_and_drops_different_chapters():
    assert comparison.pair_allowed("Chapter 7", "Chapter 7.1", "name_and_hash") is True
    assert comparison.pair_allowed("Ch. 7", "7.1_extra", "name_and_hash") is True
    assert comparison.pair_allowed("Chapter 7", "Chapter 8", "name_and_hash") is False
    assert comparison.chapters_share_base("Chapter 7", "Chapter 7.1") is True
    assert comparison.chapters_share_base("Chapter 7", "Chapter 8") is False


def test_visual_and_exact_ignore_chapter_names():
    assert comparison.pair_allowed("Chapter 7", "Chapter 8", "visual_similarity") is True
    assert comparison.pair_allowed("Chapter 7", "Chapter 8", "exact_hash") is True


def test_unknown_mode_falls_back_to_name_and_hash():
    assert comparison.resolve_detection_mode("not-a-real-mode") == "name_and_hash"
    assert comparison.resolve_detection_mode(None) == "name_and_hash"
    assert comparison.resolve_detection_mode("  VISUAL_SIMILARITY ") == "visual_similarity"
    assert comparison.pair_allowed("Chapter 7", "Chapter 8", "nope") is False
    assert normalize_detection_mode("manga_folder_duplicates", "nope") == "name_and_hash"
    assert normalize_detection_mode("copy_manga_folder", "exact_hash") is None
    assert normalize_detection_mode("manga_folder_duplicates", "exact_hash") == "exact_hash"


if __name__ == "__main__":
    test_name_and_hash_keeps_same_chapter_and_drops_different_chapters()
    test_visual_and_exact_ignore_chapter_names()
    test_unknown_mode_falls_back_to_name_and_hash()
    print("ALL DETECTION MODE TESTS PASSED")
