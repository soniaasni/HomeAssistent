# CRC-16 über einen Speicherbereich (`baseAddress`, `Size`)

## Kurzantwort

`baseAddress` wird zum Zeiger, `Size` (in Bytes) halbiert zur Wortanzahl:

```c
uint16_t crc = calcCrc16Bit((uint16_t *)baseAddress, Size / 2);
```

| Eingang | Parameter von `calcCrc16Bit` | Warum |
|---|---|---|
| `baseAddress` (32 Bit) | `words = (uint16_t *)baseAddress` | Die Zahl ist die Adresse des ersten Worts. Auf einem 32-Bit-Mikrocontroller ist ein Zeiger genau 32 Bit breit, die Umwandlung verliert nichts. |
| `Size` (32 Bit, in Bytes) | `wordLength = Size / 2` | Die Funktion zählt 16-Bit-Wörter, ein Wort sind 2 Bytes. |

Die CRC-Funktion selbst bleibt unverändert. Zählt `Size` bereits 16-Bit-Wörter, entfällt das `/ 2`.
Voraussetzungen und Fallstricke stehen in Abschnitt 3.

Am PC berechnet Python denselben Wert aus einem Speicherabbild, z. B. als Sollwert für die Firmware:

```
python crc16.py firmware.bin 0x08004000 0x1000 --file-start 0x08000000
```

| Datei | Inhalt |
|---|---|
| `crc16.py` | Python-Port von `calcCrc16Bit`, Berechnung über einen Bereich, Kommandozeile |
| `test_crc16.py` | Validierung (Abschnitt 6), nur Standardbibliothek |
| `README.md` | diese Dokumentation |

## 1 Fragestellung und Annahmen

Gegeben ist die Funktion `calcCrc16Bit(uint16_t *words, int wordLength)`. Sie berechnet eine
16-Bit-Prüfsumme über `wordLength` aufeinanderfolgende 16-Bit-Wörter ab dem Zeiger `words`.
Außerdem liegen zwei 32-Bit-Größen vor, `baseAddress` und `Size`. Gesucht ist die Prüfsumme über
den Speicherbereich `[baseAddress, baseAddress + Size)`.

| Nr. | Annahme |
|---|---|
| A1 | `baseAddress` ist die Byte-Adresse des ersten Bytes im 32-Bit-Adressraum des Zielsystems. |
| A2 | `Size` ist die Länge des Bereichs in Bytes (übliche Konvention, vgl. `sizeof` und Linker-Skripte). |
| A3 | `baseAddress` und `Size` sind gerade: Der Bereich besteht aus ganzen, 2-Byte-ausgerichteten Wörtern. |
| A4 | Das Zielsystem ist ein 32-Bit-Mikrocontroller, der den Bereich direkt lesen kann (Flash, RAM). |

Ist statt des Speicherinhalts die Prüfsumme über die beiden Werte selbst gemeint, gilt Abschnitt 8.

## 2 Das Prüfverfahren

### 2.1 Parameter

`calcCrc16Bit` berechnet bitweise eine zyklische Redundanzprüfung (CRC) [1]. Ihre Parameter,
angegeben im Rocksoft-Modell [2]:

| Parameter | Wert | im C-Code |
|---|---|---|
| Breite | 16 Bit | `uint16_t` |
| Generatorpolynom | 0x1021, d. h. G(x) = x¹⁶ + x¹² + x⁵ + 1 | `4129` |
| Startwert | 0xFFFF | `65535` |
| Bitreihenfolge | höchstwertiges Bit zuerst (nicht gespiegelt) | `& 32768` |
| Abschluss-XOR | 0x0000 (keines) | – |
| Prüfwert für ASCII `123456789` | 0x29B1 | – |

Das ist CRC-16/CCITT-FALSE. Der Katalog parametrisierter CRC-Verfahren [3] führt sie als
CRC-16/IBM-3740 mit den Aliassen CRC-16/CCITT-FALSE und CRC-16/AUTOSAR. Das Polynom ist das
CCITT-Polynom aus ITU-T V.41 [5].

### 2.2 Mathematische Beschreibung

Eine Bitfolge m₍ₙ₋₁₎ … m₁ m₀, von der m₍ₙ₋₁₎ zuerst verarbeitet wird, entspricht dem Polynom
M(x) = Σ mᵢ·xⁱ mit Koeffizienten aus GF(2); Addition und Subtraktion sind dort XOR [1].
Das 16-Bit-Register entspricht einem Polynom R(x) vom Grad < 16.

Ein Durchlauf der inneren Schleife verarbeitet ein Datenbit m:

```
R(x) ← ( x·R(x) + m·x¹⁶ ) mod G(x)
```

Das Schieben um eine Stelle ist die Multiplikation mit x. Die Bedingung
`(CurrentWord & 32768) ^ (Syndrome & 32768)` ist der Koeffizient von x¹⁶ nach dem Schieben
(Bit 15 des Registers XOR Datenbit). Ist er 1, wird G(x) einmal abgezogen: `^ 4129` erledigt die
unteren Terme, das x¹⁶ entfällt durch `& 65535`.

Durch Induktion über die n = 8 · Size Datenbits folgt die geschlossene Form (geprüft in V2):

```
CRC(x) = ( xⁿ·I(x) + x¹⁶·M(x) ) mod G(x)        mit I(x) ≙ Startwert 0xFFFF
```

Mit Startwert 0 wäre die CRC der gewöhnliche Divisionsrest von x¹⁶·M(x), und führende Nullbytes
blieben unsichtbar. Der Startwert 0xFFFF macht sie sichtbar.

Die Variable `Syndrome` im C-Code ist eine Kopie des Registers `CRC`, die pro Wort hin- und
zurückkopiert wird. Sie ändert das Ergebnis nicht; der Python-Port kommt mit einer Variablen aus.

## 3 Abbildung von `baseAddress` und `Size`

```c
uint16_t crc = calcCrc16Bit((uint16_t *)baseAddress, Size / 2);
```

1. **`(uint16_t *)baseAddress`**: Die Umwandlung einer Ganzzahl in einen Zeiger ist in C
   implementierungsdefiniert [6, §6.3.2.3 Abs. 5] und auf Mikrocontrollern das übliche Mittel,
   eine feste Adresse zu lesen. Ein Zeiger ist dort 32 Bit breit, es geht keine Information verloren.
2. **`Size / 2`**: Wort i liegt an Adresse baseAddress + 2·i für i = 0 … Size/2 − 1. Gelesen wird
   genau `[baseAddress, baseAddress + Size)`, kein Byte mehr oder weniger.
3. **Wertebereich**: Size/2 ≤ (2³² − 1)/2 < 2³¹. Die Wortanzahl passt immer in den
   32-Bit-`int`-Parameter.

| Fall | Folge | Abhilfe |
|---|---|---|
| `Size` ungerade | Die Ganzzahldivision verwirft das letzte Byte stillschweigend. | `Size` gerade wählen |
| `baseAddress` ungerade | Der Zeiger ist falsch ausgerichtet [6, §6.3.2.3 Abs. 5]; auf Cortex-M0/M0+ löst der Zugriff einen HardFault aus [7]. | Bereich auf 2 Byte ausrichten |
| `Size` zählt schon Wörter | Nur die erste Hälfte des Bereichs wird geprüft. | `calcCrc16Bit((uint16_t *)baseAddress, Size)` |
| Funktion steht in einer `.c`-Datei (C statt C++) | Mit `inline` allein meldet der Linker ohne Optimierung (`-O0`) *undefined reference to calcCrc16Bit* [6, §6.7.4]. | `static inline uint16_t calcCrc16Bit(...)` |
| Übersetzen auf einem 64-Bit-PC | Warnung *cast to pointer from integer of different size*; eine 32-Bit-Zahl ist dort meist keine gültige Adresse. | nur auf dem Zielsystem verwenden, sonst `(uint16_t *)(uintptr_t)baseAddress` |

## 4 Byte-Reihenfolge (Endianness)

`calcCrc16Bit` liest 16-Bit-Wörter. Wie zwei Bytes im Speicher ein Wort bilden, legt der Prozessor fest:

| Byte-Reihenfolge | Wort an Adresse a | Beispiele |
|---|---|---|
| Little-Endian | Byte[a] + 256 · Byte[a+1] | ARM Cortex-M, x86, RISC-V |
| Big-Endian | 256 · Byte[a] + Byte[a+1] | z. B. PowerPC (NXP MPC5xxx) |

Jedes Wort wird mit Bit 15 zuerst verarbeitet, also sein höherwertiges Byte vor dem
niederwertigen. Die Schrittfunktion aus 2.2 hängt nur von der Reihenfolge der Bits ab, daher gilt:

- **Big-Endian**: Die CRC ist die byteweise CRC-16/CCITT-FALSE über die Bytes in Speicherreihenfolge.
- **Little-Endian**: Die CRC ist die byteweise CRC-16/CCITT-FALSE über die paarweise vertauschten
  Bytes (b1 b0 b3 b2 …).

Folge für die Praxis: Ein Werkzeug, das die CRC byteweise über eine `.bin`-Datei rechnet
(Online-Rechner, `binascii.crc_hqx`, …), liefert auf einem Little-Endian-Zielsystem einen anderen
Wert als der Mikrocontroller. `crc16.py` liest die Wörter deshalb so wie das Zielsystem
(Parameter `byteorder`, Standard `"little"`).

Testvektoren (geprüft in V3):

| Speicherinhalt ab `baseAddress` (hex) | `Size` | CRC Little-Endian | CRC Big-Endian |
|---|---|---|---|
| (leer) | 0 | 0xFFFF | 0xFFFF |
| `00 00 00 00` | 4 | 0x84C0 | 0x84C0 |
| `31 32 33 34 35 36 37 38` (ASCII `12345678`) | 8 | 0x3D14 | 0xA12B |

## 5 Fehlererkennung und Grenzen

Ein Fehlermuster E(x), das Polynom der gekippten Bits, bleibt genau dann unerkannt, wenn G(x) es
teilt [1]. Der Startwert spielt dafür keine Rolle: Bei gleicher Länge gilt
CRC(M + E) = CRC(M) + (x¹⁶·E(x) mod G(x)), und weil G(x) den Faktor x nicht enthält, ist der zweite
Summand genau dann 0, wenn G(x) das Polynom E(x) teilt.

Das Generatorpolynom zerfällt in

```
G(x) = (x + 1) · (x¹⁵ + x¹⁴ + x¹³ + x¹² + x⁴ + x³ + x² + x + 1)
```

Der zweite Faktor ist primitiv; gleichwertig dazu ist die Ordnung von x modulo G(x) gleich
2¹⁵ − 1 = 32 767 (geprüft in V5). Daraus folgt:

| Fehlerart | erkannt | Begründung |
|---|---|---|
| ungerade Anzahl gekippter Bits (1, 3, 5, …) | immer | (x + 1) teilt G(x) und damit jedes Vielfache; jedes Vielfache hat eine gerade Anzahl Terme |
| 2 gekippte Bits im Abstand d | genau dann, wenn d kein Vielfaches von 32 767 ist | G(x) teilt xⁱ·(xᵈ + 1) ⇔ 32 767 teilt d |
| Bündelfehler bis 16 Bit Länge | immer | E(x) = xⁱ·B(x) mit B ≠ 0 und Grad B < 16 = Grad G |
| großflächige, zufällige Verfälschung | mit Wahrscheinlichkeit ≈ 1 − 2⁻¹⁶ | 2¹⁶ mögliche Prüfwerte |

Konsequenz für `Size`: Solange Daten und CRC zusammen höchstens 32 767 Bit umfassen
(`Size` ≤ 4092 Byte), wird jeder Fehler mit 1, 2 oder 3 gekippten Bits erkannt; die
Hamming-Distanz ist HD ≥ 4 [4]. Darüber sinkt sie auf HD = 2: Zwei Bitfehler im Abstand von genau
32 767 Bit bleiben unerkannt, V5 führt das an einem 4-KiB-Bereich vor. Über typische
Firmware-Bereiche (weit über 4 KiB) erkennt diese CRC-16 also alle Einzelbitfehler und alle
Bündelfehler bis 16 Bit, aber nicht mehr alle Doppelbitfehler. Wird das gefordert, hilft eine
CRC-16 je Block von höchstens 4092 Byte oder eine CRC-32; beides geht über diese einfache Lösung hinaus.

## 6 Validierung

Als unabhängige Referenz dient `binascii.crc_hqx` aus der Python-Standardbibliothek [8], eine
tabellengesteuerte C-Implementierung desselben Polynoms mit wählbarem Startwert.

| Nr. | Prüfung | Ergebnis |
|---|---|---|
| V1 | Die Referenz ist CRC-16/CCITT-FALSE: `crc_hqx(b"123456789", 0xFFFF)` ergibt den Katalog-Prüfwert 0x29B1 [3]. | bestanden |
| V2 | 500 zufällige Bereiche (0–128 Byte, fester Startwert): Big-Endian = Referenz(Bytes), Little-Endian = Referenz(paarweise vertauscht). 200 zufällige Wortfolgen = geschlossene Form aus 2.2. | bestanden |
| V3 | Testvektoren aus Abschnitt 4, Standard-Byte-Reihenfolge, Gegenprobe auf Wortebene, Wert aus Abschnitt 8 | bestanden |
| V4 | Nur der Bereich zählt; ungerade, negative oder zu große Bereiche werden abgewiesen. | bestanden |
| V5 | Aussagen aus Abschnitt 5: gerade Termanzahl, Ordnung von x = 32 767, unerkannter 2-Bit-Fehler in 4 KiB | bestanden |
| V6 | Kommandozeile mit `--file-start` und `--big-endian` | bestanden |
| V7 | Gegenprobe gegen die Original-C-Funktion (einmalig, siehe unten) | 3000 von 3000 identisch |

**V7**: Die Funktion `calcCrc16Bit` wurde unverändert aus der Vorlage übernommen und mit GCC 13.3
auf x86-64 Linux (Little-Endian) übersetzt: als C++ mit `-O0` und `-O2` sowie als C11 mit
`static inline`. Aufgerufen wurde sie exakt als `calcCrc16Bit((uint16_t *)baseAddress, Size / 2)`
mit `uint32_t baseAddress, Size`. Damit die Adresse in 32 Bit passt, lag der Speicher unterhalb
von 4 GiB (`mmap` mit `MAP_32BIT`). Für 1000 zufällige Bereiche (Abbilder mit 2–599 Byte,
zufällige gerade Startadresse und Länge) stimmen alle drei Übersetzungen mit `calc_crc16_region`
überein. Dabei zeigte sich auch der `inline`-Fallstrick aus Abschnitt 3.

**Gegenprobe auf dem Zielsystem**: Das Testmuster ist als Wörter definiert, das Ergebnis hängt also
nicht von der Byte-Reihenfolge ab. Es prüft Funktion und Aufruf gemeinsam:

```c
static const uint16_t probe[4] = { 0x3132, 0x3334, 0x3536, 0x3738 };
uint32_t baseAddress = (uint32_t)probe;
uint32_t Size        = sizeof(probe);                              // 8 Byte
uint16_t crc = calcCrc16Bit((uint16_t *)baseAddress, Size / 2);   // erwartet: 0xA12B
```

**Tests ausführen** (im Wurzelverzeichnis des Repositorys, Python ≥ 3.7, keine Abhängigkeiten):

```
python -m unittest discover -s crc -v
```

## 7 Python-Implementierung

| Funktion | Zweck |
|---|---|
| `calc_crc16_bit(words)` | 1:1-Port von `calcCrc16Bit` für eine beliebige Folge von 16-Bit-Wörtern |
| `calc_crc16_region(memory, base_address, size, byteorder="little")` | Gegenstück zu `calcCrc16Bit((uint16_t *)baseAddress, Size / 2)` |

Python kann keine Hardware-Adresse lesen. Der Speicher wird daher als Bytefolge modelliert:
`memory[i]` ist das Byte an Adresse i, typischerweise aus einem Speicherabbild (`.bin`). Beginnt
die Datei nicht bei Adresse 0, wird ihre Startadresse abgezogen:

```python
from crc16 import calc_crc16_region

with open("firmware.bin", "rb") as f:
    image = f.read()                                  # Datei beginnt bei 0x08000000
crc = calc_crc16_region(image, baseAddress - 0x08000000, Size)
```

Die Kommandozeile tut dasselbe. `--file-start` ist die Adresse des ersten Datei-Bytes,
`--big-endian` schaltet die Byte-Reihenfolge um:

```
python crc16.py firmware.bin 0x08004000 0x1000 --file-start 0x08000000
```

**Laufzeit**: Der Aufwand wächst linear mit `Size` (16 Schleifendurchläufe je Wort). Gemessen mit
Python 3.11 auf einem Intel Xeon mit 2,1 GHz: 85 ms je 64 KiB, also rund 1,4 s je MiB. Für große
Abbilder liefert `binascii.crc_hqx(swap_pairs(region), 0xFFFF)` laut V2 dasselbe Ergebnis und war
in der Messung rund 340-mal schneller (`swap_pairs` steht in `test_crc16.py`). Die bitweise Fassung
bleibt der Standard, weil sie Zeile für Zeile dem C-Code entspricht.

## 8 Alternative Lesart: Prüfsumme über die beiden Werte selbst

Soll nicht der Speicher hinter `baseAddress` geprüft werden, sondern die beiden 32-Bit-Werte selbst
(z. B. in einem Telegramm), wird jeder Wert in zwei 16-Bit-Wörter zerlegt. Hier steht das
höherwertige Wort zuerst; diese Reihenfolge muss mit der Gegenseite vereinbart sein.

```c
uint16_t w[4] = { (uint16_t)(baseAddress >> 16), (uint16_t)baseAddress,
                  (uint16_t)(Size >> 16),        (uint16_t)Size };
uint16_t crc = calcCrc16Bit(w, 4);   // baseAddress = 0x08004000, Size = 0x1000 -> 0x4687
```

```python
crc = calc_crc16_bit([baseAddress >> 16, baseAddress & 0xFFFF, Size >> 16, Size & 0xFFFF])
```

Die `(uint16_t)`-Casts sind nötig, weil C++ verengende Umwandlungen in `{ }` verbietet
(Clang bricht ab, GCC warnt). Der Wert 0x4687 stimmt in C, C++ und Python überein (V3).

## Literatur

1. W. W. Peterson, D. T. Brown: *Cyclic Codes for Error Detection.* Proceedings of the IRE 49 (1),
   1961, S. 228–235. doi:10.1109/JRPROC.1961.287814
2. R. N. Williams: *A Painless Guide to CRC Error Detection Algorithms.* Version 3, 1993.
3. G. Cook: *Catalogue of parametrised CRC algorithms*, Eintrag CRC-16/IBM-3740.
   https://reveng.sourceforge.io/crc-catalogue/
4. P. Koopman, T. Chakravarty: *Cyclic Redundancy Code (CRC) Polynomial Selection for Embedded
   Networks.* Proc. International Conference on Dependable Systems and Networks (DSN), 2004,
   S. 145–154. doi:10.1109/DSN.2004.1311885
5. ITU-T (vormals CCITT), Empfehlung V.41: *Code-independent error-control system.*
6. ISO/IEC 9899:2011 (C11): §6.3.2.3 Zeiger, §6.7.4 Funktionsspezifizierer (`inline`).
7. Arm: *ARMv6-M Architecture Reference Manual* (ARM DDI 0419), Abschnitt zur Ausrichtung.
8. Python-Dokumentation: `binascii.crc_hqx`. https://docs.python.org/3/library/binascii.html
