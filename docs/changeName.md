# `changeName` – rekursive Namensersetzung in Verzeichnisbäumen

**Dokumenttyp:** Methoden- und Validierungsdokumentation
**Implementierung:** [`changeName`](../changeName) (Python 3, nur Standardbibliothek)
**Validierung:** [`tests/test_changeName.py`](../tests/test_changeName.py)
**Stand:** 2026-10-14

---

## 1 Zusammenfassung

`changeName` ersetzt eine Zeichenkette *A* („alter Name“) durch eine
Zeichenkette *N* („neuer Name“) in einem Verzeichnisbaum – in Ordnernamen,
Dateinamen, Dateiinhalten und Zielen symbolischer Links. Metadaten von
Versionsverwaltungen (z. B. `.git`), Caches und Fremdabhängigkeiten werden
ausgenommen. Das Verfahren arbeitet in getrennten Phasen: Es berechnet
zunächst *alle* Änderungen, ohne etwas zu schreiben, zeigt sie an, holt eine
Bestätigung ein und führt sie erst dann aus. Dateiinhalte werden atomar
ersetzt, bestehende Einträge werden nie überschrieben, Binärdateien werden
nie verändert. Die Korrektheit der Umbenennungsreihenfolge wird in
Abschnitt 4.4 begründet; das Verhalten ist durch 23 automatisierte Tests
validiert (Abschnitt 8).

## 2 Problemstellung und Anforderungen

Beim Umbenennen eines Projekts oder einer Komponente muss ein Name an allen
Stellen konsistent geändert werden. Manuelle Ersetzung ist fehleranfällig;
naive Werkzeugketten (z. B. `find … -exec sed -i …` plus `rename`) scheitern
typischerweise an der Reihenfolge der Ordnerumbenennungen, verändern
Binärdateien oder beschädigen das `.git`-Verzeichnis.

| Nr. | Anforderung |
|-----|-------------|
| R1  | Ersetzung in Ordnernamen, Dateinamen und Dateiinhalten („einfach überall“). |
| R2  | Rekursiv ab einem Startordner; Aufruf `./changeName .` für den aktuellen Ordner. |
| R3  | Ausnahme von Versionsverwaltungs-Ordnern und vergleichbaren Werkzeugordnern. |
| R4  | Kein Datenverlust: nie überschreiben, Binärdateien nicht beschädigen, keine halb geschriebenen Dateien. |
| R5  | Nachvollziehbarkeit: Vorschau aller Änderungen, Rückfrage, Probelauf ohne Änderungen. |
| R6  | Konsistenz: Verweise in Form symbolischer Links bleiben nach der Umbenennung gültig. |

## 3 Formale Definition

Seien *A* und *N* nichtleere Zeichenketten mit *A* ≠ *N*, die weder das
Pfadtrennzeichen `/` noch das NUL-Zeichen enthalten (beides ist in
Dateinamen unzulässig bzw. bedeutungstragend).

**Ersetzungsfunktion.** Für eine Zeichenkette *s* sei

- σ(*s*) = *s*, falls *A* nicht in *s* vorkommt,
- σ(*s*) = *u* · *N* · σ(*v*), falls *s* = *u* · *A* · *v* und *u* das
  kürzestmögliche Präfix ist (erstes Vorkommen).

σ ersetzt also alle Vorkommen von links nach rechts, nicht überlappend, in
einem einzigen Durchlauf; das Ergebnis wird nicht erneut durchsucht. Dies
entspricht exakt der Semantik von Pythons `str.replace` bzw.
`bytes.replace` [1]. Unmittelbare Eigenschaften:

1. **Terminierung:** σ terminiert immer, auch wenn *A* Teilkette von *N* ist
   (z. B. `Foo` → `FooBar`).
2. **Keine Idempotenz:** Ist *A* Teilkette von *N*, gilt σ(σ(*s*)) ≠ σ(*s*);
   ein zweiter Lauf ersetzt erneut (`FooBar` → `FooBarBar`).
3. **Keine Injektivität:** Verschiedene Namen können auf denselben Namen
   abgebildet werden (*A* = `aa`, *N* = `a`: `xaaa` ↦ `xaa` und
   `xaaaa` ↦ `xaa`). Daraus entstehen Namenskonflikte (Abschnitt 4.4).

**Anwendung auf den Baum.** Sei *r* der Startordner und
*p* = *r*/*c*₁/…/*c*ₖ der Pfad eines Eintrags mit den Komponenten *c*ᵢ.
Ziel ist der Pfad *r*/σ(*c*₁)/…/σ(*c*ₖ). Der Startordner *r* selbst wird
nicht umbenannt. Für den Inhalt *B* einer Textdatei ist das Ziel σ(*B*),
angewandt auf Bytefolgen mit *A* und *N* in UTF-8-Kodierung (Abschnitt 4.3).

## 4 Verfahren

Das Werkzeug arbeitet in sechs Phasen. Phasen 1–3 sind rein lesend; erst ab
Phase 4 wird geschrieben.

| Phase | Inhalt | Funktion im Code |
|-------|--------|------------------|
| 1 | Erfassung des Baums | `iter_entries` |
| 2 | Planung aller Änderungen | `build_plan`, `plan_content`, `map_link_target` |
| 3 | Anzeige und Bestätigung | `show_plan`, `confirm` |
| 4 | Ersetzung in Dateiinhalten | `rewrite_file` |
| 5 | Neusetzen von Symlink-Zielen | `retarget_symlink` |
| 6 | Umbenennung, tiefste Einträge zuerst | `apply_plan` |

### 4.1 Phase 1 – Erfassung des Baums

Der Baum wird mit `os.walk` [2] in Pre-Order durchlaufen. Ausgeschlossene
Namen (Abschnitt 6) werden aus der Liste der Unterordner entfernt, *bevor*
`os.walk` in sie absteigt (Pruning). Ihr Inhalt wird dadurch nie gelesen; das
ist sowohl korrekt (R3) als auch effizient, da z. B. `.git` oder
`node_modules` oft den Großteil der Dateien eines Projekts enthalten.

Symbolische Links auf Ordner werden als Eintrag erfasst, aber **nicht**
betreten (`followlinks=False`). Andernfalls könnte das Werkzeug Dateien
außerhalb des Startordners verändern oder bei zyklischen Links nicht
terminieren.

Das Skript nimmt sich selbst aus (Vergleich von Gerät und Inode), damit es
sich nicht verändert, wenn es im bearbeiteten Ordner liegt.

### 4.2 Phase 2 und 3 – Planung und Bestätigung

Für jeden erfassten Eintrag wird mit `os.lstat` (folgt keinen Links) der Typ
bestimmt:

- **Reguläre Datei:** Inhaltsprüfung nach Abschnitt 4.3.
- **Symbolischer Link:** Zielprüfung nach Abschnitt 4.5.
- **Sonstige** (FIFO, Socket, Gerätedatei): Inhalt wird nicht gelesen. Das
  Lesen eines FIFOs würde blockieren; Gerätedateien haben keinen Inhalt im
  Sinne dieser Aufgabe.

Enthält der *Name* des Eintrags *A*, wird die Umbenennung geplant
(Abschnitt 4.4). Alle Pfade im Plan beziehen sich auf den **Ausgangszustand**
des Baums. Der vollständige Plan wird angezeigt; ausgeführt wird nur nach
Bestätigung (`j`/`ja`), mit Option `-y` ohne Rückfrage, mit Option `-n` nie
(Probelauf, R5).

### 4.3 Ersetzung in Dateiinhalten

**Byte-Ebene statt Text-Ebene.** Ersetzt wird auf der Bytefolge der Datei mit
*A* und *N* in UTF-8. Gegenüber Dekodieren → Ersetzen → Kodieren hat das zwei
Vorteile: Zeilenenden (`\n`, `\r\n`), eine evtl. vorhandene Byte-Order-Mark
und alle Bytes außerhalb der Vorkommen bleiben bitgenau erhalten; und die
Datei muss nicht in einer bekannten Kodierung vorliegen. Die Korrektheit
hängt von der Kodierung ab:

*Fall 1 – A und N bestehen nur aus ASCII-Zeichen.* In jeder
ASCII-kompatiblen Kodierung, in der ein Byte < 0x80 stets genau das
entsprechende ASCII-Zeichen darstellt und nie Teil einer Mehrbytefolge ist
(UTF-8, ISO 8859-x, Windows-125x, EUC-JP/-KR), entspricht ein Byte-Vorkommen
von *A* genau einem Zeichen-Vorkommen. Die Byte-Ersetzung ist dort also
gleich der Text-Ersetzung σ.

*Fall 2 – A oder N enthält Nicht-ASCII-Zeichen.* Dann wird nur ersetzt, wenn
die Datei gültiges UTF-8 ist. Begründung: UTF-8 ist selbstsynchronisierend
[3]. Startbytes (`0xxxxxxx`, `11xxxxxx`) und Folgebytes (`10xxxxxx`) bilden
disjunkte Mengen. Die Kodierung von *A* beginnt mit einem Startbyte; ein
Vorkommen in gültigem UTF-8 beginnt deshalb an einer Zeichengrenze und
umfasst, da die Dekodierung ab einer Zeichengrenze eindeutig ist, genau die
Zeichen von *A*. Byte-Vorkommen und Zeichen-Vorkommen stimmen überein, die
Byte-Ersetzung ist gleich σ. Dateien in anderen Kodierungen (z. B.
Latin-1) würden durch Einfügen von UTF-8-Bytes eine gemischte Kodierung
erhalten; sie werden übersprungen und gemeldet.

**Binärdateien.** Eine Datei gilt als binär, wenn sie ein NUL-Byte enthält.
Dieselbe Heuristik verwendet Git zur Unterscheidung von Text- und
Binärdateien (`buffer_is_binary`, dort auf die ersten 8000 Bytes
beschränkt) [4]. Hier wird die ganze Datei geprüft, was strenger ist.
Textdateien in UTF-8 oder ASCII-kompatiblen Kodierungen enthalten praktisch
nie NUL; UTF-16/-32-Dateien enthalten bei ASCII-Text zwangsläufig NUL und
werden daher ebenfalls als binär behandelt – das ist gewollt, da eine
Ersetzung von UTF-8-Bytes in ihnen falsch wäre. Binärdateien werden **nie**
verändert (R4), Vorkommen darin aber gemeldet, damit der Anwender sie ggf.
von Hand anpassen kann (z. B. Bilder, Office-Dokumente, die ZIP-Archive sind).

### 4.4 Umbenennung: Reihenfolge und Konfliktfreiheit

**Problem.** Wird ein Ordner vor seinen Kindern umbenannt, sind die
gespeicherten Pfade der Kinder ungültig (`Foo/Foo.txt` existiert nach
`Foo` → `Bar` nicht mehr).

**Verfahren.** Die geplanten Umbenennungen werden absteigend nach Tiefe
(Anzahl der Pfadkomponenten) sortiert; jede Umbenennung ändert nur die
**letzte** Komponente (`os.rename(p, dirname(p)/σ(basename(p)))`).

**Satz.** Wird jede Umbenennung mit dem im Ausgangszustand gespeicherten
Pfad ausgeführt, so ist dieser Pfad zum Zeitpunkt der Ausführung gültig, und
nach Abschluss hat jeder umbenannte Eintrag den Pfad
*r*/σ(*c*₁)/…/σ(*c*ₖ).

*Beweis (Skizze).* Betrachte den Eintrag *e* der Tiefe *k* mit Pfad
*r*/*c*₁/…/*c*ₖ. Alle vor *e* ausgeführten Umbenennungen betreffen Einträge
der Tiefe ≥ *k*. Ein Vorfahre von *e* hat Tiefe < *k*; also wurde noch kein
Vorfahre umbenannt, und *r*/*c*₁/…/*c*ₖ₋₁ existiert unverändert. Die
Umbenennung eines Eintrags *f* ändert nur Pfade von *f* und seinen
Nachkommen. Die bereits behandelten Einträge der Tiefe ≥ *k* sind keine
Vorfahren von *e*, also ist auch *c*ₖ unverändert, und der Pfad von *e* ist
gültig. Für den Endzustand folgt per Induktion über die Tiefe von unten nach
oben, dass jede Komponente genau einmal durch σ ersetzt wurde. ∎

**Konfliktfreiheit (R4).** Eine Umbenennung wird nicht ausgeführt, wenn

1. der Zielname bereits existiert und nicht derselbe Eintrag ist, oder
2. ein anderer Eintrag im Plan bereits denselben Zielpfad hat
   (Nicht-Injektivität von σ, Abschnitt 3), oder
3. das Ergebnis `.` oder `..` wäre.

„Derselbe Eintrag“ wird über Gerät und Inode festgestellt. Das ist nötig
auf Dateisystemen ohne Unterscheidung von Groß-/Kleinschreibung (z. B.
macOS-Standard), wo `foo` → `Foo` sonst fälschlich als Konflikt gälte.
Bedingung 1 wird unmittelbar vor jeder Umbenennung erneut geprüft, da sich der
Baum seit der Planung verändert haben kann. Die Prüfung ist konservativ: Ein
Ziel, das erst durch eine andere Umbenennung frei würde, gilt als Konflikt.
Konflikte werden gemeldet und führen zu Exit-Code 1; alle übrigen Änderungen
werden durchgeführt.

### 4.5 Symbolische Links

Ein Link `start.py → Foo/main.py` wäre nach der Umbenennung von `Foo` ins
Leere gerichtet. Das Linkziel wird deshalb so angepasst, dass es denselben
Eintrag bezeichnet wie zuvor (R6). Eine einfache Textersetzung σ(Ziel) ist
dafür **nicht** korrekt: Heißt der Startordner selbst `Foo`, wird er nicht
umbenannt, und `../Foo/x` oder `/home/u/Foo/x` würden zerstört.

**Verfahren (`map_link_target`).** Das Ziel wird lexikalisch, Komponente für
Komponente, vom Ordner des Links aus durchlaufen (bei absoluten Zielen von
`/` aus). Dabei wird der aktuelle absolute Ort *d* mitgeführt (`..` →
Elternordner, Name → Unterordner). Eine Namenskomponente *c* wird genau dann
durch σ(*c*) ersetzt, wenn *d* innerhalb des Startordners, aber nicht in
einem ausgeschlossenen Bereich liegt und *c* selbst nicht ausgeschlossen ist –
also genau dann, wenn Phase 6 den Eintrag *d*/*c* umbenennt. Damit ist das
neue Ziel die Abbildung des alten Ziels unter derselben Umbenennung wie der
Baum. Relative Ziele bleiben relativ, absolute absolut; Komponenten außerhalb
des Startordners bleiben unverändert.

Linkziele werden vor den Umbenennungen (Phase 5) atomar neu gesetzt: ein
neuer Link unter temporärem Namen, dann `os.replace`. Die Inhalte der
Zieldateien werden nie über einen Link verändert; liegt das Ziel im Baum,
wird die Zieldatei ohnehin direkt bearbeitet.

### 4.6 Atomares Schreiben

Der neue Inhalt wird in eine temporäre Datei im selben Ordner geschrieben,
mit `fsync` auf den Datenträger gebracht, die Zugriffsrechte werden
übernommen (`shutil.copymode`), und schließlich ersetzt `os.replace` die
Originaldatei. Nach POSIX ist `rename` atomar: Der Name verweist zu jedem
Zeitpunkt entweder auf die alte oder auf die neue Datei [5]; Python
garantiert dies für `os.replace` auf POSIX-Systemen [1]. Ein Abbruch
(Stromausfall, `Strg+C`) hinterlässt damit nie eine halb geschriebene Datei
(R4). Derselbe Ansatz wird von GNU `sed -i` verwendet [6]. Der temporäre Name
beginnt mit `.changeName-` und wird bei Fehlern entfernt.

Die Änderungszeit wird bewusst **nicht** übernommen: Build-Systeme erkennen
geänderte Dateien an ihr.

## 5 Komplexität

Sei *n* die Anzahl der nicht ausgeschlossenen Einträge, *u* die Anzahl der
Umbenennungen und *B* die Gesamtgröße der regulären Dateien.

- **Zeit:** O(*n* + *u* log *u* + *B*). Jede Datei wird in Phase 2 einmal
  gelesen und durchsucht, Dateien mit Treffern in Phase 4 ein zweites Mal.
  Die Suche (`bytes.count`/`bytes.replace`) ist in der Praxis linear in der
  Dateigröße; CPython verwendet ab Version 3.10 für längere Suchmuster den
  Two-Way-Algorithmus, der lineare Laufzeit garantiert [7].
- **Speicher:** O(*n*) für die Erfassung plus O(größte Datei), da eine Datei
  jeweils vollständig im Speicher gehalten wird.

## 6 Ausgenommene Namen

Ausgenommen sind Einträge, deren Veränderung schädlich oder sinnlos ist. Das
Kriterium ist: Der Inhalt wird von einem Werkzeug verwaltet oder erzeugt,
nicht vom Anwender geschrieben.

| Name | Kategorie | Begründung |
|------|-----------|------------|
| `.git`, `.hg`, `.svn`, `.bzr` | Versionsverwaltung | Objektdatenbank und Index; Veränderung beschädigt das Repository. `.git` ist in Submodulen und Worktrees eine *Datei*, daher gilt die Ausnahme für Ordner und Dateien. |
| `__pycache__`, `.mypy_cache`, `.pytest_cache`, `.ruff_cache`, `.tox` | Caches | werden automatisch neu erzeugt |
| `.venv`, `venv`, `node_modules` | Fremdabhängigkeiten | fremder Code, wird aus Paketquellen neu installiert |

Bewusst **nicht** ausgenommen sind projekteigene Konfigurationsdateien und
-ordner wie `.gitignore`, `.github`, `.vscode` oder `.idea`, denn sie enthalten
den Projektnamen oft gerade dort, wo er geändert werden soll. Weitere Namen
lassen sich mit `-e NAME` (mehrfach) ausnehmen, z. B. `-e build -e dist`.

## 7 Annahmen und Grenzen

1. **Groß-/Kleinschreibung:** Die Ersetzung unterscheidet sie. Varianten
   (`foo`, `FOO`) erfordern eigene Läufe.
2. **Keine Idempotenz** bei *A* ⊂ *N* (Abschnitt 3): Das Werkzeug nur einmal
   ausführen.
3. **Startordner:** wird nicht umbenannt; danach ggf. von Hand
   (`cd .. && mv Alt Neu`).
4. **Kodierungen:** Ersetzung von ASCII-Namen ist in Kodierungen falsch, in
   denen ASCII-Bytes als Folgebytes von Mehrbytezeichen vorkommen
   (Shift_JIS, Big5, GBK). Nicht-ASCII-Namen werden nur in UTF-8-Dateien
   ersetzt.
5. **Binärdateien** (Abschnitt 4.3) und damit auch Office-Dokumente, PDFs
   und Bilder werden nicht verändert, nur gemeldet.
6. **Folgen des atomaren Schreibens:** Die Datei erhält einen neuen Inode.
   Harte Links werden dadurch getrennt; Eigentümer, ACLs und erweiterte
   Attribute werden nicht übernommen (nur die Zugriffsrechte). Für
   Projektordner eines Benutzers ist das unerheblich.
7. **Kein Rollback:** Bei Fehlern während der Ausführung bleibt ein
   Teilzustand. Empfohlen wird daher, das Werkzeug in einem sauberen
   Git-Arbeitsstand auszuführen; dann lässt sich jede Änderung mit
   `git diff` prüfen und mit `git checkout`/`git clean` zurücknehmen.
8. **Nebenläufigkeit:** Ändert ein anderer Prozess den Baum zwischen Planung
   und Ausführung, sind Wettlaufsituationen möglich. Zielkonflikte werden
   unmittelbar vor jeder Umbenennung erneut geprüft, aber nicht atomar
   (Pythons Standardbibliothek bietet kein `RENAME_NOREPLACE`).
9. **Symlinks** werden lexikalisch aufgelöst (Abschnitt 4.5). Führt ein
   Linkziel per `..` aus einem verlinkten Ordner heraus, kann die
   tatsächliche Auflösung durch das Betriebssystem abweichen. Scheitert eine
   Umbenennung wegen eines Konflikts, zeigt ein angepasster Link auf den
   neuen, nicht entstandenen Namen.
10. **Plattform:** entwickelt und getestet unter Linux; macOS (POSIX) sollte
    sich gleich verhalten. Windows ist nicht getestet.

## 8 Validierung

Die Testsuite [`tests/test_changeName.py`](../tests/test_changeName.py)
erzeugt für jeden Test einen frischen temporären Verzeichnisbaum, führt das
Werkzeug aus und vergleicht den Endzustand mit dem erwarteten. Die
Kommandozeilentests rufen das Skript wie vorgesehen als `./changeName .` in
einem eigenen Prozess auf.

| Test | prüft | Anf. |
|------|-------|------|
| `test_replaces_in_nested_dirs_files_and_contents` | Ersetzung in Ordnern, Dateien, Inhalten; Bottom-up-Reihenfolge bei `Foo/Foo/Foo.txt` (Satz in 4.4) | R1, R2 |
| `test_new_name_containing_old_name_is_replaced_once` | einmaliger Durchlauf von σ bei *A* ⊂ *N* | R1 |
| `test_replacement_is_case_sensitive` | Unterscheidung der Groß-/Kleinschreibung | R1 |
| `test_preserves_line_endings_and_file_mode` | bitgenaue Erhaltung von `\r\n`, Zugriffsrechte | R4 |
| `test_leaves_no_temporary_files` | keine Reste des atomaren Schreibens | R4 |
| `test_vcs_cache_and_dependency_dirs_are_untouched` | Ausnahmen inkl. `.git` als Datei; `.gitignore` wird bearbeitet | R3 |
| `test_additional_exclude_option` | Option `-e` | R3 |
| `test_binary_files_are_reported_but_not_modified` | NUL-Heuristik | R4 |
| `test_ascii_names_are_replaced_in_latin1_files` | Fall 1 aus 4.3 | R1, R4 |
| `test_non_ascii_names_require_utf8` | Fall 2 aus 4.3 | R4 |
| `test_non_ascii_old_name` | Umlaute in Pfaden und Inhalten | R1 |
| `test_dry_run_changes_nothing` | Probelauf verändert den Baum nicht | R5 |
| `test_existing_target_is_never_overwritten` | Konfliktbedingung 1 | R4 |
| `test_two_sources_with_same_target_are_detected` | Konfliktbedingung 2 (Nicht-Injektivität) | R4 |
| `test_invalid_names_are_rejected` | leere Namen, `/`, *A* = *N* | R4 |
| `test_starting_directory_itself_is_not_renamed` | Startordner bleibt | R2 |
| `test_relative_link_follows_renamed_entries` | Linkziel folgt der Umbenennung | R6 |
| `test_link_through_unrenamed_start_directory` | Startordner namens *A* im Linkziel bleibt erhalten | R6 |
| `test_targets_outside_the_tree_are_untouched` | Ziele außerhalb des Baums | R4 |
| `test_linked_directories_are_not_followed` | keine Änderung außerhalb des Baums | R4 |
| `test_interactive_invocation` | Aufruf `./changeName .` mit interaktiver Eingabe | R2, R5 |
| `test_declined_confirmation_changes_nothing` | Ablehnung der Rückfrage | R5 |
| `test_script_does_not_modify_itself` | Selbstausnahme | R4 |

**Ausführung:**

```bash
python3 -m unittest discover -s tests -v
```

**Ergebnis (2026-10-14):** 23 Tests, alle bestanden; Python 3.13.16,
Linux 6.18.

## 9 Bedienung

```text
./changeName VERZEICHNIS [ALT NEU] [-n] [-y] [-e NAME ...]
```

| Option | Bedeutung |
|--------|-----------|
| `VERZEICHNIS` | Startordner, `.` für den aktuellen Ordner |
| `ALT NEU` | alter und neuer Name; fehlen sie, werden sie abgefragt |
| `-n`, `--dry-run` | nur anzeigen, nichts ändern |
| `-y`, `--yes` | ohne Rückfrage ausführen |
| `-e NAME`, `--exclude NAME` | zusätzlichen Ordner-/Dateinamen ausnehmen |

| Exit-Code | Bedeutung |
|-----------|-----------|
| 0 | erfolgreich, oder keine Vorkommen gefunden |
| 1 | Konflikte, fehlgeschlagene Operationen oder Rückfrage abgelehnt |
| 2 | ungültige Eingabe (kein Ordner, leere/ungültige Namen) |
| 130 | Abbruch mit `Strg+C` |

**Empfohlener Ablauf:**

```bash
git status                                  # sauberer Arbeitsstand
./changeName . MeinProjekt NeuesProjekt -n   # Probelauf
./changeName . MeinProjekt NeuesProjekt      # ausführen (mit Rückfrage)
git add -A && git status                    # Änderungen prüfen
```

**Beispielausgabe** (interaktiv, gekürzt):

```text
$ ./changeName .
Alter Name (wird gesucht): MeinProjekt
Neuer Name (ersetzt ihn):   NeuesProjekt
Verzeichnis : /home/user/projekt
Ersetzung   : 'MeinProjekt' -> 'NeuesProjekt'
Ausgenommen : .bzr, .git, .hg, .mypy_cache, …

Dateiinhalte (2 Dateien, 2 Vorkommen):
  README.md  (1x)
  MeinProjekt/src/MeinProjekt.py  (1x)

Symlink-Ziele (1):
  start.py:  MeinProjekt/src/MeinProjekt.py  ->  NeuesProjekt/src/NeuesProjekt.py

Umbenennungen (2):
  MeinProjekt  ->  NeuesProjekt
  MeinProjekt/src/MeinProjekt.py  ->  NeuesProjekt.py

Übersprungen (1):
  logo.bin: Binärdatei, 1 Vorkommen nicht ersetzt

Änderungen durchführen? [j/N] j

Fertig: 5 Änderungen durchgeführt, 0 fehlgeschlagen.
```

Um das Werkzeug in jedem Ordner ohne `./` aufrufen zu können, kann es in ein
Verzeichnis des Suchpfads kopiert werden, z. B.
`cp changeName ~/.local/bin/`; Aufruf dann mit `changeName .`.

**Voraussetzungen:** Python 3 (getestet mit 3.13), nur Standardbibliothek;
POSIX-System für den Aufruf über die Shebang-Zeile.

## 10 Referenzen

1. Python Software Foundation: *The Python Standard Library* – `str.replace`,
   `bytes.replace`, `os.replace`. <https://docs.python.org/3/library/>
2. Python Software Foundation: `os.walk`.
   <https://docs.python.org/3/library/os.html#os.walk>
3. F. Yergeau: *UTF-8, a transformation format of ISO 10646*. RFC 3629,
   IETF, 2003. <https://www.rfc-editor.org/rfc/rfc3629>
4. Git-Projekt: `xdiff-interface.c`, Funktion `buffer_is_binary`
   (`FIRST_FEW_BYTES = 8000`). <https://github.com/git/git/blob/master/xdiff-interface.c>
5. IEEE/The Open Group: *POSIX.1-2017*, `rename()`.
   <https://pubs.opengroup.org/onlinepubs/9699919799/functions/rename.html>
6. Free Software Foundation: *GNU sed manual*, Option `-i`/`--in-place`.
   <https://www.gnu.org/software/sed/manual/sed.html>
7. M. Crochemore, D. Perrin: *Two-way string-matching*. Journal of the ACM
   38(3), 1991, S. 650–674. Umsetzung in CPython: bpo-41972 (Python 3.10).
