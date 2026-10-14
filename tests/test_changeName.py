"""Testsuite für changeName (Validierung, siehe docs/changeName.md, Abschnitt 8).

Ausführen im Projektordner:  python3 -m unittest discover -s tests -v
"""

import importlib.util
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import unittest
from contextlib import redirect_stderr, redirect_stdout
from importlib.machinery import SourceFileLoader
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "changeName"


def load_script():
    """Lädt das Skript (ohne .py-Endung) als Modul, ohne Bytecode abzulegen."""
    sys.dont_write_bytecode = True
    loader = SourceFileLoader("changeName", str(SCRIPT))
    spec = importlib.util.spec_from_loader("changeName", loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules["changeName"] = module  # von dataclasses beim Laden benötigt
    loader.exec_module(module)
    return module


cn = load_script()


class ChangeNameTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)

    def write(self, rel, data, root=None):
        path = (root or self.tmp) / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, str):
            path.write_text(data, encoding="utf-8")
        else:
            path.write_bytes(data)
        return path

    def run_tool(self, *args, root=None):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cn.main([str(root or self.tmp), *args])
        return code, out.getvalue(), err.getvalue()

    def snapshot(self):
        """Vollständiger Zustand des Baums: relativer Pfad -> Inhalt/Linkziel."""
        state = {}
        for dirpath, dirnames, filenames in os.walk(self.tmp):
            for name in dirnames + filenames:
                path = os.path.join(dirpath, name)
                rel = os.path.relpath(path, self.tmp)
                if os.path.islink(path):
                    state[rel] = ("link", os.readlink(path))
                elif os.path.isdir(path):
                    state[rel] = ("dir",)
                else:
                    state[rel] = ("file", Path(path).read_bytes())
        return state


class ReplacementTest(ChangeNameTestCase):
    def test_replaces_in_nested_dirs_files_and_contents(self):
        # Gleicher Name auf drei Ebenen prüft die Bottom-up-Reihenfolge.
        self.write("Foo/Foo/Foo.txt", "Foo und Foo\n")
        self.write("Foo/readme.md", "Projekt Foo\n")
        self.write("src/main.py", "import Foo\n")

        code, out, _ = self.run_tool("Foo", "Bar", "--yes")

        self.assertEqual(code, 0, out)
        self.assertEqual((self.tmp / "Bar/Bar/Bar.txt").read_text(), "Bar und Bar\n")
        self.assertEqual((self.tmp / "Bar/readme.md").read_text(), "Projekt Bar\n")
        self.assertEqual((self.tmp / "src/main.py").read_text(), "import Bar\n")
        self.assertFalse(any("Foo" in p for p in self.snapshot()))

    def test_new_name_containing_old_name_is_replaced_once(self):
        self.write("Foo.txt", "Foo Foo")
        self.run_tool("Foo", "FooBar", "--yes")
        self.assertEqual((self.tmp / "FooBar.txt").read_text(), "FooBar FooBar")

    def test_case_sensitive_option_replaces_only_typed_form(self):
        self.write("a.txt", "Foo foo FOO")
        self.run_tool("Foo", "Bar", "--yes", "--case-sensitive")
        self.assertEqual((self.tmp / "a.txt").read_text(), "Bar foo FOO")

    def test_preserves_line_endings_and_file_mode(self):
        path = self.write("run.sh", b"#!/bin/sh\r\necho Foo\r\n")
        path.chmod(0o750)
        self.run_tool("Foo", "Bar", "--yes")
        self.assertEqual(path.read_bytes(), b"#!/bin/sh\r\necho Bar\r\n")
        self.assertEqual(path.stat().st_mode & 0o777, 0o750)

    def test_leaves_no_temporary_files(self):
        self.write("a/Foo.txt", "Foo")
        self.run_tool("Foo", "Bar", "--yes")
        self.assertFalse([p for p in self.snapshot() if cn.TEMP_PREFIX in p])


class CaseStyleTest(ChangeNameTestCase):
    """Schreibweisen-Abbildung (Abschnitt 3.2)."""

    def test_lower_capitalized_and_upper_are_mapped_in_same_style(self):
        self.write("lstm/Lstm.py", "lstm = Lstm(LSTM)\n")
        self.write("LSTM.md", "# LSTM\n")

        code, out, _ = self.run_tool("lstm", "abcd", "--yes")

        self.assertEqual(code, 0, out)
        self.assertEqual((self.tmp / "abcd/Abcd.py").read_text(), "abcd = Abcd(ABCD)\n")
        self.assertEqual((self.tmp / "ABCD.md").read_text(), "# ABCD\n")

    def test_typed_form_has_precedence(self):
        # Neuer Name in camelCase: die eingegebene Form wird wörtlich übernommen.
        self.write("a.txt", "lstm Lstm LSTM")
        self.run_tool("lstm", "convLstm", "--yes")
        self.assertEqual((self.tmp / "a.txt").read_text(), "convLstm ConvLstm CONVLSTM")

    def test_camel_case_name_variants(self):
        self.write("a.txt", "HomeAssistent homeAssistent homeassistent HOMEASSISTENT Homeassistent")
        self.run_tool("HomeAssistent", "SmartHome", "--yes")
        self.assertEqual((self.tmp / "a.txt").read_text(),
                         "SmartHome smartHome smarthome SMARTHOME Smarthome")

    def test_unsupported_style_is_reported_not_replaced(self):
        self.write("a.txt", "lstm lStM")
        self.write("LsTm.py", "")
        code, out, _ = self.run_tool("lstm", "abcd", "--yes")
        self.assertEqual(code, 0)
        self.assertEqual((self.tmp / "a.txt").read_text(), "abcd lStM")
        self.assertTrue((self.tmp / "LsTm.py").exists())
        self.assertIn("'lStM'", out)
        self.assertIn("'LsTm'", out)

    def test_changing_only_the_case(self):
        # Identische Paare (LSTM -> LSTM) dürfen weder zählen noch Konflikte melden.
        self.write("lstm.txt", "lstm LSTM")
        self.write("LSTM.md", "x")
        code, out, _ = self.run_tool("lstm", "LSTM", "--yes")
        self.assertEqual(code, 0, out)
        self.assertEqual((self.tmp / "LSTM.txt").read_text(), "LSTM LSTM")
        self.assertIn("(1x)", out)

    def test_non_ascii_case_variants(self):
        self.write("Müller/müller.txt", "müller Müller MÜLLER")
        self.run_tool("müller", "meier", "--yes")
        self.assertEqual((self.tmp / "Meier/meier.txt").read_text(encoding="utf-8"),
                         "meier Meier MEIER")

    def test_sharp_s_uppercase_changes_length(self):
        # upper("straße") = "STRASSE": wird als eigene Form erkannt.
        self.write("a.txt", "straße Straße STRASSE")
        self.run_tool("straße", "weg", "--yes")
        self.assertEqual((self.tmp / "a.txt").read_text(encoding="utf-8"), "weg Weg WEG")

    def test_ascii_variants_in_latin1_file(self):
        path = self.write("alt.txt", "café lstm LSTM".encode("latin-1"))
        self.run_tool("lstm", "abcd", "--yes")
        self.assertEqual(path.read_bytes(), "café abcd ABCD".encode("latin-1"))

    def test_digits_and_separators_keep_their_form(self):
        self.write("lstm2_v3/a.txt", "lstm2_v3 LSTM2_V3 Lstm2_v3")
        self.run_tool("lstm2_v3", "abcd4-x5", "--yes")
        self.assertEqual((self.tmp / "abcd4-x5/a.txt").read_text(), "abcd4-x5 ABCD4-X5 Abcd4-x5")

    def test_name_starting_with_digit(self):
        self.write("a.txt", "2lstm 2LSTM")
        self.run_tool("2lstm", "3abcd", "--yes")
        self.assertEqual((self.tmp / "a.txt").read_text(), "3abcd 3ABCD")

    def test_no_case_style_changes_a_digit_or_ascii_symbol(self):
        # Annahme aus Abschnitt 3.1, geprüft für alle Unicode-Dezimalziffern (Nd).
        digits = [chr(cp) for cp in range(sys.maxunicode + 1)
                  if unicodedata.category(chr(cp)) == "Nd"]
        symbols = [chr(cp) for cp in range(128) if not chr(cp).isalpha()]
        for style in cn.CASE_STYLES:
            for c in digits + symbols:
                self.assertEqual(style(c), c, (style.__name__, hex(ord(c))))

    def test_replacer_mapping_and_precedence(self):
        r = cn.Replacer("lstm", "abcd")
        self.assertEqual(r.pairs, {"lstm": "abcd", "LSTM": "ABCD", "Lstm": "Abcd"})
        self.assertEqual(cn.Replacer("lstm", "abcd", ignore_case=False).pairs, {"lstm": "abcd"})
        # Treffer werden nicht erneut durchsucht: σ terminiert auch bei NEU ⊃ ALT.
        self.assertEqual(cn.Replacer("a", "aA").sub("a A"), "aA AA")


class ExclusionTest(ChangeNameTestCase):
    def test_vcs_cache_and_dependency_dirs_are_untouched(self):
        self.write(".git/Foo/config", "Foo")
        self.write("sub/.git", "gitdir: ../.git/modules/Foo\n")  # Submodul: .git ist Datei
        self.write("node_modules/Foo.js", "Foo")
        self.write("__pycache__/Foo.pyc", "Foo")
        self.write(".gitignore", "Foo\n")  # keine Ausnahme: gehört zum Projekt
        before = self.snapshot()

        self.run_tool("Foo", "Bar", "--yes")
        after = self.snapshot()

        for rel in (".git/Foo/config", "sub/.git", "node_modules/Foo.js", "__pycache__/Foo.pyc"):
            self.assertEqual(after[rel], before[rel], rel)
        self.assertEqual((self.tmp / ".gitignore").read_text(), "Bar\n")

    def test_additional_exclude_option(self):
        self.write("build/Foo.txt", "Foo")
        self.run_tool("Foo", "Bar", "--yes", "-e", "build")
        self.assertEqual((self.tmp / "build/Foo.txt").read_text(), "Foo")

    def test_binary_files_are_reported_but_not_modified(self):
        path = self.write("bild.png", b"\x89PNG\0Foo\0")
        code, out, _ = self.run_tool("Foo", "Bar", "--yes")
        self.assertEqual(code, 0)
        self.assertEqual(path.read_bytes(), b"\x89PNG\0Foo\0")
        self.assertIn("Binärdatei", out)


class EncodingTest(ChangeNameTestCase):
    def test_ascii_names_are_replaced_in_latin1_files(self):
        path = self.write("alt.txt", "café Foo".encode("latin-1"))
        self.run_tool("Foo", "Bar", "--yes")
        self.assertEqual(path.read_bytes(), "café Bar".encode("latin-1"))

    def test_non_ascii_names_require_utf8(self):
        latin1 = self.write("latin1.txt", "café Foo".encode("latin-1"))
        utf8 = self.write("utf8.txt", "café Foo")
        code, out, _ = self.run_tool("Foo", "Bär", "--yes")
        self.assertEqual(code, 0)
        self.assertEqual(latin1.read_bytes(), "café Foo".encode("latin-1"))
        self.assertEqual(utf8.read_text(encoding="utf-8"), "café Bär")
        self.assertIn("kein gültiges UTF-8", out)

    def test_non_ascii_old_name(self):
        self.write("Müller/Müller.txt", "Herr Müller")
        self.run_tool("Müller", "Meier", "--yes")
        self.assertEqual((self.tmp / "Meier/Meier.txt").read_text(encoding="utf-8"), "Herr Meier")


class SafetyTest(ChangeNameTestCase):
    def test_dry_run_changes_nothing(self):
        self.write("Foo/Foo.txt", "Foo")
        before = self.snapshot()
        code, out, _ = self.run_tool("Foo", "Bar", "--dry-run")
        self.assertEqual(code, 0)
        self.assertEqual(self.snapshot(), before)
        self.assertIn("Foo.txt  ->  Bar.txt", out)

    def test_existing_target_is_never_overwritten(self):
        self.write("Foo.txt", "alt")
        self.write("Bar.txt", "bestehend")
        code, out, _ = self.run_tool("Foo", "Bar", "--yes")
        self.assertEqual(code, 1)
        self.assertEqual((self.tmp / "Foo.txt").read_text(), "alt")
        self.assertEqual((self.tmp / "Bar.txt").read_text(), "bestehend")
        self.assertIn("existiert bereits", out)

    def test_two_sources_with_same_target_are_detected(self):
        # "xaaa" -> "xaa" und "xaaaa" -> "xaa": die Abbildung ist nicht injektiv.
        self.write("xaaa", "1")
        self.write("xaaaa", "2")
        code, out, _ = self.run_tool("aa", "a", "--yes")
        self.assertEqual(code, 1)
        self.assertEqual((self.tmp / "xaa").read_text(), "1")
        self.assertEqual((self.tmp / "xaaaa").read_text(), "2")
        self.assertIn("existiert bereits", out)

    def test_invalid_names_are_rejected(self):
        for args in (("", "Bar"), ("Foo", ""), ("Fo/o", "Bar"), ("Foo", "B/ar"), ("Foo", "Foo")):
            code, _, err = self.run_tool(*args, "--yes")
            self.assertEqual(code, 2, args)
            self.assertIn("changeName:", err)

    def test_starting_directory_itself_is_not_renamed(self):
        root = self.tmp / "Foo"
        self.write("Foo.txt", "Foo", root=root)
        self.run_tool("Foo", "Bar", "--yes", root=root)
        self.assertTrue((self.tmp / "Foo/Bar.txt").is_file())


@unittest.skipUnless(hasattr(os, "symlink") and os.name == "posix", "benötigt POSIX-Symlinks")
class SymlinkTest(ChangeNameTestCase):
    def test_relative_link_follows_renamed_entries(self):
        self.write("Foo/data.txt", "x")
        (self.tmp / "links").mkdir()
        os.symlink("../Foo/data.txt", self.tmp / "links/zu_Foo")

        self.run_tool("Foo", "Bar", "--yes")

        link = self.tmp / "links/zu_Bar"
        self.assertEqual(os.readlink(link), "../Bar/data.txt")
        self.assertEqual(link.read_text(), "x")

    def test_link_through_unrenamed_start_directory(self):
        # Das Startverzeichnis heißt selbst "Foo" und wird nicht umbenannt.
        root = self.tmp / "Foo"
        self.write("Foo.txt", "x", root=root)
        os.symlink("../Foo/Foo.txt", root / "l")

        self.run_tool("Foo", "Bar", "--yes", root=root)

        self.assertEqual(os.readlink(root / "l"), "../Foo/Bar.txt")
        self.assertEqual((root / "l").read_text(), "x")

    def test_targets_outside_the_tree_are_untouched(self):
        os.symlink("/nicht/vorhanden/Foo", self.tmp / "extern")
        code, out, _ = self.run_tool("Foo", "Bar", "--yes")
        self.assertEqual(code, 0)
        self.assertEqual(os.readlink(self.tmp / "extern"), "/nicht/vorhanden/Foo")
        self.assertIn("außerhalb des Baums", out)

    def test_linked_directories_are_not_followed(self):
        outside = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, outside)
        (outside / "Foo.txt").write_text("Foo")
        os.symlink(outside, self.tmp / "ext")

        self.run_tool("Foo", "Bar", "--yes")

        self.assertEqual((outside / "Foo.txt").read_text(), "Foo")


@unittest.skipUnless(os.name == "posix", "ruft ./changeName über die Shebang-Zeile auf")
class CommandLineTest(ChangeNameTestCase):
    """Aufruf genau wie vorgesehen: ./changeName . im Zielordner."""

    def setUp(self):
        super().setUp()
        shutil.copy2(SCRIPT, self.tmp / "changeName")

    def invoke(self, *args, stdin=""):
        return subprocess.run(["./changeName", ".", *args], cwd=self.tmp, input=stdin,
                              capture_output=True, text=True, timeout=60)

    def test_interactive_invocation(self):
        self.write("Foo/Foo.txt", "Foo")
        result = self.invoke(stdin="Foo\nBar\nj\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.tmp / "Bar/Bar.txt").read_text(), "Bar")

    def test_declined_confirmation_changes_nothing(self):
        self.write("Foo.txt", "Foo")
        before = self.snapshot()
        result = self.invoke(stdin="Foo\nBar\nn\n")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.snapshot(), before)

    def test_script_does_not_modify_itself(self):
        original = (self.tmp / "changeName").read_bytes()
        self.write("notiz.txt", "argparse")
        result = self.invoke("argparse", "Zzz", "--yes")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.tmp / "changeName").read_bytes(), original)
        self.assertEqual((self.tmp / "notiz.txt").read_text(), "Zzz")


if __name__ == "__main__":
    unittest.main()
