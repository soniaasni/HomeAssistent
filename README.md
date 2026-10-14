# HomeAssistent

## Inhalt

| Datei | Beschreibung |
|-------|--------------|
| `logic.cpp` | Positionsregelung der Azimut- und Elevationsachse (C++) |
| `changeName` | Werkzeug zum projektweiten Umbenennen (Python 3) |
| `docs/changeName.md` | wissenschaftliche Dokumentation von `changeName` |
| `tests/test_changeName.py` | Testsuite (Validierung) von `changeName` |

## `changeName` – Namen überall ersetzen

Ersetzt einen Namen rekursiv ab dem angegebenen Ordner in **Ordnernamen,
Dateinamen, Dateiinhalten und Symlink-Zielen**. Ausgenommen sind `.git` und
andere Versionsverwaltungs-, Cache- und Abhängigkeitsordner (`.hg`, `.svn`,
`__pycache__`, `.venv`, `node_modules`, …).

```bash
./changeName .                         # fragt alten und neuen Namen ab
./changeName . AlterName NeuerName -n  # Probelauf: nur anzeigen
./changeName . AlterName NeuerName     # ausführen (mit Rückfrage)
./changeName . AlterName NeuerName -y  # ausführen ohne Rückfrage
./changeName . AlterName NeuerName -e build   # zusätzlich "build" ausnehmen
```

Eigenschaften:

- zeigt vor jeder Änderung den vollständigen Plan und fragt nach,
- überschreibt nie bestehende Dateien oder Ordner (Konflikte werden gemeldet),
- verändert keine Binärdateien und schreibt Dateien atomar,
- benennt Ordner von innen nach außen um, damit alle Pfade gültig bleiben,
- der Startordner selbst wird nicht umbenannt.

Verfahren, Korrektheitsbegründung, Grenzen und Validierung:
**[docs/changeName.md](docs/changeName.md)**.

Tests ausführen:

```bash
python3 -m unittest discover -s tests -v
```
